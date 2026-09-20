"""Canonical Robinhood Stock Token discovery and identity verification.

Robinhood's own docs warn: "a token with a matching name/ticker but a different
contract address is not a Robinhood Stock Token." The master document records
the concrete version of this risk — the "IF" token had 21+ copycat contracts,
and screeners sorted by holder count or liquidity surfaced the *fakes* first,
because impersonators deliberately seed inflated numbers.

So identity here is never established by ticker. Blockscout exposes three
independent markers that impersonators cannot forge, because they are set by the
explorer operator rather than by the token contract:

  * ``is_verified_via_admin_panel`` — explorer-operator attestation.
  * an ``icon_url`` served from ``cdn.robinhood.com`` — Robinhood's own CDN.
  * ``priority`` > 0 — explorer-assigned ranking above ordinary tokens.

A token must satisfy the CDN marker (the strongest of the three, since it
requires Robinhood to have published the asset) before it is treated as
canonical. The others are recorded for audit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

from .chain import Blockscout

ROBINHOOD_CDN = "cdn.robinhood.com"

# Stock tokens are named "<Company> • Robinhood Token" on chain.
_STOCK_TOKEN_NAME = re.compile(r"Robinhood Token\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class StockToken:
    """A verified-canonical Robinhood Stock Token."""

    address: str
    symbol: str
    name: str
    total_supply_raw: str
    decimals: int
    verified_via_admin_panel: bool
    has_robinhood_cdn_icon: bool
    priority: int
    blockscout_exchange_rate: float | None
    circulating_market_cap: float | None

    @property
    def total_supply(self) -> float:
        """Supply in whole tokens.

        Note: Stock Tokens carry a share multiplier that adjusts the
        shares-per-token ratio while the raw balance stays static, so this is
        token count and NOT a share count. Do not use it as a float figure
        without applying the multiplier.
        """
        return int(self.total_supply_raw) / (10**self.decimals)

    @property
    def is_canonical(self) -> bool:
        """Whether this passed identity verification.

        The CDN-hosted icon is required. Admin-panel verification alone is not
        sufficient, since it is a weaker attestation than Robinhood publishing
        the asset on its own CDN.
        """
        return self.has_robinhood_cdn_icon

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _from_search_item(item: dict[str, Any]) -> StockToken | None:
    """Build a StockToken from a Blockscout search hit, or None if not a token."""
    if item.get("type") != "token" or item.get("token_type") != "ERC-20":
        return None
    address = item.get("address_hash")
    symbol = item.get("symbol")
    if not address or not symbol:
        return None
    icon_url = item.get("icon_url") or ""
    return StockToken(
        address=address,
        symbol=symbol,
        name=item.get("name") or "",
        total_supply_raw=str(item.get("total_supply") or "0"),
        # Blockscout search omits decimals; Robinhood Stock Tokens are 18dp.
        # resolve() re-reads this from the token endpoint where it is present.
        decimals=int(item.get("decimals") or 18),
        verified_via_admin_panel=bool(item.get("is_verified_via_admin_panel")),
        has_robinhood_cdn_icon=ROBINHOOD_CDN in icon_url,
        priority=int(item.get("priority") or 0),
        blockscout_exchange_rate=_coerce_float(item.get("exchange_rate")),
        circulating_market_cap=_coerce_float(item.get("circulating_market_cap")),
    )


def resolve(client: Blockscout, ticker: str) -> StockToken | None:
    """Resolve a ticker to its canonical Stock Token contract, or None.

    Returns None rather than a best guess when no candidate passes verification.
    A caller must never fall back to "the first search hit" — that is precisely
    the failure mode impersonators exploit.
    """
    candidates = [
        token
        for item in client.search(ticker)
        if (token := _from_search_item(item)) is not None
        and token.symbol.upper() == ticker.upper()
    ]
    canonical = [t for t in candidates if t.is_canonical]
    if not canonical:
        return None
    if len(canonical) > 1:
        # Should not happen; if it does, the identity markers are compromised
        # and a human needs to look rather than the code picking one.
        raise ValueError(
            f"{len(canonical)} tokens claim canonical identity for {ticker}: "
            + ", ".join(t.address for t in canonical)
        )
    token = canonical[0]
    # Re-read decimals from the token endpoint, which search does not return.
    detail = client.token(token.address)
    decimals = int(detail.get("decimals") or token.decimals)
    if decimals != token.decimals:
        token = StockToken(**{**token.to_dict(), "decimals": decimals})
    return token


def impostors(client: Blockscout, ticker: str) -> list[StockToken]:
    """Return non-canonical contracts claiming this ticker.

    Useful as a standing safety check: a rising impostor count on a ticker is
    itself a signal that the token is drawing enough attention to be worth
    impersonating.
    """
    return [
        token
        for item in client.search(ticker)
        if (token := _from_search_item(item)) is not None
        and token.symbol.upper() == ticker.upper()
        and not token.is_canonical
    ]
