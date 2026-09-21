#!/usr/bin/env python3
"""Daily snapshot of the chain's most active pools.

The lockup scan builds a forward series for ~176 stock tokens. This builds the
other half: a daily record of whichever memecoins are actually trading, with the
metrics that exist at snapshot time.

**Why a daily snapshot rather than a historical scan.** Several catalogue metrics
have no history available anywhere — pool composition, holder distribution as of
a past date, social handles as of a past date. Those only exist going forward,
from the day capture starts. A historical scan cannot recover them, so every day
not captured is permanently lost.

Uses GeckoTerminal rather than the RPC, so it can run while a bulk scan holds
the node, and so the daily job stays cheap enough to never be worth skipping.

Usage:
    python scripts/daily_movers.py --pages 5
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rhc.premium import GeckoTerminal, Pool, PremiumError

STABLES = {"USDG", "USDC", "USDT", "WETH"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=5,
                        help="Pages of pools to walk; 20 pools per page")
    parser.add_argument("--min-volume", type=float, default=1000.0,
                        help="Skip pools below this 24h volume in USD")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    if args.out is None:
        args.out = Path("data/movers") / f"{now:%Y-%m-%d}.jsonl"
    args.out.parent.mkdir(parents=True, exist_ok=True)

    captured_at = now.isoformat()
    seen: set[str] = set()
    written = 0

    with GeckoTerminal() as gecko, args.out.open("w") as handle:
        for page in range(1, args.pages + 1):
            try:
                payload = gecko.get("/networks/robinhood/pools", page=page)
            except PremiumError as exc:
                print(f"  page {page} failed: {exc}", file=sys.stderr)
                continue
            items = payload.get("data") or []
            if not items:
                break

            for item in items:
                pool = Pool.from_api(item)
                if pool.address in seen or pool.volume_24h_usd < args.min_volume:
                    continue
                seen.add(pool.address)

                attrs = item.get("attributes", {})
                relationships = item.get("relationships") or {}
                base_id = (relationships.get("base_token") or {}).get("data", {}).get("id", "")
                changes = attrs.get("price_change_percentage") or {}
                transactions = attrs.get("transactions") or {}
                h24 = transactions.get("h24") or {}

                record = {
                    "captured_at": captured_at,
                    "pool": pool.address,
                    "name": pool.name,
                    "base_token": base_id.split("_")[-1],
                    "base_symbol": pool.base_symbol,
                    "quote_symbol": pool.quote_symbol,
                    "quote_is_stable": pool.quote_symbol.upper() in STABLES,
                    "price_usd": pool.base_price_usd,
                    "reserve_usd": pool.reserve_usd,
                    "volume_24h_usd": pool.volume_24h_usd,
                    "pool_created_at": attrs.get("pool_created_at"),
                    "dex": (relationships.get("dex") or {}).get("data", {}).get("id"),
                    # Volume relative to depth is the catalogue's 3.7 and needs
                    # no history: a pool turning over many times its own
                    # reserves in a day is behaving very differently from one
                    # that is not.
                    "volume_to_reserve": (
                        pool.volume_24h_usd / pool.reserve_usd if pool.reserve_usd > 0 else None
                    ),
                }
                for horizon in ("m5", "m15", "m30", "h1", "h6", "h24"):
                    record[f"price_change_{horizon}"] = changes.get(horizon)
                    bucket = transactions.get(horizon) or {}
                    record[f"buys_{horizon}"] = bucket.get("buys")
                    record[f"sells_{horizon}"] = bucket.get("sells")
                    record[f"buyers_{horizon}"] = bucket.get("buyers")
                    record[f"sellers_{horizon}"] = bucket.get("sellers")
                # Unique-wallet count against raw transaction count is the
                # cheapest wash-trading tell available (catalogue 3.1).
                buys, buyers = h24.get("buys") or 0, h24.get("buyers") or 0
                record["h24_buys_per_buyer"] = buys / buyers if buyers else None

                handle.write(json.dumps(record) + "\n")
                written += 1

    print(f"{written} pools above ${args.min_volume:,.0f} volume -> {args.out}",
          file=sys.stderr)
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
