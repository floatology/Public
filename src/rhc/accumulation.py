"""Accumulation structures, and whether one is forming right now.

`rhc.patterns` detects a bull flag after the fact. That is the wrong shape of
tool for the question that matters, which is **"is a base forming?"** — asked of
a token that has not broken out yet, while there is still something to do about
it.

The named patterns differ in outline and agree almost completely on mechanics.
Reading across Wyckoff accumulation, Minervini's VCP, the Darvas box, cup and
handle, the flat base, the ascending triangle and the rounding bottom, every one
of them is built from the same four observations:

1. **Volatility contracts.** Each swing is smaller than the last. In a VCP this
   is the definition — pullbacks running roughly 18% → 12% → 6% across two to
   four contractions. In Wyckoff it is the trading range narrowing through
   Phase B into C.
2. **Volume dries up.** Supply is exhausting. Minervini wants volume lowest
   immediately before the pivot; Wyckoff's spring is explicitly a false break on
   *30–50% of average volume*; the cup's volume is lightest at its base.
3. **Support holds, flat or rising.** Flat in a Darvas box or flat base, rising
   in an ascending triangle or a Wyckoff LPS sequence of higher lows.
4. **Then volume expands on the break.** Minervini's threshold is roughly 40–50%
   above average. A breakout without it is the classic failure.

So the primary output here is not a pattern name. It is a continuous
`BaseState` measuring those four things as of the last candle, which is what a
scanner needs. The named classifiers sit on top and say which archetype the
shape most resembles — useful for describing a setup, not for detecting one.

**Why a score rather than a verdict.** These definitions were written for
equities on daily bars, over decades, by people who eyeballed them. Ported to a
chain where the median token trades for fifteen minutes, their thresholds have
no claim to authority. Every constant below is declared, in one place, and the
scanner reports the components alongside the score so a reader can disagree with
the weighting without re-running anything.

**Nothing here predicts anything.** A base that looks textbook is a base that
looks textbook. Whether that carries information on this chain is an empirical
question that needs `P(ran | base)` measured against the unconditional rate, and
that is the job of the scan scripts, not of this module.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict, field
from typing import Any, Sequence

from .patterns import Candle

# --- declared constants ----------------------------------------------------
# From the literature, not fitted to this chain. Changing them changes every
# number downstream, which is why they live here and are reported with results.
VOLUME_DRYUP_TARGET = 0.5      # Wyckoff spring volume, 30-50% of average
BREAKOUT_VOLUME_EXPANSION = 1.4  # Minervini: ~40-50% above average on the break
MIN_BASE_PERIODS = 5           # below this there is no structure to measure
TIGHT_RANGE = 0.15             # a "tight" final contraction, as a fraction
MAX_BASE_DEPTH = 0.50          # cup-and-handle tolerates 15-50% from the high
SWING_THRESHOLD = 0.015        # move needed to count as a new swing leg
# 1.5% rather than something coarser, because a VCP's defining feature is that
# its later pullbacks are SMALL -- a threshold above them is blind to exactly
# the part that carries the information. Measured on a textbook contraction
# (17.8% -> 8.0% -> 3.6% -> 1.8%) against a distribution series:
#
#   threshold   contraction sequence found        contractions counted
#   5.0%        [.178, .080]                      1   <- misses the tightening
#   3.0%        [.178, .080, .036]                2
#   1.5%        [.178, .080, .036, .018]          3   <- the whole sequence
#
# At 5% the distribution series scored MORE contractions than the VCP, which
# inverts the signal entirely. At 1.5% the distribution series shows pullbacks
# growing (8% -> 12% -> 14% -> 15% -> 17%), which is what it is doing.


@dataclass
class BaseState:
    """How base-like a token's recent action is, as of the last candle."""

    periods: int = 0
    # --- the four mechanics ---
    contraction_ratio: float | None = None   # last swing / first swing; <1 tightens
    contractions: int = 0                    # successively smaller pullbacks
    volume_dryup: float | None = None        # recent volume / base-average volume
    support_slope: float | None = None       # per-period drift of the swing lows
    range_pct: float | None = None           # high-low of the base, on closes
    depth_from_high: float | None = None     # how far below the base high price sits
    position_in_range: float | None = None   # 0 at the base low, 1 at its high

    # --- composite, deliberately transparent ---
    base_score: float | None = None
    is_forming: bool = False

    # --- breakout, if it has happened ---
    broke_out: bool = False
    breakout_volume_ratio: float | None = None
    breakout_confirmed: bool = False

    archetype: str = "none"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _swings(candles: Sequence[Candle], threshold: float = SWING_THRESHOLD
            ) -> list[tuple[int, float, str]]:
    """Alternating swing highs and lows, on closes, ignoring noise.

    A zig-zag rather than every local extreme: a pivot is only committed once
    price has retraced `threshold` against the current leg. Without that a noisy
    series yields a swing per candle and "contractions" becomes a candle count.

    The first version of this tangled its two direction branches, so a single
    candle could be recorded as both a high and a low, and the walk terminated
    early -- a twelve-period base reported swings over its first five periods
    and a rising support line came back negative.
    """
    closes = [c.close for c in candles]
    if len(closes) < 3:
        return []

    points: list[tuple[int, float, str]] = []
    direction: str | None = None
    extreme_index, extreme_price = 0, closes[0]

    for index in range(1, len(closes)):
        price = closes[index]
        if extreme_price <= 0:
            extreme_index, extreme_price = index, price
            continue
        change = (price - extreme_price) / extreme_price

        if direction is None:
            # Not yet trending: follow the extreme, and commit once a move
            # exceeds the threshold in either direction.
            if change >= threshold:
                points.append((extreme_index, extreme_price, "low"))
                direction = "up"
                extreme_index, extreme_price = index, price
            elif change <= -threshold:
                points.append((extreme_index, extreme_price, "high"))
                direction = "down"
                extreme_index, extreme_price = index, price
            elif price > extreme_price if change > 0 else price < extreme_price:
                extreme_index, extreme_price = index, price
        elif direction == "up":
            if price > extreme_price:
                extreme_index, extreme_price = index, price
            elif change <= -threshold:
                points.append((extreme_index, extreme_price, "high"))
                direction = "down"
                extreme_index, extreme_price = index, price
        else:  # direction == "down"
            if price < extreme_price:
                extreme_index, extreme_price = index, price
            elif change >= threshold:
                points.append((extreme_index, extreme_price, "low"))
                direction = "up"
                extreme_index, extreme_price = index, price

    # The unconfirmed final leg still describes where price currently sits.
    if direction is not None:
        points.append((extreme_index, extreme_price,
                       "high" if direction == "up" else "low"))
    return points


