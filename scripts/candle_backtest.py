#!/usr/bin/env python3
"""The pre-breakout pattern tested on every GeckoTerminal-tracked token, V4 included.

Complements `flow_backtest.py`, which has on-chain flow but only V2/V3 pools up
to 21 Sep. This has only price and volume, but covers the whole tracked market
up to today, including coins that have since been delisted (the universe unions
today's listing with the September census).

Tokens are grouped from pool candles by base token. A token's price comes from
its highest-volume pool; its volume is the sum across its pools. Supply is
fdv / price from the listing where available, otherwise the cached
`token_supply.json` at 18 decimals, and market cap is price x supply, which
assumes supply is constant (`docs/17`). Pools whose base is WETH, ETH or USDG
are the quote side, not a token, and are skipped.

Same outputs as the flow backtest: base rates, each signal alone and combined,
time and token splits, and base rates by age, market cap and weekly volume.
It also writes the live screen: every token whose latest complete day shows
SETUP or BREAK, and every token listed in the last 7 days.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rhc.breakout import MIN_HISTORY, outcomes, signals

QUOTES = {"0x0bd7d308f8e1639fab988df18a8011f41eacad73", "0x5fc5360d0400a0fd4f2af552add042d716f1d168",
          "0x0000000000000000000000000000000000000000", "eth", ""}


VOL_EDGES = [0, 1e3, 1e4, 5e4, 2.5e5, 1e6, float("inf")]


def vol_bucket(v: float) -> int:
    for k, (a, z) in enumerate(zip(VOL_EDGES, VOL_EDGES[1:])):
        if a <= v < z:
            return k
    return len(VOL_EDGES) - 2


def matched_lift(ev: list[dict], universe: list[dict], key: str) -> tuple[float, float, float]:
    """Observed rate vs the rate expected from activity alone.

    A signal that only fires on active coins will beat an all-days base rate
    by an order of magnitude while predicting nothing: on the flow archive,
    token-days with under $1k of weekly volume are 99% of the sample and almost
    never move. So each event is matched to the base rate of its own 7-day
    volume bucket, and the lift is observed / expected. A lift near 1 means the
    signal is only detecting that the coin is alive.
    """
    rate = {}
    for b in range(len(VOL_EDGES) - 1):
        u = [o for o in universe if vol_bucket(o["vol7"]) == b]
        rate[b] = sum(o[key] for o in u) / len(u) if u else 0.0
    if not ev:
        return (0.0, 0.0, 0.0)
    obs = sum(o[key] for o in ev) / len(ev)
    exp = sum(rate[vol_bucket(o["vol7"])] for o in ev) / len(ev)
    return (obs, exp, obs / exp if exp else float("nan"))


def wilson(k, n):
    if not n:
        return (0.0, 0.0, 0.0)
    p = k / n; z = 1.96; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0, c - h), min(1, c + h))


def build_series():
    uni = json.loads((ROOT / "data/chain/universe.json").read_text())
    supply_raw = {k.lower(): int(v) for k, v in
                  json.loads((ROOT / "data/token_supply.json").read_text()).items() if v}
    per_token = defaultdict(list)
    sym = {}
    for line in (ROOT / "data/chain/candles.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("error") or not r.get("candles"):
            continue
        base = r.get("base") or (uni.get(r["pool"], {}).get("base") or "")
        if base in QUOTES:
            continue
        per_token[base].append(r)
        sym[base] = r.get("base_symbol")
    series = {}
    today = int(time.time()) // 86400
    for tok, pools in per_token.items():
        vol_by_pool = {p["pool"]: sum(c[5] for c in p["candles"]) for p in pools}
        main = max(pools, key=lambda p: vol_by_pool[p["pool"]])
        days = defaultdict(float)
        for p in pools:
            for c in p["candles"]:
                days[int(c[0]) // 86400] += c[5]
        px = {int(c[0]) // 86400: c for c in main["candles"]}
        # supply: fdv / price from any listed pool of this token, else cache
        sup = None
        for p in pools:
            u = uni.get(p["pool"], {})
            try:
                f, pr = float(u.get("fdv_usd") or 0), float(u.get("price_usd") or 0)
            except ValueError:
                f = pr = 0
            if f > 0 and pr > 0:
                sup = f / pr; break
        if sup is None and tok in supply_raw:
            sup = supply_raw[tok] / 1e18
        d0 = min(px)
        seq, prev = [], None
        for d in range(d0, today + 1):
            c = px.get(d)
            if c:
                o, h, l, cl = c[1], c[2], c[3], c[4]; prev = cl
            else:
                o = h = l = cl = prev
            seq.append({"d": d, "o": o, "h": h, "l": l, "c": cl, "vol": days.get(d, 0.0)})
        created = min((uni.get(p["pool"], {}).get("created") or "9") for p in pools)
        series[tok] = {"symbol": sym.get(tok), "seq": seq, "supply": sup, "pools": len(pools),
                       "main_pool": main["pool"], "created": created}
    return series


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--horizon", type=int, default=14)
    args = ap.parse_args()
    H = args.horizon
    series = build_series()
    print(f"{len(series):,} tokens with candles", file=sys.stderr)

    obs = []
    for tok, s in series.items():
        seq = s["seq"]
        for i in range(MIN_HISTORY, len(seq) - H - 1):   # -1: today is partial
            out = outcomes(seq, i, H)
            if not out:
                continue
            sg = signals(seq, i)
            c = seq[i]["c"]
            mcap = c * s["supply"] if s["supply"] else None
            vol7 = sum(x["vol"] for x in seq[i - 6:i + 1])
            obs.append({"token": tok, "d": seq[i]["d"], "age": i, "mcap": mcap, "vol7": vol7, **sg, **out})
    print(f"{len(obs):,} token-days with {H}-day outcomes", file=sys.stderr)

    def events(sel, u):
        ev, last = [], {}
        for o in sorted((o for o in u if sel(o)), key=lambda o: (o["token"], o["d"])):
            if o["token"] in last and o["d"] - last[o["token"]] < H:
                continue
            last[o["token"]] = o["d"]; ev.append(o)
        return ev

    def table(title, u):
        print(f"\n== {title}: {len(u):,} token-days, {len({o['token'] for o in u}):,} tokens")
        print(f"   {'':22} {'events':>7} {'run2x':>18} {'crash':>18} {'clean':>18} {'held':>18}")
        base = {k: wilson(sum(o[k] for o in u), len(u)) for k in ("run2x", "crash", "clean", "held")}
        print(f"   {'BASE (all days)':22} {len(u):>7} " + " ".join(
            f"{base[k][0]:6.1%} [{base[k][1]:4.0%}-{base[k][2]:4.0%}]" for k in ("run2x", "crash", "clean", "held")))
        res = {"base": base}
        for name in ("dry", "ignite", "hlows", "coil", "SETUP", "BREAK"):
            ev = events(lambda o: o[name], u)
            if not ev:
                continue
            r = {k: wilson(sum(o[k] for o in ev), len(ev)) for k in ("run2x", "crash", "clean", "held")}
            lift = {k: matched_lift(ev, u, k) for k in ("run2x", "crash", "clean", "held")}
            r["events"] = len(ev); r["lift_vs_activity"] = lift; res[name] = r
            print(f"   {name:22} {len(ev):>7} " + " ".join(
                f"{r[k][0]:6.1%} [{r[k][1]:4.0%}-{r[k][2]:4.0%}]" for k in ("run2x", "crash", "clean", "held"))
                + "   lift vs same-activity: " + " ".join(f"{k} {lift[k][2]:.2f}x" for k in ("run2x", "crash", "clean", "held")))
        return res

    results = {"all": table("ALL", obs)}
    ds = sorted({o["d"] for o in obs}); mid = ds[len(ds) // 2]
    results["early"] = table("TIME SPLIT first half", [o for o in obs if o["d"] < mid])
    results["late"] = table("TIME SPLIT second half", [o for o in obs if o["d"] >= mid])
    hh = lambda t: int(hashlib.md5(t.encode()).hexdigest(), 16) % 2
    results["tokA"] = table("TOKEN SPLIT A", [o for o in obs if hh(o["token"]) == 0])
    results["tokB"] = table("TOKEN SPLIT B", [o for o in obs if hh(o["token"]) == 1])

    def buckets(title, key, edges, labels):
        print(f"\n== BASE RATES BY {title}")
        res = {}
        for lab, (a, z) in zip(labels, zip(edges, edges[1:])):
            u = [o for o in obs if o[key] is not None and a <= o[key] < z]
            if not u:
                continue
            r = {k: sum(o[k] for o in u) / len(u) for k in ("run2x", "crash", "clean", "held")}
            res[lab] = dict(r, n=len(u), tokens=len({o["token"] for o in u}))
            print(f"   {lab:>10} {len(u):>8,} days {res[lab]['tokens']:>6,} tokens  run2x {r['run2x']:6.1%}  "
                  f"crash {r['crash']:6.1%}  clean {r['clean']:6.1%}  held {r['held']:6.1%}")
        return res
    inf = float("inf")
    results["by_age"] = buckets("AGE (days of trading history)", "age",
                                [0, 21, 30, 45, 60, inf], ["14-20d", "21-29d", "30-44d", "45-59d", "60d+"])
    results["by_mcap"] = buckets("MARKET CAP", "mcap", [0, 25e3, 1e5, 3e5, 1e6, 5e6, inf],
                                 ["<25k", "25-100k", "100-300k", "300k-1M", "1-5M", "5M+"])
    results["by_vol7"] = buckets("7-DAY VOLUME", "vol7", [0, 1e3, 1e4, 5e4, 2.5e5, 1e6, inf],
                                 ["<1k", "1-10k", "10-50k", "50-250k", "250k-1M", "1M+"])
    results["active"] = table("ACTIVE ONLY (7d volume >= $1k)", [o for o in obs if o["vol7"] >= 1e3])
    results["active10k"] = table("ACTIVE ONLY (7d volume >= $10k)", [o for o in obs if o["vol7"] >= 1e4])
    filt = [o for o in obs if o["mcap"] and 1e5 <= o["mcap"] < 5e6 and o["vol7"] >= 1e4]
    results["filtered"] = table("FILTERED mcap $100k-5M, 7d vol >= $10k", filt)
    (ROOT / "data/overnight/candle_backtest.json").write_text(json.dumps(results, indent=1, default=str))

    # ---------------- live screen: latest complete day ----------------
    live = []
    for tok, s in series.items():
        seq = s["seq"]
        i = len(seq) - 2               # yesterday: the last complete day
        if i < MIN_HISTORY:
            continue
        sg = signals(seq, i)
        if not (sg["SETUP"] or sg["BREAK"] or sg["ignite"] and sg["hlows"]):
            continue
        c = seq[i]["c"]
        mcap = c * s["supply"] if s["supply"] else None
        live.append({"token": tok, "symbol": s["symbol"], "mcap": mcap, "age_days": i,
                     "vol7": sum(x["vol"] for x in seq[i - 6:i + 1]), "close": c,
                     "signals": [k for k, v in sg.items() if v], "pools": s["pools"]})
    live.sort(key=lambda x: (not ("SETUP" in x["signals"] or "BREAK" in x["signals"]), -(x["vol7"] or 0)))
    new = [{"token": t, "symbol": s["symbol"], "days": len(s["seq"]), "created": s["created"],
            "vol7": sum(x["vol"] for x in s["seq"][-7:]),
            "mcap": (s["seq"][-1]["c"] * s["supply"]) if s["supply"] and s["seq"][-1]["c"] else None}
           for t, s in series.items() if len(s["seq"]) <= 7]
    new.sort(key=lambda x: -(x["vol7"] or 0))
    (ROOT / "data/overnight/live_screen.json").write_text(json.dumps({"live": live, "new": new}, indent=1))
    print(f"\n== LIVE SCREEN (last complete day): {len(live)} tokens flagged")
    for x in live[:40]:
        print(f"   {str(x['symbol'])[:12]:12} {x['token']}  mcap ${(x['mcap'] or 0):>12,.0f}  "
              f"7d vol ${x['vol7']:>11,.0f}  age {x['age_days']:>3}d  {','.join(x['signals'])}")
    print(f"\n== NEW LISTINGS (<=7 days of candles): {len(new)}")
    for x in new[:25]:
        print(f"   {str(x['symbol'])[:12]:12} {x['token']}  {x['days']}d  mcap ${(x['mcap'] or 0):>12,.0f}  "
              f"7d vol ${x['vol7']:>11,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
