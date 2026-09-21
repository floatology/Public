"""Bundle and bump bot detection — catalogue 7.1 and 7.3.

These are the two manipulation metrics the catalogue listed as unbuilt, and
**7.3 is the reason to care**. In the copy-trading paper's LASSO model
(arXiv 2601.08641), bump-bot presence carried the highest normalised feature
importance of any variable — above every historical-performance feature the
paper computed. Manipulation signatures are not merely noise to be filtered out
before the real features are measured; in the one published model over a
comparable feature space, they *were* the strongest feature.

The two bots do opposite things and need opposite detectors.

**A bundle bot buys once, across many wallets, in one block.** Its purpose is to
acquire supply before anybody else can, while looking like organic demand from a
crowd. Its signature is width: many distinct addresses, one block, near-identical
sizes. The paper used it as a *required-FALSE* gate — presence disqualifies a
token outright rather than adjusting a score.

**A bump bot trades forever, from one wallet, in tiny amounts.** Its purpose is
to keep a pair visible on aggregator trending boards, which rank on trade count
and recency. Its signature is depth: one address, hundreds of trades, sizes that
barely vary, gaps between them that barely vary, and a net position near zero
because every buy is undone.

**What makes these hard is that the naive version of each detector fires on
something ordinary.** Many wallets buying in one block is also what a genuinely
anticipated launch looks like, so bundling is scored on *size uniformity* as well
as width: real buyers choose their own amounts, and a bundler's contract does
not. One wallet trading repeatedly is also what a market maker or an active
trader looks like, so bumping requires near-zero net position *and* regular
timing together — a trader who round-trips does not do it on a metronome, and a
bot driven by a scheduler cannot help it.

Every metric here is computed from decoded trades alone. Nothing calls the RPC,
which means these can be recomputed over a persisted trade archive without
touching a node that rate-limits globally.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any

from .features import Trade


@dataclass
class BotSignatures:
    """Bundle and bump signatures for one pool."""

    # --- 7.1 bundling ---
    bundle_max_buyers_in_block: int = 0
    bundle_block_count: int = 0
    bundle_buyer_count: int = 0
    bundle_volume_share: float | None = None
    bundle_size_uniformity: float | None = None
    is_bundled: bool = False

    # --- 7.3 bumping ---
    bump_wallet_count: int = 0
    bump_trade_share: float | None = None
    bump_volume_share: float | None = None
    max_bump_score: float | None = None
    has_bump_bot: bool = False

    # --- shared: repeated identical amounts ---
    repeated_amount_share: float | None = None
    modal_amount_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _uniformity(values: list[int]) -> float | None:
    """1.0 when every value is identical, falling towards 0 as they spread.

    Defined as 1 - CV, clipped at zero. A bundler splitting a fixed budget
    across wallets produces amounts that agree to several significant figures;
    a crowd does not.
    """
    positives = [float(v) for v in values if v > 0]
    if len(positives) < 2:
        return None
    mean = statistics.fmean(positives)
    if mean <= 0:
        return None
    cv = statistics.pstdev(positives) / mean
    return max(0.0, 1.0 - cv)


def _regularity(blocks: list[int]) -> float | None:
    """1.0 when the gaps between trades are perfectly even.

    A scheduled bot fires on a timer. Its inter-trade gaps have almost no
    dispersion, and that is difficult to disguise without giving up the
    scheduling that makes the bot cheap to run.
    """
    if len(blocks) < 3:
        return None
    ordered = sorted(blocks)
    gaps = [b - a for a, b in zip(ordered, ordered[1:]) if b > a]
    if len(gaps) < 2:
        return None
    mean = statistics.fmean(gaps)
    if mean <= 0:
        return None
    cv = statistics.pstdev(gaps) / mean
    return max(0.0, 1.0 - cv)


def detect(
    trades: list[Trade],
    *,
    bundle_window_blocks: int = 50,
    bundle_min_buyers: int = 4,
    bundle_min_uniformity: float = 0.8,
    bump_min_trades: int = 10,
    bump_max_net_share: float = 0.1,
    bump_max_size_pctile: float = 0.25,
    bump_min_score: float = 0.6,
) -> BotSignatures:
    """Score one pool's trade history for bundling and bumping.

    Args:
        bundle_window_blocks: how far past the first trade still counts as
            launch. Bundling after launch is not bundling — the supply is
            already distributed and there is nothing left to front-run.
        bundle_min_buyers: distinct wallets in one block before the block is a
            bundle candidate. Below four, coincidence is the likelier
            explanation on a chain producing blocks every ~100ms.
        bundle_min_uniformity: how alike the amounts must be for `is_bundled`.
            Width alone is not evidence; width plus matching sizes is.
        bump_max_net_share: a bumper's net position, as a fraction of its own
            gross volume. A wallet that ends near flat after hundreds of trades
            was not accumulating; it was generating trade count.
        bump_max_size_pctile: bumping only makes sense if it is cheap, so a
            candidate's median trade must sit in the small tail of the pool's
            own size distribution rather than at some absolute threshold —
            "small" is a property of the pool, not of a dollar figure.
    """
    signatures = BotSignatures()
    if not trades:
        return signatures

    # ---- 7.1 bundling -------------------------------------------------
    first_block = min(t.block for t in trades)
    launch_buys = [
        t for t in trades
        if t.is_buy and t.wallet and t.block <= first_block + bundle_window_blocks
    ]
    by_block: dict[int, list[Trade]] = defaultdict(list)
    for trade in launch_buys:
        by_block[trade.block].append(trade)

    bundle_blocks = {
        block: group for block, group in by_block.items()
        if len({t.wallet for t in group}) >= bundle_min_buyers
    }
    if bundle_blocks:
        widths = [len({t.wallet for t in g}) for g in bundle_blocks.values()]
        signatures.bundle_max_buyers_in_block = max(widths)
        signatures.bundle_block_count = len(bundle_blocks)
        bundled_trades = [t for g in bundle_blocks.values() for t in g]
        signatures.bundle_buyer_count = len({t.wallet for t in bundled_trades})
        signatures.bundle_size_uniformity = _uniformity(
            [t.quote_amount for t in bundled_trades]
        )
        total_volume = sum(t.quote_amount for t in trades)
        if total_volume > 0:
            bundled_volume = sum(t.quote_amount for t in bundled_trades)
            signatures.bundle_volume_share = bundled_volume / total_volume
        signatures.is_bundled = (
            signatures.bundle_size_uniformity is not None
            and signatures.bundle_size_uniformity >= bundle_min_uniformity
        )

    # ---- 7.3 bumping ---------------------------------------------------
    sizes = sorted(t.quote_amount for t in trades if t.quote_amount > 0)
    small_cut = (
        sizes[min(len(sizes) - 1, int(len(sizes) * bump_max_size_pctile))]
        if sizes else 0
    )

    by_wallet: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        if trade.wallet:
            by_wallet[trade.wallet].append(trade)

    bump_wallets: list[str] = []
    bump_scores: list[float] = []
    for wallet, wallet_trades in by_wallet.items():
        if len(wallet_trades) < bump_min_trades:
            continue
        gross = sum(t.quote_amount for t in wallet_trades)
        if gross <= 0:
            continue
        net = abs(
            sum(t.quote_amount for t in wallet_trades if t.is_buy)
            - sum(t.quote_amount for t in wallet_trades if not t.is_buy)
        )
        if net / gross > bump_max_net_share:
            continue  # accumulating or distributing, not bumping
        median_size = statistics.median(t.quote_amount for t in wallet_trades)
        if small_cut and median_size > small_cut:
            continue  # too large to be a cheap visibility trade

        uniformity = _uniformity([t.quote_amount for t in wallet_trades]) or 0.0
        regularity = _regularity([t.block for t in wallet_trades]) or 0.0
        flatness = 1.0 - min(1.0, net / gross / max(1e-9, bump_max_net_share))
        # Equal weights: no calibration set exists on this chain to fit them,
        # and inventing weights would dress a guess up as a measurement.
        score = (uniformity + regularity + flatness) / 3.0
        if score >= bump_min_score:
            bump_wallets.append(wallet)
            bump_scores.append(score)

    if bump_scores:
        signatures.max_bump_score = max(bump_scores)
    signatures.bump_wallet_count = len(bump_wallets)
    signatures.has_bump_bot = bool(bump_wallets)
    if bump_wallets:
        flagged = {w for w in bump_wallets}
        bump_trades = [t for t in trades if t.wallet in flagged]
        signatures.bump_trade_share = len(bump_trades) / len(trades)
        total_volume = sum(t.quote_amount for t in trades)
        if total_volume > 0:
            signatures.bump_volume_share = (
                sum(t.quote_amount for t in bump_trades) / total_volume
            )

    # ---- repeated amounts ------------------------------------------------
    # Independent of either bot, and the cheapest wash tell there is: distinct
    # traders acting independently do not keep arriving at the same amount to
    # the wei.
    counts: dict[int, int] = defaultdict(int)
    for trade in trades:
        if trade.quote_amount > 0:
            counts[trade.quote_amount] += 1
    if counts:
        signatures.modal_amount_count = max(counts.values())
        repeated = sum(c for c in counts.values() if c > 1)
        signatures.repeated_amount_share = repeated / len(trades)

    return signatures
