"""Velocity and time-shape features — catalogue 3.5 and 3.6.

These are shape, not level. Two tokens with identical total volume can differ
entirely in whether it arrived in the first minute or accumulated over a week,
and only the shape tells them apart. The test is therefore a discrimination
test: a front-loaded launch and a steadily-traded token must come out at
opposite ends of every one of these columns, or the columns are not measuring
what they claim to.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.features import Trade, compute

HOUR = 36_000


def tr(block, wallet, is_buy, quote, index=0):
    return Trade(block=block, wallet=wallet, is_buy=is_buy, quote_amount=quote,
                 base_amount=10**18, log_index=index)


def front_loaded():
    trades = [tr(i, f"0x{i:040x}", True, 10**18, i) for i in range(20)]
    trades += [tr(200_000 + i * 5000, f"0xz{i:039x}", False, 10**15, i) for i in range(5)]
    return compute(pool="0xp", quote_asset="0xq", created_block=0,
                   trades=trades, syncs=[], head_block=400_000)


def steady():
    trades = [tr(i * 1200, f"0x{i:040x}", i % 2 == 0, 10**18, i) for i in range(180)]
    return compute(pool="0xp", quote_asset="0xq", created_block=0,
                   trades=trades, syncs=[], head_block=400_000)


def test_front_loaded_and_steady_separate():
    a, b = front_loaded(), steady()
    assert a.first_hour_volume_share > 0.99 and b.first_hour_volume_share < 0.25
    assert a.peak_hour_volume_share > 0.99 and b.peak_hour_volume_share < 0.25
    # Half the front-loaded token's volume had traded within the first
    # hundredth of a percent of its life.
    assert a.time_to_half_volume_frac < 1e-3
    assert 0.4 < b.time_to_half_volume_frac < 0.6
    assert a.quiet_hour_share > 0.5 and b.quiet_hour_share == 0.0


def test_acceleration_direction():
    # The front-loaded token slows down; the steady one does not change pace.
    assert front_loaded().trade_acceleration < 1.0
    assert steady().trade_acceleration == 1.0


def test_buy_share_rotation_catches_the_turn():
    # All buys early, all sells late: the crowd turned completely.
    assert front_loaded().buy_share_rotation == -1.0
    assert steady().buy_share_rotation == 0.0


def test_single_trade_invents_no_shape():
    # A token with one trade has no time shape. Returning zeros here would give
    # a model a value to fit where there is no measurement.
    only = compute(pool="0xp", quote_asset="0xq", created_block=0,
                   trades=[tr(5, "0xa", True, 10**18)], syncs=[], head_block=100)
    assert only.trade_acceleration is None
    assert only.quiet_hour_share is None
    assert only.time_to_half_volume_frac is None
    assert only.first_hour_trade_count == 1


def test_no_trades_is_safe():
    empty = compute(pool="0xp", quote_asset="0xq", created_block=0,
                    trades=[], syncs=[], head_block=100)
    assert empty.first_hour_trade_count == 0
    assert empty.peak_hour_volume_share is None


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
