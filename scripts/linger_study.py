#!/usr/bin/env python3
"""Did the big runners linger at a market-cap level first, or blow through it?

The hypothesis, stated plainly: a token that spends time consolidating around
$300k is absorbing supply, and that absorption is what makes the later run
possible. The alternative is that time spent at a level means nothing, and the
runners simply passed through it on their way up like everything else.

These make opposite predictions and the data can separate them.

**The comparison that matters is not runners against everything.** Every token
that reached $2M necessarily passed through $300k, so "runners spent time near
$300k" is close to a tautology -- they were there, by definition, for at least
a moment. The question is whether they spent *longer* than the tokens that
reached $300k and went nowhere.

And the tradeable form is the inverse, as always: **among tokens that lingered,
what share became runners?** If lingering is common among failures too, it is a
description of a dying token, not a setup. A token that sits at $300k for three
weeks may be accumulating or may simply be stuck.

Definitions, all declared here:

- **Zone**: the market-cap band around the entry level, `--zone-low` to
  `--zone-high`. A band rather than a point, because no token sits at exactly
  $300k.
- **Linger**: days with market cap inside the zone, counted up to and including
  the first day it closed above the zone. Days after that belong to the move,
  not to the base.
- **Runner**: peak market cap at or above `--runner-cap`.

Usage:
    python scripts/linger_study.py --zone-low 200000 --zone-high 500000 \
        --runner-cap 2000000
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


def number(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    p = hits / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def describe(values: list[float]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    n = len(ordered)
    return {
        "n": n, "median": statistics.median(ordered),
        "mean": statistics.fmean(ordered),
        "p25": ordered[n // 4], "p75": ordered[(3 * n) // 4],
        "p90": ordered[min(n - 1, (9 * n) // 10)], "max": ordered[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool-cache", type=Path, default=Path("data/gt_pools.json"))
    parser.add_argument("--candle-cache", type=Path, default=Path("data/gt_candles.json"))
    parser.add_argument("--zone-low", type=float, default=200_000)
    parser.add_argument("--zone-high", type=float, default=500_000)
    parser.add_argument("--runner-cap", type=float, default=2_000_000)
    parser.add_argument("--linger-days", type=int, default=5,
                        help="days inside the zone before a token counts as "
                             "having lingered rather than passed through")
    parser.add_argument("--out", type=Path, default=Path("data/linger_study.json"))
    args = parser.parse_args()

    for path in (args.pool_cache, args.candle_cache):
        if not path.exists():
            print(f"{path} not found; run scripts/marketcap_study.py first.",
                  file=sys.stderr)
            return 1
    pools = json.loads(args.pool_cache.read_text())
    candles = json.loads(args.candle_cache.read_text())

    records: list[dict] = []
    for address, raw in candles.items():
        attributes = pools.get(address) or {}
        price_now = number(attributes.get("base_token_price_usd"))
        fdv_now = number(attributes.get("fdv_usd"))
        if not raw or not price_now or not fdv_now or len(raw) < 3:
            continue
        supply = fdv_now / price_now
        caps = [close * supply for _ts, _o, _h, _l, close, _v in raw]
        peak_cap = max(caps)
        if peak_cap < args.zone_low:
            continue  # never got near the zone; not part of this question

        entered = next((i for i, c in enumerate(caps) if c >= args.zone_low), None)
        if entered is None:
            continue
        # Days inside the zone, up to and including the first close above it.
        # After that the token is in its move, not its base.
        left = next((i for i, c in enumerate(caps) if i >= entered and c > args.zone_high), None)
        window = caps[entered: (left + 1) if left is not None else len(caps)]
        days_in_zone = sum(1 for c in window if args.zone_low <= c <= args.zone_high)

        records.append({
            "pool": address, "name": attributes.get("name"),
            "peak_cap": peak_cap,
            "days_of_history": len(caps),
            "days_in_zone": days_in_zone,
            "escaped_zone": left is not None,
            "is_runner": peak_cap >= args.runner_cap,
            "reserve_now": number(attributes.get("reserve_in_usd")),
        })

    if not records:
        print("no pool reached the zone", file=sys.stderr)
        return 1

    runners = [r for r in records if r["is_runner"]]
    others = [r for r in records if not r["is_runner"]]
    lingered = [r for r in records if r["days_in_zone"] >= args.linger_days]
    passed = [r for r in records if r["days_in_zone"] < args.linger_days]

    p_runner_given_linger = (
        sum(r["is_runner"] for r in lingered) / len(lingered) if lingered else None
    )
    p_runner_given_pass = (
        sum(r["is_runner"] for r in passed) / len(passed) if passed else None
    )

    report = {
        "zone": [args.zone_low, args.zone_high],
        "runner_cap": args.runner_cap,
        "linger_days": args.linger_days,
        "tokens_reaching_zone": len(records),
        "runners": len(runners),
        "runner_rate": len(runners) / len(records),
        "days_in_zone_runners": describe([r["days_in_zone"] for r in runners]),
        "days_in_zone_others": describe([r["days_in_zone"] for r in others]),
        "lingered_n": len(lingered),
        "passed_through_n": len(passed),
        "p_runner_given_linger": p_runner_given_linger,
        "p_runner_given_linger_ci": wilson(
            sum(r["is_runner"] for r in lingered), len(lingered)),
        "p_runner_given_pass": p_runner_given_pass,
        "p_runner_given_pass_ci": wilson(
            sum(r["is_runner"] for r in passed), len(passed)),
        "biggest": sorted(records, key=lambda r: -r["peak_cap"])[:20],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=float) + "\n")

    zone = f"${args.zone_low:,.0f}-${args.zone_high:,.0f}"
    print(f"\n  {len(records):,} tokens reached {zone}; "
          f"{len(runners):,} went on to ${args.runner_cap:,.0f}+ "
          f"({report['runner_rate']:.1%})\n", file=sys.stderr)

    print(f"  days spent in the zone", file=sys.stderr)
    for label, stats in (("runners", report["days_in_zone_runners"]),
                         ("everything else", report["days_in_zone_others"])):
        if stats:
            print(f"    {label:<16} n={stats['n']:<5} median {stats['median']:.0f}d   "
                  f"p25 {stats['p25']:.0f}d  p75 {stats['p75']:.0f}d  "
                  f"p90 {stats['p90']:.0f}d  max {stats['max']:.0f}d",
                  file=sys.stderr)

    print(f"\n  the tradeable form -- does lingering predict anything?",
          file=sys.stderr)
    for label, rate, ci, n in (
        (f"lingered >= {args.linger_days}d", p_runner_given_linger,
         report["p_runner_given_linger_ci"], len(lingered)),
        (f"passed through", p_runner_given_pass,
         report["p_runner_given_pass_ci"], len(passed)),
    ):
        if rate is None:
            continue
        print(f"    P(runner | {label:<18}) = {rate:6.1%}   "
              f"95% CI {ci[0]:.1%}-{ci[1]:.1%}   (n={n})", file=sys.stderr)
    if p_runner_given_linger is not None and p_runner_given_pass is not None:
        low_a, high_a = report["p_runner_given_linger_ci"]
        low_b, high_b = report["p_runner_given_pass_ci"]
        overlap = not (low_a > high_b or high_a < low_b)
        print(f"\n    intervals {'OVERLAP - not distinguishable' if overlap else 'separate'}",
              file=sys.stderr)

    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
