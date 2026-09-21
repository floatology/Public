#!/usr/bin/env python3
"""Fit the feature set against the outcome, with the pre-registered discipline.

This is where breadth stops being free. Computing 49 features costs nothing
statistically; *selecting among them* is where false positives are manufactured,
and this project has already produced a result that was significant, replicated,
and still meant nothing.

Three safeguards, all from `PREREGISTRATION.md`:

**Discovery / confirmation split.** The model sees only the discovery half. The
confirmation half is scored exactly once, at the end. A number that survives it
is real; a number that only appears in discovery is a hypothesis.

**Regularisation over testing.** L1-penalised logistic regression shrinks useless
coefficients to zero rather than testing each feature and keeping the winners,
which is the approach the published wallet paper used over a comparable feature
space. Gradient boosting runs alongside because trees find interactions without
enumerating them — 49 features imply 1,176 pairwise interactions, far too many
to test explicitly at this sample size, but a tree splits on B within a branch
already split on A and discovers the useful ones directly.

**A negative control that must be beaten.** Labels are shuffled and the identical
pipeline refit. Whatever AUC that produces is what this procedure yields from
noise alone. A real model has to beat it, and reporting a model's AUC without
that floor is how an overfit gets mistaken for a finding.

Outcome and features are separated strictly: anything describing what happened
*after* entry — peak price, drawdown, final reserves — is excluded, or the model
predicts the outcome from the outcome.

Usage:
    python scripts/model_features.py --label realisable_peak_over_launch --threshold 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np

# Features that encode the outcome. Including any of these produces a perfect
# model that knows nothing.
LEAKY = {
    "peak_over_launch", "final_over_launch", "peak_price", "peak_block",
    "drawdown_from_peak", "peak_quote_reserve", "final_quote_reserve",
    "launch_vwap", "created_block",
    # The realisable-outcome block. Every one of these describes where the
    # price went, so any of them as an input predicts the outcome from the
    # outcome and returns an AUC near 1.0 that means nothing.
    "realisable_peak_over_launch", "peak_trade_volume_share",
    "volume_above_2x_share", "volume_above_10x_share",
}
IDENTIFIERS = {"pool", "token", "quote_asset", "protocol"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("data/parquet/features.parquet"))
    # The default label is the volume-backed one. See PREREGISTRATION.md
    # amendment 3: a peak reached on a dust trade is not an outcome anyone
    # could have taken.
    parser.add_argument("--label", default="realisable_peak_over_launch")
    parser.add_argument("--threshold", type=float, default=10.0)
    parser.add_argument(
        "--stratum", choices=("v2", "v3", "pooled"), default=None,
        help="which protocol population to fit. PREREGISTRATION standing "
             "rule: V2 and V3 are different populations (z=3.28, p<0.01) "
             "and are never pooled without an explicit test that pooling "
             "is valid. A mixed table therefore requires this flag; "
             "'pooled' is that explicit choice and is recorded in the "
             "output.",
    )
    parser.add_argument(
        "--min-positive-tokens", type=int, default=15,
        help="panel input only: distinct tokens that must carry a positive "
             "before a fit is attempted. Positive ROWS are not independent "
             "observations when a token's label is constant across its "
             "decision points.",
    )
    parser.add_argument("--discovery-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--out", type=Path, default=Path("data/model_result.json"))
    args = parser.parse_args()

    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    con = duckdb.connect()
    described = con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{args.features}')"
    ).fetchall()

    # V2 and V3 are different populations by measurement (z=3.28, p<0.01) and
    # by construction: V3 has no reserves, so half the liquidity columns are
    # null for it and a pooled fit would learn to split on the nulls. Pooling
    # is allowed but has to be chosen, not defaulted into.
    stratum_filter = ""
    if any(name == "protocol" for name, *_ in described):
        strata = [
            row[0] for row in con.execute(
                f"SELECT DISTINCT protocol FROM read_parquet('{args.features}') "
                f"WHERE protocol IS NOT NULL"
            ).fetchall()
        ]
        if len(strata) > 1 and args.stratum is None:
            print(f"this table mixes {sorted(strata)}. The pre-registration "
                  f"forbids pooling them without an explicit decision: pass "
                  f"--stratum v2, --stratum v3, or --stratum pooled.",
                  file=sys.stderr)
            return 1
        if args.stratum in ("v2", "v3"):
            stratum_filter = f" AND protocol = '{args.stratum}'"
    elif args.stratum in ("v2", "v3"):
        print(f"--stratum {args.stratum} was given but the table has no "
              f"protocol column; refusing to guess which population this is.",
              file=sys.stderr)
        return 1
    feature_cols = [
        name for name, dtype, *_ in described
        # BOOLEAN is included deliberately. `is_bundled` and `has_bump_bot`
        # are flags, and the published model gives bump-bot presence the
        # highest importance of any feature -- dropping booleans would
        # silently exclude the strongest candidate in the catalogue.
        if any(t in dtype.upper() for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "BOOL"))
        and name not in LEAKY and name not in IDENTIFIERS
    ]
    quoted = ", ".join(f'"{c}"' for c in feature_cols)
    has_token = any(name == "token" for name, *_ in described)
    token_select = '"token", ' if has_token else "'' AS token, "
    rows = con.execute(
        f'SELECT {token_select}{quoted}, "{args.label}" FROM read_parquet(?) '
        f'WHERE "{args.label}" IS NOT NULL{stratum_filter}',
        [str(args.features)],
    ).fetchall()

    if len(rows) < 60:
        print(f"only {len(rows)} labelled rows; refusing to model. A split of this "
              f"would put ~{len(rows)//2} in each half, where any AUC is noise.",
              file=sys.stderr)
        return 1

    tokens = np.array([r[0] for r in rows])
    data = np.array([[np.nan if v is None else float(v) for v in r[1:-1]] for r in rows])
    labels = np.array([1 if float(r[-1]) >= args.threshold else 0 for r in rows])

    positives = int(labels.sum())
    print(f"{len(rows)} rows, {len(feature_cols)} features, "
          f"{positives} positives ({positives/len(rows):.1%})", file=sys.stderr)
    if positives < 10 or positives == len(rows):
        print(f"only {positives} positives; refusing to model.", file=sys.stderr)
        return 1

    rng = np.random.default_rng(args.seed)
    distinct_tokens = sorted(set(tokens.tolist()))
    is_panel = has_token and len(distinct_tokens) < len(rows)

    if is_panel:
        # A panel carries many decision points per token, and rows from one
        # token are heavily correlated -- overlapping windows on one
        # trajectory. Splitting by row puts the same token on both sides, and
        # the held-out score stops meaning anything. The split is therefore by
        # TOKEN, so no token appears in both halves.
        print(f"panel input: {len(rows):,} rows over {len(distinct_tokens):,} "
              f"tokens ({len(rows)/len(distinct_tokens):.1f} each). Splitting by "
              f"token, not by row.", file=sys.stderr)
        if len(distinct_tokens) < 20:
            print(f"only {len(distinct_tokens)} tokens. A token-level split of "
                  f"this puts ~{len(distinct_tokens)//2} on each side, where any "
                  f"score is noise. Refusing.", file=sys.stderr)
            return 1
        # The row count is an illusion if the label barely varies within a
        # token. When a token's decision points are all positive or all
        # negative, "predict the label" collapses into "identify the token",
        # and a tree with enough features does that perfectly -- 464 rows over
        # 29 tokens produced GBM AUC 0.995 with every positive coming from
        # four tokens. The effective sample size is the number of tokens
        # carrying positives, not the number of positive rows.
        positive_tokens = sorted({
            tok for tok, flag in zip(tokens.tolist(), labels.tolist()) if flag
        })
        constant = sum(
            1 for tok in distinct_tokens
            if len(set(labels[tokens == tok].tolist())) == 1
        )
        print(f"  {len(positive_tokens)} of {len(distinct_tokens)} tokens carry "
              f"any positive; {constant} tokens have a constant label "
              f"({constant / len(distinct_tokens):.0%})", file=sys.stderr)
        if len(positive_tokens) < args.min_positive_tokens:
            print(f"\nonly {len(positive_tokens)} tokens carry a positive. The "
                  f"{int(labels.sum())} positive rows are {len(positive_tokens)} "
                  f"trajectories seen repeatedly, so the effective sample size is "
                  f"{len(positive_tokens)}, not {int(labels.sum())}. Any model "
                  f"fitted here learns to recognise those tokens. Refusing; raise "
                  f"--min-positive-tokens only if you know why.", file=sys.stderr)
            return 1

        shuffled_tokens = list(distinct_tokens)
        rng.shuffle(shuffled_tokens)
        cut_tokens = set(shuffled_tokens[:int(len(shuffled_tokens) * args.discovery_frac)])
        mask = np.array([tok in cut_tokens for tok in tokens])
        discovery = np.flatnonzero(mask)
        confirmation = np.flatnonzero(~mask)
    else:
        order = rng.permutation(len(rows))
        cut = int(len(rows) * args.discovery_frac)
        discovery, confirmation = order[:cut], order[cut:]

    if len(discovery) == 0 or len(confirmation) == 0:
        print("a split half is empty; cannot score.", file=sys.stderr)
        return 1

    def lift_at(scores, truth, fraction: float) -> dict[str, float | int] | None:
        """Precision in the top `fraction` of predictions, against the base rate.

        AUC answers "does the model rank winners above losers", which is not the
        question anyone acts on. The question anyone acts on is "if I buy the
        top decile, what share of them win, and is that better than buying at
        random". A model can have a respectable AUC and a lift of 1.0, and it
        would be worth nothing.
        """
        count = max(1, int(len(scores) * fraction))
        if count >= len(scores):
            return None
        order = np.argsort(scores)[::-1][:count]
        hits = int(truth[order].sum())
        base = float(truth.mean())
        if base <= 0:
            return None
        precision = hits / count
        return {
            "k": count, "hits": hits, "precision": precision,
            "base_rate": base, "lift": precision / base,
        }

    def fit_and_score(train_idx, test_idx, y_train, y_test):
        results = {}
        if len(set(y_train)) < 2 or len(set(y_test)) < 2:
            return None
        lasso = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(penalty="l1", solver="liblinear", C=0.1, max_iter=2000),
        )
        lasso.fit(data[train_idx], y_train)
        results["lasso_auc"] = roc_auc_score(y_test, lasso.predict_proba(data[test_idx])[:, 1])
        coefs = lasso[-1].coef_[0]
        results["lasso_selected"] = sorted(
            ((feature_cols[i], float(c)) for i, c in enumerate(coefs) if abs(c) > 1e-8),
            key=lambda p: -abs(p[1]),
        )

        trees = make_pipeline(
            SimpleImputer(strategy="median"),
            GradientBoostingClassifier(random_state=args.seed, n_estimators=150, max_depth=3),
        )
        trees.fit(data[train_idx], y_train)
        results["gbm_auc"] = roc_auc_score(y_test, trees.predict_proba(data[test_idx])[:, 1])
        importances = trees[-1].feature_importances_
        results["gbm_top"] = sorted(
            ((feature_cols[i], float(v)) for i, v in enumerate(importances) if v > 0),
            key=lambda p: -p[1],
        )[:15]

        # Lift on whichever model ranked better, since the decision would use
        # that one. Reported at the top decile and the top quintile.
        best = trees if results["gbm_auc"] >= results["lasso_auc"] else lasso
        scores = best.predict_proba(data[test_idx])[:, 1]
        for fraction, name in ((0.1, "lift_top_decile"), (0.2, "lift_top_quintile")):
            results[name] = lift_at(scores, np.asarray(y_test), fraction)
        return results

    real = fit_and_score(discovery, confirmation, labels[discovery], labels[confirmation])
    if real is None:
        print("a split half contains only one class; cannot score.", file=sys.stderr)
        return 1

    # Negative control: identical pipeline, labels shuffled. This is the floor.
    control_aucs = []
    control_lifts: list[float | None] = []
    for trial in range(5):
        trial_rng = np.random.default_rng(args.seed + trial)
        if is_panel:
            # Shuffle labels BETWEEN tokens, keeping each token's own sequence
            # intact. A row-wise shuffle destroys the within-token correlation
            # that makes a panel hard, so the control would be easier to beat
            # than the real task and the floor would be set too low.
            by_token: dict[str, np.ndarray] = {}
            for tok in distinct_tokens:
                by_token[tok] = labels[tokens == tok]
            donors = list(distinct_tokens)
            trial_rng.shuffle(donors)
            swap = dict(zip(distinct_tokens, donors))
            shuffled = labels.copy()
            for tok in distinct_tokens:
                target = np.flatnonzero(tokens == tok)
                donor = by_token[swap[tok]]
                # Donor sequences differ in length; tile or truncate to fit.
                take = np.resize(donor, len(target)) if len(donor) else labels[target]
                shuffled[target] = take
        else:
            shuffled = labels.copy()
            trial_rng.shuffle(shuffled)
        out = fit_and_score(discovery, confirmation, shuffled[discovery], shuffled[confirmation])
        if out:
            control_aucs.append(max(out["lasso_auc"], out["gbm_auc"]))
            decile = out.get("lift_top_decile")
            control_lifts.append(decile["lift"] if decile else None)
    control = float(np.mean(control_aucs)) if control_aucs else None

    result = {
        "rows": len(rows), "features": len(feature_cols), "positives": positives,
        "label": args.label, "threshold": args.threshold, "seed": args.seed,
        "stratum": args.stratum or "unstratified",
        "discovery_n": len(discovery), "confirmation_n": len(confirmation),
        "split": "by_token" if is_panel else "by_row",
        "positive_tokens": (
            len({tok for tok, flag in zip(tokens.tolist(), labels.tolist()) if flag})
            if has_token else None
        ),
        "distinct_tokens": len(distinct_tokens),
        "lasso_auc": real["lasso_auc"], "gbm_auc": real["gbm_auc"],
        "shuffled_label_auc": control,
        "beats_control": (
            control is not None and max(real["lasso_auc"], real["gbm_auc"]) > control + 0.05
        ),
        "lasso_selected": real["lasso_selected"],
        "gbm_top": real["gbm_top"],
        "lift_top_decile": real.get("lift_top_decile"),
        "lift_top_quintile": real.get("lift_top_quintile"),
        "shuffled_lift_top_decile": (
            float(np.mean([c for c in control_lifts if c is not None]))
            if any(c is not None for c in control_lifts) else None
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")

    print(f"\n--- confirmation-half performance ---", file=sys.stderr)
    print(f"  L1 logistic AUC : {real['lasso_auc']:.3f}", file=sys.stderr)
    print(f"  gradient boost  : {real['gbm_auc']:.3f}", file=sys.stderr)
    if control is not None:
        print(f"  shuffled labels : {control:.3f}   <-- the floor to beat",
              file=sys.stderr)
        verdict = "BEATS control" if result["beats_control"] else "does NOT beat control"
        print(f"  verdict         : {verdict}", file=sys.stderr)
    decile = real.get("lift_top_decile")
    if decile:
        print(f"\n  buying the top {decile['k']} of {len(confirmation)} predictions:",
              file=sys.stderr)
        print(f"    {decile['hits']}/{decile['k']} win = {decile['precision']:.1%} "
              f"against a {decile['base_rate']:.1%} base rate "
              f"({decile['lift']:.2f}x lift)", file=sys.stderr)
        if result["shuffled_lift_top_decile"] is not None:
            print(f"    shuffled labels reach {result['shuffled_lift_top_decile']:.2f}x, "
                  f"which is the floor", file=sys.stderr)

    print(f"\n  L1 kept {len(real['lasso_selected'])} of {len(feature_cols)} features",
          file=sys.stderr)
    for name, coef in real["lasso_selected"][:10]:
        print(f"    {coef:+.4f}  {name}", file=sys.stderr)
    print(f"\n  tree importance top 10:", file=sys.stderr)
    for name, value in real["gbm_top"][:10]:
        print(f"    {value:.4f}  {name}", file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
