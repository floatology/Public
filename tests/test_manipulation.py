"""Detector tests. The negative cases matter more than the positive ones.

A detector that fires on a bundle is easy. A detector that stays silent on
twenty ordinary traders is the thing that decides whether the feature carries
information or just tracks pool activity.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.features import Trade
from rhc.manipulation import detect


def trade(block, wallet, is_buy, quote, base=10**18, index=0):
    return Trade(block=block, wallet=wallet, is_buy=is_buy,
                 quote_amount=quote, base_amount=base, log_index=index)


def test_bundle_detected():
    # Eight wallets, one block, the same amount to the wei.
    trades = [trade(100, f"0x{i:040x}", True, 5 * 10**17, index=i) for i in range(8)]
    trades += [trade(100 + 50 * i, f"0xf{i:039x}", True, random.randint(10**16, 10**18))
               for i in range(1, 30)]
    sig = detect(trades)
    assert sig.is_bundled, sig
    assert sig.bundle_max_buyers_in_block == 8, sig.bundle_max_buyers_in_block
    assert sig.bundle_size_uniformity == 1.0, sig.bundle_size_uniformity


def test_organic_launch_not_bundled():
    # The same width -- eight wallets in the launch block -- but each chose its
    # own size. This is what an anticipated launch looks like and it must not
    # read as bundling.
    rng = random.Random(7)
    trades = [trade(100, f"0x{i:040x}", True, rng.randint(10**16, 2 * 10**18), index=i)
              for i in range(8)]
    sig = detect(trades)
    assert sig.bundle_max_buyers_in_block == 8
    assert not sig.is_bundled, sig.bundle_size_uniformity


def test_bundle_after_launch_ignored():
    # Same uniform block, but 5,000 blocks in. There is no supply left to
    # front-run, so this is not the thing 7.1 is about.
    trades = [trade(50, "0xaa", True, 3 * 10**17)]
    trades += [trade(5000, f"0x{i:040x}", True, 5 * 10**17, index=i) for i in range(8)]
    sig = detect(trades)
    assert sig.bundle_block_count == 0, sig
    assert not sig.is_bundled


def test_bump_bot_detected():
    rng = random.Random(3)
    # One wallet, 40 alternating trades, identical size, even 60-block cadence.
    bot = []
    for i in range(40):
        bot.append(trade(1000 + i * 60, "0xb0t", i % 2 == 0, 10**15, index=i))
    # Real traffic around it, far larger and irregular.
    noise = [trade(1000 + rng.randint(0, 2400), f"0x{i:040x}",
                   rng.random() < 0.5, rng.randint(10**17, 10**19), index=i)
             for i in range(60)]
    sig = detect(bot + noise)
    assert sig.has_bump_bot, sig
    assert sig.bump_wallet_count == 1, sig.bump_wallet_count
    assert sig.max_bump_score > 0.9, sig.max_bump_score


def test_active_trader_is_not_a_bump_bot():
    # 40 trades from one wallet, but sizes vary, timing is irregular, and it
    # ends up net long. An active trader, not a metronome.
    rng = random.Random(11)
    trades = [trade(1000 + rng.randint(0, 3000), "0xtrader",
                    rng.random() < 0.75, rng.randint(10**17, 10**19), index=i)
              for i in range(40)]
    sig = detect(trades)
    assert not sig.has_bump_bot, (sig.max_bump_score, sig.bump_wallet_count)


def test_flat_but_irregular_is_not_a_bump_bot():
    # Net-flat and small, but the timing and sizes are noisy. Flatness alone
    # must not be enough, or every scalper reads as a bot.
    rng = random.Random(5)
    trades = []
    for i in range(30):
        size = rng.randint(10**14, 10**16)
        block = 1000 + rng.randint(0, 5000)
        trades.append(trade(block, "0xscalp", i % 2 == 0, size, index=i))
    sig = detect(trades)
    assert not sig.has_bump_bot, (sig.max_bump_score,)


def test_empty_and_tiny_inputs():
    assert detect([]).bundle_block_count == 0
    one = detect([trade(1, "0xa", True, 10**18)])
    assert one.bundle_max_buyers_in_block == 0
    assert not one.has_bump_bot
    assert one.repeated_amount_share == 0.0


def test_repeated_amounts():
    trades = [trade(100 + i, f"0x{i:040x}", True, 10**17, index=i) for i in range(6)]
    trades += [trade(200 + i, f"0xe{i:039x}", True, 10**17 + i + 1, index=i) for i in range(4)]
    sig = detect(trades)
    assert sig.modal_amount_count == 6, sig.modal_amount_count
    assert abs(sig.repeated_amount_share - 0.6) < 1e-9, sig.repeated_amount_share


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
