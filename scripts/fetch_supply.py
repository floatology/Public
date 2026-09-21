#!/usr/bin/env python3
"""Total supply for every token in the trade archive, via eth_call.

This exists to remove survivorship bias from the market-cap work.

The GeckoTerminal study can only see pools an aggregator lists **today**, so a
token that crossed $250k and died is absent from it by construction. The
extraction archives are different: they sample from the chain's own census of
pool creations, so they contain the dead alongside the living, in their true
proportion.

What they lack is supply. GeckoTerminal hands over `fdv_usd` and a price, from
which supply falls out; the chain does not volunteer it. `totalSupply()` does,
for one `eth_call` per token.

**The arithmetic needs less than it looks like.** A trade's raw ratio is
`quote_amount / base_amount`, and market cap is that price times supply:

    cap = (quote_raw / base_raw) x (supply_raw / 10^base_decimals)
          x 10^(base_decimals - quote_decimals) x quote_usd
        = (quote_raw / base_raw) x supply_raw / 10^quote_decimals x quote_usd

The base token's decimals cancel. Only the **quote** side's decimals are
needed, and those are known constants. So one call per token is enough and no
`decimals()` lookup is required.

**Supply is read once, at the current block.** A token that minted or burned
since launch has its early market cap misstated — overstated if it minted,
understated if it burned. `rhc.contracts` finds mint functions routinely, so
this is a real limitation rather than a hypothetical one, and it is the same
limitation the GeckoTerminal reconstruction carries.

Usage:
    python scripts/fetch_supply.py --trades "data/parquet/trades*.parquet"
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb

from rhc.rpc import Rpc, RpcError

TOTAL_SUPPLY_SELECTOR = "0x18160ddd"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", default="data/parquet/trades*.parquet")
    parser.add_argument("--out", type=Path, default=Path("data/token_supply.json"))
    parser.add_argument("--progress-every", type=int, default=250)
    args = parser.parse_args()

    if not sorted(glob.glob(args.trades)):
        print(f"no trade archive matches {args.trades!r}", file=sys.stderr)
        return 1

    con = duckdb.connect()
    tokens = [
        row[0] for row in con.execute(
            "SELECT DISTINCT token FROM read_parquet(?) WHERE token IS NOT NULL",
            [args.trades],
        ).fetchall()
    ]
    print(f"{len(tokens):,} distinct tokens in the archive", file=sys.stderr)

    known: dict[str, str | None] = {}
    if args.out.exists():
        known = json.loads(args.out.read_text())
        print(f"  {len(known):,} already known", file=sys.stderr)

    pending = [t for t in tokens if t not in known]
    print(f"  {len(pending):,} to fetch", file=sys.stderr)

    started = time.time()
    failures = 0
    with Rpc() as rpc:
        for index, token in enumerate(pending, start=1):
            try:
                raw = rpc.call("eth_call",
                               [{"to": token, "data": TOTAL_SUPPLY_SELECTOR}, "latest"])
            except RpcError:
                # A token that does not answer totalSupply is recorded as a
                # null rather than skipped, so a later run does not retry it
                # forever and so the count of unreadable tokens stays visible.
                known[token] = None
                failures += 1
                continue
            if not raw or raw == "0x":
                known[token] = None
                failures += 1
                continue
            try:
                known[token] = str(int(raw, 16))
            except ValueError:
                known[token] = None
                failures += 1

            if index % args.progress_every == 0:
                rate = index / max(1e-9, time.time() - started)
                print(f"  {index:,}/{len(pending):,}  {rate:.1f}/s  "
                      f"{failures} unreadable", file=sys.stderr)
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(known))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(known))
    usable = sum(1 for v in known.values() if v)
    print(f"\n  {usable:,} of {len(known):,} tokens returned a supply "
          f"({failures:,} unreadable this run)", file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
