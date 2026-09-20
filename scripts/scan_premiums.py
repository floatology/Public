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
from contextlib import contextmanager
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


@contextmanager
def _single_instance(path: Path):
    """Refuse to run if another scan is already writing this file.

    Two concurrent scans append interleaved rows under different timestamps,
    which silently duplicates the day's snapshot. That happened on 2026-09-20
    and had to be cleaned up afterwards.
    """
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(
            f"another scan holds {lock}; remove it if no scan is running"
        ) from None
    try:
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        yield
    finally:
        lock.unlink(missing_ok=True)


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
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Override the output file; default partitions by month",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap universe size")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    captured_at = now.isoformat()
    # One file per run day. Appending every run to a shared file makes a git
    # rebase conflict inevitable: two runs append different lines at the same
    # end-of-file, and CI cannot resolve that unattended -- it happened on the
    # first scheduled run and left the working tree unmerged, which no amount
    # of push-retry recovers from. A new file per day never collides, stays
    # small, and reads back identically via a glob.
    if args.out is None:
        args.out = Path("data/premiums") / f"{now:%Y-%m-%d}.jsonl"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _ping_healthcheck("start")

    written = 0
    failed: list[str] = []
    try:
        with _single_instance(args.out), Blockscout() as bs, GeckoTerminal() as gt:
            universe = _universe(bs, args.tickers, args.limit)
            print(f"scanning {len(universe)} tokens", file=sys.stderr)

            # A full rescan replaces the day; a partial one appends. Always
            # truncating lets a two-ticker spot check destroy that day's whole
            # snapshot, which is exactly what happened once.
            full_scan = not args.tickers and args.limit is None
            with args.out.open("w" if full_scan else "a") as handle:
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
                                "live_lockup_ratio": reading.live_lockup_ratio,
                                "dormant_share": reading.dormant_share,
                                "live_memecoin_pool_reserve_usd": reading.live_memecoin_pool_reserve_usd,
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