def _pullbacks(swings: Sequence[tuple[int, float, str]]) -> list[float]:
    """Each high-to-low decline, as a fraction. The VCP's raw material."""
    out: list[float] = []
    for (i_a, price_a, kind_a), (i_b, price_b, kind_b) in zip(swings, swings[1:]):
        if kind_a == "high" and kind_b == "low" and price_a > 0:
            out.append((price_a - price_b) / price_a)
    return out


def analyse(
    candles: Sequence[Candle],
    *,
    lookback: int = 30,
    min_periods: int = MIN_BASE_PERIODS,
    volume_dryup_target: float = VOLUME_DRYUP_TARGET,
    breakout_expansion: float = BREAKOUT_VOLUME_EXPANSION,
) -> BaseState:
    """Measure the base as of the final candle.

    Args:
        lookback: how many periods form the base under examination. A base is a
            recent structure; measuring over a token's whole life would let an
            ancient consolidation dominate.
    """
    state = BaseState()
    window = list(candles[-lookback:])
    state.periods = len(window)
    if len(window) < min_periods:
        state.notes.append(f"only {len(window)} periods; need {min_periods}")
        return state

    closes = [c.close for c in window]
    volumes = [c.volume for c in window]
    high, low = max(closes), min(closes)
    if high <= 0:
        state.notes.append("no positive prices")
        return state

    mid = (high + low) / 2
    state.range_pct = (high - low) / mid if mid > 0 else None
    state.depth_from_high = (high - closes[-1]) / high
    state.position_in_range = (closes[-1] - low) / (high - low) if high > low else None

    # --- 1. volatility contraction ---
    swings = _swings(window)
    pullbacks = _pullbacks(swings)
    if len(pullbacks) >= 2:
        state.contraction_ratio = (
            pullbacks[-1] / pullbacks[0] if pullbacks[0] > 0 else None
        )
        state.contractions = sum(
            1 for a, b in zip(pullbacks, pullbacks[1:]) if b < a
        )
    elif len(pullbacks) == 1:
        state.contractions = 0

    # --- 2. volume dry-up ---
    # Recent third against the whole base. Wyckoff and Minervini both want the
    # quietest volume immediately before the move.
    tail = max(2, len(volumes) // 3)
    base_volume = statistics.fmean(volumes)
    recent_volume = statistics.fmean(volumes[-tail:])
    if base_volume > 0:
        state.volume_dryup = recent_volume / base_volume

    # --- 3. support structure ---
    lows = [(i, p) for i, p, kind in swings if kind == "low"]
    if len(lows) >= 2:
        first_i, first_p = lows[0]
        last_i, last_p = lows[-1]
        if last_i > first_i and first_p > 0:
            state.support_slope = ((last_p - first_p) / first_p) / (last_i - first_i)

    # --- 4. breakout and its volume ---
    prior_high = max(closes[:-1]) if len(closes) > 1 else high
    if closes[-1] > prior_high:
        state.broke_out = True
        prior_volume = statistics.fmean(volumes[:-1]) if len(volumes) > 1 else 0.0
        if prior_volume > 0:
            state.breakout_volume_ratio = volumes[-1] / prior_volume
            state.breakout_confirmed = (
                state.breakout_volume_ratio >= breakout_expansion
            )
            if not state.breakout_confirmed:
                state.notes.append(
                    f"broke out on {state.breakout_volume_ratio:.2f}x volume; "
                    f"{breakout_expansion:g}x is the conventional threshold"
                )

    # --- composite ---
    # Four components, equal weight, each clipped to [0, 1]. Equal weight
    # because there is no calibration set on this chain to fit anything else,
    # and a fitted weighting would look like evidence.
    components: dict[str, float] = {}
    if state.contraction_ratio is not None:
        components["contraction"] = max(0.0, min(1.0, 1.0 - state.contraction_ratio))
    if state.volume_dryup is not None:
        # 1.0 when volume has fallen to the target share of the base average.
        components["volume"] = max(0.0, min(
            1.0, (1.0 - state.volume_dryup) / (1.0 - volume_dryup_target)
        ))
    if state.support_slope is not None:
        # Flat or rising support scores; falling support does not.
        components["support"] = 1.0 if state.support_slope >= -0.002 else 0.0
    if state.range_pct is not None:
        components["tightness"] = max(0.0, min(1.0, 1.0 - state.range_pct))
    if components:
        state.base_score = sum(components.values()) / len(components)

    state.is_forming = bool(
        state.base_score is not None
        and state.base_score >= 0.5
        and not state.broke_out
        and (state.depth_from_high or 0.0) <= MAX_BASE_DEPTH
    )
    state.archetype = classify(state)
    return state


def classify(state: BaseState) -> str:
    """Which archetype the measured shape most resembles.

    Descriptive only. Two analysts will name the same chart differently, and the
    numbers in `BaseState` are the part worth trusting.
    """
    if state.periods < MIN_BASE_PERIODS or state.range_pct is None:
        return "none"
    tight = state.range_pct <= TIGHT_RANGE
    rising = (state.support_slope or 0.0) > 0.002
    flat = abs(state.support_slope or 0.0) <= 0.002
    contracting = state.contractions >= 2

    # Falling support is checked FIRST. A series making lower lows produces
    # successively smaller pullbacks on its way down and was being classified
    # as a VCP -- a distribution pattern wearing an accumulation label, which
    # is the most expensive mistake this module could make.
    if (state.support_slope or 0.0) < -0.002:
        return "descending"        # supply still in control
    if contracting and (state.contraction_ratio or 1.0) < 0.6:
        return "vcp"               # successively smaller pullbacks
    if tight and flat:
        return "flat_base"         # Darvas box / flat base
    if rising and not tight:
        return "ascending_triangle"
    if flat and not tight:
        return "rectangle"
    return "unclassified"
