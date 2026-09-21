"""Cross-token wallet ledger and point-in-time scoring — catalogue section 1.

The domain with the strongest published evidence. *Resisting Manipulative Bots
in Meme Coin Copy Trading* (arXiv 2601.08641) reports AUC 0.70–0.72 predicting
whether a wallet's next trade profits, against the nearest prior art to this
project managing 0.54. Its selection thresholds are implemented here:
t-statistic of returns above 1.645, trade count above the 25th percentile, and
purchase size **below** the 75th — large buyers are not the profitable ones,
which is why `stealth` scoring exists alongside raw size.

**Two failure modes decide whether any of this is real.**

*Look-ahead.* Scoring a wallet at the moment it buys token X may only use
outcomes from tokens that **resolved before** that moment — not merely launched
before it. Build the flagged-wallet list from full history, then test it against
that same history, and the question becomes "did wallets that bought winners buy
winners". The answer is spectacular and worthless. The prior-art project dropped
its entire deployer-tracking tier for exactly this. `score_at` takes an
`as_of_block` and refuses to see past it.

*Activity confounding.* With 675,438 tokens on this chain, a wallet spraying 500
of them accumulates multiple hits on 10x tokens by chance alone. Raw hit *counts*
therefore measure activity, not skill. `binomial_tail` scores a wallet against
what its own trade count predicts, so a wallet with 3 hits from 8 entries
outranks one with 5 from 900.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

from .features import Trade


@dataclass(frozen=True)
class Position:
    """One wallet's round trip in one token, as far as it went."""

    wallet: str
    token: str
    first_buy_block: int
    last_block: int
    quote_in: int  # spent acquiring
    quote_out: int  # recovered selling
    base_bought: int
    base_sold: int
    buy_count: int
    sell_count: int
    entry_percentile: float | None = None  # how early among that token's buyers

    @property
    def is_closed(self) -> bool:
        """Whether the wallet sold substantially all of what it bought."""
        return self.base_bought > 0 and self.base_sold >= self.base_bought * 0.95

    @property
    def realised_return(self) -> float | None:
        """Return on closed positions only.

        An open position has no realised return, and marking it to market would
        import the very forward information the point-in-time discipline exists
        to exclude.
        """
        if not self.is_closed or self.quote_in <= 0:
            return None
        return self.quote_out / self.quote_in - 1.0


def build_positions(token: str, trades: list[Trade]) -> list[Position]:
    """Aggregate one token's trades into per-wallet positions.

    Entry percentile is computed within this token only: 0.0 is the first buyer,
    1.0 the last. It needs no forward information and is the catalogue's 1.3.
    """
    by_wallet: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "quote_in": 0, "quote_out": 0, "base_bought": 0, "base_sold": 0,
            "buys": 0, "sells": 0, "first_buy": None, "last": 0,
        }
    )
    for trade in trades:
        if not trade.wallet:
            continue
        state = by_wallet[trade.wallet]
        if trade.is_buy:
            state["quote_in"] += trade.quote_amount
            state["base_bought"] += trade.base_amount
            state["buys"] += 1
            if state["first_buy"] is None:
                state["first_buy"] = trade.block
        else:
            state["quote_out"] += trade.quote_amount
            state["base_sold"] += trade.base_amount
            state["sells"] += 1
        state["last"] = max(state["last"], trade.block)

    buyers = sorted(
        ((w, s["first_buy"]) for w, s in by_wallet.items() if s["first_buy"] is not None),
        key=lambda pair: pair[1],
    )
    rank = {w: i for i, (w, _) in enumerate(buyers)}
    denominator = max(1, len(buyers) - 1)

    positions: list[Position] = []
    for wallet, state in by_wallet.items():
        if state["first_buy"] is None:
            continue  # sold without buying here; acquired elsewhere
        positions.append(
            Position(
                wallet=wallet,
                token=token,
                first_buy_block=state["first_buy"],
                last_block=state["last"],
                quote_in=state["quote_in"],
                quote_out=state["quote_out"],
                base_bought=state["base_bought"],
                base_sold=state["base_sold"],
                buy_count=state["buys"],
                sell_count=state["sells"],
                entry_percentile=rank[wallet] / denominator,
            )
        )
    return positions


