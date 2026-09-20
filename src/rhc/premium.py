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
    deepest_stable_pool: str | None
    memecoin_pairs: tuple[str, ...]

    @property
    def premium_pct(self) -> float | None:
        """On-chain price as a percentage above (+) or below (-) the real stock."""
        if not self.onchain_price_usd or not self.reference_price_usd:
            return None
        return (self.onchain_price_usd / self.reference_price_usd - 1.0) * 100.0

    @property
    def lockup_ratio(self) -> float | None:
        """Memecoin-paired reserves as a share of all this token's pooled value.

        High lockup is the BONER/HIMS structure: supply captured in pools that
        pair the stock token against a memecoin, where it cannot be sold back
        into the stable market without unwinding the memecoin position.
        """
        total = self.stable_pool_reserve_usd + self.memecoin_pool_reserve_usd
        if total <= 0:
            return None
        return self.memecoin_pool_reserve_usd / total


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
