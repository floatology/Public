"""The offline rebuild must not silently disagree with the extractor.

The rebuild recomputes features from archived trades alone. Anything that needs
reserves (`Sync` logs) or the chain head cannot be derived that way, and the
dangerous case is not a missing value but a **wrong** one: with no syncs,
`stealth_accumulator_count` computes cleanly as 0 where the extractor found 9,
and nothing in the output says so. That happened, and was caught only by
diffing the two outputs by hand.

`SYNC_DERIVED` in `scripts/recompute_features.py` is the list of columns the
rebuild carries over instead of recomputing. This test derives that list
independently -- by running `compute` with and without syncs and seeing what
moves -- and fails if the declared list does not cover it. Adding a new
reserve-dependent feature without declaring it will fail here rather than
quietly corrupting every rebuilt dataset.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from rhc.features import Trade, compute
from recompute_features import SYNC_DERIVED


def trades():
    out = []
    for i in range(30):
        out.append(Trade(block=100 + i * 10, wallet=f"0xw{i % 6}", is_buy=i % 3 != 0,
                         quote_amount=10**17 * (i % 5 + 1), base_amount=10**18,
                         log_index=i))
    return out


def syncs():
    """Reserves that grow, are added to, and are then partly pulled.

    The sync blocks sit BETWEEN trade blocks deliberately. A reserve change in
    a block that also contains a swap is attributed to the swap, so syncs
    aligned with trades register no liquidity events at all -- which is how the
    first version of this fixture silently tested nothing.
    """
    out = [(105 + i * 10, 10**20 + i * 10**18, 10**21) for i in range(20)]
    out.append((305, 3 * 10**20, 10**21))   # an unmistakable add
    out.append((315, 10**20, 10**21))       # and a large removal
    return out


def test_declared_carry_set_covers_everything_that_moves():
    with_syncs = compute(pool="0xp", quote_asset="0xq", created_block=0,
                         trades=trades(), syncs=syncs(), head_block=5_000_000)
    without = compute(pool="0xp", quote_asset="0xq", created_block=0,
                      trades=trades(), syncs=[], head_block=5_000_000)

    moved = {
        name for name, value in with_syncs.to_dict().items()
        if without.to_dict()[name] != value
    }
    assert moved, "the fixture exercises no sync-dependent column; it is not testing anything"
    undeclared = moved - SYNC_DERIVED
    assert not undeclared, (
        f"these columns change when syncs are present but are not in "
        f"SYNC_DERIVED, so the offline rebuild will write wrong values for "
        f"them rather than carrying them over: {sorted(undeclared)}"
    )


def test_head_block_dependence_is_declared():
    early = compute(pool="0xp", quote_asset="0xq", created_block=0,
                    trades=trades(), syncs=syncs(), head_block=400)
    late = compute(pool="0xp", quote_asset="0xq", created_block=0,
                   trades=trades(), syncs=syncs(), head_block=9_000_000)
    moved = {
        name for name, value in late.to_dict().items()
        if early.to_dict()[name] != value
    }
    assert moved, "fixture does not exercise head_block"
    undeclared = moved - SYNC_DERIVED
    assert not undeclared, (
        f"these columns depend on the chain head, which the trade archive does "
        f"not contain -- the archive's last trade is not the head. They must be "
        f"carried, not recomputed: {sorted(undeclared)}"
    )


def test_v3_depth_is_recomputable_not_carried():
    """Depth is archived, so it must be rebuilt rather than frozen.

    V3 has no reserves, which is why the reserve columns are carried over. It
    is easy to conclude from that that everything liquidity-shaped for V3 must
    also be carried. It must not: the depth observations are archived next to
    the trades, so the rebuild recomputes them, and carrying them would freeze
    a fixed calculation at its old values.
    """
    depths = [(100 + i * 10, 1e18 * (i + 1)) for i in range(5)]
    with_depth = compute(pool="0xp", quote_asset="0xq", created_block=0,
                         trades=trades(), syncs=[], head_block=5_000_000,
                         depths=depths)
    without = compute(pool="0xp", quote_asset="0xq", created_block=0,
                      trades=trades(), syncs=[], head_block=5_000_000)
    moved = {
        name for name, value in with_depth.to_dict().items()
        if without.to_dict()[name] != value
    }
    assert moved, "fixture does not exercise the depth block"
    assert not (moved & SYNC_DERIVED), (
        f"depth columns are in the carry-over set but are recomputable from "
        f"the archive: {sorted(moved & SYNC_DERIVED)}"
    )


def test_carry_set_is_not_over_broad():
    # Carrying a column that the rebuild COULD recompute freezes it at its old
    # value, so a fixed feature would never take effect. Every declared column
    # must actually be one that moves.
    with_syncs = compute(pool="0xp", quote_asset="0xq", created_block=0,
                         trades=trades(), syncs=syncs(), head_block=400)
    without = compute(pool="0xp", quote_asset="0xq", created_block=0,
                      trades=trades(), syncs=[], head_block=9_000_000)
    moved = {
        name for name, value in with_syncs.to_dict().items()
        if without.to_dict()[name] != value
    }
    spurious = SYNC_DERIVED - moved
    assert not spurious, (
        f"declared as needing carry-over but derivable from trades alone, so "
        f"the rebuild would freeze them at stale values: {sorted(spurious)}"
    )


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
