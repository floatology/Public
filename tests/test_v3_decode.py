"""Uniswap V3 swap decoding — the population the extraction was missing.

Measured from the census and the live activity snapshot: **63% of pool
creations on this chain are V3** (447,343 against 268,151), and V3 pools carry
**74% of daily volume** at a median reserve of $1.1M against $59k for V2. The
feature extraction filtered to V2, which means it was studying the shallow
third of the chain — the part where the measured $50k execution floor bites
hardest and where nothing found could be traded anyway.

The decode has one trap and it is the expensive kind. V3 reports amounts as
**int256**: positive into the pool, negative out. Read as unsigned, an outflow
of one token becomes a number near 2^256, every price derived from it is
nonsense, and nothing in the output says so. That is the same class of error
that produced a median price ratio of 22,668x when token ordering was assumed
rather than read.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.features import decode_v3_depth, decode_v3_swaps

TRADER = "0x" + "ab" * 20


def word(value: int) -> str:
    """Encode a signed integer as a 256-bit two's-complement word."""
    return f"{value & ((1 << 256) - 1):064x}"


def swap(block: int, amount0: int, amount1: int, index: int = 0,
         recipient: str = TRADER, sqrt_price_x96: int | None = None,
         liquidity: int = 10**18) -> dict:
    data = ("0x" + word(amount0) + word(amount1)
            + word(2**96 if sqrt_price_x96 is None else sqrt_price_x96)
            + word(liquidity) + word(0))
    return {
        "blockNumber": hex(block),
        "logIndex": hex(index),
        "topics": ["0xc42079f9", "0x" + "0" * 24 + "cd" * 20,
                   "0x" + "0" * 24 + recipient[2:]],
        "data": data,
    }


def test_buy_is_quote_in_base_out():
    # token0 is the quote. +3 quote into the pool, -1 base out: a buy.
    trades = decode_v3_swaps([swap(10, 3 * 10**18, -1 * 10**18)],
                             quote_is_token0=True)
    assert len(trades) == 1
    trade = trades[0]
    assert trade.is_buy
    assert trade.quote_amount == 3 * 10**18
    assert trade.base_amount == 1 * 10**18
    assert trade.price == 3.0
    assert trade.wallet == TRADER
    assert trade.block == 10


def test_sell_is_base_in_quote_out():
    trades = decode_v3_swaps([swap(11, -3 * 10**18, 1 * 10**18)],
                             quote_is_token0=True)
    assert len(trades) == 1
    assert not trades[0].is_buy
    assert trades[0].quote_amount == 3 * 10**18
    assert trades[0].base_amount == 1 * 10**18


def test_token_ordering_is_respected():
    # Identical log, quote on the other side: the same swap is now a sell.
    log = swap(12, 3 * 10**18, -1 * 10**18)
    as_token0 = decode_v3_swaps([log], quote_is_token0=True)[0]
    as_token1 = decode_v3_swaps([log], quote_is_token0=False)[0]
    assert as_token0.is_buy and not as_token1.is_buy
    assert as_token0.quote_amount == 3 * 10**18
    assert as_token1.quote_amount == 1 * 10**18


def test_negative_amounts_are_not_read_as_huge_positives():
    """The trap. An unsigned read turns -1 into 2^256 - 1."""
    trades = decode_v3_swaps([swap(13, 5 * 10**18, -2 * 10**18)],
                             quote_is_token0=True)
    assert trades[0].base_amount == 2 * 10**18
    assert trades[0].base_amount < 2**64, "amount read as unsigned"
    assert 0 < trades[0].price < 100


def test_same_sign_on_both_sides_is_rejected():
    # Both positive or both negative is not a swap in either direction.
    assert decode_v3_swaps([swap(14, 10**18, 10**18)], quote_is_token0=True) == []
    assert decode_v3_swaps([swap(15, -10**18, -10**18)], quote_is_token0=True) == []


def test_zero_side_is_rejected():
    assert decode_v3_swaps([swap(16, 0, -10**18)], quote_is_token0=True) == []
    assert decode_v3_swaps([swap(17, 10**18, 0)], quote_is_token0=True) == []


