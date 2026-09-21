"""The outcome definition, which everything else is fitted against.

`peak_over_launch` is the price of a single trade. In a thin pool that trade can
be three dollars of dust, and a 10x nobody could sell into is not a 10x --
using it as the label teaches a model to find tokens that print a number rather
than tokens that pay. These tests are the counterexample: two tokens that reach
identical peaks, one on real volume and one on a rounding error, must not look
the same.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.features import Trade, compute


def tr(block, wallet, is_buy, quote, base, index=0):
    return Trade(block=block, wallet=wallet, is_buy=is_buy, quote_amount=quote,
                 base_amount=base, log_index=index)


def build(trades):
    return compute(pool="0xp", quote_asset="0xq", created_block=0,
                   trades=trades, syncs=[], head_block=100_000)


def at_price(block, price, quote, index=0, is_buy=True):
    """A trade at a chosen price, sized in quote units."""
    return tr(block, f"0xw{index}", is_buy, quote, int(quote / price), index)


def real_run():
    # Launches near 1.0, then a large amount of volume trades up at 10x.
    trades = [at_price(10 + i, 1.0, 10**18, i) for i in range(5)]
    trades += [at_price(100 + i, 10.0, 10**18, 10 + i) for i in range(20)]
    return build(trades)


def dust_spike():
    # Identical launch, identical peak price, but the 10x is one tiny trade.
    trades = [at_price(10 + i, 1.0, 10**18, i) for i in range(5)]
    trades += [at_price(100 + i, 1.05, 10**18, 10 + i) for i in range(20)]
    trades.append(at_price(200, 10.0, 10**12, 99))
    return build(trades)


def test_naive_peak_cannot_tell_them_apart():
    # The premise. Both look like a 10x on the existing label.
    assert abs(real_run().peak_over_launch - 10.0) < 0.01
    assert abs(dust_spike().peak_over_launch - 10.0) < 0.01


def test_realisable_peak_separates_them():
    assert abs(real_run().realisable_peak_over_launch - 10.0) < 0.01
    # The dust spike's realisable peak is where real volume actually traded.
    assert dust_spike().realisable_peak_over_launch < 1.2, (
        dust_spike().realisable_peak_over_launch
    )


def test_volume_share_at_the_peak_exposes_the_spike():
    assert real_run().peak_trade_volume_share > 0.7
    assert dust_spike().peak_trade_volume_share < 1e-5, (
        dust_spike().peak_trade_volume_share
    )


def test_volume_above_multiples():
    real = real_run()
    # Twenty of twenty-five trades happened at 10x, and they carry the volume.
    assert real.volume_above_10x_share > 0.7
    assert real.volume_above_2x_share > 0.7
    dust = dust_spike()
    assert dust.volume_above_10x_share < 1e-5
    assert dust.volume_above_2x_share < 1e-5


def test_degenerate_inputs():
    empty = build([])
    assert empty.realisable_peak_over_launch is None
    assert empty.peak_trade_volume_share is None
    one = build([at_price(1, 2.0, 10**18)])
    # A single trade is its own launch price and its own peak: exactly 1x, not
    # a win and not undefined.
    assert abs(one.realisable_peak_over_launch - 1.0) < 1e-9
    assert one.peak_trade_volume_share == 1.0


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
