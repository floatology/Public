#!/usr/bin/env python3
"""Read one token's swap archive and describe who accumulated, when, and whether.

Four questions, in the order they matter:

1. **Is the net-position ledger consistent with accumulation, or with churn?**
   Buy volume alone says nothing; a wash bot posts enormous buy volume and ends
   flat. What counts is base tokens still held from pool activity, priced
   against the quote actually paid.
2. **When did the accumulating wallets act?** A cohort that built before a move
   is a different object from one that bought the move. The split is made at a
   named block, so the answer cannot be tuned after seeing it.
3. **Did the wallets that sold the top come back?** For a token that has already
   spiked and crashed, the question is whether the sellers redistributed to new
   holders or are still sitting on the float waiting to sell again.
4. **How much of this is one entity?** `rhc.clusters` scores co-timing against a
   null of chance overlap; `rhc.manipulation` scores bundle and bump signatures.

**Position accounting is FIFO-free on purpose.** Realised profit needs a cost
basis convention and every convention is arguable. Net quote flow — what a
wallet paid in minus what it took out — is convention-free, and combined with
the base units still held it answers "are they up" without choosing a lot.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow.parquet as pq

WEI = 10**18


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=Path, required=True)
    parser.add_argument("--eth-usd", type=float, required=True,
                        help="quote asset price in USD; WETH pools only")
    parser.add_argument("--supply", type=float, default=1e9)
    parser.add_argument("--price-now", type=float, required=True,
                        help="token price in USD, for marking positions")
    parser.add_argument("--split-block", type=int, action="append", default=[],
                        help="era boundary, repeatable; eras are reported separately")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    table = pq.read_table(args.trades)
    cols = {name: table.column(name).to_pylist() for name in table.column_names}
    n = len(cols["block"])
    print(f"{n:,} trades, blocks {min(cols['block']):,}-{max(cols['block']):,}\n")

    bounds = sorted(args.split_block)
    def era_of(block: int) -> int:
        i = 0
        for b in bounds:
            if block >= b:
                i += 1
        return i

    # Per-wallet ledger. Base in units, quote in USD.
    base = defaultdict(float)        # net tokens still held from pool activity
    spent = defaultdict(float)       # USD paid in
    taken = defaultdict(float)       # USD taken out
    buys = defaultdict(int)
    sells = defaultdict(int)
    first = {}
    last = {}
    era_base = defaultdict(lambda: defaultdict(float))
    era_flow = defaultdict(float)    # net USD into the pool, per era

    for i in range(n):
        w = cols["wallet"][i]
        if not w:
            continue
        blk = cols["block"][i]
        q = int(cols["quote_amount"][i]) / WEI * args.eth_usd
        b = int(cols["base_amount"][i]) / WEI
        e = era_of(blk)
        if cols["is_buy"][i]:
            base[w] += b
            spent[w] += q
            buys[w] += 1
            era_base[w][e] += b
            era_flow[e] += q
        else:
            base[w] -= b
            taken[w] += q
            sells[w] += 1
            era_base[w][e] -= b
            era_flow[e] -= q
        if w not in first:
            first[w] = blk
        last[w] = blk

    wallets = sorted(base, key=lambda w: base[w], reverse=True)
    print(f"{len(wallets):,} distinct recipient addresses\n")

    # -- Q1: churn vs accumulation ------------------------------------------
    gross_in = sum(spent.values())
    gross_out = sum(taken.values())
    held = sum(v for v in base.values() if v > 0)
    print("=== flow ===")
    print(f"  gross bought   ${gross_in:>14,.0f}")
    print(f"  gross sold     ${gross_out:>14,.0f}")
    print(f"  net into pool  ${gross_in - gross_out:>14,.0f}")
    print(f"  tokens net held by buyers {held/args.supply:>6.2%} of supply")
    flat = sum(1 for w in wallets if abs(base[w]) < 0.001 * args.supply / 1000)
    print(f"  wallets ending within a rounding of flat: {flat:,} "
          f"({flat/max(1,len(wallets)):.1%})\n")

    if bounds:
        print("=== net USD flow by era ===")
        edges = [None] + bounds + [None]
        for e in sorted(era_flow):
            lo = edges[e] if e < len(bounds) + 1 else None
            print(f"  era {e} (from block {bounds[e-1]:,} )" if e else "  era 0 (from launch)",
                  f"  net ${era_flow[e]:>+14,.0f}")
        print()

    # -- Q2/Q3: the biggest current holders ---------------------------------
    print(f"=== top {args.top} net accumulators (by tokens still held) ===")
    hdr = f"{'#':>3} {'wallet':42} {'share':>7} {'value':>11} {'paid':>11} {'took':>11} {'net':>11} {'b/s':>9}"
    if bounds:
        hdr += "  " + " ".join(f"{'e'+str(i):>8}" for i in range(len(bounds) + 1))
    print(hdr)
    for i, w in enumerate(wallets[:args.top], 1):
        share = base[w] / args.supply
        value = base[w] * args.price_now
        net = taken[w] - spent[w]
        line = (f"{i:>3} {w:42} {share:>6.3%} ${value:>10,.0f} ${spent[w]:>10,.0f} "
                f"${taken[w]:>10,.0f} ${net:>+10,.0f} {buys[w]:>4}/{sells[w]:<4}")
        if bounds:
            line += "  " + " ".join(
                f"{era_base[w][e]/args.supply:>8.3%}" for e in range(len(bounds) + 1))
        print(line)

    # -- who took money off the table ---------------------------------------
    print(f"\n=== top {args.top} net extractors (USD out minus in) ===")
    by_profit = sorted(wallets, key=lambda w: taken[w] - spent[w], reverse=True)
    print(f"{'#':>3} {'wallet':42} {'net out':>12} {'still held':>11} {'b/s':>9} {'first blk':>12}")
    for i, w in enumerate(by_profit[:args.top], 1):
        print(f"{i:>3} {w:42} ${taken[w]-spent[w]:>+11,.0f} "
              f"{base[w]/args.supply:>10.3%} {buys[w]:>4}/{sells[w]:<4} {first[w]:>12,}")

    if args.out:
        payload = {
            "trades": n,
            "wallets": len(wallets),
            "gross_bought_usd": gross_in,
            "gross_sold_usd": gross_out,
            "era_net_flow_usd": {str(k): v for k, v in era_flow.items()},
            "holders": [
                {"wallet": w, "supply_share": base[w] / args.supply,
                 "value_usd": base[w] * args.price_now,
                 "spent_usd": spent[w], "taken_usd": taken[w],
                 "buys": buys[w], "sells": sells[w],
                 "first_block": first[w], "last_block": last[w],
                 "era_share": {str(e): era_base[w][e] / args.supply
                               for e in range(len(bounds) + 1)}}
                for w in wallets[:200]
            ],
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
