#!/usr/bin/env python3
"""Is a coin that already spiked and crashed back into the band damaged goods?

The screening tests so far took each token's **first** entry into the $100k-$400k
band, which is almost always on the way up from below. That design cannot see
the case the question is about: a coin sitting at $250k today that was at $5M
last week.

This looks at **every** moment a token is in the band, not just the first, and
splits them by what the token had already done. A point where the prior peak was
$300k is a coin that has never been anywhere; a point where the prior peak was
$5M is the wreckage of a run.

**Sampled daily rather than per trade.** A token sitting in the band for a week
produces thousands of trades and would otherwise dominate the count. One
observation per token per day, and the outcome is measured from each.

**Per-token correlation is real and is reported.** Observations from one token
are not independent — a coin that crashed and kept crashing contributes many
similar rows. The distinct-token counts are printed alongside the observation
counts so the effective sample size is visible rather than implied.

Usage:
    python scripts/spiked_and_crashed.py
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
    parser.add_argument("--out", type=Path, default=Path("data/spiked_and_crashed.json"))
    args = parser.parse_args()

    supplies = {k: v for k, v in json.loads(args.supply.read_text()).items() if v}
    con = duckdb.connect()
    rows = con.execute(
        "SELECT token, pool, quote_asset, block, quote_amount, base_amount "
        "FROM read_parquet(?) ORDER BY token, block, log_index", [args.trades],
    ).fetchall()
    depth_by_pool: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for pool, block, amount in con.execute(
        "SELECT pool, block, quote_to_move_1pct FROM read_parquet(?) ORDER BY pool, block",
        [args.depth],
    ).fetchall():
        depth_by_pool[pool].append((int(block), float(amount)))

    by_token: dict[str, list] = defaultdict(list)
    pool_of, quote_of = {}, {}
    for token, pool, quote, block, q_raw, b_raw in rows:
        by_token[token].append((int(block), int(q_raw), int(b_raw)))
        pool_of[token], quote_of[token] = pool, quote

    horizon = int(args.horizon_days * BLOCKS_PER_DAY)
    data_end = max(r[3] for r in rows)
    observations: list[dict] = []

    for token, points in by_token.items():
        supply = supplies.get(token)
        if supply is None:
            continue
        quote = quote_of[token]
        scale = 10 ** QUOTE_DECIMALS.get(quote, 18)
        usd = 1.0 if quote == USDG.lower() else args.eth_usd
        caps, blocks = [], []
        for block, q_raw, b_raw in points:
            if b_raw <= 0 or q_raw <= 0:
                continue
            caps.append(q_raw / b_raw * int(supply) / scale * usd)
            blocks.append(block)
        if not caps or max(caps) > MAX_PLAUSIBLE_CAP:
            continue

        running_peak = 0.0
        last_day = -1
        for i, (block, cap) in enumerate(zip(blocks, caps)):
            running_peak = max(running_peak, cap)
            if not (args.low <= cap <= args.high):
                continue
            day = block // BLOCKS_PER_DAY
            if day == last_day:
                continue  # one observation per token per day
            if block + horizon > data_end or i < 10:
                continue
            forward = [c for b, c in zip(blocks, caps) if block < b <= block + horizon]
            if len(forward) < 5:
                continue
            depths = [d for b, d in depth_by_pool.get(pool_of[token], []) if b <= block]
            last_day = day
            observations.append({
                "token": token, "cap": cap,
                "prior_peak": running_peak,
                "prior_peak_multiple": running_peak / cap,
                "liq_ratio": (depths[-1] / scale * usd * DEPTH_TO_RESERVE / cap)
                if depths else None,
                "survived": forward[-1] / cap >= args.survive_at,
            })

    if not observations:
        print("no observations", file=sys.stderr)
        return 1

    tokens = {o["token"] for o in observations}
    base = sum(o["survived"] for o in observations) / len(observations)
    print(f"\n  {len(observations):,} observations across {len(tokens):,} tokens "
          f"(base survival {base:.1%})\n", file=sys.stderr)

    def show(title: str, groups: list[tuple[str, list[dict]]]) -> list[dict]:
        print(f"  --- {title} ---", file=sys.stderr)
        print(f"  {'group':<28} {'obs':>6} {'tokens':>7} {'survived':>10} {'95% CI':>16}",
              file=sys.stderr)
        out = []
        for name, group in groups:
            if len(group) < 10:
                continue
            hits = sum(o["survived"] for o in group)
            lo, hi = wilson(hits, len(group))
            out.append({"group": name, "observations": len(group),
                        "tokens": len({o["token"] for o in group}),
                        "survived": hits / len(group), "ci": [lo, hi]})
            print(f"  {name:<28} {len(group):>6,} "
                  f"{len({o['token'] for o in group}):>7} {hits/len(group):>9.1%} "
                  f"{f'{lo:.1%}-{hi:.1%}':>16}", file=sys.stderr)
        print(file=sys.stderr)
        return out

    payload = {"band": [args.low, args.high], "observations": len(observations),
               "tokens": len(tokens), "base_survival": base}

    payload["prior_peak"] = show("has it already been higher?", [
        ("never above $400k", [o for o in observations if o["prior_peak"] <= 400_000]),
        ("peaked $400k-$1M", [o for o in observations
                              if 400_000 < o["prior_peak"] <= 1_000_000]),
        ("peaked $1M-$5M", [o for o in observations
                            if 1_000_000 < o["prior_peak"] <= 5_000_000]),
        ("peaked above $5M", [o for o in observations if o["prior_peak"] > 5_000_000]),
    ])

    payload["drawdown"] = show("how far below its own peak?", [
        ("at or near its high (<1.5x)", [o for o in observations
                                         if o["prior_peak_multiple"] < 1.5]),
        ("1.5x - 3x below peak", [o for o in observations
                                  if 1.5 <= o["prior_peak_multiple"] < 3]),
        ("3x - 10x below peak", [o for o in observations
                                 if 3 <= o["prior_peak_multiple"] < 10]),
        ("more than 10x below peak", [o for o in observations
                                      if o["prior_peak_multiple"] >= 10]),
    ])

    liq = [o for o in observations if o["liq_ratio"] is not None and o["liq_ratio"] >= 0.20]
    payload["with_liquidity_gate"] = show(
        "among coins already passing liquidity >= 0.20", [
            ("never above $1M", [o for o in liq if o["prior_peak"] <= 1_000_000]),
            ("has been above $1M", [o for o in liq if o["prior_peak"] > 1_000_000]),
        ])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=float) + "\n")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
