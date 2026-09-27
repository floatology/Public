#!/usr/bin/env python3
"""Do big wallets accumulate before breakouts? Tested on every archived token.

The flow backtest can see buy and sell volume but not who is behind it, because
the old per-trade archive is keyed on swap recipients, which are routers
(`docs/22`). The per-token archives built by `track_tokens.py` attribute every
trade to the address whose balance actually moved, and replay every transfer
into balances, so here the question can be asked directly.

Per token-day, using only data up to that day's close:

    whale_accum   net tokens bought over 10 days by wallets that end the day
                  holding >= 0.5% of supply, as a share of supply
    n_accum       distinct wallets that net-bought >= 0.05% of supply in 10 days
    holders_g     growth in holder count (balance > 0, pools and routers
                  excluded) over 7 days
    top20_d       change in the top-20 holders' share over 10 days
    fresh_share   share of 10-day buy volume from wallets first seen in that window

Outcomes and reporting match the other two backtests: `run2x`, `crash`, `clean`
over 14 days, events de-duplicated one per token per 14 days, and each signal
compared to the base rate of token-days with the same weekly volume.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from rhc.rpc import V4_POOL_MANAGER
from block_times import BlockClock

H = 14   # overridden by --horizon; 7 lets coins younger than four weeks count
ZERO = "0x0000000000000000000000000000000000000000"
DEAD = "0x000000000000000000000000000000000000dead"
VOL_EDGES = [0, 1e3, 1e4, 5e4, 2.5e5, 1e6, float("inf")]


def vb(v):
    for k, (a, z) in enumerate(zip(VOL_EDGES, VOL_EDGES[1:])):
        if a <= v < z:
            return k
    return len(VOL_EDGES) - 2


def wilson(k, n):
    if not n:
        return (0.0, 0.0, 0.0)
    p = k / n; z = 1.96; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0, c - h), min(1, c + h))


def load(p):
    t = pq.read_table(p)
    return {n: t.column(n).to_pylist() for n in t.column_names}


def token_days(token: str, entry: dict, clock: BlockClock) -> list[dict]:
    d = ROOT / "data/tokens" / token
    if not (d / "ledger.parquet").exists():
        return []
    L = load(d / "ledger.parquet"); T = load(d / "transfers.parquet")
    dec = 10 ** entry.get("decimals", 18)
    market = {V4_POOL_MANAGER if v["kind"] == "v4" else k for k, v in entry["pools"].items()}
    # routers: move a lot, keep nothing, or touch hundreds of counterparties
    inflow = defaultdict(int); outflow = defaultdict(int); dests = defaultdict(set)
    for i in range(len(T["block"])):
        v = int(T["value"][i])
        if v:
            outflow[T["src"][i]] += v; inflow[T["dst"][i]] += v; dests[T["src"][i]].add(T["dst"][i])
    supply = sum(int(T["value"][i]) for i in range(len(T["block"])) if T["src"][i] == ZERO) or 1
    routers = {a for a in inflow if min(inflow[a], outflow[a]) / supply > 0.02 and
               (abs(inflow[a] - outflow[a]) / supply < 0.001 or len(dests[a]) >= 500)}
    skip = market | routers | {DEAD, ZERO}

    day_of = lambda b: int(clock.at(b)) // 86400
    # daily holder snapshots from the transfer replay
    order = sorted(range(len(T["block"])), key=lambda i: (T["block"][i], T["log_index"][i]))
    bal = defaultdict(int); holders = 0; snap = {}; top20 = {}
    cur = None
    for i in order:
        dd = day_of(T["block"][i])
        if cur is not None and dd != cur:
            snap[cur] = holders
            top = sorted((v for a, v in bal.items() if a not in skip and v > 0), reverse=True)[:20]
            top20[cur] = sum(top) / supply
        cur = dd
        v = int(T["value"][i])
        for a, s in ((T["src"][i], -1), (T["dst"][i], 1)):
            if a in skip or not v:
                continue
            before = bal[a] > 0
            bal[a] += s * v
            after = bal[a] > 0
            holders += (after and not before) - (before and not after)
    if cur is not None:
        snap[cur] = holders
        top = sorted((v for a, v in bal.items() if a not in skip and v > 0), reverse=True)[:20]
        top20[cur] = sum(top) / supply

    # daily bars and wallet flows from the ledger
    lo = sorted(range(len(L["ts"])), key=lambda i: (L["block"][i], L["log_index"][i]))
    bars = {}; flows = defaultdict(lambda: defaultdict(float)); first = {}
    held = defaultdict(float)
    whale_end = defaultdict(set)
    for i in lo:
        dd = int(L["ts"][i]) // 86400; px = L["price_usd"][i]
        if px:
            b = bars.setdefault(dd, {"o": px, "h": px, "l": px, "c": px, "vol": 0.0, "buyvol": 0.0,
                                      "freshvol": 0.0})
            b["h"] = max(b["h"], px); b["l"] = min(b["l"], px); b["c"] = px
            b["vol"] += L["usd"][i]
        w = L["trader"][i]
        if not w or w in skip:
            continue
        s = 1 if L["side"][i] == "buy" else -1
        tok = L["tokens"][i] * dec          # back to raw units, comparable with supply
        flows[dd][w] += s * tok
        held[w] += s * tok
        if w not in first:
            first[w] = dd
        if s > 0 and dd in bars:
            bars[dd]["buyvol"] += L["usd"][i]
            if first[w] >= dd - 10:
                bars[dd]["freshvol"] += L["usd"][i]
        if held[w] >= 0.005 * supply:
            whale_end[dd].add(w)
    if not bars:
        return []
    days = list(range(min(bars), max(bars) + 1))
    seq, prev = [], None
    for dd in days:
        b = bars.get(dd)
        if b:
            prev = b["c"]; seq.append(dict(b, d=dd))
        else:
            seq.append({"o": prev, "h": prev, "l": prev, "c": prev, "vol": 0.0, "buyvol": 0.0,
                        "freshvol": 0.0, "d": dd})
    out = []
    running_whales = set()
    for i, s in enumerate(seq):
        running_whales |= whale_end.get(s["d"], set())
        if i < 10 or i + H >= len(seq):
            continue
        win = range(s["d"] - 9, s["d"] + 1)
        net10 = defaultdict(float)
        for dd in win:
            for w, v in flows.get(dd, {}).items():
                net10[w] += v
        whale_accum = sum(v for w, v in net10.items() if w in running_whales and v > 0) / supply
        n_accum = sum(1 for v in net10.values() if v >= 0.0005 * supply)
        h_now = max((snap[x] for x in snap if x <= s["d"]), default=0)
        h_7 = max((snap[x] for x in snap if x <= s["d"] - 7), default=0)
        t_now = next((top20[x] for x in sorted(top20, reverse=True) if x <= s["d"]), None)
        t_10 = next((top20[x] for x in sorted(top20, reverse=True) if x <= s["d"] - 10), None)
        bv = sum(seq[j]["buyvol"] for j in range(max(0, i - 9), i + 1))
        fv = sum(seq[j]["freshvol"] for j in range(max(0, i - 9), i + 1))
        c0 = s["c"]
        fwd = seq[i + 1:i + 1 + H]
        if not c0:
            continue
        clean = False
        for f in fwd:
            if f["l"] / c0 < 0.7:
                break
            if f["h"] / c0 >= 1.5:
                clean = True; break
        out.append({"token": token, "d": s["d"],
                    "vol7": sum(seq[j]["vol"] for j in range(i - 6, i + 1)),
                    "whale_accum": whale_accum, "n_accum": n_accum,
                    "holders_g": (h_now - h_7) / h_7 if h_7 else 0.0,
                    "top20_d": (t_now - t_10) if (t_now is not None and t_10 is not None) else 0.0,
                    "fresh_share": fv / bv if bv else 0.0,
                    "run2x": max(f["h"] for f in fwd) / c0 >= 2,
                    "crash": min(f["l"] for f in fwd) / c0 <= 0.5, "clean": clean})
    return out


def main() -> int:
    import argparse
    global H
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--horizon", type=int, default=14)
    H = ap.parse_args().horizon
    reg = json.loads((ROOT / "data/tokens/tokens.json").read_text())
    clock = BlockClock(json.loads((ROOT / "data/tokens/block_times.json").read_text())["anchors"])
    obs = []
    for token, e in reg.items():
        rows = token_days(token, e, clock)
        print(f"  {e['symbol']:12} {len(rows):>4} token-days", file=sys.stderr, flush=True)
        obs.extend(rows)
    obs = [o for o in obs if o["vol7"] >= 1e3]
    print(f"\n{len(obs):,} active token-days across {len({o['token'] for o in obs})} tokens "
          f"(weekly volume >= $1k)")
    rate = {}
    for k in ("run2x", "crash", "clean"):
        for b in range(len(VOL_EDGES) - 1):
            u = [o for o in obs if vb(o["vol7"]) == b]
            rate[(k, b)] = sum(o[k] for o in u) / len(u) if u else 0.0
    base = {k: wilson(sum(o[k] for o in obs), len(obs)) for k in ("run2x", "crash", "clean")}
    print(f"   {'BASE':34} {len(obs):>6}  " + "  ".join(f"{k} {base[k][0]:6.1%}" for k in base))

    def show(name, sel):
        ev, last = [], {}
        for o in sorted((o for o in obs if sel(o)), key=lambda o: (o["token"], o["d"])):
            if o["token"] in last and o["d"] - last[o["token"]] < H:
                continue
            last[o["token"]] = o["d"]; ev.append(o)
        if not ev:
            print(f"   {name:34} {0:>6}"); return {"events": 0}
        r = {"events": len(ev), "tokens": len({o['token'] for o in ev})}
        line = f"   {name:34} {len(ev):>6}  "
        for k in ("run2x", "crash", "clean"):
            ob = sum(o[k] for o in ev) / len(ev)
            ex = sum(rate[(k, vb(o['vol7']))] for o in ev) / len(ev)
            r[k] = {"obs": ob, "ci": wilson(sum(o[k] for o in ev), len(ev)), "lift": ob / ex if ex else None}
            line += f"{k} {ob:6.1%} ({(ob/ex if ex else float('nan')):.2f}x)  "
        print(line + f" [{r['tokens']} tokens]")
        return r

    res = {"base": base, "n": len(obs)}
    res["whale_accum>=0.5%"] = show("whales net-bought >= 0.5% (10d)", lambda o: o["whale_accum"] >= 0.005)
    res["whale_accum>=1%"] = show("whales net-bought >= 1% (10d)", lambda o: o["whale_accum"] >= 0.01)
    res["n_accum>=5"] = show(">= 5 wallets each took 0.05%+", lambda o: o["n_accum"] >= 5)
    res["n_accum>=15"] = show(">= 15 wallets each took 0.05%+", lambda o: o["n_accum"] >= 15)
    res["holders+10%"] = show("holders +10% in 7d", lambda o: o["holders_g"] >= 0.10)
    res["holders+25%"] = show("holders +25% in 7d", lambda o: o["holders_g"] >= 0.25)
    res["top20 up 2pts"] = show("top-20 share +2 pts (10d)", lambda o: o["top20_d"] >= 0.02)
    res["top20 down 2pts"] = show("top-20 share -2 pts (10d)", lambda o: o["top20_d"] <= -0.02)
    res["fresh>=50%"] = show("new wallets >= 50% of buying", lambda o: o["fresh_share"] >= 0.5)
    res["fresh<=15%"] = show("new wallets <= 15% of buying", lambda o: o["fresh_share"] <= 0.15)
    res["whales+quiet"] = show("whale accum 0.5%+ & fresh <= 30%",
                               lambda o: o["whale_accum"] >= 0.005 and o["fresh_share"] <= 0.3)
    (ROOT / f"data/overnight/wallet_signals_h{H}.json").write_text(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
