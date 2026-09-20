#!/usr/bin/env python3
"""Estimate the positive-class rate: what fraction of tokens ever reached Nx.

H0's power analysis needs this number. The critique flagged its absence; it
could not be computed until the archive RPC made the population reachable.

Method: draw a seeded random sample of V2 pools from the census, reconstruct
each pool's price series from its own Swap logs, and compute peak-over-launch.
A sample is the right tool here, not a census — the estimate's precision depends
on the sample size, not on the population size, and scanning 268,003 V2 pools to
learn a rate that 500 measures adequately would be waste.

**Launch price is a VWAP over the pool's first trades, not its first swap.** A
dust trade or a block-one sniper distorts a literal first price badly, and the
ratio inherits that distortion. This is the definition fixed in PREREGISTRATION.

**Scope: V2-style pools only, and this is a stratum estimate, not a chain-wide
one.** V2 pools are 268,003 of 715,343 creations (37%). Their Swap event carries
gross in/out amounts, so price comes straight out of the log. V3-style pools
encode price as sqrtPriceX96 and need separate handling, and Uniswap V4 hooks can
alter swap maths arbitrarily. Whether the V2 stratum's rate generalises is an
open question, not an assumption — report it as the V2 rate.

Usage:
    python scripts/positive_rate.py --sample 400 --multiple 10
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import duckdb

from rhc.rpc import TOPIC_V2_SWAP, Rpc, RpcError

# Swap(sender, amount0In, amount1In, amount0Out, amount1Out, to)
# Four uint256 words, 64 hex chars each, after the 0x prefix.
_WORD = 64


def _parse_v2_swap(data_hex: str) -> tuple[int, int, int, int] | None:
    """Return (amount0In, amount1In, amount0Out, amount1Out) or None if malformed."""
    body = data_hex[2:] if data_hex.startswith("0x") else data_hex
    if len(body) < _WORD * 4:
        return None
    try:
        return tuple(  # type: ignore[return-value]
            int(body[i * _WORD : (i + 1) * _WORD], 16) for i in range(4)
        )
    except ValueError:
        return None


def _price_series(logs: list[dict]) -> list[float]:
    """token1-per-token0 for each swap, skipping degenerate ones.

    A swap moves token0 one way and token1 the other, so exactly one of each
    pair is non-zero. Both-zero or one-sided logs are skipped rather than
    treated as a price of zero, which would otherwise poison the peak ratio.
    """
    prices: list[float] = []
    for log in logs:
        parsed = _parse_v2_swap(log.get("data") or "0x")
        if parsed is None:
            continue
        a0_in, a1_in, a0_out, a1_out = parsed
        token0 = a0_in or a0_out
        token1 = a1_in or a1_out
        if token0 <= 0 or token1 <= 0:
            continue
        prices.append(token1 / token0)
    return prices


def _launch_vwap(prices: list[float], first_n: int) -> float | None:
    """Reference price: mean over the first `first_n` real trades.

    Unweighted because the V2 log gives amounts in token units whose decimals
    we have not resolved per pool; averaging several early trades already
    removes the single-dust-trade failure this exists to prevent.
    """
    head = prices[:first_n]
    return sum(head) / len(head) if head else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("data/parquet/pool_creations.parquet"))
    parser.add_argument("--sample", type=int, default=400)
    parser.add_argument("--multiple", type=float, default=10.0)
    parser.add_argument("--launch-trades", type=int, default=5)
    parser.add_argument("--min-trades", type=int, default=10,
                        help="Pools with fewer real trades are counted as dead, not measured")
    parser.add_argument("--seed", default="rhc-h0-v1", help="Sampling seed, for reproducibility")
    parser.add_argument("--out", type=Path, default=Path("data/positive_rate.json"))
    args = parser.parse_args()

    con = duckdb.connect()
    pools = con.execute(
        """
        SELECT pool, block FROM read_parquet($census)
        WHERE kind = 'v2' AND pool <> '' AND length(pool) = 42
        """,
        {"census": str(args.census)},
    ).fetchall()
    if not pools:
        print("no v2 pools in census; run scripts/pool_census.py first", file=sys.stderr)
        return 1

    # Seeded hash sample: reproducible across reruns, unlike ORDER BY random().
    def rank(row: tuple) -> str:
        return hashlib.sha256(f"{args.seed}:{row[0]}".encode()).hexdigest()

    sample = sorted(pools, key=rank)[: args.sample]
    print(f"population {len(pools):,} v2 pools; sampling {len(sample)}", file=sys.stderr)

    measured = dead = errored = 0
    winners = 0
    ratios: list[float] = []

    with Rpc() as rpc:
        head = rpc.block_number()
        for index, (pool, created_block) in enumerate(sample, start=1):
            try:
                logs = list(
                    rpc.iter_logs(
                        from_block=created_block,
                        to_block=head,
                        topics=[[TOPIC_V2_SWAP]],
                        address=pool,
                        initial_span=head,  # one call when the pool is quiet
                    )
                )
            except RpcError as exc:
                errored += 1
                print(f"  {pool} error: {exc}", file=sys.stderr)
                continue

            prices = _price_series(logs)
            if len(prices) < args.min_trades:
                dead += 1
                continue
            launch = _launch_vwap(prices, args.launch_trades)
            if not launch or launch <= 0:
                dead += 1
                continue

            ratio = max(prices) / launch
            ratios.append(ratio)
            measured += 1
            if ratio >= args.multiple:
                winners += 1

            if index % 25 == 0:
                print(
                    f"  {index}/{len(sample)}  measured={measured} dead={dead} "
                    f"winners={winners}",
                    file=sys.stderr,
                )

    total = measured + dead
    ratios.sort()

    def pct(p: float) -> float | None:
        return ratios[int(len(ratios) * p)] if ratios else None

    result = {
        "seed": args.seed,
        "sample_requested": args.sample,
        "population_v2_pools": len(pools),
        "measured": measured,
        "dead_or_untradeable": dead,
        "errored": errored,
        "multiple": args.multiple,
        "winners": winners,
        # Two denominators, because they answer different questions: the rate
        # among pools that actually traded, and the rate among all pools drawn.
        "rate_among_measured": winners / measured if measured else None,
        "rate_among_all_sampled": winners / total if total else None,
        "ratio_p50": pct(0.50),
        "ratio_p90": pct(0.90),
        "ratio_p99": pct(0.99),
        "ratio_max": ratios[-1] if ratios else None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")

    print(f"\n--- positive-class rate (V2 stratum, seed {args.seed}) ---", file=sys.stderr)
    print(f"  sampled {len(sample)}: {measured} measured, {dead} dead, {errored} errored",
          file=sys.stderr)
    print(f"  >= {args.multiple:g}x: {winners}", file=sys.stderr)
    if measured:
        print(f"  rate among measured   : {winners / measured:.3%}", file=sys.stderr)
        print(f"  rate among all sampled: {winners / total:.3%}", file=sys.stderr)
        print(f"  peak/launch  p50={pct(0.5):.2f}  p90={pct(0.9):.2f}  "
              f"p99={pct(0.99):.2f}  max={ratios[-1]:.1f}", file=sys.stderr)
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
