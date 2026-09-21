"""Wallet coordination clustering — catalogue 1.8.

The catalogue specified this as **funding-graph** clustering, following MELT
(arXiv 2602.13480): wallets funded from a common source are one entity. That
framing is why it was marked "needs work" — reading each wallet's first inbound
transfer means one explorer call per address, which does not scale to the tens
of thousands of wallets in the archive.

**Co-occurrence is the better evidence anyway, and it is already on disk.** A
shared funding source says two wallets were once touched by the same hand. Two
wallets that bought the same nine obscure tokens, several of them in the same
block, are being operated by the same hand *now*. The second is closer to what
the metric is for.

**Why this needs a null model and not a threshold.** With hundreds of thousands
of tokens, two wallets that each trade a few hundred of them will overlap by
chance, and a raw overlap count therefore ranks the busiest wallets rather than
the coordinated ones — the same activity confounding that makes raw hit counts
useless in `wallets.py`. So an overlap is scored against what independence
predicts: if A traded `a` tokens and B traded `b` of `N`, their expected overlap
is `a*b/N`, and only a large excess over that is evidence.

**Same-block co-occurrence is treated as much stronger than shared-token
co-occurrence**, because it is. Two wallets buying the same token in the same
100ms block did not both read the same tweet.

What comes out is an entity map. Its purpose is not to name anyone; it is to
turn "nine early buyers" into "nine wallets, three entities", because every
concentration and crowd metric in this project silently assumes one wallet is
one participant.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

from .features import Trade


@dataclass
class Pair:
    """Two wallets and the evidence that they are one operator."""

    a: str
    b: str
    shared_tokens: int
    same_block_tokens: int
    expected_shared: float
    excess: float           # shared / expected, capped for readability
    a_tokens: int
    b_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UnionFind:
    """Standard disjoint sets, used to merge pairs into entities."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:  # path compression
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[a] = b

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for item in list(self.parent):
            out[self.find(item)].append(item)
        return dict(out)


def find_pairs(
    token_trades: dict[str, list[Trade]],
    *,
    min_shared: int = 3,
    min_excess: float = 5.0,
    same_block_weight: int = 3,
    max_wallets_per_token: int = 300,
    min_tokens_per_wallet: int = 2,
) -> list[Pair]:
    """Wallet pairs whose overlap far exceeds what independence predicts.

    Args:
        min_shared: raw overlap floor. Two shared tokens is a coincidence worth
            nothing however surprising the arithmetic makes it look.
        min_excess: how many times the expected overlap the observed one must
            reach. Five is deliberately blunt: there is no labelled set of known
            coordinated wallets on this chain to calibrate against, and fitting
            a threshold to unlabelled data would dress a choice up as a result.
        same_block_weight: a same-block co-occurrence counts this many times
            towards the overlap, because arriving in the same 100ms block is not
            the same evidence as arriving in the same week.
        max_wallets_per_token: tokens with more traders than this are skipped.
            Pair enumeration is quadratic in a token's trader count, and a pool
            with thousands of traders contributes mostly noise anyway — nothing
            is learned from two wallets having both touched the chain's busiest
            pair.
    """
    wallet_tokens: dict[str, set[str]] = defaultdict(set)
    for token, trades in token_trades.items():
        for trade in trades:
            if trade.wallet:
                wallet_tokens[trade.wallet].add(token)

    eligible = {w for w, ts in wallet_tokens.items() if len(ts) >= min_tokens_per_wallet}
    universe = len(token_trades)
    if universe == 0 or not eligible:
        return []

    shared: dict[tuple[str, str], int] = defaultdict(int)
    same_block: dict[tuple[str, str], int] = defaultdict(int)

    for token, trades in token_trades.items():
        wallets = {t.wallet for t in trades if t.wallet in eligible}
        if len(wallets) < 2 or len(wallets) > max_wallets_per_token:
            continue
        ordered = sorted(wallets)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1:]:
                shared[(left, right)] += 1

        # Same-block co-occurrence, computed per block rather than per token so
        # a wallet trading a token repeatedly cannot inflate it.
        by_block: dict[int, set[str]] = defaultdict(set)
        for trade in trades:
            if trade.wallet in eligible:
                by_block[trade.block].add(trade.wallet)
        counted: set[tuple[str, str]] = set()
        for block_wallets in by_block.values():
            if len(block_wallets) < 2 or len(block_wallets) > max_wallets_per_token:
                continue
            ordered_block = sorted(block_wallets)
            for i, left in enumerate(ordered_block):
                for right in ordered_block[i + 1:]:
                    if (left, right) not in counted:
                        counted.add((left, right))
                        same_block[(left, right)] += 1

    pairs: list[Pair] = []
    for (left, right), overlap in shared.items():
        # The raw overlap floor is checked before weighting. Letting the
        # same-block multiplier carry a pair over the line would mean two
        # wallets sharing two tokens could qualify, and two shared tokens is a
        # coincidence whatever the arithmetic does to it afterwards.
        if overlap < min_shared:
            continue
        together = same_block.get((left, right), 0)
        weighted = overlap + together * (same_block_weight - 1)
        a_count, b_count = len(wallet_tokens[left]), len(wallet_tokens[right])
        expected = a_count * b_count / universe
        if expected <= 0:
            continue
        excess = weighted / expected
        if excess < min_excess:
            continue
        pairs.append(Pair(
            a=left, b=right, shared_tokens=overlap, same_block_tokens=together,
            expected_shared=expected, excess=min(excess, 1e9),
            a_tokens=a_count, b_tokens=b_count,
        ))
    pairs.sort(key=lambda p: -p.excess)
    return pairs


