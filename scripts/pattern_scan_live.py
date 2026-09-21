#!/usr/bin/env python3
"""Flag statistics over currently-listed pools, from GeckoTerminal candles.

The trade-archive scan is the unbiased instrument and it cannot answer this yet:
Uniswap V2 on this chain is a graveyard, and only twenty tokens carry ten days
of history. This is the stopgap -- real daily candles for pools that are listed
and trading now.

**It is survivorship-biased and the bias runs one way.** Every pool here is one
that GeckoTerminal ranks today, which means it survived. Tokens that flagged and
then died are systematically missing, so `P(ran | flag)` measured this way is an
**upper bound**, not an estimate. Treat a good number here as "worth testing
properly", never as a result.

The unbiased version is the same `rhc.patterns` code pointed at the trade
archive once the V3 extraction lands, which samples pools by census rather than
by current prominence.

Usage:
    python scripts/pattern_scan_live.py --pools 150 --threshold 5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.patterns import Candle, find_flags
from rhc.premium import GeckoTerminal, PremiumError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pattern_scan import DECLARED_RANGE_SWEEP, forward_multiple


def list_pools(gecko: GeckoTerminal, wanted: int) -> list[dict]:
    pools: list[dict] = []
    page = 1
    while len(pools) < wanted and page <= 10:
        try:
            payload = gecko.get("/networks/robinhood/pools", page=page)
        except PremiumError as exc:
            print(f"  page {page}: {exc}", file=sys.stderr)
            break
        items = payload.get("data") or []
        if not items:
            break
        pools.extend(items)
        page += 1
    return pools[:wanted]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pools", type=int, default=150)
    parser.add_argument("--horizon-days", type=int, default=14)
    parser.add_argument("--threshold", type=float, default=5.0)
    parser.add_argument("--min-candles", type=int, default=12)
    parser.add_argument("--out", type=Path, default=Path("data/pattern_scan_live.json"))
    args = parser.parse_args()

    started = time.time()
    with GeckoTerminal() as gecko:
        pools = list_pools(gecko, args.pools)
        print(f"{len(pools)} pools listed; fetching candles", file=sys.stderr)

        by_pool: dict[str, list[Candle]] = {}
        names: dict[str, str] = {}
        for index, item in enumerate(pools, start=1):
            attributes = item.get("attributes") or {}
            address = attributes.get("address")
            if not address:
                continue
            try:
                payload = gecko.get(
                    f"/networks/robinhood/pools/{address}/ohlcv/day",
                    limit=100, currency="usd",
                )
            except PremiumError:
                continue
            raw = sorted(
                (payload.get("data") or {}).get("attributes", {}).get("ohlcv_list") or []
            )
            if len(raw) < args.min_candles:
                continue
            by_pool[address] = [
                Candle(index=i, open=o, high=h, low=l, close=c, volume=v)
                for i, (_, o, h, l, c, v) in enumerate(raw)
            ]
            names[address] = attributes.get("name", "?")
            if index % 25 == 0:
                print(f"  {index}/{len(pools)} scanned, {len(by_pool)} usable, "
                      f"{time.time() - started:.0f}s", file=sys.stderr)

    print(f"{len(by_pool)} pools with >= {args.min_candles} daily candles\n",
          file=sys.stderr)
    if not by_pool:
        print("nothing usable", file=sys.stderr)
        return 1

    results: dict[str, dict] = {}
    examples: list[dict] = []
    for max_range in DECLARED_RANGE_SWEEP:
        universe = runs = flagged = flagged_runs = 0
        breakouts = breakout_runs = 0
        tokens_flag: set[str] = set()
        tokens_ran: set[str] = set()
        tokens_both: set[str] = set()

        for address, candles in by_pool.items():
            flags = find_flags(candles, max_range=max_range)
            breakout_at = {f.breakout_index for f in flags if f.breakout_index is not None}
            if flags:
                tokens_flag.add(address)
            ran_here = False
            for i in range(len(candles) - 1):
                multiple = forward_multiple(candles, i, args.horizon_days)
                if multiple is None:
                    continue
                universe += 1
                ran = multiple >= args.threshold
                runs += ran
                ran_here |= ran
                if any(f.impulse_end < i <= f.consolidation_end for f in flags):
                    flagged += 1
                    flagged_runs += ran
                if i in breakout_at:
                    breakouts += 1
                    breakout_runs += ran
                    if ran and len(examples) < 12:
                        examples.append({
                            "pool": names.get(address, address),
                            "breakout_period": i,
                            "forward_multiple": round(multiple, 2),
                        })
            if ran_here:
                tokens_ran.add(address)
                if flags:
                    tokens_both.add(address)

        base = runs / universe if universe else None
        results[f"max_range_{max_range:.2f}"] = {
            "decision_points": universe, "unconditional_run_rate": base,
            "points_inside_a_flag": flagged,
            "run_rate_inside_a_flag": (flagged_runs / flagged) if flagged else None,
            "breakout_points": breakouts,
            "run_rate_after_breakout": (breakout_runs / breakouts) if breakouts else None,
            "pools_total": len(by_pool), "pools_with_a_flag": len(tokens_flag),
            "pools_that_ran": len(tokens_ran),
            "p_flag_given_ran": (len(tokens_both) / len(tokens_ran)) if tokens_ran else None,
            "p_ran_given_flag": (len(tokens_both) / len(tokens_flag)) if tokens_flag else None,
        }

    payload = {
        "source": "geckoterminal daily candles, currently-listed pools",
        "caveat": "survivorship-biased: pools that flagged and died are absent, "
                  "so P(ran | flag) here is an upper bound",
        "threshold": args.threshold, "horizon_days": args.horizon_days,
        "results": results, "breakout_examples": examples,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"  run = {args.threshold:g}x within {args.horizon_days}d  "
          f"(SURVIVORSHIP-BIASED, upper bound)\n", file=sys.stderr)
    print(f"  {'range':>6} {'points':>8} {'base':>7} {'in flag':>8} {'flag rate':>10} "
          f"{'lift':>6} {'breakouts':>10} {'bo rate':>8} {'bo lift':>8}", file=sys.stderr)
    for key, r in results.items():
        base = r["unconditional_run_rate"] or 0
        fr, br = r["run_rate_inside_a_flag"], r["run_rate_after_breakout"]
        print(f"  {key.split('_')[-1]:>6} {r['decision_points']:>8,} {base:>6.1%} "
              f"{r['points_inside_a_flag']:>8,} "
              f"{(f'{fr:.1%}' if fr is not None else 'n/a'):>10} "
              f"{(f'{fr/base:.2f}x' if fr and base else 'n/a'):>6} "
              f"{r['breakout_points']:>10,} "
              f"{(f'{br:.1%}' if br is not None else 'n/a'):>8} "
              f"{(f'{br/base:.2f}x' if br and base else 'n/a'):>8}", file=sys.stderr)
    mid = results[f"max_range_{DECLARED_RANGE_SWEEP[1]:.2f}"]
    print(f"\n  pool-level at range 0.60: P(flag | ran) = {mid['p_flag_given_ran']}, "
          f"P(ran | flag) = {mid['p_ran_given_flag']}", file=sys.stderr)
    print(f"  ({mid['pools_that_ran']} of {mid['pools_total']} pools ran; "
          f"{mid['pools_with_a_flag']} flagged)", file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
