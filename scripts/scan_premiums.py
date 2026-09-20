#!/usr/bin/env python3
"""Snapshot Stock Token premiums and float lockup; append one row per token.

This builds the H1 time series. No free source carries historical liquidity
composition (see docs/03-open-questions.md §1.4), so the lockup signal exists
only from the day this starts running. Gaps are unrecoverable — run it daily.

Output is append-only JSONL, one row per token per run, tracked in git so that
CI runs persist without external storage.

Usage:
    python scripts/scan_premiums.py                 # full discovered universe
    python scripts/scan_premiums.py NVDA HIMS SPY   # specific tickers
    python scripts/scan_premiums.py --limit 30      # cap the universe (testing)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx

from rhc.chain import Blockscout, BlockscoutError
from rhc.premium import GeckoTerminal, PremiumError, measure
from rhc.stocktokens import StockToken, discover_all, resolve


def _universe(client: Blockscout, tickers: list[str], limit: int | None) -> list[StockToken]:
    """Resolve the tickers to scan, or discover the full canonical universe."""
    if tickers:
        resolved = []
        for ticker in tickers:
            token = resolve(client, ticker)
            if token is None:
                print(f"{ticker:6} no canonical token; skipped", file=sys.stderr)
            else:
                resolved.append(token)
        return resolved
    tokens = discover_all(client)
    return tokens[:limit] if limit else tokens


def _ping_healthcheck(state: str = "") -> None:
    """Dead-man's-switch ping. A silent workflow failure is indistinguishable
    from 'nothing interesting happened', which would quietly corrupt the series.
    """
    url = os.environ.get("HEALTHCHECK_URL")
    if not url:
        return
    try:
        httpx.get(f"{url.rstrip('/')}/{state}" if state else url, timeout=10)
    except httpx.HTTPError:
        pass  # never fail the run over a monitoring ping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*", help="Specific tickers; default is all")
    parser.add_argument("--out", type=Path, default=Path("data/premiums.jsonl"))
    parser.add_argument("--limit", type=int, default=None, help="Cap universe size")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat()
    _ping_healthcheck("start")

    written = 0
    failed: list[str] = []
    try:
        with Blockscout() as bs, GeckoTerminal() as gt:
            universe = _universe(bs, args.tickers, args.limit)
            print(f"scanning {len(universe)} tokens", file=sys.stderr)

            with args.out.open("a") as handle:
                for token in universe:
                    try:
                        reading = measure(
                            gt,
                            symbol=token.symbol,
                            address=token.address,
                            total_supply=token.total_supply,
                            reference_price_usd=token.blockscout_exchange_rate,
                        )
                    except (PremiumError, BlockscoutError) as exc:
                        # One bad token must not cost the whole day's snapshot.
                        failed.append(token.symbol)
                        print(f"{token.symbol:6} FAILED: {exc}", file=sys.stderr)
                        continue

                    handle.write(
                        json.dumps(
                            {
                                "captured_at": captured_at,
                                "symbol": reading.symbol,
                                "address": reading.address,
                                "onchain_price_usd": reading.onchain_price_usd,
                                "reference_price_usd": reading.reference_price_usd,
                                "premium_pct": reading.premium_pct,
                                "total_supply": reading.total_supply,
                                "stable_pool_reserve_usd": reading.stable_pool_reserve_usd,
                                "memecoin_pool_reserve_usd": reading.memecoin_pool_reserve_usd,
                                "lockup_ratio": reading.lockup_ratio,
                                "memecoin_pairs": list(reading.memecoin_pairs),
                            }
                        )
                        + "\n"
                    )
                    handle.flush()  # survive an interrupted run
                    written += 1
    except Exception:
        _ping_healthcheck("fail")
        raise

    print(f"\nwrote {written} rows to {args.out}", file=sys.stderr)
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)

    # A run that captured almost nothing is a failure even without an exception.
    if written == 0:
        _ping_healthcheck("fail")
        return 1
    _ping_healthcheck()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
