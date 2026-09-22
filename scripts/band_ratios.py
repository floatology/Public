#!/usr/bin/env python3
"""Healthy and unhealthy ratios for tokens inside a market-cap band.

The question: for a coin between $100k and $400k, what should the relationships
between market cap, volume and liquidity look like, and what is a red flag?

Answered by measurement rather than convention. For every census token, the
moment its market cap first enters the band is located, the ratios are computed
from the trades up to that moment only, and the outcome is measured forward from
it. Bins are then compared.

**Three ratios, and they answer different questions.**

- **Turnover — 24h volume ÷ market cap.** How much of the token changes hands
  relative to what it is worth. Needs no liquidity figure, so it is measurable
  for every token here.
- **Depth ÷ market cap.** How much real money backs the valuation. A $300k
  token sitting on $3k of tradeable depth is a number, not a market.
- **Volume ÷ depth.** The wash tell. A pool cannot honestly trade many multiples
  of its own depth in a day without the price going somewhere.

**The depth figure is V3's active liquidity, not a pool reserve.** V3 emits no
`Sync`, so what is archived is the quote needed to move the price 1%, measured
at each swap. Multiplying by 200 gives a rough constant-product-equivalent
reserve, which is the right order of magnitude and not a precise TVL. Ratios
built on it are comparable to each other and only loosely comparable to the
"liquidity" an aggregator displays.

**Why entry into the band and not the whole life.** A ratio measured over a
token's entire history is contaminated by whatever happened afterwards. Taken at
the moment of entry it is a screening number: exactly what a person looking at a
$100k–$400k coin today can see.

Usage:
    python scripts/band_ratios.py --low 100000 --high 400000
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb

from rhc.chain import DEFAULT_ETH_USD, QUOTE_DECIMALS, USDG

BLOCKS_PER_DAY = 864_000
MAX_PLAUSIBLE_CAP = 10_000_000_000
# A 1% move costs roughly reserve/200 in a constant-product pool, so this
# inverts that to put V3's active liquidity on a reserve-like scale.
DEPTH_TO_RESERVE = 200.0


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", default="data/parquet/trades_v3.parquet")
    parser.add_argument("--depth", default="data/parquet/depth_v3.parquet")
    parser.add_argument("--supply", type=Path, default=Path("data/token_supply.json"))
    parser.add_argument("--low", type=float, default=100_000)
    parser.add_argument("--high", type=float, default=400_000)
    parser.add_argument("--window-days", type=float, default=1.0,
                        help="lookback for the volume figure")
    parser.add_argument("--horizon-days", type=float, default=14.0)
    parser.add_argument("--eth-usd", type=float, default=DEFAULT_ETH_USD)
    parser.add_argument("--out", type=Path, default=Path("data/band_ratios.json"))
    args = parser.parse_args()

    supplies = {k: v for k, v in json.loads(args.supply.read_text()).items() if v}
    con = duckdb.connect()
    rows = con.execute(
        "SELECT token, pool, quote_asset, block, quote_amount, base_amount "
        "FROM read_parquet(?) ORDER BY token, block, log_index", [args.trades],
    ).fetchall()
    depth_rows = con.execute(
        "SELECT pool, block, quote_to_move_1pct FROM read_parquet(?) ORDER BY pool, block",
        [args.depth],
    ).fetchall()
    depth_by_pool: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for pool, block, amount in depth_rows:
        depth_by_pool[pool].append((int(block), float(amount)))

    by_token: dict[str, list] = defaultdict(list)
    pool_of: dict[str, str] = {}
    quote_of: dict[str, str] = {}
    for token, pool, quote, block, q_raw, b_raw in rows:
        by_token[token].append((int(block), int(q_raw), int(b_raw)))
        pool_of[token] = pool
        quote_of[token] = quote

    window = int(args.window_days * BLOCKS_PER_DAY)
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
        caps, prices, blocks, volumes = [], [], [], []
        for block, q_raw, b_raw in points:
            if b_raw <= 0 or q_raw <= 0:
                continue
            price = q_raw / b_raw
            caps.append(price * int(supply) / scale * usd)
            prices.append(price)
            blocks.append(block)
            volumes.append(q_raw / scale * usd)
        if not caps or max(caps) > MAX_PLAUSIBLE_CAP:
            continue

        index = next((i for i, c in enumerate(caps)
                      if args.low <= c <= args.high), None)
        if index is None or index == 0:
            continue
        entry_block = blocks[index]
        # Right-censoring: a token entering the band within one horizon of the
        # end of data cannot be scored, and keeping it would bias toward tokens
        # that moved early.
        if entry_block + horizon > data_end:
            continue

        recent = [v for b, v in zip(blocks[:index + 1], volumes[:index + 1])
                  if b >= entry_block - window]
        volume_24h = sum(recent)
        cap = caps[index]
        depths = [d for b, d in depth_by_pool.get(pool_of[token], []) if b <= entry_block]
        depth_usd = (depths[-1] / scale * usd * DEPTH_TO_RESERVE) if depths else None

        forward = [c for b, c in zip(blocks, caps) if entry_block < b <= entry_block + horizon]
        if len(forward) < 5:
            continue
        peak_multiple = max(forward) / cap
        end_multiple = forward[-1] / cap

        records.append({
            "token": token, "entry_cap": cap,
            "volume_24h": volume_24h,
            "turnover": volume_24h / cap if cap > 0 else None,
            "depth_usd": depth_usd,
            "depth_over_cap": (depth_usd / cap) if depth_usd and cap > 0 else None,
            "volume_over_depth": (volume_24h / depth_usd) if depth_usd else None,
            "trades_in_window": len(recent),
            "peak_multiple": peak_multiple,
            "end_multiple": end_multiple,
            "ran_2x": peak_multiple >= 2.0,
            "ran_5x": peak_multiple >= 5.0,
            "survived": end_multiple >= 0.5,
        })

    if len(records) < 30:
        print(f"only {len(records)} tokens entered ${args.low:,.0f}-${args.high:,.0f} "
              f"with a scoreable forward window", file=sys.stderr)
        if not records:
            return 1

    print(f"\n  {len(records):,} tokens entered ${args.low:,.0f}-${args.high:,.0f}\n",
          file=sys.stderr)

    def report(metric: str, label: str, edges: list[float]) -> dict:
        usable = [r for r in records if r.get(metric) is not None]
        if len(usable) < 20:
            print(f"  {label}: only {len(usable)} tokens carry it; skipping",
                  file=sys.stderr)
            return {}
        print(f"  --- {label} (n={len(usable)}) ---", file=sys.stderr)
        values = [r[metric] for r in usable]
        print(f"      distribution: p10 {quantile(values,0.1):.2f}  "
              f"p25 {quantile(values,0.25):.2f}  median {statistics.median(values):.2f}  "
              f"p75 {quantile(values,0.75):.2f}  p90 {quantile(values,0.9):.2f}",
              file=sys.stderr)
        out = {}
        print(f"      {'bin':>16} {'n':>5} {'ran 2x':>8} {'ran 5x':>8} "
              f"{'survived':>9} {'med end':>8}", file=sys.stderr)
        for low, high in zip([0.0] + edges, edges + [float("inf")]):
            group = [r for r in usable if low <= r[metric] < high]
            if len(group) < 5:
                continue
            name = f"{low:g}-{high:g}" if high != float("inf") else f">{low:g}"
            stats = {
                "n": len(group),
                "ran_2x": sum(r["ran_2x"] for r in group) / len(group),
                "ran_5x": sum(r["ran_5x"] for r in group) / len(group),
                "survived": sum(r["survived"] for r in group) / len(group),
                "median_end": statistics.median([r["end_multiple"] for r in group]),
            }
            out[name] = stats
            print(f"      {name:>16} {stats['n']:>5} {stats['ran_2x']:>7.1%} "
                  f"{stats['ran_5x']:>7.1%} {stats['survived']:>8.1%} "
                  f"{stats['median_end']:>7.2f}x", file=sys.stderr)
        print(file=sys.stderr)
        return out

    payload = {
        "band": [args.low, args.high], "tokens": len(records),
        "window_days": args.window_days, "horizon_days": args.horizon_days,
        "turnover": report("turnover", "turnover  =  24h volume / market cap",
                           [0.1, 0.3, 1.0, 3.0, 10.0]),
        "depth_over_cap": report("depth_over_cap", "depth / market cap",
                                 [0.02, 0.05, 0.10, 0.25, 0.50]),
        "volume_over_depth": report("volume_over_depth", "24h volume / depth",
                                    [0.5, 1.0, 3.0, 10.0, 30.0]),
        "caveats": [
            "depth is V3 active liquidity x200, a reserve-equivalent not a TVL",
            "ratios measured at band entry, from trades up to that moment only",
            "right-censored entries excluded",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=float) + "\n")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