def build_entities(pairs: Iterable[Pair]) -> dict[str, str]:
    """Merge pairs into entities, returning wallet -> entity id.

    Transitive by construction: if A pairs with B and B with C, all three are
    one entity even though A and C were never compared. That is the intended
    behaviour for an operator running a fleet, and it is also the failure mode
    to watch — one spurious pair welds two real entities together, which is why
    `find_pairs` is strict about excess rather than permissive.
    """
    union = UnionFind()
    for pair in pairs:
        union.union(pair.a, pair.b)
    return {wallet: union.find(wallet) for wallet in union.parent}


@dataclass
class CrowdFeatures:
    """How much of a token's apparent crowd is actually independent."""

    wallet_count: int = 0
    entity_count: int = 0
    # 1.0 when every wallet is its own entity; falls as wallets merge.
    independence_ratio: float | None = None
    largest_entity_wallets: int = 0
    largest_entity_volume_share: float | None = None
    clustered_wallet_share: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def crowd_features(trades: list[Trade], entities: dict[str, str]) -> CrowdFeatures:
    """Recount one token's participants as entities rather than addresses.

    A wallet with no entity is its own entity. Treating unclustered wallets as a
    single anonymous group would be the opposite of the truth.
    """
    features = CrowdFeatures()
    wallets = {t.wallet for t in trades if t.wallet}
    if not wallets:
        return features

    features.wallet_count = len(wallets)
    membership = {w: entities.get(w, w) for w in wallets}
    features.entity_count = len(set(membership.values()))
    features.independence_ratio = features.entity_count / features.wallet_count
    features.clustered_wallet_share = (
        sum(1 for w in wallets if w in entities) / len(wallets)
    )

    by_entity: dict[str, list[str]] = defaultdict(list)
    for wallet, entity in membership.items():
        by_entity[entity].append(wallet)
    largest = max(by_entity.values(), key=len)
    features.largest_entity_wallets = len(largest)

    total = sum(t.quote_amount for t in trades)
    if total > 0:
        members = set(largest)
        features.largest_entity_volume_share = (
            sum(t.quote_amount for t in trades if t.wallet in members) / total
        )
    return features
