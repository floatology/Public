"""DexScreener client. Free, no key, and it carries two things GeckoTerminal does not.

The daily movers capture already pulls short-window price changes and per-window
buy/sell counts from GeckoTerminal. This is not a replacement for that; the two
sources are complementary and the overlap is a cross-check.

**What DexScreener adds:**

- **`marketCap` as a served field**, alongside `fdv`. Everything in
  `docs/17` reconstructed market cap as `price x totalSupply`, which forced the
  assumption that supply never changed — false for any token that mints after
  launch, and `rhc.contracts` finds mint functions routinely. A served market
  cap removes that assumption entirely for live tokens.
- **Liquidity split into base and quote sides**, so a pool seeded on one side is
  visible without a separate reserve read.

**What GeckoTerminal keeps:** m15 and m30 windows, *distinct buyer and seller
counts* rather than only trade counts — the unique-wallet measure that the wash
screen depends on — and an OHLCV history endpoint. DexScreener serves trade
counts but not trader counts, so it cannot answer "twenty buys from three
buyers" on its own.

**The batch endpoint takes up to 30 token addresses per call**, which makes a
wide sweep cheap: a few hundred calls covers everything either source tracks.
Tokens neither tracks return nothing, which is itself the signal that nobody is
watching them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

import httpx

BASE = "https://api.dexscreener.com"
MAX_BATCH = 30  # the endpoint's documented ceiling

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class DexScreenerError(RuntimeError):
    """The endpoint could not be read."""


@dataclass
class DexScreener:
    """Reader for the public DexScreener endpoints.

    Rate limits are published per endpoint (300/min for the token endpoints at
    the time of writing) and are generous relative to what a market sweep needs.
    `min_interval` is deliberately conservative anyway: being throttled midway
    through a sweep leaves a half-captured snapshot, which is worse than a slow
    complete one.
    """

    network: str = "robinhood"
    min_interval: float = 0.25
    timeout: float = 30.0
    max_retries: int = 3
    _client: httpx.Client = field(init=False, repr=False)
    _last_request: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            timeout=self.timeout, follow_redirects=True,
            headers={"User-Agent": _BROWSER_UA, "Accept": "application/json"},
        )

    def __enter__(self) -> DexScreener:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(self, path: str) -> Any:
        last: Exception | None = None
        for attempt in range(self.max_retries):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()
            try:
                response = self._client.get(f"{BASE}{path}")
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                last = DexScreenerError(f"HTTP {response.status_code}")
                time.sleep(2 ** (attempt + 1))
                continue
            if response.status_code >= 400:
                raise DexScreenerError(f"HTTP {response.status_code} for {path}")
            try:
                return response.json()
            except ValueError as exc:
                raise DexScreenerError(f"non-JSON response for {path}") from exc
        raise DexScreenerError(f"unreachable after {self.max_retries} tries: {last}")

    def pairs_for_tokens(self, addresses: Iterable[str]) -> Iterator[dict[str, Any]]:
        """Every tracked pair for these tokens, batched 30 at a time.

        A token the service does not track simply yields nothing. That is not an
        error and is not retried: it means no aggregator is watching it, which
        is worth recording rather than working around.
        """
        batch: list[str] = []
        for address in addresses:
            batch.append(address)
            if len(batch) == MAX_BATCH:
                yield from self._fetch_batch(batch)
                batch = []
        if batch:
            yield from self._fetch_batch(batch)

    def _fetch_batch(self, batch: list[str]) -> list[dict[str, Any]]:
        payload = self.get(f"/tokens/v1/{self.network}/{','.join(batch)}")
        if isinstance(payload, list):
            return payload
        return payload.get("pairs") or []

    def pairs_by_address(self, addresses: Iterable[str]) -> Iterator[dict[str, Any]]:
        """Pairs looked up by POOL address rather than token address.

        The token endpoint needs token addresses, which a pool census does not
        carry. This takes the pool addresses directly, which is what a census
        of pool-creation events actually gives you.
        """
        batch: list[str] = []
        for address in addresses:
            batch.append(address)
            if len(batch) == MAX_BATCH:
                yield from self._fetch_pairs(batch)
                batch = []
        if batch:
            yield from self._fetch_pairs(batch)

    def _fetch_pairs(self, batch: list[str]) -> list[dict[str, Any]]:
        payload = self.get(f"/latest/dex/pairs/{self.network}/{','.join(batch)}")
        pairs = (payload or {}).get("pairs")
        return pairs if isinstance(pairs, list) else []

    def search(self, query: str) -> list[dict[str, Any]]:
        """Free-text search, filtered to this network.

        The endpoint searches every chain, so the filter is applied here rather
        than trusted to the query.
        """
        payload = self.get(f"/latest/dex/search?q={query}")
        pairs = (payload or {}).get("pairs") or []
        return [p for p in pairs if p.get("chainId") == self.network]


def flatten(pair: dict[str, Any]) -> dict[str, Any]:
    """One pair's nested payload as a flat row, ready for a JSONL snapshot."""
    price_change = pair.get("priceChange") or {}
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    liquidity = pair.get("liquidity") or {}
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}

    row: dict[str, Any] = {
        "pair": pair.get("pairAddress"),
        "dex": pair.get("dexId"),
        "base_token": base.get("address"),
        "base_symbol": base.get("symbol"),
        "quote_symbol": quote.get("symbol"),
        "price_usd": pair.get("priceUsd"),
        # Served rather than reconstructed, which removes the constant-supply
        # assumption that docs/17 had to carry.
        "market_cap": pair.get("marketCap"),
        "fdv": pair.get("fdv"),
        "liquidity_usd": liquidity.get("usd"),
        "liquidity_base": liquidity.get("base"),
        "liquidity_quote": liquidity.get("quote"),
        "pair_created_at": pair.get("pairCreatedAt"),
        "url": pair.get("url"),
        # GeckoTerminal's token-info endpoint serves nothing at all for this
        # chain -- it returns empty even for USDG -- so DexScreener's info
        # block is the only source of websites and socials.
        "websites": [w.get("url") for w in ((pair.get("info") or {}).get("websites") or [])],
        "socials": [
            f"{s.get('type')}:{s.get('url')}"
            for s in ((pair.get("info") or {}).get("socials") or [])
        ],
        "has_image": bool((pair.get("info") or {}).get("imageUrl")),
    }
    for window in ("m5", "h1", "h6", "h24"):
        row[f"price_change_{window}"] = price_change.get(window)
        row[f"volume_{window}"] = volume.get(window)
        counts = txns.get(window) or {}
        row[f"buys_{window}"] = counts.get("buys")
        row[f"sells_{window}"] = counts.get("sells")
    return row
