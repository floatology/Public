#!/usr/bin/env python3
"""Build the decision panel: one row per (token, moment you could have bought).

The cross-sectional table asks "did this token eventually 10x", with features
computed over the token's whole life. That question cannot be traded. By the
time `trade_count` or `median_hold_blocks` has its final value, the run has
already happened.

This asks the tradeable question instead. Pick a block `t`. Compute every
feature from trades **at or before** `t`. Then measure what happened **after**
`t`. A token alive for forty days yields forty decision points rather than one,
which turns a six-hundred-row table into tens of thousands of observations
without a single additional RPC call.

**Entry need not be at launch, and probably should not be.** An accumulation
pattern that takes three weeks to form is invisible in the first hour, and
buying in the first hour is a different and riskier bet than buying into
something that has been quietly absorbed for weeks. Because `t` is arbitrary,
the full feature set is legitimately available at it: a token with three weeks
of history genuinely *has* wallet concentration, holder growth and volume
trend, as of that moment.

Three things decide whether this is a backtest or a fiction:

**The outcome runs forward from `t`, not from launch.** Scoring "10x from
launch" at a point where the token is already up 5x credits the model with
price action it watched happen. The forward outcome here is the volume-backed
peak in `(t, t + horizon]` against the price at `t`.

**Right-censoring is refused, not dropped quietly.** A decision point closer to
the end of the data than one horizon cannot be scored. Emitting it with a null
outcome, or with whatever partial window exists, biases everything toward
tokens that ran early.

**Rows from one token are not independent.** Overlapping windows on the same
trajectory are heavily correlated, so a random row-wise train/test split puts
the same token on both sides and the held-out score becomes fiction. The panel
carries `token` so the split can be made by token, and `scripts/model_features.py`
enforces that for panel input.

Usage:
    python scripts/build_panel.py --step-days 1 --horizon-days 14
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from rhc.chain import DEFAULT_ETH_USD, USDG, quote_scale
from rhc.features import Trade, compute, window
from rhc.manipulation import detect

# The chain targets ~100ms blocks, so a day is about this many. It is a
# parameter rather than a constant because block time is a target, not a
# guarantee, and a drift would silently rescale every window here.
BLOCKS_PER_DAY = 864_000

SCALED = (
    "buy_quote_volume", "sell_quote_volume", "net_flow_quote",
    "launch_quote_reserve", "peak_quote_reserve", "final_quote_reserve",
    "trade_size_median", "trade_size_p90",
    "v3_depth_1pct_launch", "v3_depth_1pct_median", "v3_depth_1pct_min",
    "v3_depth_1pct_final",
)

# Outcome columns computed over the token's whole life. In a panel they are the
# future, so they are dropped and replaced by the forward-looking ones.
LIFETIME_OUTCOMES = {
    "peak_price", "peak_block", "peak_over_launch", "final_over_launch",
    "realisable_peak_over_launch", "peak_trade_volume_share",
    "drawdown_from_peak", "volume_above_2x_share", "volume_above_10x_share",
}


def reference_price(trades: list[Trade], *, sample: int = 5) -> float | None:
    """The price at `t`, as a volume-weighted average of the last few trades.

    The single most recent trade is a bad reference: in a thin pool it can be
    dust at an absurd price, and every forward multiple computed against it
    would be wrong in the same direction. A handful of trades weighted by size
    is far harder to distort by accident.
    """
    tail = [x for x in trades[-sample:] if x.price > 0 and x.quote_amount > 0]
    if not tail:
        return None
    volume = sum(x.quote_amount for x in tail)
    if volume <= 0:
        return None
    return sum(x.price * x.quote_amount for x in tail) / volume


def forward_outcome(
    forward: list[Trade], *, reference: float, volume_fraction: float = 0.1
) -> dict[str, float | int | None]:
    """What happened after `t`, priced against volume that actually traded.

    `realisable_forward_multiple` is the highest price at or above which
    `volume_fraction` of the forward window's volume traded — a price the market
    demonstrably absorbed size at. The naive maximum is reported beside it so
    the gap between them stays visible; when they diverge sharply, the peak was
    a rounding error.
    """
    priced = [x for x in forward if x.price > 0 and x.quote_amount > 0]
    if not priced or reference <= 0:
        return {
            "forward_trades": len(forward), "forward_max_multiple": None,
            "realisable_forward_multiple": None, "forward_volume_share_at_peak": None,
            "forward_end_multiple": None,
        }
    total = sum(x.quote_amount for x in priced)
    peak = max(priced, key=lambda x: x.price)

    running = 0
    realisable = None
    for x in sorted(priced, key=lambda x: -x.price):
        running += x.quote_amount
        if running >= total * volume_fraction:
            realisable = x.price / reference
            break
    peak_volume = sum(x.quote_amount for x in priced if x.price >= peak.price)
    return {
        "forward_trades": len(forward),
        "forward_max_multiple": peak.price / reference,
        "realisable_forward_multiple": realisable,
        "forward_volume_share_at_peak": peak_volume / total if total > 0 else None,
        "forward_end_multiple": priced[-1].price / reference,
    }


def load_grouped(pattern: str) -> tuple[dict[tuple, list[Trade]], int]:
    con = duckdb.connect()
    columns = {
        name for name, *_ in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{pattern}')").fetchall()
    }
    protocol = "protocol" if "protocol" in columns else "'v2'"
    rows = con.execute(
        f"SELECT pool, token, quote_asset, block, log_index, wallet, is_buy, "
        f"quote_amount, base_amount, {protocol} AS protocol "
        f"FROM read_parquet(?) ORDER BY pool, block, log_index", [pattern],
    ).fetchall()
    grouped: dict[tuple, list[Trade]] = defaultdict(list)
    head = 0
    for pool, token, quote, block, log_index, wallet, is_buy, q, b, proto in rows:
        head = max(head, int(block))
        grouped[(pool, token, quote, proto)].append(
            Trade(block=int(block), wallet=(wallet or "").lower(), is_buy=bool(is_buy),
                  quote_amount=int(q), base_amount=int(b), log_index=int(log_index))
        )
    return dict(grouped), head


def load_keyed(pattern: str, value_column: str) -> dict[str, list[tuple[int, float]]]:
    """(block, value) series per pool, from an optional archive."""
    if not sorted(glob.glob(pattern)):
        return {}
    con = duckdb.connect()
    out: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for pool, block, value in con.execute(
        f"SELECT pool, block, {value_column} FROM read_parquet(?) ORDER BY pool, block",
        [pattern],
    ).fetchall():
        out[pool].append((int(block), float(value)))
    return dict(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", default="data/parquet/trades*.parquet")
    parser.add_argument("--depth", default="data/parquet/depth*.parquet")
    parser.add_argument("--syncs", default="data/parquet/syncs*.parquet")
    parser.add_argument("--step-days", type=float, default=1.0,
                        help="spacing between decision points within a token")
    parser.add_argument("--horizon-days", type=float, default=14.0,
                        help="how far forward the outcome is measured. Longer is "
                             "a fairer test of an accumulation thesis and costs "
                             "usable rows at the end of the data.")
    parser.add_argument("--min-history-days", type=float, default=1.0,
                        help="a token needs this much history before a decision "
                             "point is meaningful")
    parser.add_argument("--min-trades-before", type=int, default=10)
    parser.add_argument("--min-trades-after", type=int, default=5,
                        help="below this the forward window is unmeasurable, "
                             "which is not the same as an outcome of zero")
    parser.add_argument("--blocks-per-day", type=int, default=BLOCKS_PER_DAY)
    parser.add_argument("--eth-usd", type=float, default=DEFAULT_ETH_USD)
    parser.add_argument("--out", type=Path, default=Path("data/parquet/panel.parquet"))
    parser.add_argument("--summary", type=Path, default=Path("data/panel_summary.json"))
    args = parser.parse_args()

    if not sorted(glob.glob(args.trades)):
        print(f"no trade archive matches {args.trades!r}; run "
              f"scripts/extract_features.py first.", file=sys.stderr)
        return 1

    step = int(args.step_days * args.blocks_per_day)
    horizon = int(args.horizon_days * args.blocks_per_day)
    min_history = int(args.min_history_days * args.blocks_per_day)

    grouped, data_end = load_grouped(args.trades)
    depth_by_pool = load_keyed(args.depth, "quote_to_move_1pct")
    sync_by_pool: dict[str, list[tuple[int, int, int]]] = {}
    if sorted(glob.glob(args.syncs)):
        con = duckdb.connect()
        raw: dict[str, list] = defaultdict(list)
        for pool, block, quote_reserve, base_reserve in con.execute(
            "SELECT pool, block, quote_reserve, base_reserve FROM read_parquet(?) "
            "ORDER BY pool, block", [args.syncs],
        ).fetchall():
            raw[pool].append((int(block), int(quote_reserve), int(base_reserve)))
        sync_by_pool = dict(raw)

    print(f"{len(grouped):,} pools; data ends at block {data_end:,}", file=sys.stderr)
    print(f"step {step:,} blocks, horizon {horizon:,} blocks "
          f"({args.horizon_days:g}d), reserves for {len(sync_by_pool):,} pools, "
          f"depth for {len(depth_by_pool):,}", file=sys.stderr)
    if not sync_by_pool:
        print("  no reserve archive: V2 liquidity columns will be absent at every "
              "decision point. Extractions predating the sync archive do not carry "
              "them, and they cannot be reconstructed from trades alone.",
              file=sys.stderr)

    rows: list[dict] = []
    censored = unmeasurable = too_short = 0

    for (pool, token, quote, protocol), trades in grouped.items():
        first_block = trades[0].block
        # The last decision point that can still be scored over a full horizon.
        last_usable = data_end - horizon
        t = first_block + min_history
        if t > last_usable:
            too_short += 1
            continue

        syncs = sync_by_pool.get(pool, [])
        depths = depth_by_pool.get(pool, [])
        scale = quote_scale(quote)
        usd = 1.0 if quote == USDG.lower() else args.eth_usd

        while t <= last_usable:
            past = window(trades, start=first_block, end=t)
            if len(past) < args.min_trades_before:
                t += step
                continue
            forward = window(trades, start=t + 1, end=t + horizon)
            if len(forward) < args.min_trades_after:
                unmeasurable += 1
                t += step
                continue

            reference = reference_price(past)
            if reference is None or reference <= 0:
                t += step
                continue

            feats = compute(
                pool=pool, quote_asset=quote, created_block=first_block,
                trades=past, syncs=[s for s in syncs if s[0] <= t],
                head_block=t,
                depths=[d for d in depths if d[0] <= t] or None,
            )
            record = {k: v for k, v in feats.to_dict().items()
                      if k not in LIFETIME_OUTCOMES}
            record.update(detect(past).to_dict())
            record["token"] = token
            record["protocol"] = protocol
            record["decision_block"] = t
            record["history_blocks"] = t - first_block
            record["reference_price"] = reference
            for key in SCALED:
                if record.get(key) is not None:
                    record[key] = record[key] / scale * usd
            record.update(forward_outcome(forward, reference=reference))
            rows.append(record)
            t += step

        if first_block + min_history <= data_end and data_end - horizon < trades[-1].block:
            censored += 1

    if not rows:
        print("\nNo scoreable decision points. With a "
              f"{args.horizon_days:g}-day horizon every token either lacks "
              f"{args.min_history_days:g} days of prior history or sits within one "
              f"horizon of the end of the data. Shorten --horizon-days or extract "
              f"more history.", file=sys.stderr)
        return 1

    keys = sorted({k for r in rows for k in r})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({k: [r.get(k) for r in rows] for k in keys}),
                   args.out, compression="zstd")

    tokens = {r["token"] for r in rows}
    scored = [r for r in rows if r.get("realisable_forward_multiple") is not None]
    summary = {
        "rows": len(rows),
        "tokens": len(tokens),
        "rows_per_token": len(rows) / len(tokens),
        "step_blocks": step, "horizon_blocks": horizon,
        "horizon_days": args.horizon_days, "step_days": args.step_days,
        "data_end_block": data_end,
        "pools_too_short": too_short,
        "decision_points_without_forward_trades": unmeasurable,
        "pools_touching_the_censoring_boundary": censored,
        "reserve_coverage_pools": len(sync_by_pool),
        "depth_coverage_pools": len(depth_by_pool),
    }
    for threshold in (2, 5, 10):
        hits = sum(1 for r in scored
                   if r["realisable_forward_multiple"] >= threshold)
        summary[f"base_rate_{threshold}x"] = hits / len(scored) if scored else None
        summary[f"positives_{threshold}x"] = hits
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\n  {len(rows):,} decision points across {len(tokens):,} tokens "
          f"({summary['rows_per_token']:.1f} each)", file=sys.stderr)
    print(f"  dropped: {too_short:,} pools too short, "
          f"{unmeasurable:,} points with no forward trades", file=sys.stderr)
    for threshold in (2, 5, 10):
        rate = summary[f"base_rate_{threshold}x"]
        print(f"  {threshold:>2}x from the decision point: "
              f"{summary[f'positives_{threshold}x']:,} "
              f"({rate:.3%})" if rate is not None else "", file=sys.stderr)
    print(f"\nwrote {args.out} and {args.summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
