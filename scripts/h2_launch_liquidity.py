#!/usr/bin/env python3
"""H2: does the liquidity a deployer seeds at launch predict a 10x?

Pre-registered in PREREGISTRATION.md before this was run. It replaces the
graduation-threshold RDD, which is infeasible here — the dominant factories are
plain Uniswap factories, not bonding-curve launchpads, so no graduation event
exists to sit a discontinuity around.

**The independent variable uses the first `Sync` only**, which is the liquidity
present before any trading. Nothing derived from later state enters, so the
signal is genuinely observable at launch and carries no look-ahead.

Both labels from PREREGISTRATION are reported: the raw price 10x, and the
*tradable* 10x at a $500 clip priced against reserves at the peak block.

Usage:
    python scripts/h2_launch_liquidity.py --sample 3000 --quantiles 4
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import duckdb

from rhc.chain import USDG, WETH
from rhc.rpc import TOPIC_V2_SWAP, TOPIC_V2_SYNC, Rpc, RpcError
from positive_rate import _drop_dust, _launch_vwap, _parse_v2_swap  # noqa: E402
from tradable_rate import execution_cost  # noqa: E402


# Chi-square 5% critical values by degrees of freedom.
CRITICAL = {1: 3.84, 2: 5.99, 3: 7.81, 4: 9.49, 5: 11.07}


def _reserves(log: dict, *, quote_is_token0: bool) -> tuple[int, int] | None:
    body = (log.get("data") or "0x")[2:]
    if len(body) < 128:
        return None
    r0, r1 = int(body[:64], 16), int(body[64:128], 16)
    return (r0, r1) if quote_is_token0 else (r1, r0)


def _chi_square(table: list[tuple[int, int]]) -> float | None:
    """Chi-square statistic for a k x 2 contingency table of (wins, losses)."""
    total = sum(w + l for w, l in table)
    total_wins = sum(w for w, _ in table)
    if total == 0 or total_wins == 0 or total_wins == total:
        return None
    stat = 0.0
    for wins, losses in table:
        row = wins + losses
        if row == 0:
            continue
        for observed, p in ((wins, total_wins / total), (losses, 1 - total_wins / total)):
            expected = row * p
            if expected > 0:
                stat += (observed - expected) ** 2 / expected
    return stat


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("data/parquet/pool_creations.parquet"))
    parser.add_argument("--sample", type=int, default=3000)
    parser.add_argument("--quantiles", type=int, default=4)
    parser.add_argument("--multiple", type=float, default=10.0)
    parser.add_argument("--clip", type=float, default=500.0)
    parser.add_argument("--eth-usd", type=float, default=2576.0)
    parser.add_argument("--cost-ceiling", type=float, default=10.0)
    parser.add_argument("--max-pool-share", type=float, default=10.0)
    parser.add_argument("--launch-trades", type=int, default=5)
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument("--dust-floor", type=float, default=0.01)
    parser.add_argument("--max-plausible", type=float, default=1e6)
    parser.add_argument("--seed", default="rhc-h2-v1")
    parser.add_argument("--out", type=Path, default=Path("data/h2_launch_liquidity.json"))
    args = parser.parse_args()

    quotes = [USDG.lower(), WETH.lower()]
    con = duckdb.connect()
    pools = con.execute(
        """
        SELECT pool, block,
               lower(token0) IN $quotes AS quote_is_token0,
               CASE WHEN lower(token0) IN $quotes THEN lower(token0) ELSE lower(token1) END AS quote
        FROM read_parquet($census)
        WHERE kind = 'v2' AND pool <> '' AND length(pool) = 42
          AND (lower(token0) IN $quotes OR lower(token1) IN $quotes)
        """,
        {"census": str(args.census), "quotes": quotes},
    ).fetchall()

    sample = sorted(pools, key=lambda r: hashlib.sha256(f"{args.seed}:{r[0]}".encode()).hexdigest())
    sample = sample[: args.sample]
    print(f"population {len(pools):,}; sampling {len(sample)}", file=sys.stderr)

    def usd(raw: int, quote: str) -> float:
        return raw / 10**6 if quote == USDG.lower() else raw / 10**18 * args.eth_usd

    rows: list[dict] = []
    dead = 0
    with Rpc() as rpc:
        head = rpc.block_number()
        for index, (pool, created, quote_is_token0, quote) in enumerate(sample, start=1):
            if index % 250 == 0:
                print(f"  {index}/{len(sample)}  measured={len(rows)} dead={dead}",
                      file=sys.stderr)
            try:
                syncs = list(rpc.iter_logs(from_block=created, to_block=head,
                                           topics=[[TOPIC_V2_SYNC]], address=pool,
                                           initial_span=head))
                if not syncs:
                    dead += 1
                    continue
                swaps = list(rpc.iter_logs(from_block=created, to_block=head,
                                           topics=[[TOPIC_V2_SWAP]], address=pool,
                                           initial_span=head))
            except RpcError:
                dead += 1
                continue

            first = _reserves(syncs[0], quote_is_token0=bool(quote_is_token0))
            if first is None or first[0] <= 0:
                dead += 1
                continue
            launch_liquidity = usd(first[0], quote)

            series = []
            for log in swaps:
                parsed = _parse_v2_swap(log.get("data") or "0x")
                if parsed is None:
                    continue
                a0i, a1i, a0o, a1o = parsed
                amount0, amount1 = a0i or a0o, a1i or a1o
                if amount0 <= 0 or amount1 <= 0:
                    continue
                q, b = (amount0, amount1) if quote_is_token0 else (amount1, amount0)
                series.append((q / b, q, int(log["blockNumber"], 16)))

            kept = _drop_dust([(p, q) for p, q, _ in series], args.dust_floor)
            if len(kept) < args.min_trades:
                dead += 1
                continue
            launch_price = _launch_vwap(kept, args.launch_trades)
            if not launch_price or launch_price <= 0:
                dead += 1
                continue

            keep = {p for p, _ in kept}
            peak_price, _, peak_block = max(
                (r for r in series if r[0] in keep), key=lambda r: r[0]
            )
            ratio = peak_price / launch_price
            if ratio > args.max_plausible:
                continue

            tradable = False
            if ratio >= args.multiple:
                at_peak = None
                for log in syncs:
                    if int(log["blockNumber"], 16) > peak_block:
                        break
                    at_peak = log
                if at_peak is not None:
                    res = _reserves(at_peak, quote_is_token0=bool(quote_is_token0))
                    clip_raw = (
                        int(args.clip * 10**6) if quote == USDG.lower()
                        else int(args.clip / args.eth_usd * 10**18)
                    )
                    if res:
                        m = execution_cost(clip_raw, res[0], res[1])
                        tradable = bool(
                            m and m["impact_pct"] <= args.cost_ceiling
                            and m["pool_share_pct"] <= args.max_pool_share
                        )
            rows.append({
                "pool": pool,
                "launch_liquidity_usd": launch_liquidity,
                "ratio": ratio,
                "price_win": ratio >= args.multiple,
                "tradable_win": tradable,
            })

    if not rows:
        print("no measurable pools", file=sys.stderr)
        return 1

    rows.sort(key=lambda r: r["launch_liquidity_usd"])
    size = len(rows) // args.quantiles
    buckets = [rows[i * size: (i + 1) * size if i < args.quantiles - 1 else len(rows)]
               for i in range(args.quantiles)]

    summary = []
    for i, bucket in enumerate(buckets, start=1):
        wins = sum(1 for r in bucket if r["price_win"])
        tw = sum(1 for r in bucket if r["tradable_win"])
        summary.append({
            "quantile": i, "n": len(bucket),
            "launch_liquidity_min": bucket[0]["launch_liquidity_usd"],
            "launch_liquidity_max": bucket[-1]["launch_liquidity_usd"],
            "launch_liquidity_median": bucket[len(bucket)//2]["launch_liquidity_usd"],
            "price_wins": wins, "price_win_rate": wins / len(bucket) if bucket else None,
            "tradable_wins": tw, "tradable_win_rate": tw / len(bucket) if bucket else None,
        })

    chi = _chi_square([(s["price_wins"], s["n"] - s["price_wins"]) for s in summary])
    result = {
        "hypothesis": "H2", "seed": args.seed, "sampled": len(sample),
        "measured": len(rows), "dead": dead, "multiple": args.multiple,
        "clip_usd": args.clip, "quantiles": summary,
        "chi_square_price_win": chi,
        "chi_square_df": args.quantiles - 1,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")

    print(f"\n--- H2: launch liquidity vs 10x (seed {args.seed}) ---", file=sys.stderr)
    print(f"  measured {len(rows)}, dead {dead}\n", file=sys.stderr)
    print(f"  {'q':>3}{'n':>7}{'median liq':>13}{'price 10x':>12}{'rate':>9}"
          f"{'tradable':>10}{'rate':>9}", file=sys.stderr)
    for s in summary:
        print(f"  {s['quantile']:>3}{s['n']:>7}${s['launch_liquidity_median']:>12,.0f}"
              f"{s['price_wins']:>12}{s['price_win_rate']:>8.1%}"
              f"{s['tradable_wins']:>10}{s['tradable_win_rate']:>8.1%}", file=sys.stderr)
    if chi is not None:
        print(f"\n  chi-square = {chi:.2f} on {args.quantiles - 1} df "
              f"(5% critical {CRITICAL.get(args.quantiles - 1, 0):.2f})",
              file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
