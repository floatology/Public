"""Base-state detection — catalogue of accumulation mechanics.

The four things every accumulation archetype agrees on: volatility contracts,
volume dries up, support holds flat or rises, and the break comes on expanding
volume. These tests check each one moves in the right direction, and -- more
importantly -- that a *distribution* pattern does not score as accumulation.

The failure that matters is a false positive. A scanner that calls every quiet
stretch a base is worse than no scanner, because quiet is the normal state of a
dying token and there are hundreds of thousands of those here.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.accumulation import analyse, classify
from rhc.patterns import Candle


def bar(i, close, volume=1000.0, width=0.02):
    return Candle(index=i, open=close, high=close * (1 + width),
                  low=close * (1 - width), close=close, volume=volume)


def vcp():
    """Three successively smaller pullbacks on falling volume."""
    path = [100, 118, 97, 112, 103, 110, 106, 109, 107, 108.5, 107.5, 108]
    volumes = [5000, 4500, 3800, 3200, 2600, 2100, 1700, 1400, 1100, 900, 800, 700]
    return [bar(i, p, v) for i, (p, v) in enumerate(zip(path, volumes))]


def descending():
    """Lower highs AND lower lows on rising volume: distribution."""
    path = [100, 92, 96, 84, 88, 76, 80, 68, 72, 60, 64, 55]
    volumes = [1000, 1400, 1600, 2000, 2400, 2900, 3300, 3900, 4400, 5000, 5600, 6200]
    return [bar(i, p, v) for i, (p, v) in enumerate(zip(path, volumes))]


def test_vcp_scores_as_a_forming_base():
    state = analyse(vcp())
    assert state.base_score is not None and state.base_score >= 0.5, state.base_score
    assert state.is_forming, state.to_dict()
    assert state.contractions >= 2, state.contractions
    assert state.contraction_ratio is not None and state.contraction_ratio < 1.0


def test_volume_dryup_is_detected():
    state = analyse(vcp())
    assert state.volume_dryup is not None and state.volume_dryup < 0.6, state.volume_dryup


def test_distribution_does_not_score_as_accumulation():
    """The false positive that would matter."""
    state = analyse(descending())
    assert not state.is_forming, state.to_dict()
    assert state.archetype == "descending", state.archetype
    assert (state.support_slope or 0) < 0


def test_rising_volume_through_the_base_hurts_the_score():
    quiet = analyse(vcp())
    noisy_path = [c.close for c in vcp()]
    rising = [bar(i, p, 700 + i * 500) for i, p in enumerate(noisy_path)]
    assert analyse(rising).base_score < quiet.base_score


def test_breakout_needs_volume_to_be_confirmed():
    base = vcp()
    thin = base + [bar(len(base), 125, 700)]       # new high, no volume
    heavy = base + [bar(len(base), 125, 9000)]     # new high, volume expands
    thin_state, heavy_state = analyse(thin), analyse(heavy)
    assert thin_state.broke_out and heavy_state.broke_out
    assert not thin_state.breakout_confirmed, thin_state.breakout_volume_ratio
    assert heavy_state.breakout_confirmed, heavy_state.breakout_volume_ratio
    assert any("conventional threshold" in n for n in thin_state.notes)


def test_a_broken_out_token_is_no_longer_forming():
    # The scanner's job is to flag bases BEFORE the move, so a token that has
    # already broken must stop appearing as one that is setting up.
    base = vcp()
    after = base + [bar(len(base), 125, 9000)]
    assert analyse(base).is_forming
    assert not analyse(after).is_forming


def test_flat_base_is_classified():
    flat = [bar(i, 100 + (i % 3) - 1, 1000 - i * 40) for i in range(14)]
    state = analyse(flat)
    assert state.range_pct is not None and state.range_pct < 0.15
    assert state.archetype in ("flat_base", "vcp"), state.archetype


def test_deep_drawdown_is_not_a_forming_base():
    # Price 70% below the base high is not consolidating, whatever the volume
    # is doing.
    path = [100, 95, 90, 60, 40, 32, 30, 29, 28.5, 28]
    candles = [bar(i, p, 900 - i * 50) for i, p in enumerate(path)]
    assert not analyse(candles).is_forming


def test_too_few_periods_reports_why():
    state = analyse([bar(0, 100), bar(1, 101)])
    assert not state.is_forming
    assert state.base_score is None
    assert any("need" in n for n in state.notes)


def test_lookback_limits_the_window():
    # An ancient base must not dominate a token's current state.
    ancient = vcp()
    recent = [bar(i + len(ancient), 100 - i * 4, 2000 + i * 300) for i in range(12)]
    state = analyse(ancient + recent, lookback=12)
    assert state.periods == 12
    assert not state.is_forming


def test_classify_handles_empty_state():
    from rhc.accumulation import BaseState
    assert classify(BaseState()) == "none"


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
