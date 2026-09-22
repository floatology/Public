#!/usr/bin/env python3
"""Does the model's ranking rescue the threshold?

The threshold alone loses money: buying every $250k crossing and applying the
best of fifteen exit rules compounds at 0.80x. Separately, a model over the
feature set ranks at AUC ~0.75 under the strictest split available. This asks
whether the second fixes the first.

The design keeps them honest about each other:

**The model never sees a crossing token during training.** It is fitted on panel
decision points drawn from tokens that produce no crossing at all, then used to
score the crossings. So every score is genuinely out-of-token, and the usual
failure — a model recognising a trajectory it was trained on — cannot occur.

**Features are computed at the crossing block**, from trades at or before it,
with nothing from after. That is the moment a decision would be made.

**The comparison is selected against unselected, not selected against nothing.**
A top quartile that compounds at 0.9x has not rescued anything if the bottom
three quartiles compound at 0.9x too. What matters is the gap.

**And a shuffled control runs alongside.** With 167 crossings, a top quartile is
about forty positions, and forty positions drawn from a fat-tailed distribution
produce a wide range of geometric means by luck alone. The control says how wide.

Usage:
    python scripts/selected_entries.py --threshold 250000
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb
import numpy as np

from rhc.chain import DEFAULT_ETH_USD, QUOTE_DECIMALS, USDG
from rhc.features import Trade, compute, window
from rhc.manipulation import detect

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exit_rules import simulate

MAX_PLAUSIBLE_CAP = 10_000_000_000
LEAKY_PREFIXES = ("forward_", "realisable_", "peak_", "final_", "volume_above_")
IDENTIFIERS = {"pool", "token", "quote_asset", "protocol", "decision_block",
               "reference_price", "created_block", "launch_vwap", "drawdown_from_peak"}


def geometric(values: list[float]) -> float:
    return math.exp(statistics.fmean([math.log(max(v, 1e-6)) for v in values]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", default="data/parquet/trades_v3.parquet")
    parser.add_argument("--panel", type=Path, default=Path("data/parquet/panel_v3.parquet"))
    parser.add_argument("--supply", type=Path, default=Path("data/token_supply.json"))
    parser.add_argument("--threshold", type=float, default=250_000)
    parser.add_argument("--quantile", type=float, default=0.25,
                        help="top fraction of ranked crossings to 'buy'")
    parser.add_argument("--eth-usd", type=float, default=DEFAULT_ETH_USD)
    parser.add_argument("--seed", type=int, default=20260922)
    parser.add_argument("--out", type=Path, default=Path("data/selected_entries.json"))
    args = parser.parse_args()

    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline

    supplies = {k: v for k, v in json.loads(args.supply.read_text()).items() if v}
    con = duckdb.connect()
    rows = con.execute(
        "SELECT token, pool, quote_asset, block, log_index, wallet, is_buy, "
        "quote_amount, base_amount FROM read_parquet(?) ORDER BY token, block, log_index",
        [args.trades],
    ).fetchall()

    by_token: dict[str, list] = defaultdict(list)
    meta: dict[str, tuple[str, str]] = {}
    for token, pool, quote, block, log_index, wallet, is_buy, q_raw, b_raw in rows:
        by_token[token].append((int(block), int(q_raw), int(b_raw), int(log_index),
                                wallet or "", bool(is_buy)))
        meta[token] = (pool, quote)

    # --- locate each crossing and build the price path from it ---
    crossings: dict[str, dict] = {}
    for token, points in by_token.items():
        supply = supplies.get(token)
        if supply is None:
            continue
        pool, quote = meta[token]
        scale = 10 ** QUOTE_DECIMALS.get(quote, 18)
        usd = 1.0 if quote == USDG.lower() else args.eth_usd
        caps, prices, blocks = [], [], []
        for block, q_raw, b_raw, *_ in points:
            if b_raw <= 0 or q_raw <= 0:
                continue
            price = q_raw / b_raw
            caps.append(price * int(supply) / scale * usd)
            prices.append(price)
            blocks.append(block)
        if not caps or max(caps) > MAX_PLAUSIBLE_CAP:
            continue
        index = next((i for i, c in enumerate(caps) if c >= args.threshold), None)
        if index is None or index == 0 or prices[index] <= 0:
            continue
        crossings[token] = {
            "block": blocks[index],
            "path": [p / prices[index] for p in prices[index:]],
            "blocks": blocks[index:],
        }
    print(f"{len(crossings):,} crossings at ${args.threshold:,.0f}", file=sys.stderr)
    if len(crossings) < 40:
        print("too few crossings to split meaningfully", file=sys.stderr)
        return 1

    # --- features at the crossing block, from trades at or before it ---
    described = con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{args.panel}')").fetchall()
    feature_cols = [
        name for name, dtype, *_ in described
        if any(t in dtype.upper() for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "BOOL"))
        and name not in IDENTIFIERS and not name.startswith(LEAKY_PREFIXES)
    ]
    print(f"{len(feature_cols)} features", file=sys.stderr)

    entry_features: dict[str, dict] = {}
    for token, crossing in crossings.items():
        pool, quote = meta[token]
        trades = [
            Trade(block=b, wallet=w, is_buy=buy, quote_amount=q, base_amount=ba,
                  log_index=li)
            for b, q, ba, li, w, buy in by_token[token] if b <= crossing["block"]
        ]
        if len(trades) < 10:
            continue
        first = min(t.block for t in trades)
        feats = compute(pool=pool, quote_asset=quote, created_block=first,
                        trades=trades, syncs=[], head_block=crossing["block"])
        record = feats.to_dict()
        record.update(detect(trades).to_dict())
        entry_features[token] = record
    print(f"{len(entry_features):,} crossings with computable entry features",
          file=sys.stderr)

    # --- train on tokens that never crossed ---
    panel = con.execute(
        f"SELECT * FROM read_parquet('{args.panel}') "
        f"WHERE realisable_forward_multiple IS NOT NULL").fetchall()
    panel_cols = [d[0] for d in con.description]
    crossing_tokens = set(entry_features)
    train_rows = [
        dict(zip(panel_cols, r)) for r in panel
        if dict(zip(panel_cols, r))["token"] not in crossing_tokens
    ]
    if len(train_rows) < 200:
        print(f"only {len(train_rows)} training rows from non-crossing tokens",
              file=sys.stderr)
        return 1
    print(f"training on {len(train_rows):,} rows from "
          f"{len({r['token'] for r in train_rows}):,} tokens that never crossed",
          file=sys.stderr)

    X_train = np.array([[np.nan if r.get(c) is None else float(r[c])
                         for c in feature_cols] for r in train_rows])
    y_train = np.array([
        1 if float(r["realisable_forward_multiple"]) >= 3.0 else 0 for r in train_rows
    ])
    if y_train.sum() < 20:
        print(f"only {int(y_train.sum())} positives in training", file=sys.stderr)
        return 1

    model = make_pipeline(
        SimpleImputer(strategy="median"),
        GradientBoostingClassifier(random_state=args.seed, n_estimators=150, max_depth=3),
    )
    model.fit(X_train, y_train)

    tokens = sorted(entry_features)
    X_score = np.array([[np.nan if entry_features[t].get(c) is None
                         else float(entry_features[t][c]) for c in feature_cols]
                        for t in tokens])
    scores = model.predict_proba(X_score)[:, 1]

    rules = {
        "2x target, stop at 0.5x": {"target": 2.0, "stop": 0.5},
        "3x target, trailing 30%": {"target": 3.0, "trailing": 0.30},
        "trailing 30%": {"trailing": 0.30},
        "sell at 2x": {"target": 2.0},
        "hold to the end": {},
    }
    returns = {
        name: {t: simulate(crossings[t]["path"], blocks=crossings[t]["blocks"], **kwargs)
               for t in tokens}
        for name, kwargs in rules.items()
    }

    order = np.argsort(scores)[::-1]
    cut = max(5, int(len(tokens) * args.quantile))
    selected = [tokens[i] for i in order[:cut]]
    rejected = [tokens[i] for i in order[cut:]]

    rng = np.random.default_rng(args.seed)
    report = {}
    print(f"\n  {len(tokens)} crossings scored; buying the top {cut}\n", file=sys.stderr)
    print(f"  {'rule':<26} {'selected':>9} {'rejected':>9} {'all':>8} "
          f"{'random top-q':>13}", file=sys.stderr)
    for name in rules:
        values = returns[name]
        sel = geometric([values[t] for t in selected])
        rej = geometric([values[t] for t in rejected])
        everything = geometric([values[t] for t in tokens])
        # What a random quartile of the same size returns, as a floor.
        controls = []
        pool_values = [values[t] for t in tokens]
        for _ in range(400):
            controls.append(geometric(list(rng.choice(pool_values, size=cut, replace=False))))
        control_mean = float(np.mean(controls))
        control_p95 = float(np.quantile(controls, 0.95))
        report[name] = {
            "selected": sel, "rejected": rej, "all": everything,
            "random_quartile_mean": control_mean,
            "random_quartile_p95": control_p95,
            "beats_random_p95": sel > control_p95,
        }
        print(f"  {name:<26} {sel:>8.3f}x {rej:>8.3f}x {everything:>7.3f}x "
              f"{control_mean:>8.3f}x (p95 {control_p95:.2f}x)", file=sys.stderr)

    payload = {
        "threshold": args.threshold, "crossings": len(tokens),
        "selected_n": cut, "quantile": args.quantile,
        "training_rows": len(train_rows),
        "rules": report,
        "verdict_note": "a rule is only rescued if selected > 1.0x AND above the "
                        "random-quartile p95",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=float) + "\n")

    rescued = [n for n, r in report.items()
               if r["selected"] > 1.0 and r["beats_random_p95"]]
    print(f"\n  rules rescued (above 1.0x AND above the random p95): "
          f"{rescued or 'NONE'}", file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
