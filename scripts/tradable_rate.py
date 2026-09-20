#!/usr/bin/env python3
"""Measure what fraction of price-defined winners were actually tradable.

Every positive rate measured so far is computed on *printed* prices. The
execution work (`docs/04-execution-and-data-findings.md`) showed a $500 round
trip costs 0.90% on a $2.4M pool and 96.10% on a $20k one, so an unknown share
of those "winners" were never reachable. This closes that gap.

**Tradability is measured as one-way fill impact, not a round trip.** See
`execution_cost` — a symmetric round trip cancels itself out in a thin pool and
reports near-zero cost for a position that cannot be taken.

**Historical reserves are recoverable.** `docs/03-open-questions.md` §1.4 records
that no free source carries historical liquidity composition — true of the
aggregator APIs, but V2 pairs emit `Sync(reserve0, reserve1)` after every swap,
so a pool's exact reserves at any past block are in the logs. That makes a
genuine point-in-time execution model possible rather than a present-day proxy,
which would be the wrong measurement: a token that ran three months ago may be
dead today for reasons unrelated to whether it was tradable then.

For each sampled pool this finds the block of peak price, reads the reserves as
of that block, and prices a constant-product buy there. A token counts as a
*tradable* winner only if it reached the multiple **and** the clip both filled
within the impact ceiling and stayed under a capped share of the quote reserve.

Scope: V2 only (constant product, and Sync gives reserves directly), and only
pools quoted in USDG or WETH, since the clip must be denominated in dollars.

Usage:
    python scripts/tradable_rate.py --sample 400 --clip 500
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import duckdb

from rhc.chain import USDG, WETH
from rhc.rpc import TOPIC_V2_SWAP, TOPIC_V2_SYNC, Rpc, RpcError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from positive_rate import _drop_dust, _launch_vwap, _parse_v2_swap  # noqa: E402

# Uniswap V2 takes 0.3% of the input on every swap.
FEE_NUMERATOR = 997
FEE_DENOMINATOR = 1000


def _amount_out(amount_in: int, reserve_in: int, reserve_out: int) -> int:
    """Constant-product output for a given input, net of the 0.3% fee."""
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0
    taxed = amount_in * FEE_NUMERATOR
    return (taxed * reserve_out) // (reserve_in * FEE_DENOMINATOR + taxed)


def execution_cost(clip_raw: int, reserve_quote: int, reserve_base: int) -> dict | None:
    """Cost of acquiring `clip_raw` worth of the base token at these reserves.

    **Measures the buy leg against spot, not a round trip.** A round trip is a
    trap in a thin pool: the two legs cancel. One sampled pool held 0.0000084
    WETH (about two cents) against a $500 clip — the buy took 99.996% of the
    base reserve and selling straight back returned 99.99997% of the stake, so
    the round trip reported **0.00%** for a position nobody could take. The
    constant-product curve always permits any size; it just charges an
    arbitrarily bad price, and a symmetric round trip hides exactly that.

    Returns the one-way fill impact plus the share of the pool the clip would
    consume, since a trade that swallows most of a pool is untradable regardless
    of what the arithmetic says.
    """
    if clip_raw <= 0 or reserve_quote <= 0 or reserve_base <= 0:
        return None
    filled = _amount_out(clip_raw, reserve_quote, reserve_base)
    if filled <= 0:
        return None
    # What the clip would buy at the pre-trade price, with no fee or impact.
    at_spot = clip_raw * reserve_base / reserve_quote
    if at_spot <= 0:
        return None
    return {
        "impact_pct": (1.0 - filled / at_spot) * 100.0,
        "pool_share_pct": clip_raw / reserve_quote * 100.0,
        "base_taken_pct": filled / reserve_base * 100.0,
    }


def _reserves_at(sync_logs: list[dict], block: int, *, quote_is_token0: bool):
    """Reserves as of `block`, from the last Sync at or before it."""
    best = None
    for log in sync_logs:
        if int(log["blockNumber"], 16) > block:
            break
        best = log
    if best is None:
        return None
    body = (best.get("data") or "0x")[2:]
    if len(body) < 128:
        return None
    reserve0 = int(body[:64], 16)
    reserve1 = int(body[64:128], 16)
    return (reserve0, reserve1) if quote_is_token0 else (reserve1, reserve0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("data/parquet/pool_creations.parquet"))
    parser.add_argument("--sample", type=int, default=400)
    parser.add_argument("--multiple", type=float, default=10.0)
    parser.add_argument("--clip", type=float, default=500.0, help="Clip size in USD")
    parser.add_argument("--eth-usd", type=float, default=2576.0)
    parser.add_argument("--cost-ceiling", type=float, default=10.0,
                        help="One-way impact %% above which a winner is untradable")
    parser.add_argument("--max-pool-share", type=float, default=10.0,
                        help="Clip may not exceed this %% of the quote reserve")
    parser.add_argument("--launch-trades", type=int, default=5)
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument("--dust-floor", type=float, default=0.01)
    parser.add_argument("--max-plausible", type=float, default=1e6)
    parser.add_argument("--seed", default="rhc-h0-v1")
    parser.add_argument("--out", type=Path, default=Path("data/tradable_rate.json"))
    args = parser.parse_args()

    # Clip in raw units differs per quote asset: USDG is 6 decimals at ~$1,
    # WETH is 18 at the ETH price.
    clip_raw = {
        USDG.lower(): int(args.clip * 10**6),
        WETH.lower(): int(args.clip / args.eth_usd * 10**18),
    }

    con = duckdb.connect()
    quotes = list(clip_raw)
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
    print(f"population {len(pools):,} USDG/WETH-quoted v2 pools; sampling {len(sample)}",
          file=sys.stderr)

    measured = dead = price_winners = tradable_winners = no_reserves = 0
    costs: list[float] = []

    with Rpc() as rpc:
        head = rpc.block_number()
        for index, (pool, created, quote_is_token0, quote) in enumerate(sample, start=1):
            try:
                swaps = list(rpc.iter_logs(from_block=created, to_block=head,
                                           topics=[[TOPIC_V2_SWAP]], address=pool,
                                           initial_span=head))
            except RpcError:
                continue

            # Price series with the block each price occurred at.
            series: list[tuple[float, int, int]] = []
            for log in swaps:
                parsed = _parse_v2_swap(log.get("data") or "0x")
                if parsed is None:
                    continue
                a0_in, a1_in, a0_out, a1_out = parsed
                amount0 = a0_in or a0_out
                amount1 = a1_in or a1_out
                if amount0 <= 0 or amount1 <= 0:
                    continue
                q, b = (amount0, amount1) if quote_is_token0 else (amount1, amount0)
                series.append((q / b, q, int(log["blockNumber"], 16)))

            kept = _drop_dust([(p, q) for p, q, _ in series], args.dust_floor)
            if len(kept) < args.min_trades:
                dead += 1
                continue
            launch = _launch_vwap(kept, args.launch_trades)
            if not launch or launch <= 0:
                dead += 1
                continue

            keep_prices = {p for p, _ in kept}
            peak_price, _, peak_block = max(
                (row for row in series if row[0] in keep_prices), key=lambda r: r[0]
            )
            ratio = peak_price / launch
            if ratio > args.max_plausible:
                continue
            measured += 1
            if ratio < args.multiple:
                continue
            price_winners += 1

            # Could it have been round tripped at that peak?
            try:
                syncs = list(rpc.iter_logs(from_block=created, to_block=peak_block,
                                           topics=[[TOPIC_V2_SYNC]], address=pool,
                                           initial_span=head))
            except RpcError:
                no_reserves += 1
                continue
            reserves = _reserves_at(syncs, peak_block, quote_is_token0=bool(quote_is_token0))
            if reserves is None:
                no_reserves += 1
                continue
            metrics = execution_cost(clip_raw[quote], reserves[0], reserves[1])
            if metrics is None:
                no_reserves += 1
                continue
            cost = metrics["impact_pct"]
            costs.append(cost)
            tradable = (
                cost <= args.cost_ceiling
                and metrics["pool_share_pct"] <= args.max_pool_share
            )
            if tradable:
                tradable_winners += 1

            print(f"  {pool[:12]} ratio={ratio:8.1f}x  impact {cost:7.2f}%  "
                  f"clip={metrics['pool_share_pct']:8.1f}% of quote reserve  "
                  f"{'TRADABLE' if tradable else 'no'}", file=sys.stderr)

    total = measured + dead
    costs.sort()
    result = {
        "seed": args.seed, "clip_usd": args.clip, "multiple": args.multiple,
        "cost_ceiling_pct": args.cost_ceiling,
        "max_pool_share_pct": args.max_pool_share,
        "sampled": len(sample), "measured": measured, "dead": dead,
        "price_winners": price_winners, "tradable_winners": tradable_winners,
        "reserves_unavailable": no_reserves,
        "tradable_share_of_price_winners":
            tradable_winners / price_winners if price_winners else None,
        "price_rate_all_sampled": price_winners / total if total else None,
        "tradable_rate_all_sampled": tradable_winners / total if total else None,
        "cost_p50": costs[len(costs)//2] if costs else None,
        "cost_p90": costs[int(len(costs)*0.9)] if costs else None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")

    print(f"\n--- tradable rate (V2, ${args.clip:g} clip, seed {args.seed}) ---", file=sys.stderr)
    print(f"  measured {measured}, dead {dead}", file=sys.stderr)
    print(f"  price winners   : {price_winners}", file=sys.stderr)
    print(f"  tradable winners: {tradable_winners}", file=sys.stderr)
    if price_winners:
        print(f"  tradable share of price winners: "
              f"{tradable_winners/price_winners:.1%}", file=sys.stderr)
    if total:
        print(f"  price rate {price_winners/total:.3%} -> "
              f"tradable rate {tradable_winners/total:.3%}", file=sys.stderr)
    if costs:
        print(f"  one-way impact at peak: p50 {costs[len(costs)//2]:.2f}%  "
              f"p90 {costs[int(len(costs)*0.9)]:.2f}%", file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