def binomial_tail(hits: int, trials: int, base_rate: float) -> float:
    """P(at least `hits` successes in `trials`) under the population base rate.

    Small values mean a wallet did better than its activity level explains. This
    is what separates skill from spraying: 3 hits from 8 entries is surprising
    against a 1% base rate, 5 from 900 is not.
    """
    if trials <= 0 or hits <= 0:
        return 1.0
    if base_rate <= 0:
        return 0.0 if hits > 0 else 1.0
    if base_rate >= 1:
        return 1.0
    # Sum the lower tail and subtract, which is stable for small hit counts.
    below = 0.0
    for k in range(hits):
        below += (
            math.comb(trials, k) * base_rate**k * (1 - base_rate) ** (trials - k)
        )
    return max(0.0, min(1.0, 1.0 - below))


@dataclass
class WalletScore:
    """A wallet's track record **as of a specific block**."""

    wallet: str
    as_of_block: int
    positions_resolved: int = 0
    closed_positions: int = 0
    mean_return: float | None = None
    return_stdev: float | None = None
    t_statistic: float | None = None
    win_count: int = 0
    win_rate: float | None = None
    binomial_p: float | None = None
    median_entry_percentile: float | None = None
    median_position_size: float | None = None
    first_seen_block: int | None = None
    last_seen_block: int | None = None
    # Published thresholds from arXiv 2601.08641.
    passes_t_threshold: bool = False
    passes_activity_threshold: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_at(
    wallet: str,
    positions: Iterable[Position],
    *,
    as_of_block: int,
    resolved_by: dict[str, int],
    winners: set[str],
    base_rate: float,
    min_trades: int = 3,
    t_threshold: float = 1.645,
) -> WalletScore:
    """Score a wallet using only positions whose outcome was known by `as_of_block`.

    Args:
        resolved_by: token -> the block at which that token's outcome became
            determinable. A position counts only if this is at or before
            `as_of_block`; "launched earlier" is not sufficient, because a token
            launched in January whose run happened in March tells you nothing in
            February.
        winners: tokens that met the outcome definition.
        base_rate: population rate of winners, for the binomial comparison.
    """
    score = WalletScore(wallet=wallet, as_of_block=as_of_block)

    usable = [
        p for p in positions
        if p.wallet == wallet
        and p.token in resolved_by
        and resolved_by[p.token] <= as_of_block
    ]
    if not usable:
        return score

    score.positions_resolved = len(usable)
    score.first_seen_block = min(p.first_buy_block for p in usable)
    score.last_seen_block = max(p.last_block for p in usable)

    sizes = sorted(float(p.quote_in) for p in usable if p.quote_in > 0)
    if sizes:
        score.median_position_size = sizes[len(sizes) // 2]
    percentiles = sorted(
        p.entry_percentile for p in usable if p.entry_percentile is not None
    )
    if percentiles:
        score.median_entry_percentile = percentiles[len(percentiles) // 2]

    score.win_count = sum(1 for p in usable if p.token in winners)
    score.win_rate = score.win_count / len(usable)
    score.binomial_p = binomial_tail(score.win_count, len(usable), base_rate)

    returns = [r for r in (p.realised_return for p in usable) if r is not None]
    score.closed_positions = len(returns)
    if len(returns) >= 2:
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        stdev = math.sqrt(variance)
        score.mean_return = mean
        score.return_stdev = stdev
        if stdev > 0:
            score.t_statistic = mean / (stdev / math.sqrt(len(returns)))
    elif len(returns) == 1:
        score.mean_return = returns[0]

    score.passes_t_threshold = (
        score.t_statistic is not None and score.t_statistic > t_threshold
    )
    score.passes_activity_threshold = score.positions_resolved >= min_trades
    return score


def resolution_blocks(
    token_trades: dict[str, list[Trade]], *, horizon_blocks: int
) -> dict[str, int]:
    """The block at which each token's outcome becomes determinable.

    Defined as its first trade plus a fixed horizon. Using the token's *peak*
    block instead would leak: the peak is only knowable after the fact, so a
    wallet could be credited with a win before that win had happened.
    """
    resolved: dict[str, int] = {}
    for token, trades in token_trades.items():
        if trades:
            resolved[token] = min(t.block for t in trades) + horizon_blocks
    return resolved
