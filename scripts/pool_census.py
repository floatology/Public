#!/usr/bin/env python3
"""Census every pool creation on the chain, from genesis.

This is the population frame H0's power analysis needs: how many tokens exist,
launched when, so the positive-class size can be estimated rather than guessed.

Uses the official archive RPC (free, unauthenticated, back to block 1). Writes
Parquet for DuckDB. See docs/04-execution-and-data-findings.md §1.

Usage:
    python scripts/pool_census.py                    # full chain
    python scripts/pool_census.py --to-block 5000000 # partial
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

from rhc.rpc import TOPIC_V2_PAIR_CREATED, TOPIC_V3_POOL_CREATED, Rpc

# In both PairCreated and PoolCreated the two tokens are indexed topics 1 and 2.
TOPIC_TO_KIND = {TOPIC_V2_PAIR_CREATED: "v2", TOPIC_V3_POOL_CREATED: "v3"}


def _topic_address(topic: str) -> str:
    """A 32-byte indexed topic holding an address -> checksum-less 0x address."""
    return "0x" + topic[-40:]


def _write(rows: dict[str, list], out: Path) -> None:
    pq.write_table(pa.table(rows), out, compression="zstd")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-block", type=int, default=1)
    parser.add_argument("--to-block", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("data/parquet/pool_creations.parquet"))
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows: dict[str, list] = {
        "block": [], "pool": [], "token0": [], "token1": [], "factory": [], "kind": [],
    }
    started = time.time()

    with Rpc() as rpc:
        to_block = args.to_block or rpc.block_number()
        print(f"scanning blocks {args.from_block:,} -> {to_block:,}", file=sys.stderr)

        last_checkpoint = [0]

        def progress(end: int, span: int, yielded: int) -> None:
            pct = (end - args.from_block) / max(1, to_block - args.from_block) * 100
            print(
                f"  {pct:5.1f}%  block {end:,}  span {span:,}  pools {yielded:,}"
                f"  {time.time() - started:.0f}s",
                file=sys.stderr,
            )
            # Checkpoint periodically: a multi-minute scan that dies at 90%
            # should not have to start over.
            if yielded - last_checkpoint[0] >= 25_000:
                _write(rows, args.out)
                last_checkpoint[0] = yielded

        for log in rpc.iter_logs(
            from_block=args.from_block,
            to_block=to_block,
            topics=[[TOPIC_V2_PAIR_CREATED, TOPIC_V3_POOL_CREATED]],
            on_progress=progress,
        ):
            topics = log.get("topics") or []
            if len(topics) < 3:
                continue
            rows["block"].append(int(log["blockNumber"], 16))
            rows["token0"].append(_topic_address(topics[1]))
            rows["token1"].append(_topic_address(topics[2]))
            rows["factory"].append(log["address"])
            rows["kind"].append(TOPIC_TO_KIND.get(topics[0], "?"))
            # V2 puts the pair address in data; V3 puts pool last in data too.
            data = log.get("data") or "0x"
            rows["pool"].append("0x" + data[-40:] if len(data) >= 42 else "")

    _write(rows, args.out)
    elapsed = time.time() - started
    print(
        f"\n{len(rows['block']):,} pool creations -> {args.out} in {elapsed:.0f}s",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
