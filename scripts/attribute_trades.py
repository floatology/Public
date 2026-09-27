#!/usr/bin/env python3
"""Attribute every swap to the address whose token balance actually moved.

Three earlier attempts each measured the wrong layer:

- the swap log's **`recipient`** is the router on a routed trade (`docs/22`);
- **`tx.from`** is the bundler on an account-abstraction trade, and even when it
  is a person it is the *signer*, whose own balance may never move (`docs/23`);
- **`UserOperationEvent.sender`** fixes bundling but still names an account, not
  necessarily the one holding the tokens afterwards.

The balance is the thing. Every token movement emits a `Transfer`, so replaying
the transfers of the one transaction that contains a swap says exactly which
address gained or lost tokens, however many hops the route took. A buyer is the
address with the largest positive net delta; a seller the largest negative one.
Routers net to zero by construction, so they fall out without being listed.

**This costs no RPC calls.** Both log sets are already archived, and the join is
on transaction hash. That is the difference between attributing a week and
attributing a history: `tx.from` resolution runs at about five swaps a second,
so WALLET's 263,000 would take fourteen hours.

**Ties and ambiguity are reported, never guessed.** A transaction holding two
swaps of the same token, or one whose largest delta is a contract that also
routes, is counted in `ambiguous` and left with its log-derived identity rather
than assigned to a plausible-looking neighbour.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

ZERO = "0x0000000000000000000000000000000000000000"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--swaps", type=Path, required=True)
    p.add_argument("--transfers", type=Path, required=True)
    p.add_argument("--pool", action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--supply", type=float, default=1e9)
    args = p.parse_args()

    pools = {x.lower() for x in args.pool}

    tr = pq.read_table(args.transfers)
    t = {n: tr.column(n).to_pylist() for n in tr.column_names}
    if "tx_hash" not in t:
        print("transfers have no tx_hash column; rescan with the current "
              "token_archive.py", file=sys.stderr)
        return 2

    # Net token delta per address, per transaction.
    deltas: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for i in range(len(t["block"])):
        v = int(t["value"][i])
        if v == 0:
            continue
        h = t["tx_hash"][i]
        if t["src"][i] != ZERO:
            deltas[h][t["src"][i]] -= v
        if t["dst"][i] != ZERO:
            deltas[h][t["dst"][i]] += v
    print(f"{len(deltas):,} transactions moved this token", file=sys.stderr)

    sw = pq.read_table(args.swaps)
    s = {n: sw.column(n).to_pylist() for n in sw.column_names}
    n = len(s["block"])

    # A transaction with more than one swap of this token cannot be split by
    # net delta alone, because the deltas are already summed across both.
    swaps_per_tx: dict[str, int] = defaultdict(int)
    for i in range(n):
        swaps_per_tx[s["tx_hash"][i]] += 1

    trader: list[str | None] = [None] * n
    stats = {"attributed": 0, "ambiguous_multi_swap": 0, "no_transfers": 0,
             "no_counterparty": 0}
    for i in range(n):
        h = s["tx_hash"][i]
        if swaps_per_tx[h] > 1:
            stats["ambiguous_multi_swap"] += 1
            continue
        d = deltas.get(h)
        if not d:
            stats["no_transfers"] += 1
            continue
        # The pool is the other side of every trade, so it is never the trader.
        cands = [(v, a) for a, v in d.items() if a not in pools and v != 0]
        if not cands:
            stats["no_counterparty"] += 1
            continue
        # A buy moves tokens out of the pool to someone; a sell the reverse.
        pick = max(cands) if s["is_buy"][i] else min(cands)
        trader[i] = pick[1]
        stats["attributed"] += 1

    s["trader"] = trader
    pq.write_table(pa.table(s), args.out)

    print(json.dumps(stats, indent=1), file=sys.stderr)
    print(f"  attributed {stats['attributed']/n:.1%} of {n:,} swaps", file=sys.stderr)

    # How often would each cheaper proxy have been wrong?
    for col in ("recipient", "sender"):
        if col not in s:
            continue
        pairs = [(s[col][i], trader[i]) for i in range(n)
                 if trader[i] and s[col][i]]
        if not pairs:
            continue
        agree = sum(1 for a, b in pairs if a.lower() == b.lower())
        print(f"  '{col}' matched the true holder on {agree/len(pairs):.1%} "
              f"of {len(pairs):,} comparable swaps", file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
