#!/usr/bin/env python3
"""Scan Stock Token premiums and float lockup; append a timestamped snapshot.

Run daily. Builds the time series H1 needs, and captures pre-gas-cliff baseline
before 2026-09-29.

Usage:
    python scripts/scan_premiums.py [--out data/raw/premiums.jsonl] [TICKER ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rhc.chain import Blockscout
from rhc.premium import GeckoTerminal, measure
from rhc.stocktokens import resolve

DEFAULT_TICKERS = [
    "NVDA", "HIMS", "TSLA", "AAPL", "SPY", "GME", "AMC",
    "MSTR", "PLTR", "COIN", "GOOGL", "MSFT", "AMZN", "META",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="*", default=None)
    parser.add_argument("--out", type=Path, default=Path("data/raw/premiums.jsonl"))
    args = parser.parse_args()

    tickers = args.tickers or DEFAULT_TICKERS
    args.out.parent.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat()

    written = 0
    with Blockscout() as bs, GeckoTerminal() as gt, args.out.open("a") as handle:
        for ticker in tickers:
            token = resolve(bs, ticker)
            if token is None:
                print(f"{ticker:6} no canonical token; skipped", file=sys.stderr)
                continue
            reading = measure(
                gt,
                symbol=ticker,
                address=token.address,
                total_supply=token.total_supply,
                reference_price_usd=token.blockscout_exchange_rate,
            )
            record = {
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
            handle.write(json.dumps(record) + "\n")
            written += 1
            premium = reading.premium_pct
            lockup = reading.lockup_ratio
            print(
                f"{ticker:6} premium={premium:+.2f}%" if premium is not None
                else f"{ticker:6} premium=n/a",
                f"lockup={lockup:.1%}" if lockup is not None else "lockup=n/a",
                f"pairs={len(reading.memecoin_pairs)}",
            )
    print(f"\nwrote {written} rows to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
