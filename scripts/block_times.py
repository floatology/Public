#!/usr/bin/env python3
"""Build a block-to-timestamp index by sampling, and prove its error bound.

A trade table keyed on block numbers cannot answer "when", and fetching a
timestamp per event is not affordable: WALLET's swaps alone touch on the order
of 200,000 distinct blocks, at one RPC call each.

This chain produces blocks on a fixed ~100ms cadence, so timestamps are very
nearly linear in block number and interpolation between sparse anchors is
accurate. **"Very nearly" is not an argument, so the error is measured**: after
building the index, random blocks are fetched and compared against the
interpolation, and the run prints the worst case it found.

The first measurement came back at 2,023 seconds, which is not a small error and
is not evenly spread. The chain's first three million blocks were produced at
anything from 0.05 to 4 blocks per second while it ramped up; from about block
4,000,000 onward the rate sits in a 9.85-10.06 band. So the index is accurate
where every token in this project lives and wrong in a region none of them
reach, and `--verify-from` measures the part that is actually used rather than
reporting a worst case drawn from dead history.

**For fine timing, use block deltas, not these timestamps.** Interpolation error
is a slowly varying offset, so it cancels almost entirely in the difference
between two nearby trades: 100 blocks apart is 10 seconds apart to within a
fraction of a percent, whatever the absolute error. Behavioural work — the gap
variance that separates a bot from a person — should therefore be done on block
numbers, and these timestamps reserved for saying when something happened.

Anchors are stored, so extending the index later re-fetches nothing.
"""
from __future__ import annotations

import argparse
import bisect
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.rpc import Rpc


class BlockClock:
    """Linear interpolation between sampled (block, timestamp) anchors."""

    def __init__(self, anchors: list[list[int]]):
        self.blocks = [a[0] for a in anchors]
        self.times = [a[1] for a in anchors]

    def at(self, block: int) -> int:
        i = bisect.bisect_left(self.blocks, block)
        if i < len(self.blocks) and self.blocks[i] == block:
            return self.times[i]
        if i == 0:
            i = 1
        if i >= len(self.blocks):
            i = len(self.blocks) - 1
        b0, b1 = self.blocks[i - 1], self.blocks[i]
        t0, t1 = self.times[i - 1], self.times[i]
        if b1 == b0:
            return t0
        return int(t0 + (t1 - t0) * (block - b0) / (b1 - b0))


def load(path: Path) -> list[list[int]]:
    return json.loads(path.read_text())["anchors"] if path.exists() else []


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("data/tokens/block_times.json"))
    p.add_argument("--step", type=int, default=25_000)
    p.add_argument("--verify-from", type=int, default=4_000_000,
                   help="verify only at or above this block; below it the "
                        "chain had not reached a steady rate")
    p.add_argument("--verify", type=int, default=40)
    p.add_argument("--seed", type=int, default=20260927)
    args = p.parse_args()

    anchors = load(args.out)
    have = {a[0] for a in anchors}
    with Rpc() as rpc:
        head = rpc.block_number()
        want = list(range(1, head, args.step)) + [head]
        todo = [b for b in want if b not in have]
        print(f"head {head:,}; {len(have):,} anchors held, {len(todo):,} to fetch",
              file=sys.stderr, flush=True)
        for k, b in enumerate(todo):
            anchors.append([b, rpc.block_timestamp(b)])
            if k and k % 50 == 0:
                anchors.sort()
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps({"anchors": anchors}))
                print(f"  {k:,}/{len(todo):,}", file=sys.stderr, flush=True)
        anchors.sort()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"anchors": anchors}))

        clock = BlockClock(anchors)
        rng = random.Random(args.seed)
        worst = worst_early = 0
        for _ in range(args.verify):
            b = rng.randint(anchors[0][0], head)
            real = rpc.block_timestamp(b)
            err = abs(clock.at(b) - real)
            if b >= args.verify_from:
                worst = max(worst, err)
            else:
                worst_early = max(worst_early, err)
        print(f"{len(anchors):,} anchors; worst error above block "
              f"{args.verify_from:,}: {worst}s (below it: {worst_early}s, "
              f"where the chain had not reached a steady block rate)",
              file=sys.stderr)
    print(json.dumps({"anchors": len(anchors), "worst_error_seconds": worst,
                      "verify_from": args.verify_from,
                      "worst_error_below_verify_from": worst_early}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
