#!/usr/bin/env python3
"""Do bull flags precede big runs, and does a flag predict one?

Prompted by a concrete observation: HYPERHOOD (HH) formed a textbook impulse,
a two-week base on decaying volume, and then broke to new highs. The obvious
question is whether that shape is common among big runners. The obvious
question is also the wrong one to stop at.

**Two conditional probabilities, and only one of them is tradeable.**

- `P(flag | ran)` — among tokens that ran, how many showed a flag first. This
  conditions on the outcome. If runners mostly go up in steps, almost any
  step-shaped pattern will be "common in runners" and the number says nothing.
- `P(ran | flag)` — among tokens that showed a flag, how many then ran. This is
  the number an entry decision depends on, and it is the one nobody computes,
  because the flags that failed are the ones nobody remembers seeing.

A flag is worth something only if `P(ran | flag)` beats the unconditional base
rate. Both are reported, next to that base rate, every time.

**Thresholds are declared, and swept.** `rhc.patterns` fixes the shape
definition. The consolidation-range limit is swept across three declared values
rather than one, because validating the detector against HH showed its full
two-week base sits at a 61% close range against a 60% limit -- a knife-edge.
Moving the threshold to admit HH would be fitting the definition to the example
that motivated it. Sweeping it, and reporting every value, is the honest form of
the same question, and the spread across the sweep is itself the answer to "how
crisp is this pattern".

Usage:
    python scripts/pattern_scan.py --horizon-days 14 --threshold 5
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb

from rhc.patterns import Candle, candles_from_prices, find_flags

BLOCKS_PER_DAY = 864_000
DECLARED_RANGE_SWEEP = (0.50, 0.60, 0.75)


def forward_multiple(candles: list[Candle], start: int, periods: int,
                     volume_fraction: float = 0.1) -> float | None:
    """Volume-backed peak over the next `periods`, against the close at `start`.

    The naive maximum would count a single wick nobody could have sold into,
    which is the error the pre-registration's outcome amendment exists to stop.
    """
    reference = candles[start].close
    forward = candles[start + 1:start + 1 + periods]
    if reference <= 0 or not forward:
        return None
    priced = [c for c in forward if c.close > 0 and c.volume > 0]
    if not priced:
        return None
    total = sum(c.volume for c in priced)
    running = 0.0
    for candle in sorted(priced, key=lambda c: -c.close):
        running += candle.volume
        if running >= total * volume_fraction:
            return candle.close / reference
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", default="data/parquet/trades*.parquet")
    parser.add_argument("--period-days", type=float, default=1.0)
    parser.add_argument("--horizon-days", type=float, default=14.0)
    parser.add_argument("--threshold", type=float, default=5.0,
                        help="forward multiple that counts as a run")
    parser.add_argument("--min-candles", type=int, default=10)
    parser.add_argument("--blocks-per-day", type=int, default=BLOCKS_PER_DAY)
    parser.add_argument("--out", type=Path, default=Path("data/pattern_scan.json"))
    args = parser.parse_args()

    if not sorted(glob.glob(args.trades)):
        print(f"no trade archive matches {args.trades!r}", file=sys.stderr)
        return 1

    period = int(args.period_days * args.blocks_per_day)
    horizon = int(args.horizon_days / args.period_days)

    con = duckdb.connect()
    rows = con.execute(
        "SELECT token, block, quote_amount, base_amount FROM read_parquet(?) "
        "ORDER BY token, block, log_index", [args.trades],
    ).fetchall()
    series: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for token, block, quote, base in rows:
        quote, base = int(quote), int(base)
        if base > 0 and quote > 0:
            series[token].append((int(block), quote / base, float(quote)))

    by_token = {
        token: candles_from_prices(obs, period=period)
        for token, obs in series.items()
    }
    by_token = {t: c for t, c in by_token.items() if len(c) >= args.min_candles}
    print(f"{len(by_token):,} tokens with >= {args.min_candles} periods of history",
          file=sys.stderr)
    if not by_token:
        print("nothing with enough history to look at.", file=sys.stderr)
        return 1

    results: dict[str, dict] = {}
    for max_range in DECLARED_RANGE_SWEEP:
        # Every scoreable decision point, whether or not a flag was present.
        # This is the denominator that makes P(ran | flag) interpretable.
        universe = 0
        universe_runs = 0
        flagged = 0
        flagged_runs = 0
        tokens_with_flag: set[str] = set()
        tokens_that_ran: set[str] = set()
        tokens_flag_then_ran: set[str] = set()
        breakout_points = 0
        breakout_runs = 0

        for token, candles in by_token.items():
            flags = find_flags(candles, max_range=max_range)
            breakout_indices = {
                f.breakout_index for f in flags if f.breakout_index is not None
            }
            if flags:
                tokens_with_flag.add(token)

            token_ran = False
            for index in range(len(candles) - 1):
                multiple = forward_multiple(candles, index, horizon)
                if multiple is None:
                    continue
                universe += 1
                ran = multiple >= args.threshold
                universe_runs += ran
                token_ran |= ran
                if index in breakout_indices:
                    breakout_points += 1
                    breakout_runs += ran
                # "In a flag" = the period sits inside a detected consolidation.
                in_flag = any(
                    f.impulse_end < index <= f.consolidation_end for f in flags
                )
                if in_flag:
                    flagged += 1
                    flagged_runs += ran
            if token_ran:
                tokens_that_ran.add(token)
                if flags:
                    tokens_flag_then_ran.add(token)

        base_rate = universe_runs / universe if universe else None
        results[f"max_range_{max_range:.2f}"] = {
            "decision_points": universe,
            "unconditional_run_rate": base_rate,
            "points_inside_a_flag": flagged,
            "run_rate_inside_a_flag": (flagged_runs / flagged) if flagged else None,
            "breakout_points": breakout_points,
            "run_rate_after_breakout": (
                breakout_runs / breakout_points) if breakout_points else None,
            "tokens_total": len(by_token),
            "tokens_with_a_flag": len(tokens_with_flag),
            "tokens_that_ran": len(tokens_that_ran),
            "p_flag_given_ran": (
                len(tokens_flag_then_ran) / len(tokens_that_ran)
                if tokens_that_ran else None
            ),
            "p_ran_given_flag": (
                len(tokens_flag_then_ran) / len(tokens_with_flag)
                if tokens_with_flag else None
            ),
        }

    payload = {
        "threshold": args.threshold, "horizon_days": args.horizon_days,
        "period_days": args.period_days, "sweep": list(DECLARED_RANGE_SWEEP),
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"\n  run = {args.threshold:g}x within {args.horizon_days:g} days\n",
          file=sys.stderr)
    header = (f"  {'range':>6} {'points':>8} {'base':>7} {'in flag':>9} "
              f"{'flag rate':>10} {'lift':>6} {'breakouts':>10} {'bo rate':>8}")
    print(header, file=sys.stderr)
    for key, r in results.items():
        base = r["unconditional_run_rate"] or 0
        flag_rate = r["run_rate_inside_a_flag"]
        bo_rate = r["run_rate_after_breakout"]
        lift = (flag_rate / base) if (flag_rate and base) else None
        print(f"  {key.split('_')[-1]:>6} {r['decision_points']:>8,} "
              f"{base:>6.1%} {r['points_inside_a_flag']:>9,} "
              f"{(f'{flag_rate:.1%}' if flag_rate is not None else 'n/a'):>10} "
              f"{(f'{lift:.2f}x' if lift else 'n/a'):>6} "
              f"{r['breakout_points']:>10,} "
              f"{(f'{bo_rate:.1%}' if bo_rate is not None else 'n/a'):>8}",
              file=sys.stderr)

    print(f"\n  token-level, at range {DECLARED_RANGE_SWEEP[1]:.2f}:", file=sys.stderr)
    mid = results[f"max_range_{DECLARED_RANGE_SWEEP[1]:.2f}"]
    print(f"    P(flag | ran) = {mid['p_flag_given_ran']}   "
          f"({mid['tokens_that_ran']} tokens ran)", file=sys.stderr)
    print(f"    P(ran | flag) = {mid['p_ran_given_flag']}   "
          f"({mid['tokens_with_a_flag']} tokens flagged)", file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
