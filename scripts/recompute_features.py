#!/usr/bin/env python3
"""Rebuild the feature table from the trade archive, with no RPC.

The extraction spends roughly ninety minutes of a node that rate-limits
globally, and until trades were archived that cost was paid again for every new
feature idea. It should not be. Everything in `rhc.features` and
`rhc.manipulation` is a pure function of decoded trades, so once the trades are
on disk the features can be rebuilt in seconds, offline, as many times as an
idea needs testing.

What this deliberately does **not** rebuild is the sync-derived liquidity block.
Reserves come from `Sync` logs, which are not trades and are not archived, so
`launch_quote_reserve` and its relatives are carried across from the previous
feature table rather than recomputed. Recomputing them as zero would be worse
than leaving them out: a zero reserve is a value the model would happily fit.

Usage:
    python scripts/recompute_features.py                 # rebuild in place
    python scripts/recompute_features.py --out /tmp/x.parquet
"""
from __future__ import annotations

import argparse
import glob
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from rhc.chain import DEFAULT_ETH_USD, USDG, quote_scale
from rhc.features import Trade, compute
from rhc.manipulation import detect


# Columns that cannot be derived from trades. Carried over from the previous
# table by pool address rather than recomputed.
SYNC_DERIVED = {
    "launch_quote_reserve", "peak_quote_reserve", "final_quote_reserve",
    "liquidity_add_events", "liquidity_remove_events",
    "largest_liquidity_removal_pct",
    # Stealth accumulation is "buys that consumed under 2% of the quote
    # reserve", so it needs reserves and reads as zero without them. Left to
    # recompute it reported 0 where the extractor found 9, which is not a
    # missing value but a wrong one.
    "stealth_accumulator_count",
    # lifespan is chain-head minus pool-creation. The archive's last trade is
    # not the chain head -- for a token that died months ago it is out by the
    # months since -- so this is carried rather than re-derived.
    "lifespan_blocks",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=str, default="data/parquet/trades*.parquet",
                        help="a path or a glob. Batched extractions write "
                             "one file each and are read together.")
    parser.add_argument("--depth", type=str, default="data/parquet/depth*.parquet",
                        help="V3 depth observations archived alongside the "
                             "trades. Absent for a v2-only archive.")
    parser.add_argument("--previous", type=Path, default=Path("data/parquet/features.parquet"),
                        help="the table to carry sync-derived columns from")
    parser.add_argument("--out", type=Path, default=Path("data/parquet/features.parquet"))
    parser.add_argument("--eth-usd", type=float, default=DEFAULT_ETH_USD)
    args = parser.parse_args()

    matches = sorted(glob.glob(args.trades))
    if not matches:
        print(f"no trade archive matches {args.trades!r}. Run "
              f"scripts/extract_features.py first; it writes the archive these "
              f"stages read.", file=sys.stderr)
        return 1
    print(f"reading {len(matches)} trade file(s)", file=sys.stderr)

    con = duckdb.connect()
    # Archives written before the v3 work carry no protocol column, and
    # everything in them is v2 because that is all the extractor read.
    archive_columns = {
        name for name, *_ in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{args.trades}')").fetchall()
    }
    protocol_expr = "protocol" if "protocol" in archive_columns else "'v2'"
    rows = con.execute(
        f"SELECT pool, token, quote_asset, block, log_index, wallet, is_buy, "
        f"quote_amount, base_amount, {protocol_expr} AS protocol "
        f"FROM read_parquet(?) ORDER BY pool, block, log_index",
        [str(args.trades)],
    ).fetchall()

    grouped: dict[tuple[str, str, str, str], list[Trade]] = defaultdict(list)
    for (pool, token, quote, block, log_index, wallet, is_buy, q_amt, b_amt,
         protocol) in rows:
        grouped[(pool, token, quote, protocol)].append(
            Trade(block=int(block), wallet=(wallet or "").lower(), is_buy=bool(is_buy),
                  quote_amount=int(q_amt), base_amount=int(b_amt), log_index=int(log_index))
        )
    print(f"{len(rows):,} trades across {len(grouped):,} pools", file=sys.stderr)

    carried: dict[str, dict] = {}
    created_by_pool: dict[str, int] = {}
    if args.previous.exists():
        described = {name for name, *_ in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{args.previous}')").fetchall()}
        wanted = sorted(SYNC_DERIVED & described)
        # created_block is the pool's creation, which precedes its first trade;
        # the difference is the launch delay feature, so it is carried when the
        # previous table has it and the first trade stands in when it does not.
        has_created = "created_block" in described
        selected = ["pool", *(["created_block"] if has_created else []), *wanted]
        cols = ", ".join(f'"{c}"' for c in selected)
        for record in con.execute(
            f"SELECT {cols} FROM read_parquet(?)", [str(args.previous)]
        ).fetchall():
            fields = dict(zip(selected, record))
            pool = fields["pool"]
            if has_created and fields.get("created_block") is not None:
                created_by_pool[pool] = int(fields["created_block"])
            carried[pool] = {k: fields[k] for k in wanted}
        print(f"carrying {len(wanted)} sync-derived columns for {len(carried):,} pools",
              file=sys.stderr)
    else:
        print("no previous table: sync-derived columns will be absent", file=sys.stderr)

    # V3 depth, keyed by pool. Absent for a v2-only archive, which is not an
    # error: v2 pools have reserves instead and carry them over above.
    depths_by_pool: dict[str, list[tuple[int, float]]] = defaultdict(list)
    depth_files = sorted(glob.glob(args.depth))
    if depth_files:
        for pool, block, amount in con.execute(
            "SELECT pool, block, quote_to_move_1pct FROM read_parquet(?) "
            "ORDER BY pool, block", [args.depth],
        ).fetchall():
            depths_by_pool[pool].append((int(block), float(amount)))
        print(f"{sum(len(v) for v in depths_by_pool.values()):,} depth "
              f"observations across {len(depths_by_pool):,} pools", file=sys.stderr)

    head = max(int(r[3]) for r in rows)
    out_rows: list[dict] = []
    for (pool, token, quote, protocol), trades in grouped.items():
        created = created_by_pool.get(pool, min(t.block for t in trades))
        feats = compute(pool=pool, quote_asset=quote, created_block=created,
                        trades=trades, syncs=[], head_block=head,
                        depths=depths_by_pool.get(pool) or None)
        record = feats.to_dict()
        record["token"] = token
        record["protocol"] = protocol
        record.update(detect(trades).to_dict())

        scale = quote_scale(quote)
        usd = 1.0 if quote == USDG.lower() else args.eth_usd
        for key in ("buy_quote_volume", "sell_quote_volume", "net_flow_quote",
                    "trade_size_median", "trade_size_p90"):
            if record.get(key) is not None:
                record[key] = record[key] / scale * usd
        # Sync-derived values were already normalised when first written, so
        # they are copied after the scaling loop, not through it.
        record.update(carried.get(pool, {}))
        out_rows.append(record)

    keys = sorted({k for r in out_rows for k in r})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({k: [r.get(k) for r in out_rows] for k in keys}),
                   args.out, compression="zstd")
    print(f"wrote {len(out_rows):,} rows, {len(keys)} columns to {args.out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
