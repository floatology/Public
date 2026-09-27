#!/usr/bin/env python3
"""Cross-reference a week of trades against the full holder ledger.

Two datasets, each covering what the other cannot:

- **`--trades`**, from `token_wallets.py --resolve-senders`, keyed on the
  transaction's own sender. This is the real trader: on WALLET the swap log's
  `recipient` topic differed from `tx.from` on 83% of a week's swaps, because
  the dominant front-end routes through contracts.
- **`--transfers`**, from `token_transfers.py`, which replays every token
  movement into exact balances, including tokens acquired by transfer rather
  than by buying — invisible to any trade-keyed view.

**Bot classification is by behaviour, never by trade count.** A busy human and a
quiet bot both exist. The signals that separate them are ones a person cannot
produce by hand: identical trade sizes repeated, inter-trade gaps with almost no
variance, and both sides of the book inside the same block. Each is reported
separately rather than fused into a score, because a fused score hides which
signal fired and a reader cannot audit it.

**Profit is measured two ways and neither is a cost-basis convention.** Realised
flow is quote out minus quote in, which needs no lot-matching assumption.
Unrealised is the position still held marked at the current price. A wallet that
looks profitable on flow and holds nothing has exited; one negative on flow with
a large position has not yet.

**What this cannot see.** A week of trades misses positions built earlier, so a
wallet's cost basis is exact only if it started the week flat — reported per
wallet rather than assumed. One entity across several addresses is scored by
`rhc.clusters` and is not attempted here.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow.parquet as pq

WEI = 10**18
ZERO = "0x0000000000000000000000000000000000000000"
DEAD = "0x000000000000000000000000000000000000dead"


def load(path: Path) -> dict:
    t = pq.read_table(path)
    return {n: t.column(n).to_pylist() for n in t.column_names}


def gini(values: list[float]) -> float:
    """Concentration of a positive series; 0 is uniform, 1 is one winner."""
    xs = sorted(v for v in values if v > 0)
    if len(xs) < 2:
        return 0.0
    total = sum(xs)
    weighted = sum((i + 1) * x for i, x in enumerate(xs))
    return (2 * weighted) / (len(xs) * total) - (len(xs) + 1) / len(xs)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trades", type=Path, required=True)
    p.add_argument("--transfers", type=Path, required=True)
    p.add_argument("--pool", action="append", default=[])
    p.add_argument("--eth-usd", type=float, required=True)
    p.add_argument("--price-now", type=float, required=True)
    p.add_argument("--price-week-ago", type=float, required=True)
    p.add_argument("--supply", type=float, default=1e9)
    p.add_argument("--blocks-per-second", type=float, default=10.0)
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    pools = {x.lower() for x in args.pool}

    # ---------- balances from transfers, and how each address got them -------
    tr = load(args.transfers)
    n_tr = len(tr["block"])
    tr_order = sorted(range(n_tr), key=lambda i: (tr["block"][i], tr["log_index"][i]))
    bal = defaultdict(int)
    inflow = defaultdict(int); outflow = defaultdict(int); touches = defaultdict(int)
    first_seen: dict[str, int] = {}
    for i in tr_order:
        s, d, v, b = tr["src"][i], tr["dst"][i], int(tr["value"][i]), tr["block"][i]
        if v == 0:
            continue
        if s != ZERO:
            bal[s] -= v; outflow[s] += v; touches[s] += 1; first_seen.setdefault(s, b)
        if d != ZERO:
            bal[d] += v; inflow[d] += v; touches[d] += 1; first_seen.setdefault(d, b)

    # Routers keep nothing of what they move. Found by signature, not by list.
    routers = {a for a in bal
               if a not in pools
               and min(inflow[a], outflow[a]) / WEI / args.supply > 0.02
               and bal[a] / WEI / args.supply < 0.001
               and touches[a] >= 50}
    skip = routers | pools | {DEAD}
    holders = sorted((a for a in bal if bal[a] > 0 and a not in skip),
                     key=lambda a: bal[a], reverse=True)
    float_units = sum(bal[a] for a in holders)
    print(f"{len(holders):,} real holders; float {float_units/WEI/args.supply:.2%} of supply "
          f"(pool {sum(bal[a] for a in pools)/WEI/args.supply:.2%}, "
          f"burn {bal[DEAD]/WEI/args.supply:.2%}, {len(routers)} routers)")

    # ---------- the week's trades, keyed on the real sender ------------------
    td = load(args.trades)
    n = len(td["block"])
    idx = sorted(range(n), key=lambda i: (td["block"][i], td["log_index"][i]))
    b0, b1 = td["block"][idx[0]], td["block"][idx[-1]]
    days = (b1 - b0) / args.blocks_per_second / 86400
    print(f"{n:,} swaps over {days:.1f} days, blocks {b0:,}-{b1:,}\n")

    buys = defaultdict(int); sells = defaultdict(int)
    q_in = defaultdict(float); q_out = defaultdict(float)     # USD
    b_in = defaultdict(int); b_out = defaultdict(int)         # token units
    times = defaultdict(list)
    sizes = defaultdict(list)
    same_block = defaultdict(int)
    last_block_side: dict[str, tuple[int, bool]] = {}

    for i in idx:
        w = td["wallet"][i]
        if not w or w in skip:
            continue
        q = int(td["quote_amount"][i]) / WEI * args.eth_usd
        base = int(td["base_amount"][i])
        blk = td["block"][i]
        times[w].append(blk)
        sizes[w].append(round(q, 4))
        if td["is_buy"][i]:
            buys[w] += 1; q_in[w] += q; b_in[w] += base
        else:
            sells[w] += 1; q_out[w] += q; b_out[w] += base
        prev = last_block_side.get(w)
        if prev and prev[0] == blk and prev[1] != td["is_buy"][i]:
            same_block[w] += 1
        last_block_side[w] = (blk, td["is_buy"][i])

    traders = sorted(times, key=lambda w: buys[w] + sells[w], reverse=True)
    print(f"{len(traders):,} distinct traders in the window\n")

    # ---------- behavioural classification -----------------------------------
    def profile(w: str) -> dict:
        t = sorted(times[w]); k = len(t)
        gaps = [t[i + 1] - t[i] for i in range(k - 1)]
        cv = (statistics.pstdev(gaps) / statistics.mean(gaps)
              if len(gaps) > 1 and statistics.mean(gaps) > 0 else None)
        sz = sizes[w]
        repeat = 1 - len(set(sz)) / len(sz) if sz else 0.0
        turn = (min(q_in[w], q_out[w]) / max(q_in[w], q_out[w])
                if max(q_in[w], q_out[w]) > 0 else 0.0)
        return {"trades": k, "gap_cv": cv, "repeat_size": repeat,
                "round_trip": turn, "same_block_flips": same_block[w]}

    prof = {w: profile(w) for w in traders}

    def is_bot(w: str) -> list[str]:
        pr = prof[w]; flags = []
        if pr["trades"] >= 10 and pr["repeat_size"] >= 0.5:
            flags.append("repeat-sizes")
        if pr["trades"] >= 10 and pr["gap_cv"] is not None and pr["gap_cv"] < 0.5:
            flags.append("metronomic")
        if pr["same_block_flips"] >= 3:
            flags.append("same-block-flip")
        if pr["trades"] >= 20 and pr["round_trip"] >= 0.9:
            flags.append("flat-round-trip")
        return flags

    flagged = {w: f for w in traders if (f := is_bot(w))}
    bot_vol = sum(q_in[w] + q_out[w] for w in flagged)
    all_vol = sum(q_in[w] + q_out[w] for w in traders)
    print("=== bot signatures ===")
    print(f"  {len(flagged):,} of {len(traders):,} traders ({len(flagged)/len(traders):.1%}) "
          f"fire at least one signal")
    print(f"  they are {bot_vol/all_vol:.1%} of the week's ${all_vol:,.0f} two-way volume")
    counts = defaultdict(int)
    for f in flagged.values():
        for x in f:
            counts[x] += 1
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<18} {v:>5,} traders")
    hv = [q_in[w] + q_out[w] for w in traders]
    print(f"  volume concentration across traders: gini {gini(hv):.2f}")

    # ---------- accumulation vs distribution ---------------------------------
    print("\n=== who moved size this week (net USD, excluding flagged bots) ===")
    clean = [w for w in traders if w not in flagged]
    net = {w: q_out[w] - q_in[w] for w in clean}          # +ve = took money out
    net_units = {w: b_in[w] - b_out[w] for w in clean}    # +ve = accumulated tokens

    def row(w: str) -> str:
        pr = prof[w]
        held = bal.get(w, 0)
        started_flat = first_seen.get(w, 0) >= b0
        # Cost basis is only exact when the wallet began the window flat.
        vwap = q_in[w] / (b_in[w] / WEI) if b_in[w] else 0.0
        pnl = ""
        if started_flat and b_in[w]:
            mark = (args.price_now - vwap) / vwap
            pnl = f"{mark:>+7.0%}"
        return (f"{w:42} {net[w]:>+11,.0f} {net_units[w]/WEI/args.supply:>+7.3%} "
                f"{held/WEI/args.supply:>7.3%} {buys[w]:>4}/{sells[w]:<4} "
                f"{'exact' if started_flat else '  —  '} "
                f"{('$%.5f' % vwap) if vwap else '     —   '} {pnl}")

    hdr = (f"{'trader':42} {'net USD':>11} {'net tok':>7} {'holds':>7} "
           f"{'b/s':>9} {'basis':>5} {'vwap':>9} {'vs now':>7}")
    print("\n  -- biggest net accumulators (tokens) --")
    print("  " + hdr)
    for w in sorted(clean, key=lambda w: net_units[w], reverse=True)[:args.top]:
        print("  " + row(w))
    print("\n  -- biggest net distributors (tokens) --")
    print("  " + hdr)
    for w in sorted(clean, key=lambda w: net_units[w])[:args.top]:
        print("  " + row(w))

    # ---------- stealth distribution -----------------------------------------
    print("\n=== stealth distribution: many small sells, one direction ===")
    print(f"  {'trader':42} {'sells':>6} {'median $':>9} {'total $':>10} "
          f"{'buys':>5} {'holds':>7} {'span h':>7}")
    stealth = []
    for w in clean:
        if sells[w] >= 8 and buys[w] <= max(1, sells[w] // 8) and q_out[w] >= 2_000:
            sz = [s for s in sizes[w]]
            span = (max(times[w]) - min(times[w])) / args.blocks_per_second / 3600
            stealth.append((q_out[w], w, statistics.median(sz), span))
    for total, w, med, span in sorted(stealth, reverse=True)[:12]:
        print(f"  {w:42} {sells[w]:>6} {med:>9,.0f} {total:>10,.0f} "
              f"{buys[w]:>5} {bal.get(w,0)/WEI/args.supply:>6.3%} {span:>7.1f}")
    if not stealth:
        print("  none matched")

    # ---------- did the holders at the top move? ------------------------------
    print(f"\n=== the top {args.top} holders' activity this week ===")
    print(f"  {'#':>3} {'holder':42} {'holds':>7} {'bought $':>9} {'sold $':>9} "
          f"{'net tok':>8} {'trades':>6}")
    for i, a in enumerate(holders[:args.top], 1):
        traded = a in times
        print(f"  {i:>3} {a:42} {bal[a]/WEI/args.supply:>6.2%} "
              f"{q_in[a]:>9,.0f} {q_out[a]:>9,.0f} "
              f"{(b_in[a]-b_out[a])/WEI/args.supply:>+7.3%} "
              f"{(buys[a]+sells[a]) if traded else 0:>6}")

    # ---------- flow against price -------------------------------------------
    print("\n=== flow against price, by 6-hour bucket ===")
    span_blocks = int(6 * 3600 * args.blocks_per_second)
    buckets = defaultdict(lambda: {"in": 0.0, "out": 0.0, "n": 0,
                                   "px_first": None, "px_last": None})
    for i in idx:
        w = td["wallet"][i]
        if not w or w in skip:
            continue
        q_raw = int(td["quote_amount"][i]); base = int(td["base_amount"][i])
        if base == 0:
            continue
        px = q_raw / base * args.eth_usd
        k = (td["block"][i] - b0) // span_blocks
        bk = buckets[k]
        bk["n"] += 1
        if bk["px_first"] is None:
            bk["px_first"] = px
        bk["px_last"] = px
        q = q_raw / WEI * args.eth_usd
        if td["is_buy"][i]:
            bk["in"] += q
        else:
            bk["out"] += q
    print(f"  {'bucket':>8} {'trades':>7} {'buy $':>10} {'sell $':>10} {'net $':>10} "
          f"{'price':>9} {'move':>7}")
    for k in sorted(buckets):
        bk = buckets[k]
        move = (bk["px_last"] / bk["px_first"] - 1) if bk["px_first"] else 0
        print(f"  {k*6:>6}h  {bk['n']:>7,} {bk['in']:>10,.0f} {bk['out']:>10,.0f} "
              f"{bk['in']-bk['out']:>+10,.0f} {bk['px_last']:>9.5f} {move:>+6.1%}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "window_blocks": [b0, b1], "days": days, "swaps": n,
            "traders": len(traders), "flagged": len(flagged),
            "flagged_volume_share": bot_vol / all_vol,
            "holders": len(holders),
            "routers": sorted(routers),
            "per_trader": {w: {**prof[w], "flags": flagged.get(w, []),
                               "buys": buys[w], "sells": sells[w],
                               "usd_in": q_in[w], "usd_out": q_out[w],
                               "net_tokens_share": (b_in[w]-b_out[w])/WEI/args.supply,
                               "holds_share": bal.get(w, 0)/WEI/args.supply}
                           for w in traders[:500]},
        }, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
