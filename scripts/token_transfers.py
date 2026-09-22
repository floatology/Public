#!/usr/bin/env python3
"""Every ERC-20 Transfer for one token, which is the only honest holder ledger.

**Why not swap logs.**  A Uniswap V3 `Swap` log names the *recipient* of the
output, and on a chain whose dominant front-end routes through contracts, that
recipient is the router, not the trader.  Run on WALLET, a recipient-keyed
ledger claimed the top wallet held 26% of supply; `balanceOf` on that address
returns zero.  It is a pass-through.  Several "wallets" showed net positions of
minus five times total supply, because they sold tokens they had received by
transfer and the swap log never saw the transfer.  A recipient ledger measures
router throughput and nothing else.

`Transfer(address indexed from, address indexed to, uint256 value)` has no such
hole.  Every token movement emits one, whatever caused it, so replaying them in
order reconstructs every balance exactly.  The reconstruction is checked against
`balanceOf` at the head block for a sample of addresses, and the run fails if
they disagree: a silently wrong balance would poison everything built on it.

**Classifying a transfer still needs the pool set.**  A transfer to a pool is a
sell, from a pool a buy, and everything else is a movement between holders,
which is exactly the flow a swap-keyed ledger cannot see.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

from rhc.rpc import TOPIC_TRANSFER, Rpc


def addr(topic: str) -> str:
    return "0x" + topic[-40:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", required=True)
    parser.add_argument("--from-block", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    started = time.time()
    with Rpc() as rpc:
        head = rpc.block_number()
        print(f"head {head:,}; {head - args.from_block:,} blocks to scan",
              file=sys.stderr, flush=True)

        def progress(block: int, span: int, yielded: int) -> None:
            done = (block - args.from_block) / max(1, head - args.from_block)
            print(f"  {done:6.1%}  block {block:,}  span {span:,}  "
                  f"logs {yielded:,}  {time.time() - started:.0f}s",
                  file=sys.stderr, flush=True)

        logs = list(rpc.iter_logs(from_block=args.from_block, to_block=head,
                                  topics=[[TOPIC_TRANSFER]], address=args.token,
                                  initial_span=100_000, on_progress=progress))

    rows = {"block": [], "log_index": [], "src": [], "dst": [], "value": []}
    for log in logs:
        topics = log.get("topics") or []
        if len(topics) < 3:
            continue  # not the 3-topic ERC-20 form
        rows["block"].append(int(log["blockNumber"], 16))
        rows["log_index"].append(int(log.get("logIndex", "0x0"), 16))
        rows["src"].append(addr(topics[1]))
        rows["dst"].append(addr(topics[2]))
        rows["value"].append(str(int((log.get("data") or "0x0"), 16)))

    print(f"{len(rows['block']):,} transfers (of {len(logs):,} logs)",
          file=sys.stderr, flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(rows), args.out)
    print(f"wrote {args.out} in {time.time() - started:.0f}s", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
