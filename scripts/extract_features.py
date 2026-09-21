#!/usr/bin/env python3
"""Extract the full feature set for a sample of pools, into Parquet.

One scan per pool yields ~45 features (docs/09-metric-catalogue.md). Output
feeds the correlation analysis, which answers how many genuinely independent
dimensions those 45 represent before any model is fitted.

Usage:
    python scripts/extract_features.py --sample 2000 --kind v2
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from rhc.chain import DEFAULT_ETH_USD, QUOTE_DECIMALS, USDG, WETH, quote_scale
from rhc.features import (compute, decode_syncs, decode_v2_swaps,
                          decode_v3_swaps, drop_dust)
from rhc.manipulation import detect
from rhc.rpc import TOPIC_V2_SWAP, TOPIC_V2_SYNC, TOPIC_V3_SWAP, Rpc, RpcError



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("data/parquet/pool_creations.parquet"))
    parser.add_argument("--sample", type=int, default=2000)
    parser.add_argument(
        "--protocol", choices=("v2", "v3"), default="v2",
        help="which pool population to sample. 63%% of this chain's pools "
             "are v3 and they carry 74%% of daily volume at roughly 19x the "
             "median depth, so a v2-only run studies the shallow third. v3 "
             "pools emit no Sync event, so the reserve-derived columns are "
             "absent for them rather than approximated.",
    )
    parser.add_argument(
        "--skip", type=int, default=0,
        help="how many pools to pass over before taking --sample. The sample\n             order is a deterministic hash of the seed and the pool address,\n             so --skip 10000 takes the NEXT block of pools rather than a fresh\n             random draw: two runs extend one sample instead of overlapping.",
    )
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument("--dust-floor", type=float, default=0.01)
    parser.add_argument("--eth-usd", type=float, default=DEFAULT_ETH_USD)
    parser.add_argument("--seed", default="rhc-features-v1")
    parser.add_argument("--out", type=Path, default=Path("data/parquet/features.parquet"))
    parser.add_argument(
        "--trades-out", type=Path, default=Path("data/parquet/trades.parquet"),
        help="archive of every decoded trade. Without this the RPC work is "
             "spent once and thrown away: a new feature idea then costs "
             "another full scan of a node that rate-limits globally, and the "
             "cross-token wallet ledger cannot be built at all.",
    )
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    quotes = list(QUOTE_DECIMALS)
    con = duckdb.connect()
    pools = con.execute(
        """
        SELECT pool, block,
               lower(token0) IN $quotes AS quote_is_token0,
               CASE WHEN lower(token0) IN $quotes THEN lower(token0) ELSE lower(token1) END AS quote,
               CASE WHEN lower(token0) IN $quotes THEN lower(token1) ELSE lower(token0) END AS token
        FROM read_parquet($census)
        WHERE kind = $kind AND pool <> '' AND length(pool) = 42
          AND (lower(token0) IN $quotes OR lower(token1) IN $quotes)
        """,
        {"census": str(args.census), "quotes": quotes, "kind": args.protocol},
    ).fetchall()

    sample = sorted(pools, key=lambda r: hashlib.sha256(f"{args.seed}:{r[0]}".encode()).hexdigest())
    sample = sample[args.skip: args.skip + args.sample]
    if not sample:
        print(f"--skip {args.skip} is past the end of a {len(pools):,}-pool "
              f"population; nothing to do.", file=sys.stderr)
        return 1
    print(f"population {len(pools):,}; sampling {len(sample)} "
          f"(skipping {args.skip:,})", file=sys.stderr)

    rows: list[dict] = []
    trade_rows: list[dict] = []
    skipped = 0
    started = time.time()
    with Rpc() as rpc:
        head = rpc.block_number()
        for index, (pool, created, quote_is_token0, quote, token) in enumerate(sample, start=1):
            if index % 200 == 0:
                rate = index / max(1e-9, time.time() - started)
                print(f"  {index}/{len(sample)}  kept={len(rows)} skipped={skipped} "
                      f"{rate:.1f}/s", file=sys.stderr)
            swap_topic = TOPIC_V2_SWAP if args.protocol == "v2" else TOPIC_V3_SWAP
            try:
                swap_logs = list(rpc.iter_logs(from_block=created, to_block=head,
                                               topics=[[swap_topic]], address=pool,
                                               initial_span=head))
                if len(swap_logs) < args.min_trades:
                    skipped += 1
                    continue
                # V3 has no Sync event and no single reserve figure that means
                # what a V2 reserve means: the same nominal depth can be spread
                # across the curve or stacked in a tick the price has left.
                sync_logs = []
                if args.protocol == "v2":
                    sync_logs = list(rpc.iter_logs(from_block=created, to_block=head,
                                                   topics=[[TOPIC_V2_SYNC]], address=pool,
                                                   initial_span=head))
            except RpcError:
                skipped += 1
                continue

            flag = bool(quote_is_token0)
            decode = decode_v2_swaps if args.protocol == "v2" else decode_v3_swaps
            trades = drop_dust(decode(swap_logs, quote_is_token0=flag), args.dust_floor)
            if len(trades) < args.min_trades:
                skipped += 1
                continue
            syncs = decode_syncs(sync_logs, quote_is_token0=flag)

            feats = compute(pool=pool, quote_asset=quote, created_block=created,
                            trades=trades, syncs=syncs, head_block=head)
            record = feats.to_dict()
            record["token"] = token
            record["protocol"] = args.protocol
            record.update(detect(trades).to_dict())
            for trade in trades:
                trade_rows.append({
                    "pool": pool, "token": token, "quote_asset": quote,
                    "protocol": args.protocol,
                    "block": trade.block, "log_index": trade.log_index,
                    "wallet": trade.wallet, "is_buy": trade.is_buy,
                    # Raw units. Scaling here would lose the exact integers
                    # that repeated-amount detection depends on.
                    "quote_amount": str(trade.quote_amount),
                    "base_amount": str(trade.base_amount),
                })
            # Normalise the raw-unit volume fields to USD so they compare across
            # pools; the price ratios stay raw because decimals cancel within a
            # pool but not between them.
            scale = quote_scale(quote)
            usd = 1.0 if quote == USDG.lower() else args.eth_usd
            for key in ("buy_quote_volume", "sell_quote_volume", "net_flow_quote",
                        "launch_quote_reserve", "peak_quote_reserve", "final_quote_reserve",
                        "trade_size_median", "trade_size_p90"):
                if record.get(key) is not None:
                    record[key] = record[key] / scale * usd
            rows.append(record)

    if not rows:
        print("no pools yielded features", file=sys.stderr)
        return 1

    keys = sorted({k for r in rows for k in r})
    table = pa.table({k: [r.get(k) for r in rows] for k in keys})
    pq.write_table(table, args.out, compression="zstd")

    if trade_rows:
        trade_keys = list(trade_rows[0])
        pq.write_table(
            pa.table({k: [r[k] for r in trade_rows] for k in trade_keys}),
            args.trades_out, compression="zstd",
        )
        print(f"archived {len(trade_rows):,} trades to {args.trades_out}", file=sys.stderr)
    print(f"\n{len(rows)} pools x {len(keys)} features -> {args.out} "
          f"in {time.time() - started:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
