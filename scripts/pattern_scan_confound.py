#!/usr/bin/env python3
"""Does the base add anything, or is the impulse doing all the work?

The live scan reported that a breakout from a flag is followed by a 5x within
a fortnight 53% of the time against a 6% base rate -- an 8.6x lift. That is the
kind of number this project has learned to distrust on sight, and it has an
obvious confound.

**A flag requires a 3x impulse by definition.** Tokens that just tripled are
more likely to run again than tokens that did not, whatever shape they traced
afterwards. So the comparison "flag versus everything" is really "recently
tripled versus everything", and the base may be contributing nothing at all.

The right control is **impulse without a base**: periods following a 3x move
where no consolidation formed. If those run at the same rate, the pattern is
decoration on a momentum effect. If the base is doing work, the flagged group
should beat them, not merely beat the unconditional rate.

A second control matters as much. These pools are listed today, so they
survived, and the whole sample is biased upward. The controls share that bias,
which is exactly why a *relative* comparison is worth more here than any
absolute rate.

Usage:
    python scripts/pattern_scan_confound.py
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.patterns import Candle, find_flags

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pattern_scan import forward_multiple

MIN_IMPULSE = 3.0


def had_impulse(candles, index: int, window: int, multiple: float) -> bool:
    """Did price at least `multiple` within the preceding `window` periods?"""
    span = candles[max(0, index - window):index + 1]
    if len(span) < 2:
        return False
    lows = [c.low for c in span if c.low > 0]
    if not lows:
        return False
    low = min(lows)
    return max(c.high for c in span) / low >= multiple


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval. With fifteen observations a point estimate is theatre."""
    if total == 0:
        return (0.0, 1.0)
    p = hits / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/live_candles.json"))
    parser.add_argument("--horizon-days", type=int, default=14)
    parser.add_argument("--threshold", type=float, default=5.0)
    parser.add_argument("--impulse-window", type=int, default=6)
    parser.add_argument("--max-range", type=float, default=0.60)
    parser.add_argument("--out", type=Path, default=Path("data/pattern_confound.json"))
    args = parser.parse_args()

    if not args.cache.exists():
        print(f"{args.cache} not found; run scripts/pattern_scan_live.py first.",
              file=sys.stderr)
        return 1
    cached = json.loads(args.cache.read_text())
    by_pool = {a: [Candle(**c) for c in rows] for a, rows in cached["candles"].items()}

    groups = {
        "all periods": [0, 0],
        "impulse, no base": [0, 0],
        "impulse, in a base": [0, 0],
        "breakout from a base": [0, 0],
        "no impulse": [0, 0],
    }

    for candles in by_pool.values():
        flags = find_flags(candles, max_range=args.max_range)
        in_base = set()
        for flag in flags:
            in_base.update(range(flag.impulse_end + 1, flag.consolidation_end + 1))
        breakouts = {f.breakout_index for f in flags if f.breakout_index is not None}

        for index in range(len(candles) - 1):
            multiple = forward_multiple(candles, index, args.horizon_days)
            if multiple is None:
                continue
            ran = multiple >= args.threshold
            groups["all periods"][0] += 1
            groups["all periods"][1] += ran

            impulse = had_impulse(candles, index, args.impulse_window, MIN_IMPULSE)
            if not impulse:
                groups["no impulse"][0] += 1
                groups["no impulse"][1] += ran
            elif index in in_base:
                groups["impulse, in a base"][0] += 1
                groups["impulse, in a base"][1] += ran
            else:
                groups["impulse, no base"][0] += 1
                groups["impulse, no base"][1] += ran

            if index in breakouts:
                groups["breakout from a base"][0] += 1
                groups["breakout from a base"][1] += ran

    baseline = groups["all periods"]
    base_rate = baseline[1] / baseline[0] if baseline[0] else 0.0
    report = {}
    print(f"\n  run = {args.threshold:g}x within {args.horizon_days}d, "
          f"{len(by_pool)} pools (survivorship-biased)\n", file=sys.stderr)
    print(f"  {'group':<22} {'n':>7} {'hits':>6} {'rate':>7} "
          f"{'95% CI':>16} {'vs all':>8}", file=sys.stderr)
    for name, (total, hits) in groups.items():
        rate = hits / total if total else None
        low, high = wilson(hits, total)
        lift = (rate / base_rate) if (rate is not None and base_rate) else None
        report[name] = {
            "n": total, "hits": hits, "rate": rate,
            "ci_low": low, "ci_high": high, "lift_vs_all": lift,
        }
        print(f"  {name:<22} {total:>7,} {hits:>6,} "
              f"{(f'{rate:.1%}' if rate is not None else '-'):>7} "
              f"{f'{low:.1%} - {high:.1%}':>16} "
              f"{(f'{lift:.2f}x' if lift else '-'):>8}", file=sys.stderr)

    impulse_no_base = report["impulse, no base"]
    impulse_in_base = report["impulse, in a base"]
    breakout = report["breakout from a base"]

    print(f"\n  The comparison that matters is base against impulse-alone,",
          file=sys.stderr)
    print(f"  not against everything:", file=sys.stderr)
    for label, group in (("in a base", impulse_in_base),
                         ("breakout", breakout)):
        if impulse_no_base["rate"] and group["rate"] is not None:
            ratio = group["rate"] / impulse_no_base["rate"]
            overlap = not (group["ci_low"] > impulse_no_base["ci_high"]
                           or group["ci_high"] < impulse_no_base["ci_low"])
            verdict = ("intervals OVERLAP -- not distinguishable at this n"
                       if overlap else "intervals separate")
            print(f"    {label:<10} {ratio:.2f}x impulse-alone   ({verdict})",
                  file=sys.stderr)

    report["_meta"] = {
        "pools": len(by_pool), "threshold": args.threshold,
        "horizon_days": args.horizon_days, "max_range": args.max_range,
        "caveat": "survivorship-biased sample; overlapping forward windows mean "
                  "the effective n is pools, not periods",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
