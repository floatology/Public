#!/usr/bin/env python3
"""How many tokens crossed a market-cap threshold, and what happened next.

The question this answers: **if a token reaches $300k, is that already
evidence of something, and how far does it typically run afterwards?**

Method. GeckoTerminal exposes `fdv_usd` and a current USD price for every pool
it lists. Supply is inferred as `fdv_now / price_now`, and historical market cap
is then `close(t) x supply` from the daily candles. Two things follow from that
construction and both matter:

- **It assumes supply is constant.** True for most fixed-supply memecoins, false
  for anything that mints or burns after launch, and `rhc.contracts` finds
  mint functions routinely. A token that minted heavily will have its early
  market cap overstated here.
- **It uses fully diluted value, not circulating.** FDV is the honest figure for
  a token whose supply is entirely in the pool from day one, which is the normal
  memecoin case, and it is the only one available historically.

**The denominator is what GeckoTerminal lists, not the chain.** The census
counted 675,438 token addresses; an aggregator tracks a few thousand. So "how
many tokens crossed $300k" is answered within the tracked universe, and the
answer for the whole chain is smaller as a share and not much different as a
count -- a token nobody tracks did not reach $300k.

**Survivorship still applies to the forward return, not to the crossing.**
Whether a token ever crossed $300k is a historical fact visible in its candles.
What it did afterwards is measured on pools still listed today, so tokens that
crossed and were delisted are missing.

Usage:
    python scripts/marketcap_study.py --threshold 300000
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.premium import GeckoTerminal, PremiumError


def collect_pools(gecko: GeckoTerminal, cache: Path, max_pages: int) -> dict[str, dict]:
    """Every pool across every DEX on the network, deduped by address."""
    if cache.exists():
        pools = json.loads(cache.read_text())
        print(f"re-using {len(pools):,} pools from {cache}", file=sys.stderr)
        return pools

    try:
        dexes = [d["id"] for d in (gecko.get("/networks/robinhood/dexes").get("data") or [])]
    except PremiumError as exc:
        print(f"could not list dexes: {exc}", file=sys.stderr)
        dexes = []
    print(f"{len(dexes)} DEXes", file=sys.stderr)

    pools: dict[str, dict] = {}
    sources = ["/networks/robinhood/pools"] + [
        f"/networks/robinhood/dexes/{d}/pools" for d in dexes
    ]
    for source in sources:
        for page in range(1, max_pages + 1):
            try:
                payload = gecko.get(source, page=page)
            except PremiumError:
                break
            items = payload.get("data") or []
            if not items:
                break
            for item in items:
                attributes = item.get("attributes") or {}
                address = attributes.get("address")
                if address and address not in pools:
                    pools[address] = attributes
        print(f"  {source.split('/')[-2]:<34} total {len(pools):,}", file=sys.stderr)

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(pools))
    return pools


def number(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=300_000)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--max-fetch", type=int, default=600,
                        help="pools to pull candles for. Each costs an API call, "
                             "and the listing is far larger than the budget.")
    parser.add_argument("--min-fdv-now", type=float, default=20_000,
                        help="skip pools whose CURRENT fdv is far below the "
                             "threshold; reconstructing their history cannot "
                             "put them above it without an implausible collapse")
    parser.add_argument(
        "--max-fdv-now", type=float, default=50_000_000,
        help="skip the giants. A token worth hundreds of millions has been "
             "above any sensible threshold for its whole tracked history, so "
             "its crossing happened before the candle window opens and no "
             "multiple can be measured. Fetching those first is how a sample "
             "of 50 produced a median peak multiple of 1.09x for tokens that "
             "had every one of them reached $2M.")
    parser.add_argument("--pool-cache", type=Path, default=Path("data/gt_pools.json"))
    parser.add_argument("--candle-cache", type=Path, default=Path("data/gt_candles.json"))
    parser.add_argument("--out", type=Path, default=Path("data/marketcap_study.json"))
    args = parser.parse_args()

    started = time.time()
    with GeckoTerminal() as gecko:
        pools = collect_pools(gecko, args.pool_cache, args.max_pages)

        with_fdv = {
            address: attributes for address, attributes in pools.items()
            if number(attributes.get("fdv_usd")) and number(attributes.get("base_token_price_usd"))
        }
        above_now = {
            a: x for a, x in with_fdv.items()
            if number(x["fdv_usd"]) >= args.threshold
        }
        print(f"\n{len(pools):,} pools listed; {len(with_fdv):,} carry fdv and price",
              file=sys.stderr)
        print(f"{len(above_now):,} are above ${args.threshold:,.0f} FDV right now",
              file=sys.stderr)

        candidates = sorted(
            (a for a, x in with_fdv.items()
             if args.min_fdv_now <= number(x["fdv_usd"]) <= args.max_fdv_now),
            key=lambda a: -number(with_fdv[a]["fdv_usd"]),
        )[: args.max_fetch]
        print(f"fetching candles for {len(candidates):,} pools with FDV >= "
              f"${args.min_fdv_now:,.0f}\n", file=sys.stderr)

        cached: dict[str, list] = {}
        if args.candle_cache.exists():
            cached = json.loads(args.candle_cache.read_text())
            print(f"  {len(cached):,} already cached", file=sys.stderr)

        for index, address in enumerate(candidates, start=1):
            if address in cached:
                continue
            try:
                payload = gecko.get(
                    f"/networks/robinhood/pools/{address}/ohlcv/day",
                    limit=100, currency="usd",
                )
            except PremiumError:
                cached[address] = []
                continue
            cached[address] = sorted(
                (payload.get("data") or {}).get("attributes", {}).get("ohlcv_list") or []
            )
            if index % 50 == 0:
                print(f"  {index}/{len(candidates)}  {time.time() - started:.0f}s",
                      file=sys.stderr)
                args.candle_cache.write_text(json.dumps(cached))
        args.candle_cache.parent.mkdir(parents=True, exist_ok=True)
        args.candle_cache.write_text(json.dumps(cached))

    # --- reconstruct market-cap history and measure the run after crossing ---
    crossed: list[dict] = []
    never = 0
    unusable = 0
    for address in candidates:
        raw = cached.get(address) or []
        attributes = with_fdv[address]
        price_now = number(attributes["base_token_price_usd"])
        fdv_now = number(attributes["fdv_usd"])
        if not raw or not price_now or not fdv_now or len(raw) < 3:
            unusable += 1
            continue
        supply = fdv_now / price_now
        caps = [(ts, close * supply, close, volume) for ts, _o, _h, _l, close, volume in raw]

        first = next((i for i, (_, cap, _, _) in enumerate(caps) if cap >= args.threshold), None)
        if first is None:
            never += 1
            continue

        entry_cap = caps[first][1]
        entry_price = caps[first][2]
        forward = caps[first:]
        peak_cap = max(c for _, c, _, _ in forward)
        peak_price = max(p for _, _, p, _ in forward)
        final_price = forward[-1][2]
        # Volume-backed peak: the highest price at or above which a tenth of the
        # forward window's volume traded. The naive maximum counts a wick.
        total_volume = sum(v for _, _, _, v in forward) or 0.0
        realisable = None
        if total_volume > 0:
            running = 0.0
            for _, _, price, volume in sorted(forward, key=lambda r: -r[2]):
                running += volume
                if running >= total_volume * 0.1:
                    realisable = price / entry_price
                    break
        crossed.append({
            "pool": address, "name": attributes.get("name"),
            "entry_cap": entry_cap, "peak_cap": peak_cap,
            "days_of_history": len(caps), "days_after_crossing": len(forward),
            "peak_multiple": peak_price / entry_price,
            "realisable_multiple": realisable,
            "final_multiple": final_price / entry_price,
            "reserve_now": number(attributes.get("reserve_in_usd")),
        })

    if not crossed:
        print("\nno pool crossed the threshold in its candle history",
              file=sys.stderr)
        return 1

    def summarise(key: str) -> dict:
        values = sorted(c[key] for c in crossed if c.get(key) is not None)
        if not values:
            return {}
        n = len(values)
        return {
            "n": n, "median": statistics.median(values),
            "p25": values[n // 4], "p75": values[(3 * n) // 4],
            "p90": values[min(n - 1, (9 * n) // 10)], "max": values[-1],
            "share_above_2x": sum(v >= 2 for v in values) / n,
            "share_above_5x": sum(v >= 5 for v in values) / n,
            "share_above_10x": sum(v >= 10 for v in values) / n,
            "share_below_1x": sum(v < 1 for v in values) / n,
        }

    report = {
        "threshold": args.threshold,
        "pools_listed": len(pools),
        "pools_with_fdv": len(with_fdv),
        "above_threshold_now": len(above_now),
        "candles_fetched": len(candidates),
        "crossed_ever": len(crossed),
        "never_crossed": never,
        "unusable": unusable,
        "peak_multiple": summarise("peak_multiple"),
        "realisable_multiple": summarise("realisable_multiple"),
        "final_multiple": summarise("final_multiple"),
        "biggest": sorted(crossed, key=lambda c: -c["peak_multiple"])[:15],
        "caveats": [
            "supply inferred as fdv_now / price_now and assumed constant",
            "FDV, not circulating market cap",
            "denominator is GeckoTerminal's tracked universe, not the 675,438-address census",
            "forward returns are measured on pools still listed today",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=float) + "\n")

    print(f"\n  of {len(candidates):,} pools examined: {len(crossed):,} crossed "
          f"${args.threshold:,.0f}, {never:,} never did, {unusable:,} unusable",
          file=sys.stderr)
    for label, key in (("peak (wick)", "peak_multiple"),
                       ("peak (volume-backed)", "realisable_multiple"),
                       ("where it sits now", "final_multiple")):
        s = report[key]
        if not s:
            continue
        print(f"\n  {label} multiple from first crossing  (n={s['n']})",
              file=sys.stderr)
        print(f"    p25 {s['p25']:.2f}x   median {s['median']:.2f}x   "
              f"p75 {s['p75']:.2f}x   p90 {s['p90']:.2f}x   max {s['max']:,.0f}x",
              file=sys.stderr)
        print(f"    >=2x {s['share_above_2x']:.1%}   >=5x {s['share_above_5x']:.1%}   "
              f">=10x {s['share_above_10x']:.1%}   below 1x {s['share_below_1x']:.1%}",
              file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
