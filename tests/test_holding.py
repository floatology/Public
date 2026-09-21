"""Holding duration and the early-buyer cohort — catalogue 2.9 and 2.8.

2.9 was marked "needs work" on the assumption it required a Transfer replay.
It does not: a wallet's hold is the span from its first buy to its last sell,
and both are in the trades already on disk.

The limitation is real and the tests pin it down. This measures holding *in the
pool*. A wallet that moved its tokens to another address reads as never having
sold, which is why never_sold_share is reported beside the durations instead of
being folded into them -- a diamond hand and an exit through a side door are
indistinguishable from swap logs alone, and the column should not pretend
otherwise.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.features import Trade, compute


def tr(block, wallet, is_buy, quote=10**18, index=0):
    return Trade(block=block, wallet=wallet, is_buy=is_buy, quote_amount=quote,
                 base_amount=10**18, log_index=index)


def build(trades):
    return compute(pool="0xp", quote_asset="0xq", created_block=0,
                   trades=trades, syncs=[], head_block=100_000)


def test_hold_duration_is_first_buy_to_last_sell():
    trades = [
        tr(100, "0xa", True, index=0),
        tr(150, "0xa", True, index=1),   # a second buy must not reset the clock
        tr(400, "0xa", False, index=2),
        tr(900, "0xa", False, index=3),  # the LAST sell ends it
        tr(100, "0xb", True, index=4),
        tr(300, "0xb", False, index=5),
    ]
    f = build(trades)
    # 0xa held 800 blocks, 0xb held 200.
    assert f.round_trip_wallet_count == 2
    assert f.median_hold_blocks == 800.0, f.median_hold_blocks
    assert f.mean_hold_blocks == 500.0, f.mean_hold_blocks
    assert f.never_sold_share == 0.0


def test_never_sold_is_reported_not_imputed():
    # Two buyers, one exits, one does not. The holder that never sold must not
    # contribute a duration -- neither zero nor the token's lifespan, both of
    # which would be inventions.
    trades = [tr(100, "0xa", True, index=0), tr(500, "0xa", False, index=1),
              tr(100, "0xb", True, index=2)]
    f = build(trades)
    assert f.round_trip_wallet_count == 1
    assert f.never_sold_wallet_count == 1
    assert f.never_sold_share == 0.5
    assert f.median_hold_blocks == 400.0


def test_seller_who_never_bought_here_is_excluded():
    # Acquired the token elsewhere and sold into this pool. There is no buy to
    # measure a hold from, so it must not appear as a zero-length hold.
    trades = [tr(100, "0xa", True, index=0), tr(200, "0xa", False, index=1),
              tr(300, "0xelsewhere", False, index=2)]
    f = build(trades)
    assert f.round_trip_wallet_count == 1
    assert f.never_sold_wallet_count == 0
    assert f.round_trip_share == 1.0


def test_early_cohort_share():
    # Ten early buyers taking small amounts, then one whale. The cohort's share
    # of volume should be modest despite them being first.
    trades = [tr(100 + i, f"0xe{i}", True, 10**17, index=i) for i in range(10)]
    trades.append(tr(200, "0xwhale", True, 9 * 10**18, index=99))
    trades.append(tr(300, "0xwhale", False, 10**18, index=100))
    f = build(trades)
    assert abs(f.first_ten_buyer_volume_share - 1.0 / 11.0) < 1e-6, (
        f.first_ten_buyer_volume_share
    )
    # The cohort did none of the selling; the whale did all of it.
    assert f.first_ten_buyer_sell_share == 0.0


def test_cohort_distribution_is_visible():
    # Same ten early buyers, but this time they are the ones selling.
    trades = [tr(100 + i, f"0xe{i}", True, 10**18, index=i) for i in range(10)]
    trades += [tr(500 + i, f"0xe{i}", False, 10**18, index=20 + i) for i in range(10)]
    f = build(trades)
    assert f.first_ten_buyer_sell_share == 1.0
    assert f.never_sold_share == 0.0


def test_degenerate_inputs():
    empty = build([])
    assert empty.median_hold_blocks is None and empty.round_trip_share is None
    single = build([tr(10, "0xa", True)])
    assert single.median_hold_blocks is None
    assert single.never_sold_share == 1.0


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
