"""Robinhood Chain access layer.

Blockscout is the free official explorer for chain 4663. It sits behind a
Cloudflare challenge that rejects default HTTP client headers, so every request
carries a browser User-Agent and a same-origin Referer. This is the workaround
documented in the prior-art `robinhood-screener` source and verified working
2026-09-20.

Rate limits are "sized for humans" with no SLA, so the client self-throttles and
retries on 429/5xx with backoff. Deep pagination is slow by design here; use
this for per-token detail, not for population-wide scans.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

CHAIN_ID = 4663
BLOCKSCOUT_BASE = "https://robinhoodchain.blockscout.com"

# Official RPC. Verified 2026-09-20 to serve UNAUTHENTICATED ARCHIVE access:
# eth_getLogs reaches block 1 (2026-04-30), capped at 10,000 results per call
# rather than by block range. This is the population-scan data source, and it
# replaces Dune (paid since 2026-09-10) and SQD (does not carry this chain).
# Note publicnode's mirror rejects archive queries without a personal token.
RPC_URL = "https://rpc.mainnet.chain.robinhood.com"
RPC_MAX_LOGS = 10_000

# Canonical infrastructure addresses, from docs.robinhood.com/chain/contracts/.
WETH = "0x0Bd7D308f8E1639FAb988df18A8011f41EAcAD73"
USDG = "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168"

# Decimals for every asset used as the quote side of a pool. This lives here
# rather than in each script because two copies of it drifted once already, and
# a wrong decimal scale is the bug class that produced a median price ratio of
# 22,668x -- it does not look like an error, it looks like a finding.
QUOTE_DECIMALS = {
    USDG.lower(): 6,
    WETH.lower(): 18,
}

# Used to put WETH-quoted volumes on the same scale as USDG-quoted ones.
# It is a constant rather than a live price on purpose: a historical scan
# spanning months has no single correct spot rate, and the alternative --
# marking each trade at its own moment -- needs a price series this chain
# does not publish. The number therefore affects comparability between
# quote assets and nothing else, so it must be IDENTICAL everywhere. Two
# scripts defaulting to 2576 and 4000 produced volumes differing by 55%
# for the same pool, which is why it lives here now.
DEFAULT_ETH_USD = 2576.0


class UnknownQuoteAsset(KeyError):
    """A pool quoted in an asset whose decimals are not known.

    Guessing 18 here would silently rescale every value for that asset. The
    scripts stop instead.
    """


def quote_scale(address: str) -> int:
    """The divisor that turns raw units of a quote asset into whole units."""
    try:
        return 10 ** QUOTE_DECIMALS[address.lower()]
    except KeyError:
        raise UnknownQuoteAsset(
            f"no decimals recorded for quote asset {address}; add it to "
            f"rhc.chain.QUOTE_DECIMALS rather than assuming 18"
        ) from None

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class BlockscoutError(RuntimeError):
    """Blockscout returned an unusable response after retries."""


@dataclass
class Blockscout:
    """Rate-limited Blockscout v2 API client.

    Args:
        min_interval: seconds enforced between requests. Blockscout publishes no
            limit; 0.4s (~150/min) has been stable and stays well clear of the
            Cloudflare challenge re-triggering.
        max_retries: attempts per request before raising.
    """

    base_url: str = BLOCKSCOUT_BASE
    min_interval: float = 0.4
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
                "User-Agent": _BROWSER_UA,
                "Referer": f"{self.base_url}/",
                "Accept": "application/json",
            },
        )

    def __enter__(self) -> Blockscout:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        """GET a Blockscout v2 path, retrying transient failures.

        Raises:
            BlockscoutError: on a non-JSON body (usually an un-cleared Cloudflare
                challenge page) or after exhausting retries.
        """
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            try:
                response = self._client.get(path, params=params or None)
            except httpx.HTTPError as exc:  # network-level, worth retrying
                last_error = exc
            else:
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = BlockscoutError(f"HTTP {response.status_code} for {path}")
                elif response.status_code >= 400:
                    raise BlockscoutError(f"HTTP {response.status_code} for {path}")
                else:
                    try:
                        return response.json()
                    except ValueError as exc:
                        # Cloudflare serves an HTML challenge with a 200 status.
                        raise BlockscoutError(
                            f"Non-JSON response for {path}; Cloudflare challenge likely active"
                        ) from exc
            time.sleep(2**attempt)
        raise BlockscoutError(f"Exhausted retries for {path}") from last_error

    def paginate(self, path: str, *, max_pages: int = 50, **params: Any) -> Iterator[dict]:
        """Yield items across Blockscout's cursor pagination.

        Blockscout returns a `next_page_params` object that is fed back verbatim
        as query parameters. `max_pages` is a required guard: deep pagination is
        slow here and unbounded loops will hang a workflow.
        """
        page_params: dict[str, Any] = dict(params)
        for _ in range(max_pages):
            payload = self.get(path, **page_params)
            yield from payload.get("items", [])
            next_params = payload.get("next_page_params")
            if not next_params:
                return
            page_params = {**params, **next_params}

    def stats(self) -> dict[str, Any]:
        """Chain-level stats. Doubles as a cheap connectivity/challenge probe."""
        return self.get("/api/v2/stats")

    def search(self, query: str) -> list[dict[str, Any]]:
        """Search tokens/addresses by name, symbol, or address."""
        return self.get("/api/v2/search", q=query).get("items", [])

    def token(self, address: str) -> dict[str, Any]:
        return self.get(f"/api/v2/tokens/{address}")

    def token_holders(self, address: str, *, max_pages: int = 5) -> list[dict[str, Any]]:
        return list(self.paginate(f"/api/v2/tokens/{address}/holders", max_pages=max_pages))
