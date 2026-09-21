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
    python scripts/model_features.py --label peak_over_launch --threshold 10
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
}
IDENTIFIERS = {"pool", "token", "quote_asset"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("data/parquet/features.parquet"))
    parser.add_argument("--label", default="peak_over_launch")
    parser.add_argument("--threshold", type=float, default=10.0)
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
    rows = con.execute(
        f'SELECT {quoted}, "{args.label}" FROM read_parquet(?) WHERE "{args.label}" IS NOT NULL',
        [str(args.features)],
    ).fetchall()

    if len(rows) < 60:
        print(f"only {len(rows)} labelled rows; refusing to model. A split of this "
              f"would put ~{len(rows)//2} in each half, where any AUC is noise.",
              file=sys.stderr)
        return 1

    data = np.array([[np.nan if v is None else float(v) for v in r[:-1]] for r in rows])
    labels = np.array([1 if float(r[-1]) >= args.threshold else 0 for r in rows])

    positives = int(labels.sum())
    print(f"{len(rows)} rows, {len(feature_cols)} features, "
          f"{positives} positives ({positives/len(rows):.1%})", file=sys.stderr)
    if positives < 10 or positives == len(rows):
        print(f"only {positives} positives; refusing to model.", file=sys.stderr)
        return 1

    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(rows))
    cut = int(len(rows) * args.discovery_frac)
    discovery, confirmation = order[:cut], order[cut:]

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
        return results

    real = fit_and_score(discovery, confirmation, labels[discovery], labels[confirmation])
    if real is None:
        print("a split half contains only one class; cannot score.", file=sys.stderr)
        return 1

    # Negative control: identical pipeline, labels shuffled. This is the floor.
    control_aucs = []
    for trial in range(5):
        shuffled = labels.copy()
        np.random.default_rng(args.seed + trial).shuffle(shuffled)
        out = fit_and_score(discovery, confirmation, shuffled[discovery], shuffled[confirmation])
        if out:
            control_aucs.append(max(out["lasso_auc"], out["gbm_auc"]))
    control = float(np.mean(control_aucs)) if control_aucs else None

    result = {
        "rows": len(rows), "features": len(feature_cols), "positives": positives,
        "label": args.label, "threshold": args.threshold, "seed": args.seed,
        "discovery_n": len(discovery), "confirmation_n": len(confirmation),
        "lasso_auc": real["lasso_auc"], "gbm_auc": real["gbm_auc"],
        "shuffled_label_auc": control,
        "beats_control": (
            control is not None and max(real["lasso_auc"], real["gbm_auc"]) > control + 0.05
        ),
        "lasso_selected": real["lasso_selected"],
        "gbm_top": real["gbm_top"],
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
