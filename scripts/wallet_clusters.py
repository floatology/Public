#!/usr/bin/env python3
"""Entity map from wallet co-occurrence, and the crowd features it yields.

Catalogue 1.8. The point is to stop counting addresses as participants: nine
early buyers might be nine people or one operator with nine wallets, and every
concentration, crowd and unique-wallet metric in this project assumes the first
without checking.

**The same look-ahead rule applies here as to the wallet ledger, and it is
easier to miss.** Inferring that two wallets are one operator from their trading
over all of history, then applying that at a token's launch, uses information
that did not exist at launch — the wallets may not have co-traded anything yet.
So the entity map is built from a **training window** of blocks ending at a
cutoff, and crowd features are emitted only for tokens that launched after it.
Tokens inside the window get nulls, which costs sample and is the price of the
feature meaning anything.

The second leak is subtler: a token's *own* full trade history is also the
future at its launch. Crowd features are therefore computed over its early
buyers only, the same cohort the ledger scores.

A global entity map over all history is written alongside as a descriptive
artefact — useful for looking at who operates this chain, unusable as a model
input, and labelled as such.

Usage:
    python scripts/wallet_clusters.py
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

from rhc.clusters import build_entities, crowd_features, find_pairs
from rhc.wallets import build_positions

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wallet_ledger import load_trades


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=str, default="data/parquet/trades*.parquet",
                        help="a path or a glob. Batched extractions write "
                             "one file each and are read together.")
    parser.add_argument("--cutoff-quantile", type=float, default=0.5,
                        help="fraction of tokens, by launch block, whose trades "
                             "form the training window for the entity map")
    parser.add_argument("--early-percentile", type=float, default=0.2)
    parser.add_argument("--min-shared", type=int, default=3)
    parser.add_argument("--min-excess", type=float, default=5.0)
    parser.add_argument("--out", type=Path,
                        default=Path("data/parquet/crowd_features.parquet"))
    parser.add_argument("--entities-out", type=Path,
                        default=Path("data/wallet_entities.json"))
    args = parser.parse_args()

    matches = sorted(glob.glob(args.trades))
    if not matches:
        print(f"no trade archive matches {args.trades!r}. Run "
              f"scripts/extract_features.py first; it writes the archive these "
              f"stages read.", file=sys.stderr)
        return 1
    print(f"reading {len(matches)} trade file(s)", file=sys.stderr)

    token_trades = load_trades(args.trades)
    first_block = {t: min(x.block for x in tr) for t, tr in token_trades.items() if tr}
    if not first_block:
        print("no trades", file=sys.stderr)
        return 1

    launches = sorted(first_block.values())
    cutoff = launches[min(len(launches) - 1, int(len(launches) * args.cutoff_quantile))]
    print(f"{len(token_trades):,} tokens; training window ends at block {cutoff:,}",
          file=sys.stderr)

    # Training window: every trade at or before the cutoff, from any token.
    # Slicing by trade rather than by token keeps a long-lived token's early
    # activity usable without importing its later activity.
    window = {
        token: [x for x in trades if x.block <= cutoff]
        for token, trades in token_trades.items()
    }
    window = {t: v for t, v in window.items() if len(v) >= 2}
    try:
        pairs = find_pairs(window, min_shared=args.min_shared,
                           min_excess=args.min_excess)
    except MemoryError as exc:
        print(f"clustering aborted: {exc}", file=sys.stderr)
        return 1
    entities = build_entities(pairs)
    print(f"  training window: {len(window):,} tokens, {len(pairs):,} pairs, "
          f"{len(set(entities.values())):,} entities over {len(entities):,} wallets",
          file=sys.stderr)

    rows = []
    for token, trades in token_trades.items():
        if first_block[token] <= cutoff:
            continue  # inside the window the map used; the feature would be circular
        positions = build_positions(token, trades)
        early = {
            p.wallet for p in positions
            if p.entry_percentile is not None
            and p.entry_percentile <= args.early_percentile
        }
        if not early:
            continue
        early_trades = [x for x in trades if x.wallet in early]
        crowd = crowd_features(early_trades, entities)
        record = {"token": token}
        record.update({f"crowd_{k}": v for k, v in crowd.to_dict().items()})
        rows.append(record)

    if rows:
        keys = sorted({k for r in rows for k in r})
        args.out.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table({k: [r.get(k) for r in rows] for k in keys}),
                       args.out, compression="zstd")
        merged = [r for r in rows if (r.get("crowd_independence_ratio") or 1.0) < 1.0]
        print(f"  {len(rows):,} post-cutoff tokens scored; {len(merged):,} have at "
              f"least two early wallets that resolve to one entity", file=sys.stderr)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print("  no post-cutoff token had an early cohort; nothing written",
              file=sys.stderr)

    # Descriptive map over all history. Explicitly not a model input.
    try:
        full_pairs = find_pairs(token_trades, min_shared=args.min_shared,
                                min_excess=args.min_excess)
    except MemoryError as exc:
        # The training-window features above are already written; the
        # descriptive map is a nice-to-have and must not discard them.
        print(f"\n  all-history map skipped: {exc}", file=sys.stderr)
        return 0
    full_entities = build_entities(full_pairs)
    grouped: dict[str, list[str]] = defaultdict(list)
    for wallet, entity in full_entities.items():
        grouped[entity].append(wallet)
    biggest = sorted(grouped.values(), key=len, reverse=True)[:20]
    args.entities_out.parent.mkdir(parents=True, exist_ok=True)
    args.entities_out.write_text(json.dumps({
        "note": "Built from ALL history. Descriptive only -- using this to score "
                "a token at its launch is look-ahead, which is why the modelled "
                "columns come from the training-window map instead.",
        "cutoff_block_used_for_features": cutoff,
        "wallets_clustered": len(full_entities),
        "entities": len(grouped),
        "pairs": len(full_pairs),
        "largest_entities": [sorted(g) for g in biggest],
    }, indent=2) + "\n")
    print(f"\n  all-history map (descriptive): {len(grouped):,} entities over "
          f"{len(full_entities):,} wallets", file=sys.stderr)
    if biggest:
        print(f"  largest operator holds {len(biggest[0])} wallets", file=sys.stderr)
    print(f"wrote {args.entities_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
