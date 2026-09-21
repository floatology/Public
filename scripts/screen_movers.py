#!/usr/bin/env python3
"""Screen the accumulating movers series for candidates and for fakes.

The movers capture writes one file per day of the chain's most active pools.
This reads the whole series and asks three questions of it, in the order that
matters: what is obviously fake, what is new, and what is growing.

**Fake first, deliberately.** The first capture found pools turning over 400x
and 1,128x their own reserves in twenty-four hours. Nothing organic does that in
a pool that thin — a token cannot genuinely trade its entire liquidity a
thousand times in a day without the price going somewhere. Screening for
opportunity before screening those out would rank them at the top, because on
every conventional activity measure they look spectacular. That is the point of
wash trading.

Two independent tells are used rather than one, because either alone is
defensible in isolation:

- **Volume against reserves.** High is normal for a deep stable pair and
  impossible for a thin memecoin. The threshold therefore scales with depth
  instead of being a single number. **The thresholds are judgement, not
  calibration** — there is no labelled set of known wash-traded pools on this
  chain to fit them against, and a fitted number would only look more
  authoritative than it is. They are set where the arithmetic stops being
  physically possible rather than where some rate looks suspicious.
- **Trades per trader.** DexScreener's own documentation says unique wallet
  count exists specifically to separate genuine interest from a few wallets
  trading back and forth. Twenty buys from three buyers is not a crowd.

Everything here is descriptive. None of it is evidence that a token will go up,
and the ranking is explicitly not a buy list — it is a shortlist of things worth
a closer look, in a system whose predictive claims are still unproven.

Usage:
    python scripts/screen_movers.py
    python scripts/screen_movers.py --min-reserve 25000 --top 20
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def load(directory: Path) -> dict[str, list[dict]]:
    """Every captured row, grouped by pool, oldest first."""
    by_pool: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("pool"):
                by_pool[row["pool"]].append(row)
    for rows in by_pool.values():
        rows.sort(key=lambda r: r.get("captured_at") or "")
    return dict(by_pool)


def number(row: dict, key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def wash_flags(row: dict, *, trades_per_trader_limit: float) -> list[str]:
    """Reasons to disbelieve this pool's activity."""
    flags: list[str] = []
    reserve = number(row, "reserve_usd") or 0.0
    ratio = number(row, "volume_to_reserve")
    if ratio is not None and reserve > 0:
        # A deep pool can legitimately turn over many times a day; a thin one
        # cannot. Scaling the limit with depth avoids flagging the stable pairs
        # that carry the chain's real volume.
        limit = 5.0 if reserve < 100_000 else 25.0 if reserve < 1_000_000 else 100.0
        if ratio > limit:
            flags.append(f"turnover {ratio:.0f}x vs {limit:.0f}x limit at ${reserve:,.0f}")

    buys = number(row, "buys_h24") or 0.0
    buyers = number(row, "buyers_h24") or 0.0
    if buyers >= 1 and buys / buyers > trades_per_trader_limit:
        flags.append(f"{buys/buyers:.0f} buys per buyer")

    sells = number(row, "sells_h24") or 0.0
    total_traders = buyers + (number(row, "sellers_h24") or 0.0)
    if total_traders and (buys + sells) and total_traders < 5 and (buys + sells) > 100:
        flags.append(f"{buys+sells:.0f} trades among {total_traders:.0f} traders")
    return flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movers", type=Path, default=Path("data/movers"))
    parser.add_argument("--min-reserve", type=float, default=50_000,
                        help="below this, execution cost dominates any edge. "
                             "Measured: a $20k pool costs 96% to trade $500 through.")
    parser.add_argument("--trades-per-trader", type=float, default=8.0)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    if not args.movers.exists():
        print(f"{args.movers} not found; run scripts/daily_movers.py first",
              file=sys.stderr)
        return 1

    by_pool = load(args.movers)
    if not by_pool:
        print("no captures yet", file=sys.stderr)
        return 1
    days = len({r.get("captured_at", "")[:10] for rows in by_pool.values() for r in rows})
    print(f"{len(by_pool):,} pools across {days} capture day(s)\n", file=sys.stderr)

    latest = {pool: rows[-1] for pool, rows in by_pool.items()}

    suspect, clean = [], []
    for pool, row in latest.items():
        flags = wash_flags(row, trades_per_trader_limit=args.trades_per_trader)
        (suspect if flags else clean).append((row, flags))

    print(f"--- activity that does not add up ({len(suspect)}) ---", file=sys.stderr)
    suspect.sort(key=lambda pair: -(number(pair[0], "volume_24h_usd") or 0))
    for row, flags in suspect[: args.top]:
        print(f"  {row.get('name', '?')[:28]:30s} "
              f"vol=${number(row, 'volume_24h_usd') or 0:>14,.0f} "
              f"resv=${number(row, 'reserve_usd') or 0:>12,.0f}", file=sys.stderr)
        for flag in flags:
            print(f"      {flag}", file=sys.stderr)

    tradable = [
        (row, flags) for row, flags in clean
        if (number(row, "reserve_usd") or 0) >= args.min_reserve
    ]
    print(f"\n--- passes both the wash screen and the ${args.min_reserve:,.0f} "
          f"depth floor ({len(tradable)}) ---", file=sys.stderr)
    tradable.sort(key=lambda pair: -(number(pair[0], "volume_24h_usd") or 0))
    for row, _ in tradable[: args.top]:
        buys = number(row, "buys_h24") or 0
        buyers = number(row, "buyers_h24") or 0
        print(f"  {row.get('name', '?')[:28]:30s} "
              f"vol=${number(row, 'volume_24h_usd') or 0:>14,.0f} "
              f"resv=${number(row, 'reserve_usd') or 0:>12,.0f} "
              f"buys/buyer={buys/buyers if buyers else 0:>6.2f}", file=sys.stderr)

    if days > 1:
        # Day-over-day movement, which is the only thing the series adds that a
        # single snapshot cannot give.
        print(f"\n--- fastest reserve growth across captures ---", file=sys.stderr)
        growth = []
        for pool, rows in by_pool.items():
            if len(rows) < 2:
                continue
            first = number(rows[0], "reserve_usd") or 0
            last = number(rows[-1], "reserve_usd") or 0
            if first >= args.min_reserve and last > first:
                growth.append((last / first, rows[-1]))
        growth.sort(key=lambda pair: -pair[0])
        for multiple, row in growth[: args.top]:
            print(f"  {row.get('name', '?')[:28]:30s} reserves x{multiple:.2f}",
                  file=sys.stderr)
        newcomers = [
            rows[-1] for rows in by_pool.values()
            if len(rows) == 1 and rows[0].get("captured_at", "")[:10]
            == max(r.get("captured_at", "")[:10] for rs in by_pool.values() for r in rs)
        ]
        print(f"\n  {len(newcomers)} pools appeared for the first time in the "
              f"latest capture", file=sys.stderr)
    else:
        print(f"\nOnly one capture day so far, so nothing here is a trend yet. "
              f"Day-over-day\ngrowth and new entrants appear once a second day "
              f"lands.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
