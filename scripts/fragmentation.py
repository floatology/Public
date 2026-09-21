#!/usr/bin/env python3
"""Venue fragmentation per token — catalogue 4.7.

An original finding from the census rather than anything in the literature: this
chain's liquidity is spread across **272 factories**, far more than the eight DEX
protocols visible through aggregators, with one factory holding 61% of all pools.
A token is not one market. It can have half a dozen pools on different factories
against different quote assets, and every metric computed from a single pool
silently assumes otherwise.

That assumption fails in both directions. A token whose analysed pool holds a
tenth of its liquidity looks thinner than it is, and a token whose other pools
were seeded and abandoned looks deeper. Fragmentation is the column that says
which case you are in, and it costs nothing because the census is already on
disk.

**What this does not claim.** Pool count is not liquidity. The census records
creations, not reserves, so a token with nine pools might have $9M or $9 — the
count says how many places to look, not how much is there. Reserve-weighted
fragmentation needs a per-pool reserve read, which needs the node, and it is
noted here as the next step rather than faked from what is available.

Usage:
    python scripts/fragmentation.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from rhc.chain import USDG, WETH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path,
                        default=Path("data/parquet/pool_creations.parquet"))
    parser.add_argument("--features", type=Path,
                        default=Path("data/parquet/features.parquet"),
                        help="restrict output to tokens in this table; omit for all")
    parser.add_argument("--all-tokens", action="store_true")
    parser.add_argument("--out", type=Path,
                        default=Path("data/parquet/fragmentation.parquet"))
    args = parser.parse_args()

    if not args.census.exists():
        print(f"{args.census} not found; run scripts/pool_census.py first",
              file=sys.stderr)
        return 1

    con = duckdb.connect()
    quotes = [WETH.lower(), USDG.lower()]

    # One row per (token, pool). A pool pairs two tokens, and the non-quote side
    # is the one being measured; a quote/quote pool has no memecoin side and is
    # excluded rather than counted twice, which is what the inequality does.
    con.execute("CREATE TEMP TABLE quotes AS SELECT * FROM (VALUES (?), (?)) t(q)",
                quotes)
    con.execute(
        f"""
        CREATE TEMP VIEW sides AS
        SELECT
            CASE WHEN lower(token0) IN (SELECT q FROM quotes) THEN lower(token1)
                 ELSE lower(token0) END AS token,
            CASE WHEN lower(token0) IN (SELECT q FROM quotes) THEN lower(token0)
                 ELSE lower(token1) END AS quote,
            lower(pool) AS pool, lower(factory) AS factory, kind, block
        FROM read_parquet('{args.census}')
        WHERE (lower(token0) IN (SELECT q FROM quotes))
           != (lower(token1) IN (SELECT q FROM quotes))
        """
    )

    where = ""
    if not args.all_tokens and args.features.exists():
        con.execute(
            f"CREATE TEMP VIEW wanted AS "
            f"SELECT DISTINCT lower(token) AS token FROM read_parquet('{args.features}')"
        )
        where = "WHERE token IN (SELECT token FROM wanted)"

    rows = con.execute(
        f"""
        SELECT token,
               count(*)                       AS venue_pool_count,
               count(DISTINCT factory)        AS venue_factory_count,
               count(DISTINCT quote)          AS venue_quote_count,
               count(DISTINCT kind)           AS venue_protocol_count,
               min(block)                     AS first_pool_block,
               max(block)                     AS last_pool_block
        FROM sides
        {where}
        GROUP BY token
        """
    ).fetchall()
    if not rows:
        print("no tokens matched", file=sys.stderr)
        return 1

    records = []
    for token, pools, factories, quote_count, protocols, first, last in rows:
        records.append({
            "token": token,
            "venue_pool_count": pools,
            "venue_factory_count": factories,
            "venue_quote_count": quote_count,
            "venue_protocol_count": protocols,
            "is_multi_venue": pools > 1,
            # Blocks between the token's first and last pool. A large gap means
            # liquidity was added long after launch, which is a different story
            # from several pools opened at once by one deployer.
            "venue_spread_blocks": int(last) - int(first),
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted(records[0])
    pq.write_table(pa.table({k: [r[k] for r in records] for k in keys}),
                   args.out, compression="zstd")

    multi = sum(1 for r in records if r["is_multi_venue"])
    print(f"{len(records):,} tokens; {multi:,} ({multi/len(records):.1%}) have more "
          f"than one pool", file=sys.stderr)
    top = sorted(records, key=lambda r: -r["venue_pool_count"])[:5]
    for record in top:
        print(f"  {record['token']}  pools={record['venue_pool_count']} "
              f"factories={record['venue_factory_count']} "
              f"quotes={record['venue_quote_count']}", file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
