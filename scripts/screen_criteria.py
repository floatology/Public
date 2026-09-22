#!/usr/bin/env python3
"""Which measurable properties separate coins that survive from coins that die?

A screener needs criteria that have been tested, not criteria that sound
sensible. This takes every feature computable at the moment a token's market cap
enters a band, and asks a single question of each: **does it separate the coins
that still hold half their value a fortnight later from the ones that do not?**

**Survival rather than return, deliberately.** Everything measured in `docs/18`
says picking winners mechanically does not work on this chain. Avoiding the 96%
that collapse is a different and much easier question, and it is the one a
screener is actually for.

**Features come from trades up to band entry and nothing after.** That is what a
person looking at a coin today can see.

Each candidate is reported as the survival rate in its top and bottom third,
with Wilson intervals, so a criterion with a big gap and overlapping intervals
is visibly distinguishable from one with a big gap and separated intervals.
Many features will look promising on 300 tokens; the intervals are what stop
that becoming a screener full of noise.

Usage:
    python scripts/screen_criteria.py --low 100000 --high 400000
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
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
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - spread), min(1.0, centre + spread))


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
    parser.add_argument("--out", type=Path, default=Path("data/screen_criteria.json"))
    args = parser.parse_args()

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
    pool_of: dict[str, str] = {}
    quote_of: dict[str, str] = {}
    for token, pool, quote, block, log_index, wallet, is_buy, q_raw, b_raw in rows:
        by_token[token].append(
            (int(block), int(q_raw), int(b_raw), int(log_index), wallet or "", bool(is_buy))
        )
        pool_of[token], quote_of[token] = pool, quote

    horizon = int(args.horizon_days * BLOCKS_PER_DAY)
    data_end = max(r[3] for r in rows)
    records: list[dict] = []

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
        entry_block = blocks[index]
        if entry_block + horizon > data_end:
            continue
        forward = [c for b, c in zip(blocks, caps) if entry_block < b <= entry_block + horizon]
        if len(forward) < 5:
            continue

        trades = [
            Trade(block=b, wallet=w, is_buy=buy, quote_amount=q, base_amount=ba,
                  log_index=li)
            for b, q, ba, li, w, buy in points if b <= entry_block
        ]
        if len(trades) < 10:
            continue
        first = min(t.block for t in trades)
        feats = compute(pool=pool_of[token], quote_asset=quote, created_block=first,
                        trades=trades, syncs=[], head_block=entry_block)
        record = {k: v for k, v in feats.to_dict().items()
                  if isinstance(v, (int, float, bool)) and not isinstance(v, bool) or isinstance(v, bool)}
        record.update({k: v for k, v in detect(trades).to_dict().items()
                       if isinstance(v, (int, float, bool))})

        depths = [d for b, d in depth_by_pool.get(pool_of[token], []) if b <= entry_block]
        cap = caps[index]
        if depths:
            depth_usd = depths[-1] / scale * usd * DEPTH_TO_RESERVE
            record["depth_usd"] = depth_usd
            record["supply_in_pool"] = depth_usd / cap if cap > 0 else None
        record["entry_cap"] = cap
        record["age_days"] = (entry_block - first) / BLOCKS_PER_DAY
        record["buyers_per_trade"] = (
            feats.unique_buyers / feats.buy_count if feats.buy_count else None
        )
        record["survived"] = forward[-1] / cap >= args.survive_at
        records.append(record)

    if len(records) < 60:
        print(f"only {len(records)} tokens; too few to screen on", file=sys.stderr)
        return 1
    base_rate = sum(r["survived"] for r in records) / len(records)
    print(f"\n  {len(records)} tokens entered ${args.low:,.0f}-${args.high:,.0f}; "
          f"{base_rate:.1%} survived\n", file=sys.stderr)

    skip = {"survived", "entry_cap"}
    candidates = sorted({
        k for r in records for k, v in r.items()
        if k not in skip and isinstance(v, (int, float)) and v is not None
    })

    results = []
    for name in candidates:
        usable = [r for r in records if isinstance(r.get(name), (int, float))]
        if len(usable) < 60:
            continue
        values = sorted(r[name] for r in usable)
        low_cut = values[len(values) // 3]
        high_cut = values[2 * len(values) // 3]
        if low_cut == high_cut:
            continue  # too degenerate to split
        bottom = [r for r in usable if r[name] <= low_cut]
        top = [r for r in usable if r[name] >= high_cut]
        if len(bottom) < 25 or len(top) < 25:
            continue
        b_rate = sum(r["survived"] for r in bottom) / len(bottom)
        t_rate = sum(r["survived"] for r in top) / len(top)
        b_lo, b_hi = wilson(sum(r["survived"] for r in bottom), len(bottom))
        t_lo, t_hi = wilson(sum(r["survived"] for r in top), len(top))
        results.append({
            "feature": name, "bottom_third": b_rate, "top_third": t_rate,
            "gap": t_rate - b_rate, "n_bottom": len(bottom), "n_top": len(top),
            "separated": bool(b_hi < t_lo or t_hi < b_lo),
            "bottom_ci": [b_lo, b_hi], "top_ci": [t_lo, t_hi],
        })

    results.sort(key=lambda r: -abs(r["gap"]))
    separated = [r for r in results if r["separated"]]

    print(f"  {len(separated)} of {len(results)} candidates have non-overlapping "
          f"intervals\n", file=sys.stderr)
    print(f"  {'feature':<34} {'bottom 3rd':>11} {'top 3rd':>9} {'gap':>7} {'sep':>5}",
          file=sys.stderr)
    for r in results[:22]:
        print(f"  {r['feature']:<34} {r['bottom_third']:>10.1%} {r['top_third']:>8.1%} "
              f"{r['gap']:>+6.1%} {'yes' if r['separated'] else '':>5}", file=sys.stderr)

    payload = {"band": [args.low, args.high], "tokens": len(records),
               "base_survival": base_rate, "horizon_days": args.horizon_days,
               "criteria": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=float) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
