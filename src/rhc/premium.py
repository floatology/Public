"""Stock-token premium and float-lockup measurement.

Two related measurements, both computable from live data with no history:

**Premium** — the gap between a Stock Token's on-chain price and its underlying
equity's real price. The premium itself is *not* directly tradable by a retail
participant (see docs/02-stock-token-premium-findings.md: minting is restricted
to a single Authorised Participant, so only that party can sell supply into a
premium). It is measured here as a *diagnostic*, not a trade signal.

**Float lockup** — the share of a Stock Token's supply sitting inside liquidity
pools paired against non-stock tokens (i.e. memecoins). This is the causal
driver of the BONER/HIMS episode: BONER paired against tokenized HIMS rather
than a stablecoin, so every BONER buy pulled HIMS into the pool and locked it
there. Lockup is measurable in real time and leads the premium, which makes it
the more useful of the two.

On-chain prices come from DEX pool state via GeckoTerminal rather than from an
explorer's `exchange_rate` field — Blockscout's field for these tokens tracks
the *real* equity price, so using it would silently compute a premium of zero.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

import httpx

GECKOTERMINAL_BASE = "https://api.geckoterminal.com/api/v2"
NETWORK = "robinhood"

# Quote assets that denominate a "clean" USD price for a stock token. A pool
# against one of these prices the stock token against money; a pool against a
# memecoin prices it against sentiment.
STABLE_QUOTES = {"USDG", "USDC", "USDT"}

# Minimum stable-pool depth before an on-chain price is treated as meaningful.
# Set from measurement: round-trip execution cost explodes below roughly $50k of
# reserves (0.90% at $2.4M, 96.10% at $20k), so a price quoted from less than
# this is not one anybody could transact against.
MIN_PRICING_LIQUIDITY_USD = 50_000.0


class PremiumError(RuntimeError):
    """GeckoTerminal returned an unusable response."""


@dataclass
class GeckoTerminal:
    """Rate-limited GeckoTerminal client.

    The keyless tier is documented at ~30 requests/minute per IP; the default
    interval stays under that with margin.
    """

    base_url: str = GECKOTERMINAL_BASE
    min_interval: float = 2.2
    max_retries: int = 4
    timeout: float = 30.0
    _client: httpx.Client = field(init=False, repr=False)
    _last_request: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "rhc-research/0.1",
                "Accept": "application/json;version=20230302",
            },
        )

    def __enter__(self) -> GeckoTerminal:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()
            try:
                response = self._client.get(path, params=params or None)
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = PremiumError(f"HTTP {response.status_code} for {path}")
                    time.sleep(2 ** (attempt + 2))  # 429 here needs a real cooldown
                    continue
                if response.status_code >= 400:
                    raise PremiumError(f"HTTP {response.status_code} for {path}")
                return response.json()
            time.sleep(2**attempt)
        raise PremiumError(f"Exhausted retries for {path}") from last_error

    def token_info(self, address: str) -> dict[str, Any]:
        """Token metadata: social handles, developer holding, honeypot flag.

        This endpoint carries several catalogue items the block explorer does
        not expose at all — the explorer's token metadata has no social,
        developer or honeypot fields, so a lookup against it can never find a
        Telegram channel however well the code is written.

        Fields of interest: telegram_handle, twitter_handle, websites,
        developer_address, developer_holding_percentage, is_honeypot,
        mint_authority, freeze_authority, holders, gt_score.
        """
        payload = self.get(f"/networks/{NETWORK}/tokens/{address}/info")
        return (payload.get("data") or {}).get("attributes") or {}

    def token_pools(self, address: str) -> list[dict[str, Any]]:
        """All pools containing this token, as GeckoTerminal returns them."""
        payload = self.get(f"/networks/{NETWORK}/tokens/{address}/pools")
        return payload.get("data", [])


@dataclass(frozen=True)
class Pool:
    """A DEX pool, normalised out of GeckoTerminal's response shape."""

    address: str
    name: str
    base_symbol: str
    quote_symbol: str
    base_price_usd: float | None
    reserve_usd: float
    volume_24h_usd: float

    @property
    def quote_is_stable(self) -> bool:
        return self.quote_symbol.upper() in STABLE_QUOTES

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> Pool:
        attrs = item.get("attributes", {})
        name = attrs.get("name") or ""
        # GeckoTerminal pool names are "BASE / QUOTE <fee>"; split off the fee.
        parts = [p.strip() for p in name.split("/")]
        base_symbol = parts[0] if parts else ""
        quote_symbol = parts[1].split()[0] if len(parts) > 1 and parts[1] else ""
        return cls(
            address=attrs.get("address") or "",
            name=name,
            base_symbol=base_symbol,
            quote_symbol=quote_symbol,
            base_price_usd=_as_float(attrs.get("base_token_price_usd")),
            reserve_usd=_as_float(attrs.get("reserve_in_usd")) or 0.0,
            volume_24h_usd=_as_float((attrs.get("volume_usd") or {}).get("h24")) or 0.0,
        )


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class PremiumReading:
    """A point-in-time premium and float-lockup measurement for one stock token."""

    symbol: str
    address: str
    onchain_price_usd: float | None
    reference_price_usd: float | None
    total_supply: float
    stable_pool_reserve_usd: float
    memecoin_pool_reserve_usd: float
    live_memecoin_pool_reserve_usd: float
    deepest_stable_pool: str | None
    memecoin_pairs: tuple[str, ...]

    @property
    def premium_pct(self) -> float | None:
        """On-chain price as a percentage above (+) or below (-) the real stock.

        Returns None when the stable-pool depth is below MIN_PRICING_LIQUIDITY_USD.
        A price quoted from a near-empty pool is not a price, and without this
        guard the metric is dominated by noise: a full-universe scan on
        2026-09-20 produced an apparent +151% "premium" on AMAT from a stable
        pool holding $5,669, alongside six more beyond +/-6% all sitting on pools
        under $22k. None were dislocations; all were illiquid prints.
        """
        if not self.onchain_price_usd or not self.reference_price_usd:
            return None
        if self.stable_pool_reserve_usd < MIN_PRICING_LIQUIDITY_USD:
            return None
        return (self.onchain_price_usd / self.reference_price_usd - 1.0) * 100.0

    @property
    def priced_reliably(self) -> bool:
        """Whether this token has enough stable-pool depth to quote a price."""
        return self.stable_pool_reserve_usd >= MIN_PRICING_LIQUIDITY_USD

    @property
    def lockup_ratio(self) -> float | None:
        """Memecoin-paired reserves as a share of all this token's pooled value.

        High lockup is the BONER/HIMS structure: supply captured in pools that
        pair the stock token against a memecoin, where it cannot be sold back
        into the stable market without unwinding the memecoin position.

        Prefer `live_lockup_ratio` for signalling. This raw figure counts dead
        pools and is therefore trivially inflated by seeding a large one-sided
        position that nobody trades.
        """
        total = self.stable_pool_reserve_usd + self.memecoin_pool_reserve_usd
        if total <= 0:
            return None
        return self.memecoin_pool_reserve_usd / total

    @property
    def live_lockup_ratio(self) -> float | None:
        """Lockup counting only memecoin pools with non-zero 24h volume.

        This is the signalling metric. The raw ratio can be hijacked by a single
        dormant pool: on 2026-09-20 USAR showed 99.0% lockup on $10.2M of
        memecoin-paired reserves, of which **98% sat in one `tornadoes / USAR`
        pool holding $9.75M at zero 24h volume.** Filtering on liveness puts it
        at 69.3%, and the $10.2M headline at $244k.

        That distinction matters because a large dormant pool is the signature
        of seeded or wash liquidity rather than a genuine corner — the exact
        pattern a naive signal would rank first. Every other top-lockup token
        measured that day was 0% dormant, so this guard costs nothing on
        genuine cases and removes the one false positive.
        """
        total = self.stable_pool_reserve_usd + self.live_memecoin_pool_reserve_usd
        if total <= 0:
            return None
        return self.live_memecoin_pool_reserve_usd / total

    @property
    def dormant_share(self) -> float | None:
        """Fraction of memecoin-paired reserves sitting in zero-volume pools."""
        if self.memecoin_pool_reserve_usd <= 0:
            return None
        return 1.0 - (
            self.live_memecoin_pool_reserve_usd / self.memecoin_pool_reserve_usd
        )


