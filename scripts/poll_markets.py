#!/usr/bin/env python3
"""Snapshot the whole market from both aggregators, on a schedule.

**The fields were never the problem. The sampling rate is.**

`daily_movers.py` already captures m5, m15, m30, h1, h6 and h24 price changes
with per-window buyer and seller counts. Captured once a day, a five-minute
price change is nearly useless: it describes five minutes out of 1,440 and
those five minutes are whichever ones the scheduler happened to land on. To use
short-window data you have to sample at short intervals and build the series
yourself, because neither source stores history at that resolution.

This does that. Each run appends one row per pair to a day-file, so repeated
runs accumulate a real time series rather than overwriting a snapshot.

**Both sources, because they are complementary and because agreement is
evidence.** DexScreener serves `marketCap` directly, which removes the
constant-supply assumption that every market-cap number in `docs/17` had to
carry. GeckoTerminal serves distinct buyer and seller counts, which the wash
screen needs and DexScreener does not provide — it gives trade counts only, so
it cannot tell twenty buys from three buyers apart from twenty buys from twenty.

Where both cover a pair, the overlap is a free cross-check on price and
liquidity, and a disagreement is worth more than either number alone.

Usage:
    python scripts/poll_markets.py                 # one snapshot
    python scripts/poll_markets.py --loop 300      # every 5 minutes
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.dexscreener import DexScreener, DexScreenerError, flatten
from rhc.premium import GeckoTerminal, PremiumError


def gecko_universe(gecko: GeckoTerminal, pages: int) -> list[dict]:
    pools: list[dict] = []
    for page in range(1, pages + 1):
        try:
            payload = gecko.get("/networks/robinhood/pools", page=page)
        except PremiumError:
            break
        items = payload.get("data") or []
        if not items:
            break
        pools.extend(items)
    return pools


def snapshot(out_dir: Path, pages: int, extra_tokens: list[str]) -> int:
    captured_at = datetime.now(timezone.utc)
    day = captured_at.strftime("%Y-%m-%d")
    stamp = captured_at.isoformat()
    rows: list[dict] = []

    with GeckoTerminal() as gecko:
        pools = gecko_universe(gecko, pages)
        tokens: list[str] = []
        for item in pools:
            attributes = item.get("attributes") or {}
            relationships = item.get("relationships") or {}
            base = ((relationships.get("base_token") or {}).get("data") or {}).get("id", "")
            address = base.split("_")[-1] if base else None
            if address:
                tokens.append(address)
            rows.append({
                "captured_at": stamp, "source": "geckoterminal",
                "pair": attributes.get("address"), "name": attributes.get("name"),
                "base_token": address,
                "price_usd": attributes.get("base_token_price_usd"),
                "fdv": attributes.get("fdv_usd"),
                "market_cap": attributes.get("market_cap_usd"),
                "liquidity_usd": attributes.get("reserve_in_usd"),
                "pair_created_at": attributes.get("pool_created_at"),
                **{f"price_change_{w}": (attributes.get("price_change_percentage") or {}).get(w)
                   for w in ("m5", "m15", "m30", "h1", "h6", "h24")},
                **{f"volume_{w}": (attributes.get("volume_usd") or {}).get(w)
                   for w in ("m5", "m15", "m30", "h1", "h6", "h24")},
                # Buyer and seller counts, which DexScreener does not serve and
                # the wash screen cannot work without.
                **{f"{k}_{w}": ((attributes.get("transactions") or {}).get(w) or {}).get(k)
                   for w in ("m5", "m15", "m30", "h1", "h6", "h24")
                   for k in ("buys", "sells", "buyers", "sellers")},
            })

    seen = {t for t in tokens if t}
    for token in extra_tokens:
        seen.add(token)
    if seen:
        try:
            with DexScreener() as dex:
                for pair in dex.pairs_for_tokens(sorted(seen)):
                    row = flatten(pair)
                    row["captured_at"] = stamp
                    row["source"] = "dexscreener"
                    rows.append(row)
        except DexScreenerError as exc:
            # A failed DexScreener sweep must not discard the GeckoTerminal rows
            # already in hand; a partial snapshot beats none.
            print(f"  dexscreener unavailable: {exc}", file=sys.stderr)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day}.jsonl"
    with path.open("a") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    by_source: dict[str, int] = {}
    for row in rows:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    print(f"  {captured_at.strftime('%H:%M:%S')}  {len(rows):,} rows "
          f"({by_source}) -> {path}", file=sys.stderr)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/markets"))
    parser.add_argument("--pages", type=int, default=10,
                        help="GeckoTerminal listing pages, 20 pools each")
    parser.add_argument("--loop", type=int, default=0,
                        help="seconds between snapshots; 0 runs once and exits")
    parser.add_argument("--max-snapshots", type=int, default=0,
                        help="stop after this many; 0 means run until killed")
    parser.add_argument("--tokens", type=Path, default=None,
                        help="optional file of extra token addresses, one per line")
    args = parser.parse_args()

    extra = []
    if args.tokens and args.tokens.exists():
        extra = [l.strip() for l in args.tokens.read_text().splitlines() if l.strip()]

    if not args.loop:
        snapshot(args.out, args.pages, extra)
        return 0

    taken = 0
    while True:
        started = time.monotonic()
        try:
            snapshot(args.out, args.pages, extra)
        except Exception as exc:  # a poller that dies on one bad response is useless
            print(f"  snapshot failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        taken += 1
        if args.max_snapshots and taken >= args.max_snapshots:
            return 0
        time.sleep(max(0.0, args.loop - (time.monotonic() - started)))


if __name__ == "__main__":
    raise SystemExit(main())
