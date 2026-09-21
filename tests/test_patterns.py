"""Flag detection — the shape module, and the two bugs found by hand.

This detector was written, pointed at HYPERHOOD (a textbook impulse, two-week
base, break to new highs), and **found nothing**. Twice. Both failures are
pinned here, because both are the kind that return a clean empty answer rather
than an error.

1. The impulse stopped at the first period clearing the threshold instead of at
   its peak. That left the blow-off candle inside the consolidation, and a
   blow-off candle's own range fails any flag test by itself.
2. Retracement was measured against the intraday spike high. A wick is a price
   the market touched and rejected, not a level it accepted. HH's base reads as
   a 66% retracement against its spike high and 33% against its closing high.

The negative cases matter as much: a detector that fires on any rise, or on a
gap in the data, would make every scan downstream meaningless.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.patterns import Candle, candles_from_prices, find_flags


# A breakout must make a NEW HIGH -- a close above the impulse's high, not a
# partial recovery toward it. The first version of the fixture broke out to 9.2
# under a spike of 11.0, which is not a breakout, and no coherent definition
# should have called it one.


def bar(index, low, high, close=None, open_=None, volume=1000.0):
    close = high if close is None else close
    open_ = low if open_ is None else open_
    return Candle(index=index, open=open_, high=high, low=low, close=close,
                  volume=volume)


def textbook():
    """Impulse to a spike, base well under the spike, then a break out."""
    candles = [bar(0, 1.0, 1.1, 1.05, volume=100)]
    # Impulse: three periods to 10x, peaking on a wick that closes lower.
    candles.append(bar(1, 1.0, 4.0, 3.8, volume=5000))
    candles.append(bar(2, 3.5, 8.0, 7.5, volume=8000))
    candles.append(bar(3, 6.0, 11.0, 7.0, volume=9000))   # blow-off wick
    # Base: five periods around 7, drying up.
    for i, close in enumerate([6.8, 7.2, 6.6, 7.1, 6.9], start=4):
        candles.append(bar(i, close * 0.93, close * 1.07, close, volume=900))
    # Breakout.
    candles.append(bar(9, 7.0, 12.5, 12.2, volume=4000))
    return candles


def test_textbook_flag_is_found():
    flags = find_flags(textbook())
    assert len(flags) == 1, flags
    flag = flags[0]
    assert flag.impulse_multiple >= 3.0
    assert flag.consolidation_periods >= 3
    assert flag.breakout_index == 9, flag.breakout_index
    assert flag.breakout_multiple > 1.0


def test_impulse_runs_to_its_peak_not_to_the_threshold():
    """Bug 1. The blow-off must end the impulse, not open the base."""
    flag = find_flags(textbook())[0]
    # Period 3 carries the highest high; the base starts after it.
    assert flag.impulse_end == 3, flag.impulse_end


def test_retracement_is_measured_against_closes():
    """Bug 2. A base under a rejected wick is still a base."""
    flag = find_flags(textbook())[0]
    # Spike high 11.0, closing high 7.5, base low ~6.1.
    # Against the wick that is ~45%; against closes it is ~18%.
    assert flag.retracement_pct < 0.35, flag.retracement_pct


def test_a_steady_grind_is_not_a_flag():
    # Up 10x over twenty periods with no impulse leg. A trend, not a flag.
    candles = [bar(i, 1.0 * 1.12**i, 1.05 * 1.12**i, 1.02 * 1.12**i)
               for i in range(20)]
    assert find_flags(candles) == []


def test_a_failed_flag_is_still_reported():
    """Flags that never broke out must be returned, not filtered.

    Keeping only the ones that worked is the selection that makes chart
    patterns look reliable, and it would corrupt P(ran | flag) directly.
    """
    candles = textbook()[:-1]                       # drop the breakout
    candles.append(bar(9, 6.4, 7.0, 6.5, volume=800))   # base continues instead
    flags = find_flags(candles)
    assert len(flags) == 1
    assert flags[0].breakout_index is None


def test_rising_volume_through_the_base_is_rejected():
    # A flag dries up. Volume climbing through the base is distribution.
    candles = textbook()[:4]
    for i, close in enumerate([6.8, 7.2, 6.6, 7.1, 6.9], start=4):
        candles.append(bar(i, close * 0.93, close * 1.07, close, volume=20000))
    candles.append(bar(9, 7.0, 12.5, 12.2, volume=40000))
    assert find_flags(candles) == []


def test_deep_retracement_is_rejected():
    # Gives back almost all of the impulse: the move failed.
    candles = textbook()[:4]
    for i, close in enumerate([1.6, 1.5, 1.7, 1.6, 1.55], start=4):
        candles.append(bar(i, close * 0.95, close * 1.05, close, volume=500))
    assert find_flags(candles) == []


def test_two_period_pause_is_not_a_base():
    candles = textbook()[:4]
    for i, close in enumerate([7.0, 6.9], start=4):
        candles.append(bar(i, close * 0.97, close * 1.03, close, volume=500))
    candles.append(bar(6, 7.0, 12.5, 12.2, volume=4000))
    assert find_flags(candles) == []


def test_gaps_are_not_filled_with_flat_candles():
    """A token that did not trade had no price.

    Forward-filling would invent exactly the tight, low-volume base a flag
    detector is looking for, out of silence.
    """
    observations = [(0, 1.0, 100.0), (10, 2.0, 100.0), (1_000_000, 3.0, 100.0)]
    candles = candles_from_prices(observations, period=100)
    # Two occupied buckets, not ten thousand.
    assert len(candles) == 2, len(candles)
    assert candles[0].high == 2.0 and candles[1].close == 3.0


def test_candles_aggregate_within_a_period():
    observations = [(0, 1.0, 10.0), (5, 3.0, 20.0), (9, 2.0, 30.0)]
    candle = candles_from_prices(observations, period=100)[0]
    assert candle.open == 1.0 and candle.high == 3.0
    assert candle.low == 1.0 and candle.close == 2.0 and candle.volume == 60.0


def test_empty_and_short_inputs():
    assert find_flags([]) == []
    assert find_flags([bar(0, 1.0, 2.0)]) == []
    assert candles_from_prices([], period=10) == []


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  pass  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {name}: {exc}")
    print(f"\n{failures} failures")
    raise SystemExit(1 if failures else 0)
