#!/usr/bin/env python3
"""A small, self-contained screen for the $100k-$400k band, with its thresholds swept.

Separate from the trading work. The question here is narrow: **of the coins
sitting in this band right now, which ones are still worth half their value in a
fortnight?** Not which will run — that question was answered negatively in
`docs/18` — just which survive.

**Thresholds are swept, not chosen.** With 328 tokens it is trivial to try
several cuts and report the best one, and that number would not survive contact
with new data. Every cut is printed so the shape is visible: a criterion worth
using sits on a **plateau**, where nearby thresholds give nearby answers. A
criterion whose survival rate spikes at one cut and falls away on either side is
fitting noise, and the sweep is what tells the two apart.

**Survival, not return.** A screen that halves the failure rate is worth having
even though nothing here predicts which survivor goes up.

Usage:
    python scripts/mini_screen.py
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb

from rhc.chain import DEFAULT_ETH_USD, QUOTE_DECIMALS, USDG
from rhc.features import Trade, compute
from rhc.manipulation import detect

BLOCKS_PER_DAY = 864_000
MAX_PLAUSIBLE_CAP = 10_000_000_000
DEPTH_TO_RESERVE = 200.0


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    p = hits / total
    d = 1 + z * z / total
    c = (p + z * z / (2 * total)) / d
    s = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return (max(0.0, c - s), min(1.0, c + s))


def load(args) -> list[dict]:
    supplies = {k: v for k, v in json.loads(args.supply.read_text()).items() if v}
    con = duckdb.connect()
    rows = con.execute(
        "SELECT token, pool, quote_asset, block, log_index, wallet, is_buy, "
        "quote_amount, base_amount FROM read_parquet(?) ORDER BY token, block, log_index",
        [args.trades],
    ).fetchall()
    depth_by_pool: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for pool, block, amount in con.execute(
        "SELECT pool, block, quote_to_move_1pct FROM read_parquet(?) ORDER BY pool, block",
        [args.depth],
    ).fetchall():
        depth_by_pool[pool].append((int(block), float(amount)))

    by_token: dict[str, list] = defaultdict(list)
    pool_of, quote_of = {}, {}
    for token, pool, quote, block, log_index, wallet, is_buy, q_raw, b_raw in rows:
        by_token[token].append(
            (int(block), int(q_raw), int(b_raw), int(log_index), wallet or "", bool(is_buy)))
        pool_of[token], quote_of[token] = pool, quote

    horizon = int(args.horizon_days * BLOCKS_PER_DAY)
    data_end = max(r[3] for r in rows)
    out: list[dict] = []

    for token, points in by_token.items():
        supply = supplies.get(token)
        if supply is None:
            continue
        quote = quote_of[token]
        scale = 10 ** QUOTE_DECIMALS.get(quote, 18)
        usd = 1.0 if quote == USDG.lower() else args.eth_usd
        caps, blocks = [], []
        for block, q_raw, b_raw, *_ in points:
            if b_raw <= 0 or q_raw <= 0:
                continue
            caps.append(q_raw / b_raw * int(supply) / scale * usd)
            blocks.append(block)
        if not caps or max(caps) > MAX_PLAUSIBLE_CAP:
            continue
        index = next((i for i, c in enumerate(caps) if args.low <= c <= args.high), None)
        if index is None or index < 10:
            continue
        entry = blocks[index]
        if entry + horizon > data_end:
            continue
        forward = [c for b, c in zip(blocks, caps) if entry < b <= entry + horizon]
        if len(forward) < 5:
            continue
        depths = [d for b, d in depth_by_pool.get(pool_of[token], []) if b <= entry]
        if not depths:
            continue
        trades = [
            Trade(block=b, wallet=w, is_buy=buy, quote_amount=q, base_amount=ba, log_index=li)
            for b, q, ba, li, w, buy in points if b <= entry
        ]
        if len(trades) < 10:
            continue
        feats = compute(pool=pool_of[token], quote_asset=quote,
                        created_block=min(t.block for t in trades),
                        trades=trades, syncs=[], head_block=entry)
        signatures = detect(trades)
        cap = caps[index]
        depth_usd = depths[-1] / scale * usd * DEPTH_TO_RESERVE
        out.append({
            "token": token, "cap": cap, "depth_usd": depth_usd,
            "liq_ratio": depth_usd / cap,
            "round_trip_share": feats.round_trip_share,
            "trade_count": feats.trade_count,
            "wash_suspect_score": feats.wash_suspect_score,
            "modal_amount_count": signatures.modal_amount_count,
            "median_trade_usd": feats.trade_size_median / scale * usd
            if feats.trade_size_median else None,
            "survived": forward[-1] / cap >= args.survive_at,
            "peak_multiple": max(forward) / cap,
        })
    return out


def sweep(records, metric, cuts, above=True, label=""):
    print(f"\n  --- {label} ---", file=sys.stderr)
    print(f"  {'cut':>8} {'kept':>6} {'of':>5} {'survived':>10} {'95% CI':>16}",
          file=sys.stderr)
    rows = []
    for cut in cuts:
        group = [r for r in records if r[metric] is not None
                 and (r[metric] >= cut if above else r[metric] <= cut)]
        if len(group) < 10:
            continue
        hits = sum(r["survived"] for r in group)
        lo, hi = wilson(hits, len(group))
        rows.append({"cut": cut, "n": len(group), "survived": hits / len(group),
                     "ci": [lo, hi]})
        print(f"  {cut:>8.2f} {len(group):>6} {len(records):>5} "
              f"{hits/len(group):>9.1%} {f'{lo:.1%}-{hi:.1%}':>16}", file=sys.stderr)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", default="data/parquet/trades_v3.parquet")
    parser.add_argument("--depth", default="data/parquet/depth_v3.parquet")
    parser.add_argument("--supply", type=Path, default=Path("data/token_supply.json"))
    parser.add_argument("--low", type=float, default=100_000)
    parser.add_argument("--high", type=float, default=400_000)
    parser.add_argument("--horizon-days", type=float, default=14.0)
    parser.add_argument("--survive-at", type=float, default=0.5)
    parser.add_argument("--eth-usd", type=float, default=DEFAULT_ETH_USD)
    parser.add_argument("--out", type=Path, default=Path("data/mini_screen.json"))
    args = parser.parse_args()

    records = load(args)
    base = sum(r["survived"] for r in records) / len(records)
    print(f"\n  {len(records)} tokens in ${args.low:,.0f}-${args.high:,.0f}; "
          f"base survival {base:.1%}", file=sys.stderr)

    payload = {"band": [args.low, args.high], "n": len(records),
               "base_survival": base, "horizon_days": args.horizon_days}
    payload["liq_ratio"] = sweep(
        records, "liq_ratio", [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60],
        True, "liquidity / market cap  (keep at or above)")
    payload["round_trip"] = sweep(
        records, "round_trip_share", [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50],
        False, "round-trip share  (keep at or below)")

    # The combination, at a few plausible pairs rather than a full grid: a grid
    # over 328 tokens finds a winning cell by construction.
    print(f"\n  --- combined ---", file=sys.stderr)
    print(f"  {'liq>=':>7} {'rt<=':>6} {'kept':>6} {'survived':>10} {'95% CI':>16} "
          f"{'med peak':>9}", file=sys.stderr)
    combos = []
    for liq in (0.20, 0.25, 0.30):
        for rt in (0.15, 0.25, 1.01):
            group = [r for r in records if r["liq_ratio"] >= liq
                     and (r["round_trip_share"] is None or r["round_trip_share"] <= rt)]
            if len(group) < 10:
                continue
            hits = sum(r["survived"] for r in group)
            lo, hi = wilson(hits, len(group))
            peaks = sorted(r["peak_multiple"] for r in group)
            combos.append({"liq": liq, "round_trip": rt, "n": len(group),
                           "survived": hits / len(group), "ci": [lo, hi],
                           "median_peak": peaks[len(peaks) // 2]})
            label_rt = "any" if rt > 1 else f"{rt:.2f}"
            print(f"  {liq:>7.2f} {label_rt:>6} {len(group):>6} {hits/len(group):>9.1%} "
                  f"{f'{lo:.1%}-{hi:.1%}':>16} {peaks[len(peaks)//2]:>8.2f}x",
                  file=sys.stderr)
    payload["combined"] = combos

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=float) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
