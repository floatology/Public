"""Price-shape detection: impulse, consolidation, breakout.

A domain nothing else here covers. Every other module measures flow, wallets,
liquidity or manipulation; none of them look at the *shape* of the price path,
which is what a human means by "that looked like a bull flag".

**The thresholds below are declared, not fitted.** There is no labelled set of
flags on this chain, and tuning them until the answer looks good is how a chart
pattern becomes a story. They are written here, in one place, before being
measured against anything, and every number a scan reports is conditional on
them. Changing them changes the answer and that should be visible.

**The two questions this can answer are not the same question, and the
interesting one is the harder one.**

*Among tokens that ran, how many showed a flag first?* — cheap, and close to
useless. It conditions on the outcome. Almost any pattern is common among
winners if winners mostly go up in steps.

*Among tokens that showed a flag, how many then ran?* — the tradeable question,
and it is answered by a base rate that is easy to never compute, because the
flags that failed are the ones nobody remembers seeing. A pattern is only worth
anything if the second number beats the unconditional base rate.

`scan` returns both, which is the point.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class Candle:
    """One period of price action."""

    index: int          # period number, 0-based
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class FlagPattern:
    """An impulse followed by a consolidation, and whether it broke out."""

    impulse_start: int
    impulse_end: int
    impulse_multiple: float
    consolidation_end: int
    consolidation_periods: int
    consolidation_range_pct: float
    retracement_pct: float
    volume_decay: float          # consolidation mean volume / impulse mean volume
    breakout_index: int | None   # first period closing above the flag high
    breakout_multiple: float | None  # that close / flag high

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- declared thresholds ---------------------------------------------------
# Chosen to describe the shape people mean, not tuned against outcomes.
MIN_IMPULSE_MULTIPLE = 3.0      # the leg up that makes a flag a flag
MAX_IMPULSE_PERIODS = 5         # a slow grind is a trend, not an impulse
MIN_CONSOLIDATION_PERIODS = 3   # two periods is a pause, not a base
MAX_CONSOLIDATION_RANGE = 0.60  # high/low spread across the flag, as a fraction
MAX_RETRACEMENT = 0.60          # give back more than this and the impulse failed
MAX_VOLUME_DECAY = 1.0          # a flag dries up; rising volume is distribution
BREAKOUT_BUFFER = 0.02          # how far above the base a close must go to end it


def find_flags(
    candles: Sequence[Candle],
    *,
    min_impulse: float = MIN_IMPULSE_MULTIPLE,
    max_impulse_periods: int = MAX_IMPULSE_PERIODS,
    min_consolidation: int = MIN_CONSOLIDATION_PERIODS,
    max_range: float = MAX_CONSOLIDATION_RANGE,
    max_retracement: float = MAX_RETRACEMENT,
    max_volume_decay: float = MAX_VOLUME_DECAY,
    breakout_buffer: float = BREAKOUT_BUFFER,
) -> list[FlagPattern]:
    """Every impulse-then-consolidation in a series, breakout or not.

    Patterns that never broke out are returned with `breakout_index = None`.
    Dropping them would leave only the flags that worked, which is precisely
    the selection that makes chart patterns look reliable.
    """
    if len(candles) < 2 + min_consolidation:
        return []

    found: list[FlagPattern] = []
    used_through = -1

    for start in range(len(candles) - min_consolidation - 1):
        if start <= used_through:
            continue
        base = candles[start].low
        if base <= 0:
            continue

        # --- the impulse: a fast leg up ---
        # The impulse runs to its PEAK, not to the first period that clears the
        # threshold. Stopping early puts the blow-off candle inside the
        # consolidation, and a blow-off candle's own range is wide enough to
        # fail any flag test on its own -- which is how the first version of
        # this found zero flags in a textbook one.
        reached = None
        for end in range(start + 1, min(start + max_impulse_periods + 1, len(candles))):
            if max(c.high for c in candles[start:end + 1]) / base >= min_impulse:
                reached = end
                break
        if reached is None:
            continue
        limit = min(start + max_impulse_periods, len(candles) - 1)
        best_end = max(
            range(reached, limit + 1),
            key=lambda i: candles[i].high,
        )

        # Magnitude is reported from the wick -- the move really did reach
        # there -- but every STRUCTURAL test below uses closes. A wick is a
        # price the market touched and rejected, not a level it accepted, and
        # measuring a pullback against a blow-off wick fails flags that
        # obviously worked: HH's two-week base reads as a 66% retracement
        # against its spike high and 33% against its closing high.
        impulse_high = max(c.high for c in candles[start:best_end + 1])
        impulse_multiple = impulse_high / base
        impulse_close_high = max(c.close for c in candles[start:best_end + 1])
        impulse_volume = statistics.fmean(
            [c.volume for c in candles[start:best_end + 1]]
        ) or 0.0

        # --- the consolidation: extend while it stays a flag ---
        # The flag's tightness is measured on CLOSES, not on wicks. A base is
        # about where price settles; a single long wick through it does not end
        # the consolidation, and testing highs against lows makes any volatile
        # token fail by construction. The retracement test still uses lows,
        # because a wick that deep really did give the move back.
        flag_end = best_end
        for probe in range(best_end + 1, len(candles)):
            span = candles[best_end + 1:probe + 1]
            closes = [c.close for c in span]
            # A base must not swallow its own breakout. Consolidation happens
            # BELOW the level the impulse reached -- that is what makes it
            # consolidation -- so a close above that resistance is the break,
            # not more base. Using the impulse's closing high as the ceiling is
            # principled; using a fixed percentage above the base's own high
            # would just be a tuned number, and a base that drifted up gently
            # would end on noise.
            if closes[-1] > impulse_high * (1.0 + breakout_buffer):
                break
            high, low = max(closes), min(closes)
            mid = (high + low) / 2
            if mid <= 0:
                break
            if (high - low) / mid > max_range:
                break
            if (impulse_close_high - low) / impulse_close_high > max_retracement:
                break
            flag_end = probe

        periods = flag_end - best_end
        if periods < min_consolidation:
            continue

        span = candles[best_end + 1:flag_end + 1]
        # Breakout is judged against the closing high of the base, consistent
        # with how the base was measured.
        flag_high = max(c.close for c in span)
        flag_low = min(c.close for c in span)
        mid = (flag_high + flag_low) / 2
        flag_volume = statistics.fmean([c.volume for c in span]) or 0.0
        decay = (flag_volume / impulse_volume) if impulse_volume > 0 else float("inf")
        if decay > max_volume_decay:
            continue  # volume rising through the base is distribution, not a flag

        # --- the breakout: first close above the flag's high ---
        breakout_index = breakout_multiple = None
        for probe in range(flag_end + 1, len(candles)):
            if candles[probe].close > flag_high:
                breakout_index = probe
                breakout_multiple = candles[probe].close / flag_high
                break

        found.append(FlagPattern(
            impulse_start=start,
            impulse_end=best_end,
            impulse_multiple=impulse_multiple,
            consolidation_end=flag_end,
            consolidation_periods=periods,
            consolidation_range_pct=(flag_high - flag_low) / mid,
            retracement_pct=(impulse_close_high - flag_low) / impulse_close_high,
            volume_decay=decay,
            breakout_index=breakout_index,
            breakout_multiple=breakout_multiple,
        ))
        # Do not restart inside a pattern already described.
        used_through = flag_end

    return found


def candles_from_prices(
    observations: Iterable[tuple[int, float, float]], *, period: int
) -> list[Candle]:
    """Bucket (block, price, volume) observations into fixed-width candles.

    Empty periods are skipped rather than forward-filled. A token that did not
    trade for a week did not hold its price for a week -- it had no price -- and
    inventing flat candles would manufacture exactly the tight consolidation a
    flag detector looks for.
    """
    buckets: dict[int, list[tuple[float, float]]] = {}
    order: list[int] = []
    for block, price, volume in observations:
        if price <= 0:
            continue
        slot = block // period
        if slot not in buckets:
            buckets[slot] = []
            order.append(slot)
        buckets[slot].append((price, volume))

    out: list[Candle] = []
    for index, slot in enumerate(sorted(order)):
        prices = [p for p, _ in buckets[slot]]
        out.append(Candle(
            index=index,
            open=prices[0], high=max(prices), low=min(prices), close=prices[-1],
            volume=sum(v for _, v in buckets[slot]),
        ))
    return out
