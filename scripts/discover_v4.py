#!/usr/bin/env python3
"""Find the Uniswap V4 PoolManager and its event signatures, empirically.

V4 matters here: 18 of the top 60 pools by volume are V4, more than any other
venue, carrying $141M of roughly $703M daily at a median reserve of $124k --
deeper than V2's $59k. The census covers only V2 and V3, so this population is
currently invisible to everything downstream.

**V4 is structurally different.** Pools are not contracts. A V4 pool is a
32-byte `PoolId` inside a singleton `PoolManager`, so there is no per-pool
address to filter logs by and `pool_census.py`'s approach does not carry over.
Every pool's events arrive from the same contract with the pool id in a topic.

**The signatures are discovered, not hardcoded.** Computing them needs keccak,
which is not installed, and writing a constant from memory is the worst option
available: a wrong topic hash returns zero logs, which is indistinguishable in
the output from a chain with no V4 activity. Instead this takes a pool id that
GeckoTerminal has already reported as active, asks the node for any log
carrying that id in topic 1, and reads the PoolManager address and the topic
hashes off the answer. If the id is real and the pool traded, the result is
self-verifying; if nothing comes back, that is a real answer rather than a
silent constant error.

Usage:
    python scripts/discover_v4.py                    # ids from data/movers
    python scripts/discover_v4.py --pool-id 0x1234...
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.rpc import Rpc, RpcError


def pool_ids_from_movers(directory: Path, limit: int) -> list[tuple[str, str]]:
    """(pool_id, name) for V4 pools seen in the daily capture, busiest first."""
    rows: list[dict] = []
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    v4 = [
        r for r in rows
        if "v4" in (r.get("dex") or "") and len(str(r.get("pool") or "")) == 66
    ]
    v4.sort(key=lambda r: -(r.get("volume_24h_usd") or 0))
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for row in v4:
        if row["pool"] not in seen:
            seen.add(row["pool"])
            out.append((row["pool"], row.get("name", "?")))
        if len(out) >= limit:
            break
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movers", type=Path, default=Path("data/movers"))
    parser.add_argument("--pool-id", action="append", default=None)
    parser.add_argument("--candidates", type=int, default=3)
    parser.add_argument("--window-blocks", type=int, default=20_000,
                        help="how far back from the head to look. Kept small on "
                             "purpose: the node rate-limits globally, so this "
                             "must stay cheap enough to run beside other work.")
    parser.add_argument("--out", type=Path, default=Path("data/v4_discovery.json"))
    args = parser.parse_args()

    if args.pool_id:
        candidates = [(pid, "(given)") for pid in args.pool_id]
    else:
        candidates = pool_ids_from_movers(args.movers, args.candidates)
    if not candidates:
        print("no V4 pool ids found. Run scripts/daily_movers.py first, or pass "
              "--pool-id.", file=sys.stderr)
        return 1

    managers: Counter[str] = Counter()
    topics: Counter[str] = Counter()
    samples: list[dict] = []

    with Rpc() as rpc:
        head = rpc.block_number()
        start = max(1, head - args.window_blocks)
        print(f"searching blocks {start:,}-{head:,} for {len(candidates)} pool id(s)",
              file=sys.stderr)
        for pool_id, name in candidates:
            try:
                logs = list(rpc.iter_logs(from_block=start, to_block=head,
                                          topics=[None, pool_id],
                                          initial_span=args.window_blocks))
            except RpcError as exc:
                print(f"  {name}: {exc}", file=sys.stderr)
                continue
            print(f"  {name}: {len(logs)} log(s)", file=sys.stderr)
            for log in logs:
                address = (log.get("address") or "").lower()
                log_topics = log.get("topics") or []
                if address and log_topics:
                    managers[address] += 1
                    topics[log_topics[0]] += 1
                    if len(samples) < 5:
                        samples.append({
                            "address": address, "topic0": log_topics[0],
                            "topic_count": len(log_topics),
                            "data_words": max(0, (len(log.get("data", "0x")) - 2) // 64),
                        })

    if not managers:
        print("\nNo logs found for any candidate pool id in this window. That is "
              "\na real answer: either these pools did not trade in the last "
              f"{args.window_blocks:,} blocks, or the node does not serve "
              "\ntopic-only queries over that range. Widen --window-blocks "
              "before \nconcluding anything about V4 activity.", file=sys.stderr)
        return 1

    manager, manager_count = managers.most_common(1)[0]
    result = {
        "pool_manager": manager,
        "pool_manager_log_share": manager_count / sum(managers.values()),
        "all_addresses_seen": managers.most_common(),
        "topic0_frequencies": topics.most_common(),
        "sample_logs": samples,
        "window_blocks": args.window_blocks,
        "candidates": [pid for pid, _ in candidates],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")

    print(f"\n  PoolManager : {manager}", file=sys.stderr)
    print(f"  carries {result['pool_manager_log_share']:.0%} of the logs found",
          file=sys.stderr)
    print(f"  distinct topic0 values seen: {len(topics)}", file=sys.stderr)
    for topic, count in topics.most_common(6):
        shape = next((s for s in samples if s["topic0"] == topic), {})
        print(f"    {topic}  x{count}  "
              f"topics={shape.get('topic_count', '?')} "
              f"words={shape.get('data_words', '?')}", file=sys.stderr)
    print(f"\n  Topic identities are NOT inferred here. The shapes above narrow "
          f"\n  it -- V4 Swap carries id, sender and 6 data words -- but "
          f"confirming \n  which is Swap needs decoding a known trade against a "
          f"known amount.", file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
