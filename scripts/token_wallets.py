#!/usr/bin/env python3
"""Per-wallet accumulation analysis for one token, from its own swap logs.

Everything else in this project works on a *sample* of pools, because the chain
carries hundreds of thousands of them and a census of trades is not affordable.
This does the opposite: one token, every swap in its main pool, every wallet.

**What it can see and what it cannot.**  The swap log names the *recipient* of
each trade, which for a router-mediated swap is the trader's own address and for
an aggregator-mediated one is the aggregator's.  It cannot see a wallet that
accumulated by transfer rather than by buying, and it cannot see the same person
split across ten addresses — `rhc.clusters` scores that separately, from timing
and size coincidence, against a null of how often unrelated wallets would
overlap by chance.

**`--resolve-senders` is what makes the trader column real.**  The swap log's
`recipient` topic is the router on a routed trade, and on a sample of 14 recent
WALLET swaps it matched the transaction's own sender on only 6.  `tx.from` is
the trader in all 14, and the addresses it yields are the ones DexScreener
prints in its TRADER column.  Resolving it costs one `eth_getTransactionByHash`
per swap, so it is affordable for a window of recent activity and not for a
token's whole history — 263,408 swaps at the client's own rate limit is about
eleven hours.  For whole-history holdings use `token_transfers.py` instead,
which gets exact balances without any per-trade lookup.

**The net-position ledger is the point.**  A wallet that bought $50k and sold
$49k of it is not accumulating, however large its buy volume looks in a
leaderboard.  Positions here are tracked in base units (tokens), so a wallet's
net holding is what it actually still owns from pool activity, and its cost
basis is the quote it paid net of what it took back out.

Usage:
    python scripts/token_wallets.py --token 0x... --pool 0x... --protocol v3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

from rhc.features import decode_v2_swaps, decode_v3_swaps
from rhc.rpc import TOPIC_V2_SWAP, TOPIC_V3_SWAP, Rpc, RpcError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", required=True)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--protocol", choices=("v2", "v3"), default="v3")
    parser.add_argument("--created-block", type=int, required=True)
    parser.add_argument("--quote-is-token0", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resolve-senders", type=int, default=0, metavar="N",
                        help="replace the recipient with the transaction's own "
                             "sender for the last N swaps. One RPC call each, so "
                             "this is for a window, not a history.")
    args = parser.parse_args()

    topic = TOPIC_V2_SWAP if args.protocol == "v2" else TOPIC_V3_SWAP
    decode = decode_v2_swaps if args.protocol == "v2" else decode_v3_swaps

    started = time.time()
    with Rpc() as rpc:
        head = rpc.block_number()
        print(f"head {head:,}; scanning from {args.created_block:,} "
              f"({head - args.created_block:,} blocks)", file=sys.stderr)

        def progress(block: int, span: int, yielded: int) -> None:
            done = (block - args.created_block) / max(1, head - args.created_block)
            print(f"  {done:6.1%}  block {block:,}  span {span:,}  "
                  f"logs {yielded:,}  {time.time() - started:.0f}s", file=sys.stderr)

        logs = list(rpc.iter_logs(from_block=args.created_block, to_block=head,
                                  topics=[[topic]], address=args.pool,
                                  initial_span=200_000, on_progress=progress))

    print(f"{len(logs):,} swap logs", file=sys.stderr)
    trades = decode(logs, quote_is_token0=args.quote_is_token0)
    print(f"{len(trades):,} decoded trades", file=sys.stderr)

    senders: list[str] = [t.wallet for t in trades]
    if args.resolve_senders:
        # Log order and trade order agree only while the decoder drops nothing,
        # so pair them by (block, logIndex) rather than by position.
        by_key = {(int(lg["blockNumber"], 16), int(lg.get("logIndex", "0x0"), 16)):
                  lg["transactionHash"] for lg in logs}
        window = range(max(0, len(trades) - args.resolve_senders), len(trades))
        replaced = failed = 0
        # A failed lookup falls back to the recipient rather than aborting: on a
        # 12,708-swap window a single exhausted retry would otherwise throw away
        # forty minutes of completed work. Failures are counted and reported, so
        # a run that silently degraded is visible rather than assumed clean.
        with Rpc(min_interval=0.2) as rpc:
            for pos, i in enumerate(window):
                tx_hash = by_key.get((trades[i].block, trades[i].log_index))
                if not tx_hash:
                    continue
                try:
                    tx = rpc.call("eth_getTransactionByHash", [tx_hash])
                except RpcError:
                    failed += 1
                    continue
                if not tx:
                    failed += 1
                    continue
                if tx["from"].lower() != senders[i].lower():
                    replaced += 1
                senders[i] = tx["from"].lower()
                if pos % 2000 == 0 and pos:
                    print(f"    resolved {pos:,}/{len(window):,} "
                          f"({failed:,} failed)", file=sys.stderr, flush=True)
        print(f"resolved {len(window)-failed:,} senders; {replaced:,} differed from "
              f"the swap recipient ({replaced/max(1,len(window)-failed):.0%}); "
              f"{failed:,} fell back to the recipient", file=sys.stderr)

    rows = {
        "block": [t.block for t in trades],
        "log_index": [t.log_index for t in trades],
        "wallet": senders,
        "is_buy": [t.is_buy for t in trades],
        "quote_amount": [str(t.quote_amount) for t in trades],
        "base_amount": [str(t.base_amount) for t in trades],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(rows), args.out)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
