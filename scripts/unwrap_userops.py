#!/usr/bin/env python3
"""Attribute bundled ERC-4337 swaps to the smart account, not the bundler.

`tx.from` fixes the router problem — the swap log's `recipient` is the router on
a routed trade — but it introduces a second one. Under account abstraction the
transaction is sent by a **bundler**, which batches many unrelated users'
UserOperations into one call to the EntryPoint. Keyed on `tx.from`, every user
in a batch collapses into the bundler's address.

On WALLET this looked like a discovery and was not. Ten of twelve apparent
"stealth distributors" shared the `0x4337` address prefix, which reads as one
entity spreading across addresses until you notice 4337 is the ERC number: they
are bundlers, and the prefix is a vanity choice advertising that. 99 of them,
8.4% of the week's swaps.

**The attribution rule.** The EntryPoint emits `UserOperationEvent` *after* each
operation executes, so within one transaction a swap log belongs to the first
UserOperationEvent at a higher log index. Ordering by log index is what makes
this exact rather than a guess; a swap with no later UserOperationEvent in its
transaction is left with the bundler, and counted, rather than assigned to a
neighbouring account.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

from rhc.rpc import Rpc, RpcError

# UserOperationEvent(bytes32 indexed userOpHash, address indexed sender,
#                    address indexed paymaster, uint256 nonce, bool success,
#                    uint256 actualGasCost, uint256 actualGasUsed)
TOPIC_USEROP = "0x49628fd1471006c1482da88028e9ce4dbb080b815c9b0344d39e5a8e6ec1419f"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trades", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--prefix", default="0x4337",
                   help="only unwrap senders matching this; '' means all")
    args = p.parse_args()

    t = pq.read_table(args.trades)
    c = {n: t.column(n).to_pylist() for n in t.column_names}
    n = len(c["block"])

    targets = [i for i in range(n)
               if not args.prefix or c["wallet"][i].startswith(args.prefix)]
    by_block = defaultdict(list)
    for i in targets:
        by_block[c["block"][i]].append(i)
    print(f"{len(targets):,} of {n:,} swaps to unwrap, in {len(by_block):,} blocks",
          file=sys.stderr, flush=True)

    fixed = unmatched = failed = 0
    with Rpc(min_interval=0.2) as rpc:
        for k, (block, rows) in enumerate(sorted(by_block.items())):
            try:
                ops = rpc.get_logs(from_block=block, to_block=block,
                                   topics=[[TOPIC_USEROP]])
            except RpcError:
                failed += len(rows)
                continue
            # log_index -> account, for every UserOperationEvent in the block
            events = sorted((int(lg.get("logIndex", "0x0"), 16),
                             "0x" + lg["topics"][2][-40:]) for lg in ops
                            if len(lg.get("topics") or []) > 2)
            for i in rows:
                li = c["log_index"][i]
                nxt = next((acct for idx, acct in events if idx > li), None)
                if nxt:
                    c["wallet"][i] = nxt
                    fixed += 1
                else:
                    unmatched += 1
            if k and k % 200 == 0:
                print(f"  {k:,}/{len(by_block):,} blocks", file=sys.stderr, flush=True)

    print(f"reassigned {fixed:,}; {unmatched:,} had no later UserOperationEvent "
          f"(left with the bundler); {failed:,} lookups failed", file=sys.stderr)
    pq.write_table(pa.table(c), args.out)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
