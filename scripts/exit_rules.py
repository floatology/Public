#!/usr/bin/env python3
"""If you bought every crossing, what would each exit rule have returned?

Every result so far says the same thing from a different angle: the median token
crossing $250k **peaks at 2.24x and ends at 0.13x**. The upside is real and the
round trip is ruinous, so the entry threshold is at most half the problem and
the smaller half. This simulates the other half.

**Each rule is walked forward along the actual trade sequence.** No rule may see
a price before it happens: a target sells the first time the path touches it, a
trailing stop sells the first time the path falls the stated distance from the
running peak, a time stop sells at the first trade past its deadline. "Sell at
the peak" is not among them, because nobody can do it.

**Three things this does not model, all of which make the numbers optimistic.**

- **Execution cost.** Measured across four orders of magnitude on this chain:
  a $500 trade through a $20k pool cost 96%. Returns here are gross of that, and
  the pools where the biggest multiples appear are the thin ones.
- **Your own impact.** A fill at the observed price assumes your order did not
  move it, which is false in precisely the pools that look best.
- **Slippage on the exit.** A trailing stop fires when the price is already
  falling, and the print you get is worse than the one that triggered it.

So read the ordering between rules, not the absolute returns. The ordering is
what survives those omissions; the level does not.

Usage:
    python scripts/exit_rules.py --threshold 250000
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


def simulate(path: list[float], *, target: float | None = None,
             trailing: float | None = None, stop: float | None = None,
             horizon: int | None = None, blocks: list[int] | None = None) -> float:
    """Return multiple achieved, walking the path forward one trade at a time.

    `path` is the price sequence from entry onward, normalised so path[0] = 1.0.
    Whichever condition fires first wins; if none does, the position is closed
    at the last observed price.
    """
    peak = path[0]
    start_block = blocks[0] if blocks else 0
    for index, price in enumerate(path):
        peak = max(peak, price)
        if stop is not None and price <= stop:
            return price
        if target is not None and price >= target:
            return target  # filled at the target, not above it
        if trailing is not None and peak > path[0] and price <= peak * (1 - trailing):
            return price
        if horizon is not None and blocks and blocks[index] - start_block >= horizon:
            return price
    return path[-1]


def describe(values: list[float]) -> dict:
    ordered = sorted(values)
    n = len(ordered)
    return {
        "n": n,
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p25": ordered[n // 4], "p75": ordered[(3 * n) // 4],
        "p90": ordered[min(n - 1, (9 * n) // 10)],
        "share_profitable": sum(v > 1.0 for v in ordered) / n,
        "share_total_loss": sum(v < 0.1 for v in ordered) / n,
        # The geometric mean is what compounding actually delivers. An
        # arithmetic mean of multiples flatters any strategy with a fat tail
        # and one total loss in it.
        "geometric_mean": (
            statistics.fmean([__import__("math").log(max(v, 1e-6)) for v in ordered])
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", default="data/parquet/trades*.parquet")
    parser.add_argument("--supply", type=Path, default=Path("data/token_supply.json"))
    parser.add_argument("--threshold", type=float, default=250_000)
    parser.add_argument("--eth-usd", type=float, default=DEFAULT_ETH_USD)
    parser.add_argument("--out", type=Path, default=Path("data/exit_rules.json"))
    args = parser.parse_args()

    supplies = {k: v for k, v in json.loads(args.supply.read_text()).items() if v}
    con = duckdb.connect()
    rows = con.execute(
        "SELECT token, quote_asset, block, quote_amount, base_amount "
        "FROM read_parquet(?) ORDER BY token, block, log_index", [args.trades],
    ).fetchall()

    series: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for token, quote, block, quote_raw, base_raw in rows:
        supply = supplies.get(token)
        if supply is None:
            continue
        quote_raw, base_raw = int(quote_raw), int(base_raw)
        if base_raw <= 0 or quote_raw <= 0:
            continue
        scale = 10 ** QUOTE_DECIMALS.get(quote, 18)
        usd = 1.0 if quote == USDG.lower() else args.eth_usd
        price = quote_raw / base_raw
        series[token].append((int(block), price, price * int(supply) / scale * usd))

    entries: list[tuple[list[int], list[float]]] = []
    for points in series.values():
        caps = [c for _, _, c in points]
        if max(caps) > MAX_PLAUSIBLE_CAP:
            continue
        index = next((i for i, c in enumerate(caps) if c >= args.threshold), None)
        if index is None or index == 0:
            continue
        entry_price = points[index][1]
        if entry_price <= 0:
            continue
        entries.append((
            [b for b, _, _ in points[index:]],
            [p / entry_price for _, p, _ in points[index:]],
        ))

    if not entries:
        print("no crossings to simulate", file=sys.stderr)
        return 1
    print(f"{len(entries):,} entries at ${args.threshold:,.0f}\n", file=sys.stderr)

    rules: dict[str, dict] = {
        "hold to the end": {},
        "sell at 1.5x": {"target": 1.5},
        "sell at 2x": {"target": 2.0},
        "sell at 3x": {"target": 3.0},
        "sell at 5x": {"target": 5.0},
        "sell at 10x": {"target": 10.0},
        "trailing 30%": {"trailing": 0.30},
        "trailing 50%": {"trailing": 0.50},
        "trailing 30% + stop at 0.5x": {"trailing": 0.30, "stop": 0.5},
        "2x target, stop at 0.5x": {"target": 2.0, "stop": 0.5},
        "3x target, stop at 0.5x": {"target": 3.0, "stop": 0.5},
        "3x target, trailing 30%": {"target": 3.0, "trailing": 0.30},
        "hold 3 days": {"horizon": 3 * BLOCKS_PER_DAY},
        "hold 7 days": {"horizon": 7 * BLOCKS_PER_DAY},
        "hold 14 days": {"horizon": 14 * BLOCKS_PER_DAY},
    }

    report = {}
    for name, kwargs in rules.items():
        results = [simulate(path, blocks=blocks, **kwargs) for blocks, path in entries]
        report[name] = describe(results)

    import math
    print(f"  {'rule':<28} {'median':>8} {'mean':>8} {'geo':>7} "
          f"{'profitable':>11} {'wiped out':>10}", file=sys.stderr)
    for name, stats in sorted(report.items(),
                              key=lambda kv: -kv[1]["geometric_mean"]):
        print(f"  {name:<28} {stats['median']:>7.2f}x {stats['mean']:>7.2f}x "
              f"{math.exp(stats['geometric_mean']):>6.2f}x "
              f"{stats['share_profitable']:>10.1%} "
              f"{stats['share_total_loss']:>9.1%}", file=sys.stderr)

    payload = {"threshold": args.threshold, "entries": len(entries),
               "rules": report,
               "caveats": ["gross of execution cost, own impact and exit slippage",
                           "read the ordering between rules, not the levels"]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=float) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
