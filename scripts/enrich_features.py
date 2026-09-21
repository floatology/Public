#!/usr/bin/env python3
"""Join contract risk, holder distribution and social metrics onto the features.

The feature engine covers what a pool's own swap and sync logs yield. This adds
the rest of the catalogue from sources that do not touch the RPC, so it can run
alongside a bulk scan without starving it:

  * contract risk (section 6) from the explorer's verified ABI
  * Telegram audience and engagement (5.1, 5.2) from public channel previews
  * holder distribution (section 2) from Transfer logs, which *does* need the
    RPC and is therefore opt-in via --holders

Every source is independently optional. A token with no Telegram link, an
unverified contract and unreadable transfers still produces a row — with nulls
that say so, rather than being dropped and quietly biasing the sample toward
well-documented tokens.

Usage:
    python scripts/enrich_features.py --limit 200
    python scripts/enrich_features.py --holders      # only when the RPC is free
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from rhc.chain import Blockscout
from rhc.contracts import creator_of, inspect
from rhc.features import holder_features, replay_balances
from rhc.premium import GeckoTerminal, PremiumError
from rhc.social import Telegram, channel_from_url

# Catalogue items this endpoint supplies directly, which the block explorer
# does not carry at all.
INFO_FIELDS = {
    "telegram_handle": "info_telegram",
    "twitter_handle": "info_twitter",
    "discord_url": "info_discord",
    "developer_address": "info_developer",
    "developer_holding_percentage": "info_dev_holding_pct",
    "is_honeypot": "info_is_honeypot",
    "mint_authority": "info_mint_authority",
    "freeze_authority": "info_freeze_authority",
    "gt_score": "info_gt_score",
}


def _numeric(value) -> float | None:
    """Parse a value that may be a number, a numeric string, or absent."""
    if value in (None, "", []):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise(value):
    """Coerce a metadata value to a single stable type.

    This endpoint returns tri-state fields inconsistently: is_honeypot comes
    back as a boolean for some tokens and the string "unknown" for others, which
    Arrow rejects when writing the column. Booleans stay booleans, "unknown" and
    empty values become None so the absence is explicit, and anything else is
    stringified rather than guessed at.
    """
    if value in ("", [], {}, None):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"unknown", "n/a", "none"}:
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return value.strip()
    if isinstance(value, (int, float)):
        return value
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("data/parquet/features.parquet"))
    parser.add_argument("--out", type=Path, default=Path("data/parquet/enriched.parquet"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--holders", action="store_true",
                        help="Also replay Transfer logs for holder metrics (uses the RPC)")
    parser.add_argument("--no-social", action="store_true")
    parser.add_argument("--no-contracts", action="store_true")
    parser.add_argument(
        "--wallet-features", type=Path,
        default=Path("data/parquet/wallet_features.parquet"),
        help="point-in-time wallet features from scripts/wallet_ledger.py. "
             "Joined when present and skipped when absent, because the "
             "ledger needs a trade archive that older extractions did not "
             "write.",
    )
    parser.add_argument("--crowd-features", type=Path,
                        default=Path("data/parquet/crowd_features.parquet"),
                        help="entity-corrected crowd counts from "
                             "scripts/wallet_clusters.py")
    parser.add_argument("--fragmentation", type=Path,
                        default=Path("data/parquet/fragmentation.parquet"),
                        help="per-token venue counts from scripts/fragmentation.py")
    args = parser.parse_args()

    con = duckdb.connect()
    rows = con.execute(
        f"SELECT * FROM read_parquet('{args.features}')"
        + (f" LIMIT {args.limit}" if args.limit else "")
    ).fetchall()
    columns = [d[0] for d in con.description]
    records = [dict(zip(columns, r)) for r in rows]
    print(f"{len(records)} tokens to enrich", file=sys.stderr)

    started = time.time()
    counts = {"contract": 0, "telegram": 0, "holders": 0}

    with Blockscout() as explorer, Telegram() as telegram, GeckoTerminal() as gecko:
        rpc = None
        if args.holders:
            from rhc.rpc import Rpc
            rpc = Rpc(min_interval=0.3)
        try:
            for index, record in enumerate(records, start=1):
                token = record.get("token")
                if not token:
                    continue
                if index % 25 == 0:
                    print(f"  {index}/{len(records)}  {counts}  "
                          f"{time.time() - started:.0f}s", file=sys.stderr)

                if not args.no_contracts:
                    risk = inspect(explorer, token)
                    for key, value in risk.to_dict().items():
                        if key != "address":
                            record[f"contract_{key}"] = value
                    record["deployer"] = creator_of(explorer, token)
                    if risk.is_verified:
                        counts["contract"] += 1

                if not args.no_social:
                    info = {}
                    try:
                        info = gecko.token_info(token)
                    except PremiumError:
                        info = {}
                    for source, target in INFO_FIELDS.items():
                        record[target] = _normalise(info.get(source))
                    websites = info.get("websites") or []
                    record["info_website_count"] = len(websites)
                    # The holders field arrives as a nested object carrying the
                    # count and a concentration breakdown. Flattening it yields
                    # catalogue 2.1 and 2.3 without replaying Transfer logs,
                    # which is the expensive route to the same numbers.
                    holders_info = info.get("holders") or {}
                    record["info_holder_count"] = _numeric(holders_info.get("count"))
                    distribution = holders_info.get("distribution_percentage") or {}
                    record["info_top10_pct"] = _numeric(distribution.get("top_10"))
                    record["info_holders_11_30_pct"] = _numeric(distribution.get("11_30"))
                    record["info_holders_31_50_pct"] = _numeric(distribution.get("31_50"))
                    record["info_holders_rest_pct"] = _numeric(distribution.get("rest"))

                    raw = (info.get("telegram_handle") or "").strip()
                    handle = channel_from_url(raw) if "/" in raw else (raw or None)
                    record["telegram_channel"] = handle
                    if handle:
                        metrics = telegram.fetch(handle)
                        for key, value in metrics.to_dict().items():
                            if key != "channel":
                                record[f"tg_{key}"] = value
                        if metrics.reachable:
                            counts["telegram"] += 1

                if rpc is not None:
                    from rhc.rpc import TOPIC_TRANSFER, RpcError
                    try:
                        logs = list(rpc.iter_logs(
                            from_block=int(record.get("created_block") or 1),
                            to_block=rpc.block_number(),
                            topics=[[TOPIC_TRANSFER]], address=token,
                        ))
                    except RpcError:
                        logs = []
                    if logs:
                        balances, applied = replay_balances(
                            logs, exclude={str(record.get("pool") or "")}
                        )
                        holders = holder_features(balances, transfer_count=applied)
                        for key, value in holders.to_dict().items():
                            record[f"holder_{key}"] = value
                        counts["holders"] += 1
        finally:
            if rpc is not None:
                rpc.close()

    # The wallet ledger is a separate, offline pass over the trade archive, so
    # it is joined here rather than computed inline. A token with no matching
    # row gets nulls, not zeros: "this token's early buyers had no prior track
    # record" and "we never looked" are different states, and filling zero
    # would merge them into the first.
    side_tables = [
        ("wallet ledger", args.wallet_features),
        ("crowd clustering", args.crowd_features),
        ("venue fragmentation", args.fragmentation),
    ]
    for label, path in side_tables:
        if not path.exists():
            print(f"  {label}: {path} absent, skipped", file=sys.stderr)
            continue
        side_rows = con.execute(f"SELECT * FROM read_parquet('{path}')").fetchall()
        side_columns = [d[0] for d in con.description]
        by_token = {}
        for row in side_rows:
            fields = dict(zip(side_columns, row))
            by_token[str(fields["token"]).lower()] = fields
        matched = 0
        for record in records:
            found = by_token.get(str(record.get("token") or "").lower())
            if found:
                matched += 1
                record.update({k: v for k, v in found.items() if k != "token"})
        print(f"  {label}: {matched}/{len(records)} tokens matched", file=sys.stderr)

    keys = sorted({k for r in records for k in r})
    table = pa.table({k: [r.get(k) for r in records] for k in keys})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, args.out, compression="zstd")
    print(f"\n{len(records)} rows x {len(keys)} columns -> {args.out}", file=sys.stderr)
    print(f"  enriched: {counts}  in {time.time() - started:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
