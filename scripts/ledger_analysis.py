#!/usr/bin/env python3
"""The story behind the chart, read from a token's full ledger.

Reads `data/tokens/<token>/{ledger,transfers,swaps}.parquet` and prints a
sectioned report. Every section answers one question and says how it measured
it, because on this chain the obvious measurement has been wrong often enough
(`docs/22`, `docs/23`) that an unexplained number should not be trusted.

**Prices are compared in ETH, not USD,** wherever the comparison spans time.
The ledger's USD column uses one ETH price for the whole history, so a USD
comparison between July and September carries ETH's own move inside it. Ratios
of ETH prices do not.

**"Insider" is never asserted, only evidenced.** The report lists behaviours
that would be consistent with advance knowledge — buying in the first seconds,
receiving supply from the deployer rather than the market, exiting in the hours
before a collapse — and for each it gives the base rate to compare against.
Being early is not proof of anything; being early *and* identical in size to
three other addresses in the same block is a pattern worth naming.

**Liquidity events are separated from trades.** A transfer into or out of the
pool in a transaction that contains no swap is a liquidity add or removal, not a
buy or sell, and a removal immediately before a collapse is a different story
from a sale.
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from block_times import BlockClock

WEI = 10**18
ZERO = "0x0000000000000000000000000000000000000000"
DEAD = "0x000000000000000000000000000000000000dead"
BLOCKS_PER_SEC = 10.0


def load(path: Path) -> dict[str, list]:
    t = pq.read_table(path)
    return {n: t.column(n).to_pylist() for n in t.column_names}


def day(ts: int) -> str:
    return dt.datetime.utcfromtimestamp(ts).strftime("%m-%d")


def when(ts: int) -> str:
    return dt.datetime.utcfromtimestamp(ts).strftime("%m-%d %H:%M")


def short(a: str | None) -> str:
    return (a[:6] + "…" + a[-4:]) if a else "(none)"


def usd(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e6:
        return f"{sign}${x/1e6:.2f}M"
    if x >= 1e3:
        return f"{sign}${x/1e3:.1f}k"
    return f"{sign}${x:.0f}"


def section(title: str) -> None:
    print(f"\n{'='*78}\n{title}\n{'='*78}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--pool", required=True)
    p.add_argument("--supply", type=float, required=True)
    p.add_argument("--price-now", type=float, required=True, help="USD")
    p.add_argument("--eth-usd", type=float, required=True)
    p.add_argument("--snipe-blocks", type=int, default=600,
                   help="blocks after the first swap that count as sniping (~60s)")
    p.add_argument("--whale-share", type=float, default=0.005,
                   help="supply share that makes a holder or trader a major player")
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    pool = args.pool.lower()
    SUP = args.supply
    clock = BlockClock(json.loads(Path("data/tokens/block_times.json").read_text())["anchors"])
    px_now_eth = args.price_now / args.eth_usd
    report: dict = {"token": args.name}

    L = load(args.dir / "ledger.parquet")
    T = load(args.dir / "transfers.parquet")
    n = len(L["ts"])
    order = sorted(range(n), key=lambda i: (L["block"][i], L["log_index"][i]))
    swap_tx = set(L["tx_hash"])
    px_eth = [L["quote_eth"][i] / L["tokens"][i] if L["tokens"][i] else 0.0 for i in range(n)]

    # ------------------------------------------------------------------ balances
    tord = sorted(range(len(T["block"])), key=lambda i: (T["block"][i], T["log_index"][i]))
    bal = defaultdict(int)
    inflow = defaultdict(int); outflow = defaultdict(int); touches = defaultdict(int)
    first_seen: dict[str, int] = {}
    mint_to = None
    for i in tord:
        s, d, v, b = T["src"][i], T["dst"][i], int(T["value"][i]), T["block"][i]
        if not v:
            continue
        if s == ZERO:
            mint_to = mint_to or d
        if s != ZERO:
            bal[s] -= v; outflow[s] += v; touches[s] += 1; first_seen.setdefault(s, b)
        if d != ZERO:
            bal[d] += v; inflow[d] += v; touches[d] += 1; first_seen.setdefault(d, b)
    # Routers keep almost nothing of what they move. Some keep dust or fees,
    # which the balance test alone misses: on WALLET one router retains 0.31%
    # of supply and was reported as the biggest bot, a feeder of 32 holders and
    # a $147k loser, all of it artifact. No person sends tokens to hundreds of
    # distinct addresses, so breadth of counterparties catches what balance
    # does not.
    dests = defaultdict(set)
    for i in tord:
        if int(T["value"][i]):
            dests[T["src"][i]].add(T["dst"][i])
    routers = {a for a in bal if a != pool and (
        (min(inflow[a], outflow[a]) / WEI / SUP > 0.02
         and bal[a] / WEI / SUP < 0.001 and touches[a] >= 50)
        or (len(dests[a]) >= 500 and min(inflow[a], outflow[a]) / WEI / SUP > 0.02))}
    market = routers | {pool}
    skip = market | {DEAD}

    # An intermediary's "trades" belong to whoever it later pays out to, so they
    # are not one trader's behaviour. Their rows are kept for volume and price,
    # and removed from every per-trader measure.
    intermediary_usd = 0.0
    for i in range(n):
        if L["trader"][i] in routers:
            intermediary_usd += L["usd"][i]
            L["trader"][i] = None

    first_swap_block = L["block"][order[0]]
    ts0, ts1 = L["ts"][order[0]], L["ts"][order[-1]]

    # ================================================================== 1. PRICE
    section(f"1. THE CHART — {args.name}, daily, from the ledger (price in USD at "
            f"${args.eth_usd:,.0f}/ETH)")
    days = defaultdict(lambda: {"o": None, "h": 0, "l": 1e18, "c": None, "vol": 0.0,
                                "buy": 0.0, "sell": 0.0, "traders": set(), "new": 0})
    seen_trader: set[str] = set()
    for i in order:
        d = day(L["ts"][i]); r = days[d]; pe = px_eth[i] * args.eth_usd
        if not pe:
            continue
        r["o"] = r["o"] if r["o"] is not None else pe
        r["h"] = max(r["h"], pe); r["l"] = min(r["l"], pe); r["c"] = pe
        r["vol"] += L["usd"][i]
        r["buy" if L["side"][i] == "buy" else "sell"] += L["usd"][i]
        w = L["trader"][i]
        if w:
            r["traders"].add(w)
            if w not in seen_trader:
                seen_trader.add(w); r["new"] += 1
    ath = max(days.items(), key=lambda kv: kv[1]["h"])
    print(f"{'day':>6} {'close':>9} {'high':>9} {'volume':>9} {'net flow':>9} "
          f"{'traders':>7} {'new':>5}")
    for d, r in sorted(days.items()):
        print(f"{d:>6} {r['c']:>9.5f} {r['h']:>9.5f} {usd(r['vol']):>9} "
              f"{usd(r['buy']-r['sell']):>9} {len(r['traders']):>7} {r['new']:>5}")
    print(f"\nATH ${ath[1]['h']:.5f} on {ath[0]}; now ${args.price_now:.5f} "
          f"({args.price_now/ath[1]['h']-1:+.0%} from ATH)")
    report["ath"] = {"day": ath[0], "price": ath[1]["h"]}

    # ============================================================ 2. SUPPLY ORIGIN
    section("2. WHERE THE SUPPLY CAME FROM")
    print(f"minted to {mint_to} at block {first_seen.get(mint_to, 0):,}")
    print(f"minter holds now: {bal[mint_to]/WEI/SUP:.2%} of supply")
    # Where did the minter's tokens go?
    mdest = defaultdict(int)
    for i in tord:
        if T["src"][i] == mint_to and int(T["value"][i]):
            mdest[T["dst"][i]] += int(T["value"][i])
    print("minter sent to:")
    for a, v in sorted(mdest.items(), key=lambda kv: -kv[1])[:8]:
        tag = "POOL" if a == pool else ("router" if a in routers else "")
        print(f"   {a}  {v/WEI/SUP:>7.2%}  holds now {bal[a]/WEI/SUP:>6.2%}  {tag}")

    # Liquidity events: pool transfers in transactions with no swap.
    lp_in = defaultdict(int); lp_out = defaultdict(int); lp_events = []
    for i in tord:
        h = T["tx_hash"][i]
        if h in swap_tx:
            continue
        v = int(T["value"][i])
        if not v:
            continue
        if T["dst"][i] == pool and T["src"][i] != ZERO:
            lp_in[T["src"][i]] += v; lp_events.append((T["block"][i], "add", T["src"][i], v))
        elif T["src"][i] == pool:
            lp_out[T["dst"][i]] += v; lp_events.append((T["block"][i], "remove", T["dst"][i], v))
    print(f"\nliquidity events (pool transfers with no swap in the tx): {len(lp_events):,}")
    print(f"  tokens added {sum(lp_in.values())/WEI/SUP:.2%} of supply by "
          f"{len(lp_in)} addresses; removed {sum(lp_out.values())/WEI/SUP:.2%} by "
          f"{len(lp_out)}")
    for a, v in sorted(lp_in.items(), key=lambda kv: -kv[1])[:4]:
        print(f"    added   {a}  {v/WEI/SUP:.2%}")
    for a, v in sorted(lp_out.items(), key=lambda kv: -kv[1])[:4]:
        print(f"    removed {a}  {v/WEI/SUP:.2%}")
    report["lp"] = {"added": sum(lp_in.values())/WEI/SUP,
                    "removed": sum(lp_out.values())/WEI/SUP}

    # =============================================================== 3. SNIPERS
    section(f"3. THE FIRST {args.snipe_blocks} BLOCKS (~{args.snipe_blocks/BLOCKS_PER_SEC:.0f}s) "
            f"AFTER TRADING OPENED")
    snipe = defaultdict(lambda: [0.0, 0.0, 0])   # tokens, usd, n
    snipe_sizes = defaultdict(list)
    for i in order:
        if L["block"][i] > first_swap_block + args.snipe_blocks:
            break
        if L["side"][i] != "buy" or not L["trader"][i]:
            continue
        w = L["trader"][i]
        snipe[w][0] += L["tokens"][i]; snipe[w][1] += L["usd"][i]; snipe[w][2] += 1
        snipe_sizes[round(L["tokens"][i], -3)].append((w, L["block"][i]))
    tot_snipe = sum(v[0] for v in snipe.values())
    print(f"{len(snipe)} addresses bought {tot_snipe/SUP:.2%} of supply for "
          f"{usd(sum(v[1] for v in snipe.values()))}")
    # later fate of each sniper
    sold_by = defaultdict(float); got_by = defaultdict(float)
    for i in order:
        w = L["trader"][i]
        if w in snipe:
            (got_by if L["side"][i] == "buy" else sold_by)[w] += L["usd"][i]
    print(f"{'address':>13} {'bought':>8} {'paid':>8} {'later sold':>11} {'holds now':>9}")
    for w, (tok, u, k) in sorted(snipe.items(), key=lambda kv: -kv[1][0])[:12]:
        print(f"{short(w):>13} {tok/SUP:>7.2%} {usd(u):>8} {usd(sold_by[w]):>11} "
              f"{bal[w]/WEI/SUP:>8.3%}")
    same = [(sz, ws) for sz, ws in snipe_sizes.items() if len({w for w, _ in ws}) >= 3]
    if same:
        print("\nidentical-size buys by 3+ different addresses in the snipe window:")
        for sz, ws in sorted(same, key=lambda x: -x[0])[:5]:
            addrs = sorted({w for w, _ in ws}); blks = sorted({b for _, b in ws})
            print(f"   {sz:,.0f} tokens ({sz/SUP:.2%}) x {len(addrs)} addresses, blocks "
                  f"{blks[0]:,}-{blks[-1]:,}: {', '.join(short(a) for a in addrs[:6])}")
    report["snipers"] = {"addresses": len(snipe), "share": tot_snipe / SUP,
                         "paid_usd": sum(v[1] for v in snipe.values()),
                         "later_sold_usd": sum(sold_by.values())}

    # ========================================================= 4. PER-TRADER BOOK
    book = defaultdict(lambda: {"buy_t": 0.0, "sell_t": 0.0, "buy_e": 0.0, "sell_e": 0.0,
                                "buy_u": 0.0, "sell_u": 0.0, "nb": 0, "ns": 0,
                                "blocks": [], "sizes": [], "flips": 0, "first": None,
                                "last": None, "last_side": None, "last_block": None})
    for i in order:
        w = L["trader"][i]
        if not w:
            continue
        b = book[w]; buy = L["side"][i] == "buy"
        if buy:
            b["buy_t"] += L["tokens"][i]; b["buy_e"] += L["quote_eth"][i]
            b["buy_u"] += L["usd"][i]; b["nb"] += 1
        else:
            b["sell_t"] += L["tokens"][i]; b["sell_e"] += L["quote_eth"][i]
            b["sell_u"] += L["usd"][i]; b["ns"] += 1
        if b["last_block"] == L["block"][i] and b["last_side"] != L["side"][i]:
            b["flips"] += 1
        b["last_block"], b["last_side"] = L["block"][i], L["side"][i]
        b["blocks"].append(L["block"][i]); b["sizes"].append(round(L["usd"][i], 2))
        b["first"] = b["first"] or L["ts"][i]; b["last"] = L["ts"][i]

    def flags(w: str) -> list[str]:
        b = book[w]; k = b["nb"] + b["ns"]; f = []
        if k >= 10 and 1 - len(set(b["sizes"])) / k >= 0.5:
            f.append("repeat-size")
        gaps = [y - x for x, y in zip(b["blocks"], b["blocks"][1:])]
        if len(gaps) >= 9 and statistics.mean(gaps) > 0 and \
                statistics.pstdev(gaps) / statistics.mean(gaps) < 0.5:
            f.append("metronomic")
        if b["flips"] >= 3:
            f.append("same-block-flip")
        mx = max(b["buy_u"], b["sell_u"])
        if k >= 20 and mx and min(b["buy_u"], b["sell_u"]) / mx >= 0.9:
            f.append("flat-round-trip")
        if k >= 200 and b["last"] - b["first"] < 86400 * 3:
            f.append("high-frequency")
        return f

    fl = {w: flags(w) for w in book}
    bots = {w for w, f in fl.items() if f}
    vol = {w: book[w]["buy_u"] + book[w]["sell_u"] for w in book}
    total_vol = sum(L["usd"])
    unattr_vol = sum(L["usd"][i] for i in range(n) if not L["trader"][i])
    whale_cut = sorted(vol.values(), reverse=True)[max(0, len(vol) // 100 - 1)] if vol else 0
    whales = {w for w in book if vol[w] >= whale_cut and w not in bots}
    retail = set(book) - bots - whales

    # ================================================================ 5. BOTS
    section("5. BOTS VS ORGANIC")
    def share(ws):
        return sum(vol[w] for w in ws) / 2 / total_vol
    print(f"{len(book):,} attributed traders; total two-way volume {usd(total_vol)}")
    print(f"  bot-signature traders : {len(bots):>6,}  {share(bots):>6.1%} of volume")
    print(f"  top-1% non-bot traders: {len(whales):>6,}  {share(whales):>6.1%}")
    print(f"  everyone else         : {len(retail):>6,}  {share(retail):>6.1%}")
    print(f"  unattributed or intermediary: {unattr_vol/total_vol:.1%} "
          f"(of which custodial/router intermediaries {intermediary_usd/total_vol:.1%}; "
          f"the rest same-tx arbitrage netting to zero)")
    c = Counter(x for f in fl.values() for x in f)
    print("  signals fired:", ", ".join(f"{k} {v}" for k, v in c.most_common()))
    print("\n  biggest bots by volume:")
    for w in sorted(bots, key=lambda w: -vol[w])[:8]:
        b = book[w]
        print(f"    {short(w)}  {usd(vol[w]):>8}  {b['nb']:>5}b/{b['ns']:<5}s  "
              f"net {usd(b['sell_u']-b['buy_u']):>8}  {','.join(fl[w])}")
    sizes = sorted(L["usd"])
    print(f"\n  trade size: median {usd(sizes[len(sizes)//2])}, p90 "
          f"{usd(sizes[int(len(sizes)*.9)])}, p99 {usd(sizes[int(len(sizes)*.99)])}; "
          f"{sum(1 for s in sizes if s < 100)/len(sizes):.0%} under $100")
    report["bots"] = {"traders": len(bots), "volume_share": share(bots),
                      "whale_volume_share": share(whales),
                      "retail_volume_share": share(retail),
                      "unattributed_share": unattr_vol / total_vol}

    # ======================================================== 6. MAJOR PLAYERS
    section("6. MAJOR PLAYERS — by profit taken (convention-free: ETH out minus ETH in)")
    def pnl_eth(w):
        b = book[w]
        # open position marked at today's price, from pool position not holdings
        open_t = max(0.0, b["buy_t"] - b["sell_t"])
        return b["sell_e"] - b["buy_e"], open_t * px_now_eth
    rows = []
    for w in book:
        realised, open_val = pnl_eth(w)
        rows.append((realised, open_val, w))
    print(f"{'address':>13} {'realised':>9} {'open@now':>9} {'bought':>8} {'sold':>8} "
          f"{'buy px':>9} {'sell px':>9} {'x':>5} {'first':>11} {'holds':>6}  flags")
    for realised, open_val, w in sorted(rows, reverse=True)[:15]:
        b = book[w]
        bp = b["buy_e"] / b["buy_t"] * args.eth_usd if b["buy_t"] else 0
        sp = b["sell_e"] / b["sell_t"] * args.eth_usd if b["sell_t"] else 0
        print(f"{short(w):>13} {usd(realised*args.eth_usd):>9} {usd(open_val*args.eth_usd):>9} "
              f"{usd(b['buy_u']):>8} {usd(b['sell_u']):>8} {bp:>9.5f} {sp:>9.5f} "
              f"{(sp/bp if bp and sp else 0):>5.1f} {when(b['first']):>11} "
              f"{bal.get(w,0)/WEI/SUP:>5.2%}  {','.join(fl[w])}")
    print("\n  biggest losers:")
    for realised, open_val, w in sorted(rows)[:8]:
        b = book[w]
        bp = b["buy_e"] / b["buy_t"] * args.eth_usd if b["buy_t"] else 0
        print(f"{short(w):>13} {usd(realised*args.eth_usd):>9} open {usd(open_val*args.eth_usd):>8} "
              f"bought {usd(b['buy_u']):>8} at {bp:.5f}  first {when(b['first'])}  "
              f"holds {bal.get(w,0)/WEI/SUP:.2%}")
    winners = sum(1 for r, o, w in rows if r + o > 0)
    tot_real = sum(r for r, o, w in rows) * args.eth_usd
    print(f"\n  {winners:,} of {len(rows):,} traders ({winners/len(rows):.0%}) are up on "
          f"realised + open-at-today's-price; net across all: {usd(tot_real)} realised")
    top10 = sorted((r for r, o, w in rows), reverse=True)[:10]
    print(f"  the top 10 took {usd(sum(top10)*args.eth_usd)} — "
          f"{sum(top10)/max(1e-9, sum(r for r, o, w in rows if r > 0)):.0%} of all realised profit")
    report["pnl"] = {"winners": winners, "traders": len(rows),
                     "top10_share_of_profit": sum(top10) / max(1e-9, sum(r for r, o, w in rows if r > 0))}

    # ============================================================ 7. HOLDERS
    section("7. WHO HOLDS IT NOW, AND HOW THEY GOT IT")
    holders = sorted((a for a in bal if bal[a] > 0 and a not in skip),
                     key=lambda a: -bal[a])
    fl_tot = sum(bal[a] for a in holders)
    print(f"{len(holders):,} holders; pool {bal[pool]/WEI/SUP:.2%}, burn "
          f"{bal[DEAD]/WEI/SUP:.2%}, float {fl_tot/WEI/SUP:.2%}")
    cum = 0
    for k, a in enumerate(holders, 1):
        cum += bal[a]
        if k in (1, 5, 10, 25, 100):
            print(f"  top {k:>3}: {cum/WEI/SUP:.2%}")
    # acquisition route: bought (from market) vs received (peer transfer)
    recv_market = defaultdict(int); recv_peer = defaultdict(int)
    peer_src = defaultdict(lambda: defaultdict(int))
    for i in tord:
        s, d, v = T["src"][i], T["dst"][i], int(T["value"][i])
        if not v or d in skip or d == ZERO:
            continue
        if s in market:
            recv_market[d] += v
        elif s != ZERO:
            recv_peer[d] += v; peer_src[d][s] += v
    print(f"\n{'#':>3} {'holder':>13} {'holds':>6} {'value':>8} {'bought':>7} "
          f"{'recvd':>7} {'from':>13} {'since':>11} {'pool basis':>10} {'vs now':>7}")
    for k, a in enumerate(holders[:20], 1):
        b = book.get(a)
        basis = (b["buy_e"] / b["buy_t"] * args.eth_usd) if b and b["buy_t"] else 0
        top_src = max(peer_src[a].items(), key=lambda kv: kv[1])[0] if peer_src[a] else None
        print(f"{k:>3} {short(a):>13} {bal[a]/WEI/SUP:>5.2%} "
              f"{usd(bal[a]/WEI*args.price_now):>8} "
              f"{recv_market[a]/WEI/SUP:>6.2%} {recv_peer[a]/WEI/SUP:>6.2%} "
              f"{short(top_src) if top_src else '—':>13} "
              f"{when(clock.at(first_seen.get(a, first_swap_block))):>11} "
              f"{(f'{basis:.5f}' if basis else '—'):>10} "
              f"{(f'{args.price_now/basis-1:+.0%}' if basis else '—'):>7}")
    peer_share = sum(recv_peer[a] for a in holders) / max(1, sum(recv_peer[a] + recv_market[a] for a in holders))
    print(f"\n  across all holders, {peer_share:.0%} of tokens ever received came from "
          f"another holder rather than the market")

    # funding links among the top 50 holders
    top = set(holders[:50])
    links = []
    for i in tord:
        s, d, v = T["src"][i], T["dst"][i], int(T["value"][i])
        if v and s in top and d in top:
            links.append((s, d, v))
    agg = defaultdict(int)
    for s, d, v in links:
        agg[(s, d)] += v
    print(f"\n  direct transfers between top-50 holders: {len(agg)} links")
    for (s, d), v in sorted(agg.items(), key=lambda kv: -kv[1])[:8]:
        print(f"    {short(s)} -> {short(d)}  {v/WEI/SUP:.2%}")
    # common upstream source for top holders
    src_count = defaultdict(set)
    for a in holders[:100]:
        for s in peer_src[a]:
            if s not in skip:
                src_count[s].add(a)
    shared = sorted(((len(v), s) for s, v in src_count.items() if len(v) >= 3), reverse=True)
    if shared:
        print("\n  addresses that supplied 3+ of the top 100 holders directly:")
        for k, s in shared[:6]:
            held = sum(bal[a] for a in src_count[s])
            print(f"    {s}  fed {k} holders now holding {held/WEI/SUP:.2%}; itself holds "
                  f"{bal[s]/WEI/SUP:.2%}")
    report["holders"] = {"count": len(holders), "top10": sum(bal[a] for a in holders[:10])/WEI/SUP,
                         "peer_received_share": peer_share}

    # ======================================================== 8. THE BIG MOVES
    section("8. THE BIG MOVES — who acted before them")
    # hourly closes in ETH
    hourly: dict[int, float] = {}
    for i in order:
        if px_eth[i]:
            hourly[L["ts"][i] // 3600] = px_eth[i]
    hrs = sorted(hourly)
    # largest single-hour drop, and largest multi-day run (trough -> later peak)
    worst = min(((hourly[h] / hourly[hrs[k-1]] - 1, h) for k, h in enumerate(hrs) if k),
                default=(0, hrs[0]))
    best_run = (1.0, hrs[0], hrs[0]); low_h = hrs[0]
    for h in hrs:
        if hourly[h] < hourly[low_h]:
            low_h = h
        r = hourly[h] / hourly[low_h]
        if r > best_run[0]:
            best_run = (r, low_h, h)
    print(f"biggest run: {best_run[0]:.1f}x from {when(best_run[1]*3600)} to "
          f"{when(best_run[2]*3600)}")
    print(f"worst hour : {worst[0]:+.0%} at {when(worst[1]*3600)}")

    def window_flow(t_lo, t_hi):
        f = defaultdict(float)
        for i in order:
            if t_lo <= L["ts"][i] < t_hi and L["trader"][i]:
                f[L["trader"][i]] += L["tokens"][i] * (1 if L["side"][i] == "buy" else -1)
        return f

    # before the run: net buyers in the 3 days up to the trough + first quarter of the run
    lo_t, hi_t = best_run[1] * 3600, best_run[2] * 3600
    pre = window_flow(lo_t - 3 * 86400, lo_t + (hi_t - lo_t) // 4)
    into = window_flow(hi_t - (hi_t - lo_t) // 4, hi_t + 86400)
    rode = [(pre[w], -into[w], w) for w in pre if pre[w] > 0 and into.get(w, 0) < 0]
    rode.sort(key=lambda x: -min(x[0], x[1]))
    print(f"\n  bought in the base (3d before trough to first quarter of run) AND sold into "
          f"the top (last quarter to peak+1d): {len(rode)} traders")
    for bought, sold, w in rode[:10]:
        print(f"    {short(w)}  bought {bought/SUP:.3%}  sold {sold/SUP:.3%}  "
              f"realised {usd((book[w]['sell_e']-book[w]['buy_e'])*args.eth_usd)}  "
              f"{','.join(fl.get(w, []))}")
    # base rate: what share of base buyers sold into the top at all
    base_buyers = [w for w in pre if pre[w] > 0]
    print(f"  base rate: {len(rode)}/{len(base_buyers)} base buyers "
          f"({len(rode)/max(1,len(base_buyers)):.0%}) sold into the top")

    # before the crash: sellers in the 6 hours before the worst hour vs their norm
    c_t = worst[1] * 3600
    pre_crash = window_flow(c_t - 6 * 3600, c_t)
    sellers = sorted(((-v, w) for w, v in pre_crash.items() if v < 0), reverse=True)
    print(f"\n  sold in the 6 hours BEFORE the worst hour ({when(c_t)}):")
    for v, w in sellers[:10]:
        b = book[w]
        print(f"    {short(w)}  sold {v/SUP:.3%}  lifetime sold {b['sell_t']/SUP:.3%}  "
              f"holds now {bal.get(w,0)/WEI/SUP:.3%}  first {when(b['first'])}  "
              f"{','.join(fl.get(w, []))}")
    # liquidity removed around the crash
    c_block_lo = min(L["block"][i] for i in order if L["ts"][i] >= c_t - 6 * 3600)
    c_block_hi = max(L["block"][i] for i in order if L["ts"][i] <= c_t + 3600)
    near = [(b, k, a, v) for b, k, a, v in lp_events if c_block_lo <= b <= c_block_hi]
    print(f"  liquidity events from 6h before to 1h after: {len(near)}")
    for b, k, a, v in sorted(near, key=lambda x: -x[3])[:5]:
        print(f"    {k:>6} {short(a)}  {v/WEI/SUP:.2%}  block {b:,}")
    during = window_flow(c_t, c_t + 3600)
    dsell = sorted(((-v, w) for w, v in during.items() if v < 0), reverse=True)
    print(f"  sold DURING the worst hour:")
    for v, w in dsell[:8]:
        b = book[w]
        print(f"    {short(w)}  sold {v/SUP:.3%}  first {when(b['first'])}  "
              f"holds now {bal.get(w,0)/WEI/SUP:.3%}  {','.join(fl.get(w, []))}")

    # ============================================================= 9. COHORTS
    section("9. ENTRY COHORTS — when people first bought, and how that went (ETH terms)")
    cohort = defaultdict(lambda: {"n": 0, "in": 0.0, "out": 0.0, "open_t": 0.0, "hold": 0})
    for w, b in book.items():
        if not b["nb"]:
            continue
        wk = dt.datetime.utcfromtimestamp(b["first"]).strftime("%m-%d")
        key = (b["first"] - ts0) // (7 * 86400)
        c2 = cohort[key]
        c2["n"] += 1; c2["in"] += b["buy_e"]; c2["out"] += b["sell_e"]
        c2["open_t"] += max(0.0, b["buy_t"] - b["sell_t"])
        c2["hold"] += 1 if bal.get(w, 0) > 0 else 0
        c2["start"] = c2.get("start") or wk
    print(f"{'week':>5} {'from':>6} {'buyers':>7} {'put in':>9} {'took out':>9} "
          f"{'open@now':>9} {'result':>9} {'still hold':>10}")
    for k in sorted(cohort):
        c2 = cohort[k]
        res = (c2["out"] + c2["open_t"] * px_now_eth - c2["in"]) * args.eth_usd
        print(f"{k:>5} {c2.get('start',''):>6} {c2['n']:>7,} {usd(c2['in']*args.eth_usd):>9} "
              f"{usd(c2['out']*args.eth_usd):>9} {usd(c2['open_t']*px_now_eth*args.eth_usd):>9} "
              f"{usd(res):>9} {c2['hold']/c2['n']:>9.0%}")

    # ===================================================== 10. RECENT DIRECTION
    section("10. LAST 7 DAYS — who is moving the price now")
    t7 = ts1 - 7 * 86400
    cls_flow = defaultdict(float)
    for i in order:
        if L["ts"][i] < t7:
            continue
        w = L["trader"][i]
        k = "unattributed" if not w else ("bots" if w in bots else ("whales" if w in whales else "retail"))
        cls_flow[k] += L["usd"][i] * (1 if L["side"][i] == "buy" else -1)
    for k, v in sorted(cls_flow.items()):
        print(f"  {k:>13}: net {usd(v):>9} ({'buying' if v > 0 else 'selling'})")
    recent = window_flow(t7, ts1 + 1)
    print("\n  biggest net accumulators, 7d:")
    for w, v in sorted(recent.items(), key=lambda kv: -kv[1])[:6]:
        print(f"    {short(w)}  +{v/SUP:.3%}  holds {bal.get(w,0)/WEI/SUP:.3%}  "
              f"first {when(book[w]['first'])}  {','.join(fl.get(w, []))}")
    print("  biggest net sellers, 7d:")
    for w, v in sorted(recent.items(), key=lambda kv: kv[1])[:6]:
        print(f"    {short(w)}  {v/SUP:.3%}  holds {bal.get(w,0)/WEI/SUP:.3%}  "
              f"first {when(book[w]['first'])}  {','.join(fl.get(w, []))}")
    new7 = sum(1 for w, b in book.items() if b["first"] >= t7)
    print(f"\n  new traders in the last 7 days: {new7:,}")

    if args.out:
        args.out.write_text(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