def test_short_data_is_skipped_not_fatal():
    bad = swap(18, 10**18, -10**18)
    bad["data"] = "0x" + "00" * 32          # one word, not five
    good = swap(19, 2 * 10**18, -10**18, index=1)
    trades = decode_v3_swaps([bad, good], quote_is_token0=True)
    assert len(trades) == 1 and trades[0].block == 19


def test_missing_topics_leaves_wallet_empty_not_crashing():
    log = swap(20, 10**18, -10**18)
    log["topics"] = ["0xc42079f9"]
    trades = decode_v3_swaps([log], quote_is_token0=True)
    assert len(trades) == 1 and trades[0].wallet == ""


# ---------------------------------------------------------------------------
# Depth (catalogue 4.1 for V3)
# ---------------------------------------------------------------------------


def test_depth_scales_with_liquidity():
    """Twice the active liquidity is twice the cost of the same price move."""
    thin = decode_v3_depth([swap(10, 10**18, -10**18, liquidity=10**18)],
                           quote_is_token0=False)
    deep = decode_v3_depth([swap(10, 10**18, -10**18, liquidity=2 * 10**18)],
                           quote_is_token0=False)
    assert len(thin) == len(deep) == 1
    assert abs(deep[0][1] / thin[0][1] - 2.0) < 1e-9


def test_depth_matches_the_closed_form():
    # sqrtPriceX96 = 2^96 means price 1.0, so sqrt(P) = 1 and the quote needed
    # to move 1% is L * (sqrt(1.01) - 1).
    liquidity = 10**18
    got = decode_v3_depth([swap(10, 10**18, -10**18, liquidity=liquidity)],
                          quote_is_token0=False)[0][1]
    expected = liquidity * (1.01**0.5 - 1.0)
    assert abs(got - expected) / expected < 1e-12, (got, expected)


def test_depth_respects_which_side_is_quote():
    # At price 4.0 (sqrtP = 2), the two sides cost different amounts to move.
    sqrt_price_x96 = 2 * (2**96)
    log = swap(10, 10**18, -10**18, sqrt_price_x96=sqrt_price_x96)
    as_token1 = decode_v3_depth([log], quote_is_token0=False)[0][1]
    as_token0 = decode_v3_depth([log], quote_is_token0=True)[0][1]
    liquidity = 10**18
    assert abs(as_token1 - liquidity * 2.0 * (1.01**0.5 - 1)) / as_token1 < 1e-12
    assert abs(as_token0 - liquidity * 0.5 * (1 - 1 / 1.01**0.5)) / as_token0 < 1e-12
    # Quoting in the more valuable token costs fewer units for the same move.
    assert as_token0 < as_token1


def test_depth_move_size_is_a_parameter():
    log = swap(10, 10**18, -10**18)
    one = decode_v3_depth([log], quote_is_token0=False, move=0.01)[0][1]
    ten = decode_v3_depth([log], quote_is_token0=False, move=0.10)[0][1]
    assert ten > one * 8, (one, ten)


def test_zero_liquidity_yields_no_observation():
    # A pool with no active liquidity at the tick has no measurable depth;
    # reporting zero would say "free to move", which is the opposite.
    assert decode_v3_depth([swap(10, 10**18, -10**18, liquidity=0)],
                           quote_is_token0=False) == []
    assert decode_v3_depth([swap(10, 10**18, -10**18, sqrt_price_x96=0)],
                           quote_is_token0=False) == []


def test_depth_feeds_the_feature_block():
    from rhc.features import compute
    logs = [swap(10 + i, 10**18, -10**18, index=i, liquidity=10**18 * (i + 1))
            for i in range(5)]
    trades = decode_v3_swaps(logs, quote_is_token0=False)
    depths = decode_v3_depth(logs, quote_is_token0=False)
    features = compute(pool="0xp", quote_asset="0xq", created_block=0,
                       trades=trades, syncs=[], head_block=1000, depths=depths)
    assert features.v3_depth_observations == 5
    assert features.v3_depth_1pct_min == min(d for _, d in depths)
    assert features.v3_depth_1pct_launch == depths[0][1]
    assert features.v3_depth_1pct_final == depths[-1][1]
    # V3 has no reserves, and the reserve columns must stay untouched rather
    # than quietly absorbing the depth numbers.
    assert features.launch_quote_reserve == 0.0
    assert features.peak_quote_reserve == 0.0


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
