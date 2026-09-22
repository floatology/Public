#!/usr/bin/env python3
"""Run the mini screen against the live market and list what passes.

The criteria and the evidence behind them are in `docs/21-the-mini-screen.md`.
In short: of coins sitting in the $100k-$400k band, roughly 24% still hold half
their value a fortnight later; the liquidity gate raises that to about 73%.

**This is a survival filter, not a buy list.** Nothing in this project predicts
which survivor goes up — `docs/18` covers four separate attempts that failed.
What passing means is that a coin is much less likely to be part of the 76% that
collapse.

**The peak check needs price history**, so it costs one extra call per candidate.
A coin's historical high market cap is reconstructed as
`current cap x (highest close / current close)`, which assumes supply has not
changed — the same assumption carried everywhere else here, and wrong for
anything that minted after launch.

Usage:
    python scripts/run_screen.py
    python scripts/run_screen.py --min-liq-ratio 0.30   # looser
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.dexscreener import DexScreener, DexScreenerError, flatten
from rhc.premium import GeckoTerminal, PremiumError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen_movers import wash_flags


def number(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--low-cap", type=float, default=100_000)
    parser.add_argument("--high-cap", type=float, default=400_000)
    parser.add_argument("--min-liq-ratio", type=float, default=0.40,
                        help="liquidity / market cap, in AGGREGATOR terms "
                             "(double the internal 0.20 figure)")
    parser.add_argument("--min-liq-usd", type=float, default=50_000)
    parser.add_argument("--max-ever-cap", type=float, default=1_000_000)
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument(
        "--pool-cache", type=Path, default=Path("data/gt_pools.json"),
        help="the full census of pools across every DEX, from "
             "scripts/marketcap_study.py. Without it the universe is only what "
             "a single listing call returns -- about 135 tokens against the "
             "thousands the chain actually carries.")
    parser.add_argument("--out", type=Path, default=Path("data/screen_results"))
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc)
    universe: dict[str, dict] = {}

    with GeckoTerminal() as gecko:
        # The listing endpoint returns only the busiest few hundred pools, which
        # is the wrong universe for a screen aimed at $100k-$400k coins. The
        # census covers every DEX on the chain, keyed by pool address.
        pool_addresses: list[str] = []
        if args.pool_cache.exists():
            pool_addresses = sorted(json.loads(args.pool_cache.read_text()))
            print(f"{len(pool_addresses):,} pools from the census", file=sys.stderr)
        else:
            for page in range(1, args.pages + 1):
                try:
                    payload = gecko.get("/networks/robinhood/pools", page=page)
                except PremiumError:
                    break
                items = payload.get("data") or []
                if not items:
                    break
                pool_addresses.extend(
                    (i.get("attributes") or {}).get("address") for i in items)
            pool_addresses = [a for a in pool_addresses if a]
            print(f"{len(pool_addresses)} pools from the listing (no census cache)",
                  file=sys.stderr)

        try:
            with DexScreener() as dex:
                for pair in dex.pairs_by_address(pool_addresses):
                    row = flatten(pair)
                    key = (row.get("base_token") or "").lower()
                    if not key:
                        continue
                    prior = universe.get(key)
                    if prior is None or (number(row.get("liquidity_usd")) or 0) > (
                            number(prior.get("liquidity_usd")) or 0):
                        universe[key] = row
        except DexScreenerError as exc:
            print(f"dexscreener failed: {exc}", file=sys.stderr)
            return 1
        print(f"{len(universe):,} distinct tokens with a tracked pair",
              file=sys.stderr)

        # --- criteria 1-3 ---
        candidates = []
        rejected = {"cap": 0, "liq_ratio": 0, "liq_usd": 0, "wash": 0}
        for row in universe.values():
            cap = number(row.get("market_cap")) or number(row.get("fdv"))
            liq = number(row.get("liquidity_usd"))
            if cap is None or liq is None:
                continue
            if not (args.low_cap <= cap <= args.high_cap):
                rejected["cap"] += 1
                continue
            if liq < args.min_liq_usd:
                rejected["liq_usd"] += 1
                continue
            ratio = liq / cap
            if ratio < args.min_liq_ratio:
                rejected["liq_ratio"] += 1
                continue
            probe = {
                "reserve_usd": liq,
                "volume_24h_usd": number(row.get("volume_h24")) or 0,
                "volume_to_reserve": (number(row.get("volume_h24")) or 0) / liq,
                "buys_h24": row.get("buys_h24"), "buyers_h24": None,
                "sells_h24": row.get("sells_h24"), "sellers_h24": None,
            }
            flags = wash_flags(probe, trades_per_trader_limit=1e9)
            if flags:
                rejected["wash"] += 1
                row["wash_flags"] = flags
                continue
            row["market_cap_used"] = cap
            row["liq_ratio"] = ratio
            candidates.append(row)

        print(f"\n  after cap / liquidity / wash filters: {len(candidates)} candidates "
              f"(rejected {rejected})", file=sys.stderr)

        # --- criterion 4: never above the ceiling ---
        passed, spiked = [], []
        for row in candidates:
            price_now = number(row.get("price_usd"))
            try:
                payload = gecko.get(
                    f"/networks/robinhood/pools/{row['pair']}/ohlcv/day",
                    limit=100, currency="usd")
            except PremiumError:
                row["peak_cap_ever"] = None
                row["peak_note"] = "no history available"
                passed.append(row)
                continue
            candles = (payload.get("data") or {}).get("attributes", {}).get("ohlcv_list") or []
            closes = [c[4] for c in candles if c[4] and c[4] > 0]
            if not closes or not price_now:
                row["peak_cap_ever"] = None
                row["peak_note"] = "no history available"
                passed.append(row)
                continue
            peak_cap = row["market_cap_used"] * (max(closes) / price_now)
            row["peak_cap_ever"] = peak_cap
            row["days_of_history"] = len(candles)
            (spiked if peak_cap > args.max_ever_cap else passed).append(row)

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{stamp.strftime('%Y-%m-%dT%H%M')}.json"
    path.write_text(json.dumps({
        "run_at": stamp.isoformat(),
        "criteria": {
            "market_cap": [args.low_cap, args.high_cap],
            "min_liquidity_over_cap": args.min_liq_ratio,
            "min_liquidity_usd": args.min_liq_usd,
            "max_peak_cap_ever": args.max_ever_cap,
        },
        "universe": len(universe), "passed": passed, "excluded_for_spike": spiked,
    }, indent=2, default=float) + "\n")

    print(f"\n  {len(spiked)} excluded for having been above "
          f"${args.max_ever_cap:,.0f}", file=sys.stderr)
    print(f"\n  === {len(passed)} COINS PASS ===\n", file=sys.stderr)
    if passed:
        passed.sort(key=lambda r: -r["liq_ratio"])
        print(f"  {'token':<14} {'cap':>10} {'liquidity':>11} {'liq/cap':>8} "
              f"{'peak ever':>11} {'vol 24h':>11} {'24h %':>8}", file=sys.stderr)
        for row in passed:
            peak = (f"${row['peak_cap_ever']/1000:,.0f}k"
                    if row.get("peak_cap_ever") else "unknown")
            change = number(row.get("price_change_h24"))
            print(f"  {(row.get('base_symbol') or '?')[:13]:<14} "
                  f"${row['market_cap_used']/1000:>8,.0f}k "
                  f"${number(row['liquidity_usd'])/1000:>9,.0f}k "
                  f"{row['liq_ratio']:>8.2f} {peak:>11} "
                  f"${(number(row.get('volume_h24')) or 0)/1000:>9,.0f}k "
                  f"{(f'{change:+.1f}%' if change is not None else '-'):>8}",
                  file=sys.stderr)
    print(f"\nwrote {path}", file=sys.stderr)
    print("\n  A survival filter, not a buy list. Nothing here predicts which "
          "passer goes up.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
