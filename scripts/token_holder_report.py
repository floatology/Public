#!/usr/bin/env python3
"""Replay a token's transfers into balances, then describe the accumulation.

Built on `scripts/token_transfers.py` output, which is the only ledger on this
chain that survives contact with routers (see that script's docstring).

Three things this answers that a swap ledger cannot:

**Who actually holds the float.**  Balances are replayed from genesis and
checked against `balanceOf` at head, so a claimed holder is a real one.

**When they built.**  Each address's position is tracked per era, so a wallet
that accumulated before a move is separated from one that bought the move.  The
era boundaries are arguments, named before the run, not fitted afterwards.

**Whether they bought it or were given it.**  Received-from-pool is a purchase;
received-from-an-address is a transfer, and a cohort that grew by transfer is
usually one entity spreading across addresses, or an airdrop, and in neither
case is it demand.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow.parquet as pq

from rhc.rpc import Rpc

WEI = 10**18
ZERO = "0x0000000000000000000000000000000000000000"
DEAD = "0x000000000000000000000000000000000000dead"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transfers", type=Path, required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--pool", action="append", default=[],
                        help="pool address; repeatable. Transfers to/from these "
                             "are trades, everything else is a movement.")
    parser.add_argument("--supply", type=float, default=1e9)
    parser.add_argument("--price-now", type=float, required=True)
    parser.add_argument("--split-block", type=int, action="append", default=[])
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--audit", type=int, default=25,
                        help="addresses to re-check against balanceOf")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    pools = {p.lower() for p in args.pool}
    bounds = sorted(args.split_block)

    def era_of(block: int) -> int:
        return sum(1 for b in bounds if block >= b)

    table = pq.read_table(args.transfers)
    cols = {n: table.column(n).to_pylist() for n in table.column_names}
    n = len(cols["block"])
    order = sorted(range(n), key=lambda i: (cols["block"][i], cols["log_index"][i]))
    print(f"{n:,} transfers, blocks {min(cols['block']):,}-{max(cols['block']):,}\n")

    bal = defaultdict(int)
    era_delta = defaultdict(lambda: defaultdict(int))
    bought = defaultdict(int)       # units received from a pool
    sold = defaultdict(int)         # units sent to a pool
    recv_moved = defaultdict(int)   # units received from a non-pool address
    sent_moved = defaultdict(int)
    first_seen: dict[str, int] = {}
    last_seen: dict[str, int] = {}

    for i in order:
        src, dst, v, blk = cols["src"][i], cols["dst"][i], int(cols["value"][i]), cols["block"][i]
        if v == 0:
            continue
        e = era_of(blk)
        if src != ZERO:
            bal[src] -= v
            era_delta[src][e] -= v
            (sold if dst in pools else sent_moved)[src] += v
            last_seen[src] = blk
            first_seen.setdefault(src, blk)
        if dst != ZERO:
            bal[dst] += v
            era_delta[dst][e] += v
            (bought if src in pools else recv_moved)[dst] += v
            last_seen[dst] = blk
            first_seen.setdefault(dst, blk)

    holders = sorted((a for a in bal if bal[a] > 0), key=lambda a: bal[a], reverse=True)
    total = sum(bal[a] for a in holders)
    print(f"{len(holders):,} addresses with a positive balance; "
          f"replayed supply {total/WEI/args.supply:.4%} of nominal\n")

    # -- audit: the replay must agree with the chain ------------------------
    # Pinned to the scan's last block, not "latest". A pool's balance changes
    # with every trade, so auditing an actively traded address against a head
    # that has moved on reports a mismatch that is only elapsed time.
    if args.audit:
        at_block = max(cols["block"])
        print(f"=== balance audit ({args.audit} addresses vs balanceOf "
              f"at block {at_block:,}) ===")
        step = max(1, len(holders) // args.audit)
        sample = holders[::step][:args.audit]
        bad = 0
        with Rpc() as rpc:
            for a in sample:
                data = "0x70a08231" + "0" * 24 + a[2:]
                raw = rpc.call("eth_call", [{"to": args.token, "data": data}, hex(at_block)])
                chain = int(raw, 16) if raw and raw != "0x" else 0
                if chain != bal[a]:
                    bad += 1
                    print(f"  MISMATCH {a}  replay={bal[a]/WEI:,.4f}  chain={chain/WEI:,.4f}")
        if bad:
            print(f"  {bad}/{len(sample)} disagree — the ledger is unusable.\n")
            return 1
        print(f"  all {len(sample)} agree exactly\n")

    # -- concentration ------------------------------------------------------
    print("=== concentration ===")
    cum = 0
    marks = (1, 5, 10, 20, 50, 100, 500)
    for i, a in enumerate(holders, 1):
        cum += bal[a]
        if i in marks:
            print(f"  top {i:>4}: {cum/WEI/args.supply:>7.2%} of supply")
    print()

    label = {}
    for p in pools:
        label[p] = "POOL"
    label[DEAD] = "BURN"

    print(f"=== top {args.top} holders ===")
    hdr = (f"{'#':>3} {'address':42} {'share':>7} {'value':>11} "
           f"{'from pool':>10} {'from addr':>10} {'to pool':>10} {'to addr':>10}")
    if bounds:
        hdr += "  " + " ".join(f"{'e'+str(i):>8}" for i in range(len(bounds) + 1))
    print(hdr)
    for i, a in enumerate(holders[:args.top], 1):
        share = bal[a] / WEI / args.supply
        line = (f"{i:>3} {a:42} {share:>6.2%} ${bal[a]/WEI*args.price_now:>10,.0f} "
                f"{bought[a]/WEI/args.supply:>9.2%} {recv_moved[a]/WEI/args.supply:>9.2%} "
                f"{sold[a]/WEI/args.supply:>9.2%} {sent_moved[a]/WEI/args.supply:>9.2%}")
        if bounds:
            line += "  " + " ".join(
                f"{era_delta[a][e]/WEI/args.supply:>+8.2%}" for e in range(len(bounds) + 1))
        if a in label:
            line += f"  <- {label[a]}"
        print(line)

    # -- era cohorts --------------------------------------------------------
    if bounds:
        print("\n=== who added supply in each era (excluding pools and burn) ===")
        skip = pools | {DEAD}
        for e in range(len(bounds) + 1):
            adds = [(era_delta[a][e], a) for a in bal
                    if a not in skip and era_delta[a][e] > 0]
            drops = [(era_delta[a][e], a) for a in bal
                     if a not in skip and era_delta[a][e] < 0]
            up = sum(v for v, _ in adds) / WEI / args.supply
            down = -sum(v for v, _ in drops) / WEI / args.supply
            era_from = "launch" if e == 0 else f"block {bounds[e-1]:,}"
            print(f"  era {e} (from {era_from}): {len(adds):,} addresses added "
                  f"{up:.2%}, {len(drops):,} shed {down:.2%}, net {up-down:+.2%}")
            top = sorted(adds, reverse=True)[:5]
            for v, a in top:
                still = bal[a] / WEI / args.supply
                print(f"      +{v/WEI/args.supply:>6.2%}  {a}  (holds {still:.2%} now)")

    if args.out:
        payload = {
            "transfers": n,
            "holders": len(holders),
            "top": [
                {"address": a, "share": bal[a] / WEI / args.supply,
                 "value_usd": bal[a] / WEI * args.price_now,
                 "from_pool": bought[a] / WEI / args.supply,
                 "from_address": recv_moved[a] / WEI / args.supply,
                 "to_pool": sold[a] / WEI / args.supply,
                 "to_address": sent_moved[a] / WEI / args.supply,
                 "first_block": first_seen.get(a), "last_block": last_seen.get(a),
                 "era_delta": {str(e): era_delta[a][e] / WEI / args.supply
                               for e in range(len(bounds) + 1)}}
                for a in holders[:300]
            ],
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
