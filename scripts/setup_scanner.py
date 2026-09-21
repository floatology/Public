#!/usr/bin/env python3
"""What is forming a base right now, ranked.

This is the alerting tool, not the research one. It asks a single question of
every liquid pool on the chain: **as of today, does this look like
accumulation?** Tokens that have already broken out are excluded, because by
then the answer is no longer actionable.

**Why it scans listed pools rather than the whole chain.** The median token here
trades for about fifteen minutes; the 90th percentile lasts under a day. An
accumulation structure needs weeks, so only the top percentile of tokens can
have one at all, and those are exactly the ones an aggregator lists. Scanning
675,438 token addresses to find them would be the wrong instrument as well as a
slow one.

**A depth floor is applied and it is not cosmetic.** Execution cost on this
chain was measured across four orders of magnitude: a $500 trade through a $20k
pool cost 96%. A perfect base in a pool nobody can trade is not a setup, so
anything below the floor is dropped before ranking rather than shown with a
warning.

The output is a watchlist, not a buy list. Nothing here has been shown to
predict anything — `P(ran | base)` against the unconditional rate is still
unmeasured on this chain, which is what `scripts/pattern_scan.py` exists to do
once the V3 sample lands. Until then this tells you what a textbook base looks
like today, and that is all it tells you.

Usage:
    python scripts/setup_scanner.py --pools 200 --min-reserve 50000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.accumulation import BaseState, analyse
from rhc.patterns import Candle, find_flags
from rhc.premium import GeckoTerminal, PremiumError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen_movers import wash_flags


def fetch_candles(gecko: GeckoTerminal, address: str, timeframe: str,
                  aggregate: int, limit: int) -> list[Candle]:
    params = {"limit": limit, "currency": "usd"}
    if aggregate > 1:
        params["aggregate"] = aggregate
    try:
        payload = gecko.get(
            f"/networks/robinhood/pools/{address}/ohlcv/{timeframe}", **params
        )
    except PremiumError:
        return []
    raw = sorted((payload.get("data") or {}).get("attributes", {}).get("ohlcv_list") or [])
    return [
        Candle(index=i, open=o, high=h, low=l, close=c, volume=v)
        for i, (_, o, h, l, c, v) in enumerate(raw)
        if c > 0
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pools", type=int, default=200)
    parser.add_argument("--timeframe", default="day", choices=("day", "hour"))
    parser.add_argument("--aggregate", type=int, default=1,
                        help="candle width in units of --timeframe, e.g. 4 with "
                             "hour for 4h bars")
    parser.add_argument("--lookback", type=int, default=20,
                        help="periods forming the base under examination")
    parser.add_argument("--min-candles", type=int, default=12)
    parser.add_argument("--min-reserve", type=float, default=50_000,
                        help="below this, execution cost eats any edge. Measured: "
                             "a $500 trade through a $20k pool cost 96%%.")
    parser.add_argument("--min-score", type=float, default=0.5)
    parser.add_argument("--out", type=Path, default=Path("data/setups"))
    args = parser.parse_args()

    started = time.time()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows: list[dict] = []
    skipped = {"shallow": 0, "wash": 0, "short": 0, "broke_out": 0, "weak": 0}

    with GeckoTerminal() as gecko:
        listed: list[dict] = []
        page = 1
        while len(listed) < args.pools and page <= 10:
            try:
                payload = gecko.get("/networks/robinhood/pools", page=page)
            except PremiumError as exc:
                print(f"  listing page {page}: {exc}", file=sys.stderr)
                break
            items = payload.get("data") or []
            if not items:
                break
            listed.extend(items)
            page += 1
        listed = listed[: args.pools]
        print(f"{len(listed)} pools listed", file=sys.stderr)

        for index, item in enumerate(listed, start=1):
            attributes = item.get("attributes") or {}
            address = attributes.get("address")
            if not address:
                continue
            reserve = float(attributes.get("reserve_in_usd") or 0)
            if reserve < args.min_reserve:
                skipped["shallow"] += 1
                continue

            # The wash screen runs before the pattern, not after. A base drawn
            # by two wallets trading with each other is a picture, not a market.
            volume_24h = float(
                (attributes.get("volume_usd") or {}).get("h24") or 0
            )
            transactions = (attributes.get("transactions") or {}).get("h24") or {}
            probe = {
                "reserve_usd": reserve, "volume_24h_usd": volume_24h,
                "volume_to_reserve": (volume_24h / reserve) if reserve else 0,
                "buys_h24": transactions.get("buys"),
                "buyers_h24": transactions.get("buyers"),
                "sells_h24": transactions.get("sells"),
                "sellers_h24": transactions.get("sellers"),
            }
            flags = wash_flags(probe, trades_per_trader_limit=8.0)
            if flags:
                skipped["wash"] += 1
                continue

            candles = fetch_candles(gecko, address, args.timeframe,
                                    args.aggregate, 100)
            if len(candles) < args.min_candles:
                skipped["short"] += 1
                continue

            state = analyse(candles, lookback=args.lookback)
            if state.broke_out:
                skipped["broke_out"] += 1
                continue
            if state.base_score is None or state.base_score < args.min_score:
                skipped["weak"] += 1
                continue

            record = {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "pool": address, "name": attributes.get("name"),
                "reserve_usd": reserve, "volume_24h_usd": volume_24h,
                "candles": len(candles),
                "timeframe": f"{args.aggregate}{args.timeframe}",
            }
            record.update(state.to_dict())
            record["notes"] = "; ".join(state.notes)
            # A prior completed flag says this token has broken out of a base
            # before, which is context rather than a signal.
            record["prior_flags"] = len(find_flags(candles))
            rows.append(record)

            if index % 25 == 0:
                print(f"  {index}/{len(listed)}  {len(rows)} setups  "
                      f"{time.time() - started:.0f}s", file=sys.stderr)

    rows.sort(key=lambda r: -(r["base_score"] or 0))
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{today}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    print(f"\n  {len(rows)} setups; skipped {skipped}", file=sys.stderr)
    if rows:
        print(f"\n  {'name':<26} {'score':>6} {'arch':>18} {'contr':>6} "
              f"{'dryup':>6} {'slope':>8} {'resv':>12}", file=sys.stderr)
        for r in rows[:20]:
            dryup = f"{r['volume_dryup']:.2f}" if r["volume_dryup"] else "-"
            slope = (f"{r['support_slope']:+.4f}"
                     if r["support_slope"] is not None else "-")
            reserve = f"${r['reserve_usd']:,.0f}"
            print(f"  {(r['name'] or '?')[:25]:<26} {r['base_score']:>6.3f} "
                  f"{r['archetype']:>18} {r['contractions']:>6} "
                  f"{dryup:>6} {slope:>8} {reserve:>12}", file=sys.stderr)
    print(f"\nwrote {path}", file=sys.stderr)
    print("\n  Watchlist, not a buy list. P(ran | base) is unmeasured on this "
          "chain.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
