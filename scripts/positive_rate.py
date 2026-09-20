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

from rhc.chain import USDG, WETH
from rhc.rpc import TOPIC_V2_SWAP, Rpc, RpcError

# The two other assets that act as quote sides on this chain, by pool count:
# VIRTUAL appears in 51,453 v2 pools and HOODon in 3,146.
VIRTUAL = "0xc6911796042b15d7fa4f6cde69e245ddcd3d9c31"
HOODON = "0xfb5b5778d45ae47f15323fb59b666c655174a79c"

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


def _trades(logs: list[dict], *, quote_is_token0: bool) -> list[tuple[float, int]]:
    """(quote-per-base, quote amount) for each swap, skipping degenerate ones.

    **Orientation is not optional.** A first attempt took token1/token0 by
    position, but the quote asset is token0 in some pools and token1 in others
    (Uniswap orders the pair by address, not by role). That inverted the price
    series for roughly half the sample, and an inverted collapse is
    indistinguishable from an enormous runner — it produced a median
    peak-over-launch of 22,668x, which is how the bug was caught.

    A swap moves token0 one way and token1 the other, so exactly one of each
    pair is non-zero. Both-zero or one-sided logs are skipped rather than
    treated as a price of zero, which would poison the peak ratio.

    Decimals are deliberately not normalised: these are *ratios over time*
    within a single pool, where the decimal factor is constant and cancels.
    They are not comparable across pools and must not be read as prices.
    """
    trades: list[tuple[float, int]] = []
    for log in logs:
        parsed = _parse_v2_swap(log.get("data") or "0x")
        if parsed is None:
            continue
        a0_in, a1_in, a0_out, a1_out = parsed
        amount0 = a0_in or a0_out
        amount1 = a1_in or a1_out
        if amount0 <= 0 or amount1 <= 0:
            continue
        quote, base = (amount0, amount1) if quote_is_token0 else (amount1, amount0)
        trades.append((quote / base, quote))
    return trades


def _drop_dust(trades: list[tuple[float, int]], floor_frac: float) -> list[tuple[float, int]]:
    """Remove trades far smaller than the pool's own real activity.

    A one-wei quote leg drives the computed launch price to near zero, and the
    peak-over-launch ratio then explodes: an unfiltered 1,200-pool sample
    produced a p99 of 9.4e18, a physically impossible number.

    **Anchor to the 90th percentile trade, not the median.** A first attempt
    used the median, which fails precisely where it matters: in a pool where
    most trades are dust the median *is* dust, so one percent of it is dust
    too, and the filter passes everything. That version still produced a p99 of
    8.8e18 across 1,200 pools while looking clean on a 60-pool smoke test. The
    p90 anchors to whatever genuine activity a pool had, however rare.

    The threshold stays relative to each pool rather than absolute, because
    pools differ by orders of magnitude in size and the quote assets differ in
    decimals (USDG has 6, WETH and VIRTUAL have 18), so no single wei figure
    is meaningful across them.
    """
    if not trades:
        return []
    amounts = sorted(amount for _, amount in trades)
    anchor = amounts[min(len(amounts) - 1, int(len(amounts) * 0.9))]
    floor = anchor * floor_frac
    return [(price, amount) for price, amount in trades if amount >= floor]


def _launch_vwap(trades: list[tuple[float, int]], first_n: int) -> float | None:
    """Reference price: volume-weighted mean over the first `first_n` trades.

    Weighted by quote amount, per PREREGISTRATION — a simple mean lets one
    small early trade pull the reference as hard as a large one.
    """
    head = trades[:first_n]
    volume = sum(amount for _, amount in head)
    if volume <= 0:
        return None
    return sum(price * amount for price, amount in head) / volume


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("data/parquet/pool_creations.parquet"))
    parser.add_argument("--sample", type=int, default=400)
    parser.add_argument("--multiple", type=float, default=10.0)
    parser.add_argument("--launch-trades", type=int, default=5)
    parser.add_argument("--min-trades", type=int, default=10,
                        help="Pools with fewer real trades are counted as dead, not measured")
    parser.add_argument("--max-plausible", type=float, default=1e6,
                        help="Ratios above this are artefacts, counted separately")
    parser.add_argument("--dust-floor", type=float, default=0.01,
                        help="Drop trades below this fraction of the pool's median trade size")
    parser.add_argument("--seed", default="rhc-h0-v1", help="Sampling seed, for reproducibility")
    parser.add_argument("--out", type=Path, default=Path("data/positive_rate.json"))
    args = parser.parse_args()

    con = duckdb.connect()
    # Restrict to pools with a recognised quote asset on one side, and record
    # which side it is. A memecoin/memecoin pool has no meaningful price at all
    # (21% of v2 pools), and without knowing the quote side the ratio inverts.
    quotes = [q.lower() for q in (WETH, USDG, VIRTUAL, HOODON)]
    pools = con.execute(
        """
        SELECT pool, block, lower(token0) IN $quotes AS quote_is_token0
        FROM read_parquet($census)
        WHERE kind = 'v2' AND pool <> '' AND length(pool) = 42
          AND (lower(token0) IN $quotes OR lower(token1) IN $quotes)
        """,
        {"census": str(args.census), "quotes": quotes},
    ).fetchall()
    if not pools:
        print("no v2 pools in census; run scripts/pool_census.py first", file=sys.stderr)
        return 1

    # Seeded hash sample: reproducible across reruns, unlike ORDER BY random().
    def rank(row: tuple) -> str:
        return hashlib.sha256(f"{args.seed}:{row[0]}".encode()).hexdigest()

    sample = sorted(pools, key=rank)[: args.sample]
    print(
        f"population {len(pools):,} quote-paired v2 pools; sampling {len(sample)}",
        file=sys.stderr,
    )

    measured = dead = errored = implausible = 0
    winners = 0
    ratios: list[float] = []

    with Rpc() as rpc:
        head = rpc.block_number()
        for index, (pool, created_block, quote_is_token0) in enumerate(sample, start=1):
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

            trades = _drop_dust(
                _trades(logs, quote_is_token0=bool(quote_is_token0)), args.dust_floor
            )
            if len(trades) < args.min_trades:
                dead += 1
                continue
            launch = _launch_vwap(trades, args.launch_trades)
            if not launch or launch <= 0:
                dead += 1
                continue

            ratio = max(price for price, _ in trades) / launch
            # A ratio this large is an artefact, not a token that went up a
            # trillion-fold. Count it as unmeasurable rather than silently
            # booking it as the sample's biggest winner.
            if ratio > args.max_plausible:
                implausible += 1
                continue
            ratios.append(ratio)
            measured += 1
            if ratio >= args.multiple:
                winners += 1

            if index % 25 == 0:
                print(
                    f"  {index}/{len(sample)}  measured={measured} dead={dead} "
                    f"implausible={implausible} winners={winners}",
                    file=sys.stderr,
                )

    total = measured + dead
    ratios.sort()

    def pct(p: float) -> float | None:
        return ratios[int(len(ratios) * p)] if ratios else None

    result = {
        "seed": args.seed,
        "sample_requested": args.sample,
        "population_quote_paired_v2_pools": len(pools),
        "measured": measured,
        "dead_or_untradeable": dead,
        "errored": errored,
        "implausible": implausible,
        "multiple": args.multiple,
        "dust_floor": args.dust_floor,
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
    print(f"  sampled {len(sample)}: {measured} measured, {dead} dead, "
          f"{implausible} implausible, {errored} errored", file=sys.stderr)
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
