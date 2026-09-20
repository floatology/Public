#!/usr/bin/env python3
"""Measure the round-trip execution cost of memecoins against pool depth.

Establishes the liquidity floor below which a token is untradable regardless of
what its chart shows. See docs/04-execution-findings.md.

Usage:
    python scripts/execution_floor.py <stock-token-address> [--clip 500]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rhc.chain import USDG
from rhc.execution import Aggregator, ExecutionError, NoRouteError
from rhc.premium import GeckoTerminal


def paired_memecoins(gecko: GeckoTerminal, stock_token: str, symbol: str) -> list[tuple]:
    """Memecoins pairing against this stock token, deepest pool first."""
    found: dict[str, tuple[str, str, float]] = {}
    for pool in gecko.token_pools(stock_token):
        attrs = pool["attributes"]
        name = attrs.get("name") or ""
        if f"/ {symbol}" not in name:
            continue
        base_id = (
            (pool.get("relationships") or {})
            .get("base_token", {})
            .get("data", {})
            .get("id", "")
        )
        base_symbol = name.split("/")[0].strip()
        address = base_id.split("_")[-1]
        reserve = float(attrs.get("reserve_in_usd") or 0)
        if address and reserve > found.get(base_symbol, ("", "", 0.0))[2]:
            found[base_symbol] = (base_symbol, address, reserve)
    return sorted(found.values(), key=lambda row: -row[2])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock_token", help="Canonical stock token address")
    parser.add_argument("--symbol", required=True, help="Stock token ticker, e.g. HIMS")
    parser.add_argument("--clip", type=float, default=500.0)
    parser.add_argument("--out", type=Path, default=Path("data/execution_costs.jsonl"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat()

    with GeckoTerminal() as gt, Aggregator() as ag, args.out.open("a") as handle:
        candidates = paired_memecoins(gt, args.stock_token, args.symbol)
        print(f"{len(candidates)} memecoins paired against {args.symbol}", file=sys.stderr)
        for symbol, address, reserve in candidates:
            record = {
                "captured_at": captured_at,
                "symbol": symbol,
                "address": address,
                "paired_against": args.symbol,
                "pool_reserve_usd": reserve,
                "clip_usd": args.clip,
            }
            try:
                trip = ag.round_trip(
                    symbol=symbol, token=address, quote_token=USDG, clip_usd=args.clip
                )
            except (NoRouteError, ExecutionError) as exc:
                record |= {"round_trip_cost_pct": None, "error": str(exc)[:200]}
                print(f"{symbol:14} {reserve:>12,.0f}  UNROUTABLE", file=sys.stderr)
            else:
                record |= {
                    "round_trip_cost_pct": trip.total_cost_pct,
                    "is_tradable": trip.is_tradable,
                    "hops": trip.buy.hops,
                }
                flag = "" if trip.is_tradable else "  <-- UNTRADABLE"
                print(
                    f"{symbol:14} {reserve:>12,.0f}  {trip.total_cost_pct:>7.2f}%{flag}",
                    file=sys.stderr,
                )
            handle.write(json.dumps(record) + "\n")
            handle.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
