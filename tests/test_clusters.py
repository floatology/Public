"""Coordination clustering — catalogue 1.8.

The failure mode is over-merging. Clustering is transitive, so one spurious
pair welds two unrelated fleets into a single entity and every crowd metric
downstream reads too low. The tests therefore spend most of their effort on
wallets that must *not* merge: busy independent traders that overlap by volume
alone, and a pair that shares tokens without ever sharing a block.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.clusters import build_entities, crowd_features, find_pairs
from rhc.features import Trade


def tr(block, wallet, quote=10**18, index=0, is_buy=True):
    return Trade(block=block, wallet=wallet, is_buy=is_buy, quote_amount=quote,
                 base_amount=10**18, log_index=index)


def universe(count=400, rng_seed=1):
    """Background chatter: many tokens, each with a few unrelated traders."""
    rng = random.Random(rng_seed)
    tokens = {}
    for i in range(count):
        tokens[f"0xt{i:04d}"] = [
            tr(1000 + i * 100 + j, f"0xr{rng.randrange(5000):04d}", index=j)
            for j in range(rng.randint(2, 6))
        ]
    return tokens


def test_fleet_is_merged():
    tokens = universe()
    # Three wallets buying the same six obscure tokens in the same blocks.
    fleet = ["0xaaa", "0xbbb", "0xccc"]
    for i in range(6):
        name = f"0xfleet{i}"
        tokens[name] = [tr(50_000 + i * 10, w, index=j) for j, w in enumerate(fleet)]

    pairs = find_pairs(tokens)
    entities = build_entities(pairs)
    assert entities, "no pairs found for a fleet acting in identical blocks"
    assert len({entities[w] for w in fleet}) == 1, {w: entities.get(w) for w in fleet}


def test_independent_busy_traders_do_not_merge():
    # Two active wallets each trading 60 of 400 tokens, chosen independently.
    # They will overlap on roughly nine by chance alone, which is more raw
    # overlap than the fleet above has -- so a detector that counts shared
    # tokens flags them and only the null model does not.
    rng = random.Random(99)
    tokens = universe()
    names = sorted(tokens)
    for offset, wallet in enumerate(("0xbusy1", "0xbusy2")):
        for i, name in enumerate(rng.sample(names, 60)):
            tokens[name].append(tr(90_000 + i * 1000 + offset * 7, wallet, index=50 + offset))

    overlap = sum(
        1 for name in names
        if {"0xbusy1", "0xbusy2"} <= {t.wallet for t in tokens[name]}
    )
    assert overlap >= 5, f"fixture is not exercising the null model (overlap {overlap})"

    merged = build_entities(find_pairs(tokens))
    assert merged.get("0xbusy1", "1") != merged.get("0xbusy2", "2"), (
        f"two independently busy wallets sharing {overlap} tokens by chance "
        f"were welded into one entity"
    )


def test_two_shared_tokens_is_not_evidence():
    tokens = universe()
    for i in range(2):
        tokens[f"0xpair{i}"] = [tr(70_000 + i, "0xp1", index=0), tr(70_000 + i, "0xp2", index=1)]
    pairs = find_pairs(tokens, min_shared=3)
    assert not any({p.a, p.b} == {"0xp1", "0xp2"} for p in pairs), pairs[:3]


def test_crowd_features_count_entities_not_addresses():
    trades = [tr(10, "0xaaa", 10**18, 0), tr(10, "0xbbb", 10**18, 1),
              tr(11, "0xccc", 10**18, 2), tr(12, "0xzzz", 2 * 10**18, 3)]
    entities = {"0xaaa": "E", "0xbbb": "E", "0xccc": "E"}
    crowd = crowd_features(trades, entities)
    # Four addresses, two participants.
    assert crowd.wallet_count == 4 and crowd.entity_count == 2, crowd
    assert crowd.independence_ratio == 0.5
    assert crowd.largest_entity_wallets == 3
    assert abs(crowd.largest_entity_volume_share - 0.6) < 1e-9, crowd


def test_unclustered_wallets_stay_separate():
    # A wallet with no entity is its own entity, never lumped with the others.
    trades = [tr(10, f"0x{i}", index=i) for i in range(5)]
    crowd = crowd_features(trades, {})
    assert crowd.entity_count == 5 and crowd.independence_ratio == 1.0
    assert crowd.clustered_wallet_share == 0.0


def test_empty_inputs():
    assert find_pairs({}) == []
    assert crowd_features([], {}).wallet_count == 0


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
