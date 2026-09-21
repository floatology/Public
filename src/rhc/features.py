"""One-pass feature extraction: every metric derivable from a pool's own logs.

Implements the buildable-now entries of `docs/09-metric-catalogue.md`. The design
principle is that three log types — `Swap`, `Sync` and `Transfer` — between them
yield most of the catalogue, so a single scan per token produces dozens of
features rather than one scan per feature.

**Computing features is statistically free; testing hypotheses is not.** The
multiple-comparisons problem arises from testing many hypotheses and keeping the
winners, not from calculating many numbers. Interactions in particular cannot be
discovered without their components present, so breadth here is correct — the
discipline belongs downstream, in regularised selection against a held-out
confirmation split.

**Wallet attribution caveat.** V2 `Swap` indexes `sender` and `to`. `sender` is
almost always a router contract (one sampled pool showed 187 distinct senders
against 1,143 recipients, with a single sender covering 1,282 of 9,733 swaps),
so `to` is the better proxy for the trading wallet. It is still a proxy: a
wallet routing through an aggregator that forwards elsewhere is misattributed.
Transaction-level `from` would be exact and costs an extra lookup per swap.

**Direction is derived, not assumed.** Whether a swap is a buy or a sell depends
on which side the quote asset sits, and Uniswap orders pairs by address rather
than by role. Getting this backwards silently inverts every flow metric — it
already produced a 22,668x median peak-over-launch earlier in this project.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

# Uniswap V2 constant-product fee.
_FEE_NUM, _FEE_DEN = 997, 1000
_WORD = 64


# --------------------------------------------------------------------------
# Log decoding
# --------------------------------------------------------------------------

def _words(data_hex: str, count: int) -> list[int] | None:
    body = data_hex[2:] if data_hex.startswith("0x") else data_hex
    if len(body) < _WORD * count:
        return None
    try:
        return [int(body[i * _WORD : (i + 1) * _WORD], 16) for i in range(count)]
    except ValueError:
        return None


def _topic_address(topic: str) -> str:
    return "0x" + topic[-40:].lower()


@dataclass(frozen=True)
class Trade:
    """One swap, normalised to quote/base regardless of token ordering."""

    block: int
    wallet: str
    is_buy: bool
    quote_amount: int  # always positive
    base_amount: int  # always positive
    log_index: int

    @property
    def price(self) -> float:
        """Quote per base. Ratios within one pool only — decimals do not cancel across pools."""
        return self.quote_amount / self.base_amount if self.base_amount else 0.0


def decode_v2_swaps(logs: Iterable[dict], *, quote_is_token0: bool) -> list[Trade]:
    """Decode V2 Swap logs into direction-normalised trades.

    A buy is quote flowing *into* the pool and base flowing out.
    """
    trades: list[Trade] = []
    for log in logs:
        amounts = _words(log.get("data") or "0x", 4)
        if amounts is None:
            continue
        a0_in, a1_in, a0_out, a1_out = amounts
        if quote_is_token0:
            quote_in, quote_out, base_in, base_out = a0_in, a0_out, a1_in, a1_out
        else:
            quote_in, quote_out, base_in, base_out = a1_in, a1_out, a0_in, a0_out

        is_buy = quote_in > 0 and base_out > 0
        is_sell = base_in > 0 and quote_out > 0
        if not (is_buy or is_sell):
            continue  # malformed or zero-sided
        quote_amount = quote_in if is_buy else quote_out
        base_amount = base_out if is_buy else base_in
        if quote_amount <= 0 or base_amount <= 0:
            continue

        topics = log.get("topics") or []
        wallet = _topic_address(topics[2]) if len(topics) > 2 else ""
        trades.append(
            Trade(
                block=int(log["blockNumber"], 16),
                wallet=wallet,
                is_buy=is_buy,
                quote_amount=quote_amount,
                base_amount=base_amount,
                log_index=int(log.get("logIndex", "0x0"), 16),
            )
        )
    return trades


def decode_syncs(logs: Iterable[dict], *, quote_is_token0: bool) -> list[tuple[int, int, int]]:
    """Decode Sync logs into (block, quote_reserve, base_reserve)."""
    out: list[tuple[int, int, int]] = []
    for log in logs:
        reserves = _words(log.get("data") or "0x", 2)
        if reserves is None:
            continue
        r0, r1 = reserves
        quote, base = (r0, r1) if quote_is_token0 else (r1, r0)
        out.append((int(log["blockNumber"], 16), quote, base))
    return out


# --------------------------------------------------------------------------
# Cleaning
# --------------------------------------------------------------------------

def drop_dust(trades: list[Trade], floor_frac: float = 0.01) -> list[Trade]:
    """Drop trades far smaller than the pool's own genuine activity.

    Anchored to the **90th percentile** trade, not the median. A median anchor
    fails exactly where it matters: in a pool where most trades are dust the
    median *is* dust, so a fraction of it filters nothing. That version passed a
    60-pool smoke test and still produced a p99 peak-over-launch of 8.8e18 at
    n=1,200.
    """
    if not trades:
        return []
    amounts = sorted(t.quote_amount for t in trades)
    anchor = amounts[min(len(amounts) - 1, int(len(amounts) * 0.9))]
    floor = anchor * floor_frac
    return [t for t in trades if t.quote_amount >= floor]


# --------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------

@dataclass
class TokenFeatures:
    """Every feature derivable from one pool's swap and sync history.

    Field names map to `docs/09-metric-catalogue.md` numbering, noted per group.
    """

    pool: str
    quote_asset: str
    created_block: int

    # --- activity (catalogue 3.1, 3.2, 3.3, 3.8) ---
    trade_count: int = 0
    buy_count: int = 0
    sell_count: int = 0
    unique_wallets: int = 0
    unique_buyers: int = 0
    unique_sellers: int = 0
    buy_sell_count_ratio: float | None = None

    # --- value flow (3.3, 3.4, 3.9, 3.10) ---
    buy_quote_volume: float = 0.0
    sell_quote_volume: float = 0.0
    buy_sell_value_ratio: float | None = None
    net_flow_quote: float = 0.0
    buy_usd_share: float | None = None
    buy_count_share: float | None = None
    usd_minus_count_share: float | None = None
    trade_size_median: float | None = None
    trade_size_p90: float | None = None
    trade_size_gini: float | None = None

    # --- liquidity (4.1, 4.2, 4.4) ---
    launch_quote_reserve: float = 0.0
    peak_quote_reserve: float = 0.0
    final_quote_reserve: float = 0.0
    liquidity_add_events: int = 0
    liquidity_remove_events: int = 0
    largest_liquidity_removal_pct: float | None = None

    # --- price / outcome ---
    launch_vwap: float | None = None
    peak_price: float | None = None
    peak_block: int | None = None
    peak_over_launch: float | None = None
    final_over_launch: float | None = None
    drawdown_from_peak: float | None = None

    # --- wallet behaviour (1.3, 1.7, 1.10) ---
    top_wallet_volume_share: float | None = None
    wallet_volume_hhi: float | None = None
    repeat_buyer_count: int = 0
    repeat_buyer_share: float | None = None
    stealth_accumulator_count: int = 0
    max_wallet_buy_count: int = 0

    # --- manipulation (7.2, 7.4, 7.5) ---
    sniper_buy_count: int = 0
    sniper_buy_share: float | None = None
    same_block_multibuy_count: int = 0
    self_trade_wallet_count: int = 0
    self_trade_volume_share: float | None = None
    wash_suspect_score: float | None = None

    # --- lifecycle ---
    lifespan_blocks: int = 0
    active_blocks: int = 0
    trades_per_active_block: float | None = None
    first_trade_delay_blocks: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _gini(values: list[float]) -> float | None:
    """Gini coefficient. 0 = perfectly equal, 1 = maximally concentrated."""
    positives = sorted(v for v in values if v > 0)
    n = len(positives)
    if n < 2:
        return None
    total = sum(positives)
    if total <= 0:
        return None
    weighted = sum((i + 1) * v for i, v in enumerate(positives))
    return (2 * weighted) / (n * total) - (n + 1) / n


def _hhi(shares: list[float]) -> float | None:
    """Herfindahl-Hirschman index over shares summing to 1."""
    total = sum(shares)
    if total <= 0:
        return None
    return sum((s / total) ** 2 for s in shares)


def compute(
    *,
    pool: str,
    quote_asset: str,
    created_block: int,
    trades: list[Trade],
    syncs: list[tuple[int, int, int]],
    head_block: int,
    sniper_window_blocks: int = 50,
    stealth_max_pool_share: float = 0.02,
    stealth_min_buys: int = 3,
) -> TokenFeatures:
    """Compute every feature from one pool's decoded history.

    Args:
        sniper_window_blocks: buys within this many blocks of pool creation count
            as snipes. At ~100ms blocks, 50 blocks is roughly five seconds.
        stealth_max_pool_share: a buy consuming less than this fraction of the
            quote reserve counts as "not moving the price" — the operational
            form of accumulating without showing size.
        stealth_min_buys: how many such buys before a wallet counts as one.
    """
    features = TokenFeatures(pool=pool, quote_asset=quote_asset, created_block=created_block)
    if not trades:
        return features

    buys = [t for t in trades if t.is_buy]
    sells = [t for t in trades if not t.is_buy]

    features.trade_count = len(trades)
    features.buy_count = len(buys)
    features.sell_count = len(sells)
    features.unique_wallets = len({t.wallet for t in trades if t.wallet})
    features.unique_buyers = len({t.wallet for t in buys if t.wallet})
    features.unique_sellers = len({t.wallet for t in sells if t.wallet})
    if sells:
        features.buy_sell_count_ratio = len(buys) / len(sells)

    buy_volume = sum(t.quote_amount for t in buys)
    sell_volume = sum(t.quote_amount for t in sells)
    features.buy_quote_volume = float(buy_volume)
    features.sell_quote_volume = float(sell_volume)
    features.net_flow_quote = float(buy_volume - sell_volume)
    if sell_volume > 0:
        features.buy_sell_value_ratio = buy_volume / sell_volume

    total_volume = buy_volume + sell_volume
    if total_volume > 0 and trades:
        # Accumulation tell: few wallets buying big while many sell small shows
        # up as a high USD share against a low count share.
        features.buy_usd_share = buy_volume / total_volume
        features.buy_count_share = len(buys) / len(trades)
        features.usd_minus_count_share = features.buy_usd_share - features.buy_count_share

    sizes = [float(t.quote_amount) for t in trades]
    sizes.sort()
    features.trade_size_median = sizes[len(sizes) // 2]
    features.trade_size_p90 = sizes[min(len(sizes) - 1, int(len(sizes) * 0.9))]
    features.trade_size_gini = _gini(sizes)

    # --- liquidity trajectory ---
    if syncs:
        quote_reserves = [q for _, q, _ in syncs]
        features.launch_quote_reserve = float(quote_reserves[0])
        features.peak_quote_reserve = float(max(quote_reserves))
        features.final_quote_reserve = float(quote_reserves[-1])

        # A reserve change with no swap in that block is a mint or a burn.
        swap_blocks = {t.block for t in trades}
        largest_removal = 0.0
        for (block, quote, _), (_, prev_quote, _) in zip(syncs[1:], syncs[:-1]):
            if block in swap_blocks or prev_quote <= 0:
                continue
            change = (quote - prev_quote) / prev_quote
            if change > 0.01:
                features.liquidity_add_events += 1
            elif change < -0.01:
                features.liquidity_remove_events += 1
                largest_removal = max(largest_removal, -change)
        if largest_removal > 0:
            features.largest_liquidity_removal_pct = largest_removal * 100.0

    # --- price trajectory ---
    priced = [t for t in trades if t.price > 0]
    if priced:
        head_trades = priced[:5]
        volume = sum(t.quote_amount for t in head_trades)
        if volume > 0:
            features.launch_vwap = sum(t.price * t.quote_amount for t in head_trades) / volume
        peak = max(priced, key=lambda t: t.price)
        features.peak_price = peak.price
        features.peak_block = peak.block
        if features.launch_vwap and features.launch_vwap > 0:
            features.peak_over_launch = peak.price / features.launch_vwap
            features.final_over_launch = priced[-1].price / features.launch_vwap
        if features.peak_price and features.peak_price > 0:
            features.drawdown_from_peak = 1.0 - priced[-1].price / features.peak_price

    # --- wallet behaviour ---
    wallet_volume: dict[str, int] = defaultdict(int)
    wallet_buys: Counter[str] = Counter()
    for trade in trades:
        if trade.wallet:
            wallet_volume[trade.wallet] += trade.quote_amount
    for trade in buys:
        if trade.wallet:
            wallet_buys[trade.wallet] += 1

    if wallet_volume:
        volumes = sorted(wallet_volume.values(), reverse=True)
        total = sum(volumes)
        if total > 0:
            features.top_wallet_volume_share = volumes[0] / total
            features.wallet_volume_hhi = _hhi([float(v) for v in volumes])
    if wallet_buys:
        features.max_wallet_buy_count = max(wallet_buys.values())
        repeat = [w for w, n in wallet_buys.items() if n >= 2]
        features.repeat_buyer_count = len(repeat)
        if features.unique_buyers:
            features.repeat_buyer_share = len(repeat) / features.unique_buyers

    # --- stealth accumulation (the original hypothesis, made measurable) ---
    # A wallet buying repeatedly while each buy stays small relative to the pool
    # is accumulating without moving price. Requires reserves at trade time.
    if syncs:
        reserve_at: list[tuple[int, int]] = [(b, q) for b, q, _ in syncs]
        quiet_buys: Counter[str] = Counter()
        cursor = 0
        for trade in buys:
            while cursor + 1 < len(reserve_at) and reserve_at[cursor + 1][0] <= trade.block:
                cursor += 1
            quote_reserve = reserve_at[cursor][1]
            if quote_reserve > 0 and trade.wallet:
                if trade.quote_amount / quote_reserve <= stealth_max_pool_share:
                    quiet_buys[trade.wallet] += 1
        features.stealth_accumulator_count = sum(
            1 for n in quiet_buys.values() if n >= stealth_min_buys
        )

    # --- manipulation signatures ---
    snipes = [t for t in buys if t.block - created_block <= sniper_window_blocks]
    features.sniper_buy_count = len(snipes)
    if buys:
        features.sniper_buy_share = len(snipes) / len(buys)

    per_block: dict[int, set[str]] = defaultdict(set)
    for trade in buys:
        if trade.wallet:
            per_block[trade.block].add(trade.wallet)
    features.same_block_multibuy_count = sum(1 for w in per_block.values() if len(w) > 1)

    # Self-trading: a wallet on both sides of the book in the same pool.
    buyers = {t.wallet for t in buys if t.wallet}
    sellers = {t.wallet for t in sells if t.wallet}
    both = buyers & sellers
    features.self_trade_wallet_count = len(both)
    if both and total_volume > 0:
        both_volume = sum(v for w, v in wallet_volume.items() if w in both)
        features.self_trade_volume_share = both_volume / total_volume

    # Composite suspicion: concentrated volume, heavy self-trading, few wallets
    # relative to trade count. Deliberately a continuous score, not a verdict.
    components = [
        features.self_trade_volume_share or 0.0,
        features.top_wallet_volume_share or 0.0,
        1.0 - min(1.0, features.unique_wallets / max(1, features.trade_count)),
    ]
    features.wash_suspect_score = sum(components) / len(components)

    # --- lifecycle ---
    blocks = [t.block for t in trades]
    features.lifespan_blocks = head_block - created_block
    features.active_blocks = max(blocks) - min(blocks)
    features.first_trade_delay_blocks = min(blocks) - created_block
    if features.active_blocks > 0:
        features.trades_per_active_block = len(trades) / features.active_blocks

    return features


def window(trades: list[Trade], *, start: int, end: int) -> list[Trade]:
    """Trades within a block range, for computing a feature over a time slice.

    Recomputing `compute` over successive windows yields the velocity and
    relative-volume metrics (catalogue 3.5, 3.6) without a separate code path.
    """
    return [t for t in trades if start <= t.block <= end]


# --------------------------------------------------------------------------
# Holder distribution (catalogue section 2)
# --------------------------------------------------------------------------

BURN_ADDRESSES = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}


@dataclass
class HolderFeatures:
    """Holder distribution, reconstructed by replaying Transfer logs.

    **Pools, burn addresses and the zero address must be excluded.** Verified
    live on this chain: the largest holder of the token checked was the
    liquidity pool itself at 6.82% of supply, and the second was the burn
    address at 5.48%. Including them measures the pool rather than the holders,
    and inflates every concentration statistic.
    """

    holder_count: int = 0
    top1_share: float | None = None
    top10_share: float | None = None
    top100_share: float | None = None
    hhi: float | None = None
    gini: float | None = None
    entropy: float | None = None
    normalised_entropy: float | None = None
    deployer_share: float | None = None
    early_buyer_share: float | None = None
    holders_with_dust_only: int = 0
    transfer_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def replay_balances(
    transfer_logs: Iterable[dict],
    *,
    exclude: set[str] | None = None,
    up_to_block: int | None = None,
) -> tuple[dict[str, int], int]:
    """Reconstruct balances at a block by replaying Transfer logs.

    Returns (balances, transfers_applied). Mints appear as transfers from the
    zero address and burns as transfers to it, so both fall out naturally
    provided the zero address is excluded from the final tally rather than from
    the replay itself.
    """
    excluded = {a.lower() for a in (exclude or set())} | BURN_ADDRESSES
    balances: dict[str, int] = defaultdict(int)
    applied = 0
    for log in transfer_logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue  # ERC-721 or a malformed log
        if up_to_block is not None and int(log["blockNumber"], 16) > up_to_block:
            break
        amounts = _words(log.get("data") or "0x", 1)
        if amounts is None:
            continue
        value = amounts[0]
        if value <= 0:
            continue
        sender = _topic_address(topics[1])
        recipient = _topic_address(topics[2])
        balances[sender] -= value
        balances[recipient] += value
        applied += 1
    return (
        {a: b for a, b in balances.items() if b > 0 and a not in excluded},
        applied,
    )


def holder_features(
    balances: dict[str, int],
    *,
    transfer_count: int = 0,
    deployer: str | None = None,
    early_buyers: set[str] | None = None,
    dust_fraction: float = 1e-6,
) -> HolderFeatures:
    """Concentration and distribution statistics over a balance map.

    Args:
        dust_fraction: holders below this share of supply are counted separately.
            Airdropped dust otherwise inflates holder counts dramatically, which
            is a cheap and common way to fake adoption.
    """
    features = HolderFeatures(transfer_count=transfer_count)
    if not balances:
        return features

    total = sum(balances.values())
    if total <= 0:
        return features

    amounts = sorted(balances.values(), reverse=True)
    features.holder_count = len(amounts)
    features.holders_with_dust_only = sum(1 for a in amounts if a / total < dust_fraction)

    features.top1_share = amounts[0] / total
    features.top10_share = sum(amounts[:10]) / total
    features.top100_share = sum(amounts[:100]) / total

    shares = [a / total for a in amounts]
    features.hhi = sum(s * s for s in shares)
    features.gini = _gini([float(a) for a in amounts])

    # Shannon entropy in bits; normalised against a uniform distribution over
    # the same holder count so it compares across tokens of different sizes.
    entropy = -sum(s * math.log2(s) for s in shares if s > 0)
    features.entropy = entropy
    if len(amounts) > 1:
        features.normalised_entropy = entropy / math.log2(len(amounts))

    if deployer:
        features.deployer_share = balances.get(deployer.lower(), 0) / total
    if early_buyers:
        cohort = {w.lower() for w in early_buyers}
        features.early_buyer_share = sum(
            b for a, b in balances.items() if a in cohort
        ) / total
    return features
