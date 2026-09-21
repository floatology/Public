#!/usr/bin/env python3
"""The market-cap question again, on a sample that contains the dead.

`scripts/marketcap_study.py` answers "what did tokens do after crossing $250k"
using pools an aggregator lists today. That sample cannot contain a token that
crossed the threshold and died, so its answer is an upper bound and its headline
rates are flattered by an unknown amount.

This asks the same question of the **extraction archives**, which sample from
the chain's own census of pool creations. Dead tokens are in it, in their true
proportion. Two further advantages fall out of that:

- **No left-censoring.** The archive starts at the pool's first trade, so every
  crossing of the threshold is observed rather than inferred. In the aggregator
  data two thirds of tokens were already above $250k on their first candle, and
  excluding those roughly doubled the median multiple.
- **Trade-level resolution** rather than daily candles, so a crossing is located
  precisely rather than to the nearest day.

Market cap uses `totalSupply()` from `scripts/fetch_supply.py`. The base token's
decimals cancel out of the arithmetic, so only the quote side's are needed:

    cap = (quote_raw / base_raw) x supply_raw / 10^quote_decimals x quote_usd

**What this still cannot do.** Supply is read once, now. A token that minted
after launch has its early cap overstated and its multiple understated. And a
pool with no trades at all never enters the archive, so tokens that died before
trading are absent here too — though those never approached $250k.

Usage:
    python scripts/marketcap_census.py --threshold 250000
"""
from __future__ import annotations

import argparse
import glob
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


def summarise(values: list[float]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    n = len(ordered)
    return {
        "n": n,
        "p10": ordered[n // 10], "p25": ordered[n // 4],
        "median": statistics.median(ordered),
        "p75": ordered[(3 * n) // 4], "p90": ordered[min(n - 1, (9 * n) // 10)],
        "max": ordered[-1],
        **{f"share_above_{t}x": sum(v >= t for v in ordered) / n
           for t in (2, 3, 5, 10, 20)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", default="data/parquet/trades*.parquet")
    parser.add_argument("--supply", type=Path, default=Path("data/token_supply.json"))
    parser.add_argument("--threshold", type=float, default=250_000)
    parser.add_argument("--runner-cap", type=float, default=2_000_000)
    parser.add_argument("--eth-usd", type=float, default=DEFAULT_ETH_USD)
    parser.add_argument("--out", type=Path, default=Path("data/marketcap_census.json"))
    args = parser.parse_args()

    if not args.supply.exists():
        print(f"{args.supply} not found; run scripts/fetch_supply.py first.",
              file=sys.stderr)
        return 1
    supplies = {k: v for k, v in json.loads(args.supply.read_text()).items() if v}
    print(f"{len(supplies):,} tokens with a known supply", file=sys.stderr)

    con = duckdb.connect()
    rows = con.execute(
        "SELECT token, quote_asset, block, quote_amount, base_amount "
        "FROM read_parquet(?) ORDER BY token, block, log_index", [args.trades],
    ).fetchall()

    series: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for token, quote, block, quote_raw, base_raw in rows:
        supply = supplies.get(token)
        if supply is None:
            continue
        quote_raw, base_raw = int(quote_raw), int(base_raw)
        if base_raw <= 0 or quote_raw <= 0:
            continue
        scale = 10 ** QUOTE_DECIMALS.get(quote, 18)
        usd = 1.0 if quote == USDG.lower() else args.eth_usd
        # Base decimals cancel; see the module docstring.
        cap = (quote_raw / base_raw) * int(supply) / scale * usd
        series[token].append((int(block), cap))

    print(f"{len(series):,} tokens with reconstructible market cap", file=sys.stderr)

    crossed: list[dict] = []
    never = 0
    implausible = 0
    for token, points in series.items():
        caps = [c for _, c in points]
        if max(caps) > MAX_PLAUSIBLE_CAP:
            implausible += 1
            continue
        index = next((i for i, c in enumerate(caps) if c >= args.threshold), None)
        if index is None:
            never += 1
            continue
        if index == 0:
            # The very first trade already above the threshold means the pool
            # opened there; there is no crossing to measure from.
            continue
        entry_cap = caps[index]
        forward = caps[index:]
        peak_cap = max(forward)
        crossed.append({
            "token": token,
            "entry_cap": entry_cap,
            "peak_cap": peak_cap,
            "final_cap": forward[-1],
            "peak_multiple": peak_cap / entry_cap,
            "final_multiple": forward[-1] / entry_cap,
            "is_runner": peak_cap >= args.runner_cap,
            "blocks_to_peak": points[index + forward.index(peak_cap)][0] - points[index][0],
            "trades_after": len(forward),
        })

    if not crossed:
        print("\nNo token in the census archive crossed the threshold. With "
              f"{len(series):,} tokens examined and {never:,} never reaching "
              f"${args.threshold:,.0f}, the census sample simply does not "
              f"contain tokens of this size.", file=sys.stderr)
        return 1

    runners = [c for c in crossed if c["is_runner"]]
    report = {
        "threshold": args.threshold, "runner_cap": args.runner_cap,
        "tokens_examined": len(series),
        "never_reached_threshold": never,
        "implausible_cap": implausible,
        "crossed": len(crossed),
        "crossing_rate": len(crossed) / len(series),
        "runners": len(runners),
        "runner_rate_given_crossed": len(runners) / len(crossed),
        "peak_multiple": summarise([c["peak_multiple"] for c in crossed]),
        "final_multiple": summarise([c["final_multiple"] for c in crossed]),
        "biggest": sorted(crossed, key=lambda c: -c["peak_multiple"])[:20],
        "caveats": [
            "supply read once at the current block and assumed constant",
            "census-sampled: contains dead tokens, unlike the aggregator study",
            "a pool that never traded never enters the archive",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=float) + "\n")

    print(f"\n  {len(series):,} tokens examined", file=sys.stderr)
    print(f"  {never:,} never reached ${args.threshold:,.0f} "
          f"({never/len(series):.1%})", file=sys.stderr)
    print(f"  {len(crossed):,} crossed it ({len(crossed)/len(series):.2%})",
          file=sys.stderr)
    print(f"  of those, {len(runners):,} reached ${args.runner_cap:,.0f}+ "
          f"({report['runner_rate_given_crossed']:.1%})", file=sys.stderr)
    for label, key in (("peak", "peak_multiple"), ("where it ended", "final_multiple")):
        s = report[key]
        print(f"\n  {label} multiple from the crossing (n={s['n']}):", file=sys.stderr)
        print(f"    p10 {s['p10']:.2f}x  p25 {s['p25']:.2f}x  "
              f"median {s['median']:.2f}x  p75 {s['p75']:.2f}x  "
              f"p90 {s['p90']:.2f}x  max {s['max']:,.0f}x", file=sys.stderr)
        print("    " + "  ".join(
            f">={t}x {s[f'share_above_{t}x']:.1%}" for t in (2, 3, 5, 10, 20)),
            file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