def measure(
    gecko: GeckoTerminal,
    *,
    symbol: str,
    address: str,
    total_supply: float,
    reference_price_usd: float | None,
) -> PremiumReading:
    """Measure one stock token's premium and float lockup from live pool state.

    Args:
        reference_price_usd: the real equity price. Supply this from an
            independent feed (Finnhub). Passing None yields a reading with
            lockup populated and premium None.
    """
    pools = [Pool.from_api(item) for item in gecko.token_pools(address)]
    stable = [p for p in pools if p.quote_is_stable and p.base_symbol.upper() == symbol.upper()]
    # Pools where the stock token is the *quote* side are memecoin pairings:
    # the memecoin is base, the stock token is what gets locked up.
    memecoin = [p for p in pools if p.quote_symbol.upper() == symbol.upper()]

    deepest = max(stable, key=lambda p: p.reserve_usd, default=None)
    return PremiumReading(
        symbol=symbol,
        address=address,
        onchain_price_usd=deepest.base_price_usd if deepest else None,
        reference_price_usd=reference_price_usd,
        total_supply=total_supply,
        stable_pool_reserve_usd=sum(p.reserve_usd for p in stable),
        memecoin_pool_reserve_usd=sum(p.reserve_usd for p in memecoin),
        live_memecoin_pool_reserve_usd=sum(
            p.reserve_usd for p in memecoin if p.volume_24h_usd > 0
        ),
        deepest_stable_pool=deepest.name if deepest else None,
        memecoin_pairs=tuple(sorted({p.base_symbol for p in memecoin})),
    )


def scan(
    gecko: GeckoTerminal,
    tokens: Iterable[tuple[str, str, float, float | None]],
) -> list[PremiumReading]:
    """Measure a batch of (symbol, address, total_supply, reference_price)."""
    return [
        measure(
            gecko,
            symbol=symbol,
            address=address,
            total_supply=supply,
            reference_price_usd=reference,
        )
        for symbol, address, supply, reference in tokens
    ]
