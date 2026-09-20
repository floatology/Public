"""Execution modelling — what a trade would actually fill at.

The master document defines every outcome on *price*. Nothing in it models
whether a trade could have transacted there. A token that prints a 10x on $3,000
of liquidity is a screenshot, not a trade: your entry moves it, your exit moves
it more, and the printed high may represent a $40 fill.

This module supplies the missing piece for **forward** testing. Liquidity on this
chain is fragmented across at least eight DEX protocols (Uniswap V3 and V4,
bankr, pons-v2, up-v3, ramses-v3, giga-v3, alandale-cl), and V4 hooks can alter
swap maths arbitrarily, so reconstructing depth per-protocol is a large and
error-prone job. A routing aggregator has already solved it: KyberSwap's
aggregator covers chain 4663 and returns an *exact* executable amount across all
venues, with gas priced in USD. A representative 500 USDG → HIMS quote routes
through five hops across five distinct DEXes — which is precisely the situation a
single-pool depth calculation would get wrong.

What this does NOT do: historical quotes. Aggregator routes do not exist for past
blocks, so backtesting still requires per-protocol reconstruction. Given that no
free source carries historical liquidity composition anyway
(docs/03-open-questions.md §1.4), forward testing is the near-term path and this
is the right tool for it.

Costs included: routing across all venues, pool fees, price impact, and gas.
Costs deliberately excluded:
  * **Sandwich/MEV** — Arbitrum Orbit sequences FCFS from a *private* mempool;
    published rollup research finds sandwiching rare to absent. Excluded
    deliberately, not by oversight. Cross-layer (L1→L2 bridge) sandwiching and
    Timeboost ordering remain possible and are not modelled.
  * **Sell-side token tax** — a transfer-fee token yields less than the quote
    implies. `round_trip` reports the quoted figures; confirm a token is not
    fee-on-transfer before trusting them (ScanHood's sell simulation covers this).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

KYBER_BASE = "https://aggregator-api.kyberswap.com"
KYBER_CHAIN = "robinhood"

USDG_DECIMALS = 6


class ExecutionError(RuntimeError):
    """The aggregator could not price this trade."""


class NoRouteError(ExecutionError):
    """No route exists — the pair is unroutable at this size.

    This is itself a finding: a token the aggregator cannot route is one you
    cannot trade, whatever its chart shows.
    """


@dataclass(frozen=True)
class Quote:
    """One directional fill estimate from the aggregator."""

    amount_in_raw: int
    amount_out_raw: int
    amount_in_usd: float
    amount_out_usd: float
    gas_usd: float
    hops: int
    exchanges: tuple[str, ...]

    @property
    def slippage_pct(self) -> float:
        """Value lost between input and output, before gas, as a percentage.

        Positive means value was lost (fees plus price impact). Negative means
        the output was worth more than the input, which happens when the pair is
        genuinely dislocated rather than when the trade was free.
        """
        if self.amount_in_usd <= 0:
            return 0.0
        return (1.0 - self.amount_out_usd / self.amount_in_usd) * 100.0


@dataclass(frozen=True)
class RoundTrip:
    """Buy-then-sell cost for a fixed clip, as a fraction of the amount risked."""

    symbol: str
    clip_usd: float
    buy: Quote
    sell: Quote

    @property
    def gross_return_pct(self) -> float:
        """Return on the round trip before gas, at unchanged market price.

        Measured in **raw quote-token units** — USDG in, USDG out — not in the
        aggregator's USD figures. The token amounts are exact; the USD legs come
        from the aggregator's own price oracle and the two legs can be priced a
        moment apart, which produces spurious sub-percent "profits" on a trade
        that cannot be profitable by construction. Using raw units removes that
        noise entirely.

        For an efficiently-priced pair this is negative and approximately twice
        the one-way cost. It is the floor a strategy must clear before any edge
        counts — the prior art's best exit policy, 'sell immediately', returned
        -3.45%, which was exactly this number and nothing else.
        """
        if self.buy.amount_in_raw <= 0:
            return 0.0
        return (self.sell.amount_out_raw / self.buy.amount_in_raw - 1.0) * 100.0

    @property
    def total_cost_pct(self) -> float:
        """Round-trip cost including gas on both legs, as a percentage.

        Positive means the round trip costs you that much. Gas is the one leg
        that must come from the USD figures, since it is paid in ETH rather than
        the quote token; it is small enough here (cents) that oracle noise in it
        is immaterial.
        """
        if self.clip_usd <= 0:
            return 0.0
        gas = self.buy.gas_usd + self.sell.gas_usd
        return -self.gross_return_pct + (gas / self.clip_usd) * 100.0

    @property
    def is_tradable(self) -> bool:
        """Whether a round trip costs less than 10% of the clip.

        A deliberately loose gate. Its purpose is to exclude pairs where the
        clip itself moves the market so far that any measured 'return' is an
        artefact of the measurement.
        """
        return self.total_cost_pct < 10.0


@dataclass
class Aggregator:
    """KyberSwap aggregator client for chain 4663.

    Verified 2026-09-20: the chain slug is ``robinhood``; ``robinhoodchain``,
    ``rhc`` and ``4663`` all 404.
    """

    base_url: str = KYBER_BASE
    chain: str = KYBER_CHAIN
    min_interval: float = 0.6
    max_retries: int = 3
    timeout: float = 30.0
    _client: httpx.Client = field(init=False, repr=False)
    _last_request: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=f"{self.base_url}/{self.chain}/api/v1",
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": "rhc-research/0.1", "Accept": "application/json"},
        )

    def __enter__(self) -> Aggregator:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def quote(self, *, token_in: str, token_out: str, amount_in_raw: int) -> Quote:
        """Price one swap. Raises NoRouteError when the pair cannot be routed."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()
            try:
                response = self._client.get(
                    "/routes",
                    params={
                        "tokenIn": token_in,
                        "tokenOut": token_out,
                        "amountIn": str(amount_in_raw),
                    },
                )
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue

            if response.status_code >= 500 or response.status_code == 429:
                last_error = ExecutionError(f"HTTP {response.status_code}")
                time.sleep(2**attempt)
                continue

            try:
                payload = response.json()
            except ValueError as exc:
                raise ExecutionError("Non-JSON response from aggregator") from exc

            summary = (payload.get("data") or {}).get("routeSummary")
            if not summary:
                raise NoRouteError(
                    f"no route {token_in[:10]}->{token_out[:10]}: "
                    f"{payload.get('message') or response.status_code}"
                )
            route = summary.get("route") or []
            exchanges = tuple(hop.get("exchange", "") for leg in route for hop in leg)
            return Quote(
                amount_in_raw=int(summary.get("amountIn") or amount_in_raw),
                amount_out_raw=int(summary.get("amountOut") or 0),
                amount_in_usd=float(summary.get("amountInUsd") or 0.0),
                amount_out_usd=float(summary.get("amountOutUsd") or 0.0),
                gas_usd=float(summary.get("gasUsd") or 0.0),
                hops=len(route),
                exchanges=exchanges,
            )
        raise ExecutionError("Exhausted retries") from last_error

    def round_trip(
        self,
        *,
        symbol: str,
        token: str,
        quote_token: str,
        clip_usd: float,
        quote_decimals: int = USDG_DECIMALS,
    ) -> RoundTrip:
        """Price a buy-then-immediate-sell of `clip_usd` worth of `token`.

        The sell leg is priced on the *actual* output of the buy leg, not on a
        notional amount, so the two legs compose into a real round trip.
        """
        amount_in = int(clip_usd * 10**quote_decimals)
        buy = self.quote(token_in=quote_token, token_out=token, amount_in_raw=amount_in)
        if buy.amount_out_raw <= 0:
            raise NoRouteError(f"{symbol}: buy leg returned zero output")
        sell = self.quote(
            token_in=token, token_out=quote_token, amount_in_raw=buy.amount_out_raw
        )
        return RoundTrip(symbol=symbol, clip_usd=clip_usd, buy=buy, sell=sell)
