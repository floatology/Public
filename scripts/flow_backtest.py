#!/usr/bin/env python3
"""Does the pre-breakout pattern seen on WALLET predict breakouts elsewhere?

WALLET's 3-4 September breakout was preceded by: a volume dry-up (sellers
exhausted), an ignition day (volume and large buys spiking), higher lows while
tokens left the pool (absorption), and a pullback that held. One example proves
nothing -- `docs/18` records four earlier attempts to predict runners that
failed out of sample -- so this measures the same pattern across every per-trade
pool history already archived (data/parquet/trades*.parquet: 4,836 V2/V3 pools,
from each pool's creation to 21 Sep) and compares it to the base rate.

**Unit of observation: a token-day.** Features use only trades up to that day's
close; outcomes use only the days after it. Each token is represented by its
most-traded pool. Days with no trades carry the last close with zero volume, so
a token that dies simply stops producing runs instead of vanishing.

**Signals, each reported alone and in combination:**

    dry      3-day volume fell to <= 50% of its prior 3-week median at some
             point in the last 10 days
    ignite   within the last 7 days, a day with volume >= 2.5x its trailing
             2-week median and a positive close
    hlows    rising lows across three consecutive 4-day blocks
    coil     close within 15% below the 20-day high, not yet above it
    absorb   tokens net-removed from the pool over 10 days >= 1% of supply
    flow     net buy volume over 10 days > 0
    bigbuys  $2k+ buys in the last 10 days >= 5 and more than the 10 before

    SETUP    = dry & ignite & hlows & coil        (the WALLET shape, pre-break)
    SETUP+F  = SETUP & absorb & flow              (with the on-chain confirmation)
    BREAK    = close above the 20-day high on >= 2x median volume,
               with a dry-up in the prior 20 days (the breakout day itself)

**Outcomes over the next 14 days:** `run2x` (high reaches 2x), `crash`
(low reaches half), and `clean` (reaches 1.5x without first... approximated as
reaching 1.5x while never trading below 0.7x).

**Signal events are de-duplicated**: one per token per 14 days, so a pattern
that stays lit for a week is not counted seven times. Rates carry Wilson 95%
intervals, and every result is repeated on two halves split by time and on two
halves split by token, because either split alone has let leaks through here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WETH = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"
USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
ETHUSD_POOL = "0xc5a01c57b2851202dcf8507a0f2bd08a8025e2c8"   # USDG/WETH, USDG is base


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


def wilson(k: int, n: int) -> tuple[float, float, float]:
    if not n:
        return (0.0, 0.0, 0.0)
    p = k / n; z = 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0, c - h), min(1, c + h))


def load_bars(con) -> tuple[dict, dict, dict]:
    anchors = json.loads((ROOT / "data/tokens/block_times.json").read_text())["anchors"]
    con.execute("create table anchors(block bigint, ts bigint)")
    con.executemany("insert into anchors values (?,?)", anchors)
    con.execute(f"""
      create table t as
      select pool, token, quote_asset q, block, log_index, is_buy,
             cast(quote_amount as double) / (case when quote_asset='{USDG}' then 1e6 else 1e18 end) qa,
             cast(base_amount as double) ba
      from (select pool, token, quote_asset, block, log_index, is_buy, quote_amount, base_amount
              from read_parquet('{ROOT}/data/parquet/trades.parquet')
            union all
            select pool, token, quote_asset, block, log_index, is_buy, quote_amount, base_amount
              from read_parquet('{ROOT}/data/parquet/trades_v3.parquet'))
      where cast(base_amount as double) > 0 and cast(quote_amount as double) > 0""")
    con.execute("""
      create table tt as
      select t.*, cast(floor((a.ts + (t.block - a.block) / 10) / 86400) as bigint) as day
      from t asof join anchors a on t.block >= a.block""")
    # ETH/USD per day from the USDG/WETH pool: USDG priced in WETH, inverted.
    eth = dict(con.execute(f"""
      select day, median(ba / 1e6 / qa) from tt where pool = '{ETHUSD_POOL}' group by day
    """).fetchall())
    rows = con.execute("""
      select pool, token, q, day,
             arg_min(qa / ba * 1e18, block * 100000 + log_index) as o,
             max(qa / ba * 1e18) h, min(qa / ba * 1e18) l,
             arg_max(qa / ba * 1e18, block * 100000 + log_index) as c,
             sum(qa) vol, sum(case when is_buy then qa else -qa end) net,
             sum(case when is_buy then ba else -ba end) base_out,
             count(*) n, list(case when is_buy then qa else null end) buys
      from tt group by pool, token, q, day""").fetchall()
    bars = defaultdict(dict)
    meta = {}
    for pool, token, q, day, o, h, l, c, vol, net, bo, n, buys in rows:
        bars[pool][day] = {"o": o, "h": h, "l": l, "c": c, "vol": vol, "net": net,
                           "base_out": bo, "n": n, "buys": [b for b in buys if b is not None]}
        meta[pool] = (token, q)
    return bars, meta, eth


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--horizon", type=int, default=14)
    ap.add_argument("--out", type=Path, default=ROOT / "data/overnight/flow_backtest.json")
    args = ap.parse_args()
    H = args.horizon

    con = duckdb.connect()
    bars, meta, eth = load_bars(con)
    supply = {k.lower(): int(v) for k, v in
              json.loads((ROOT / "data/token_supply.json").read_text()).items() if v}
    eth_days = sorted(eth)
    def eth_on(d):
        if d in eth:
            return eth[d]
        prev = [x for x in eth_days if x <= d]
        return eth[prev[-1]] if prev else eth[eth_days[0]]

    # One pool per token: the most traded.
    best = {}
    for pool, (token, q) in meta.items():
        n = sum(b["n"] for b in bars[pool].values())
        if token not in best or n > best[token][1]:
            best[token] = (pool, n)
    last_day = max(max(b) for b in bars.values())
    print(f"{len(best):,} tokens; data to day {last_day} ; ETH/USD days {len(eth)}", file=sys.stderr)

    obs = []     # every eligible token-day with features and outcomes
    for token, (pool, _) in best.items():
        q = meta[pool][1]
        b = bars[pool]
        d0 = min(b)
        days = list(range(d0, last_day + 1))
        # carry forward
        seq = []
        prev_c = None
        for d in days:
            x = b.get(d)
            if x:
                prev_c = x["c"]; seq.append(dict(x, d=d))
            else:
                seq.append({"o": prev_c, "h": prev_c, "l": prev_c, "c": prev_c, "vol": 0.0,
                            "net": 0.0, "base_out": 0.0, "n": 0, "buys": [], "d": d})
        sup = supply.get(token)
        for i in range(24, len(seq) - H):
            t = seq[i]
            usd = eth_on(t["d"]) if q == WETH else 1.0
            vol = [s["vol"] for s in seq]
            med = lambda a, z: statistics.median(vol[max(a, 0):z]) if z > max(a, 0) else 0
            # dry: 3-day mean vs prior 3-week median, any point in last 10 days
            dry = any(med(k - 23, k - 2) > 0 and sum(vol[k - 2:k + 1]) / 3 <= 0.5 * med(k - 23, k - 2)
                      for k in range(i - 10, i - 1))
            ignite = any(med(k - 14, k) > 0 and vol[k] >= 2.5 * med(k - 14, k)
                         and seq[k]["c"] > seq[k]["o"] for k in range(i - 7, i + 1))
            lo = lambda a, z: min(s["l"] for s in seq[a:z])
            hlows = lo(i - 3, i + 1) > lo(i - 7, i - 3) > lo(i - 11, i - 7)
            hi20 = max(s["h"] for s in seq[i - 20:i])
            coil = 0.85 * hi20 <= t["c"] < hi20
            brk = (t["c"] > hi20 and med(i - 14, i) > 0 and vol[i] >= 2 * med(i - 14, i)
                   and any(med(k - 23, k - 2) > 0 and sum(vol[k - 2:k + 1]) / 3 <= 0.5 * med(k - 23, k - 2)
                           for k in range(i - 20, i - 1)))
            absorb = (sup and sum(s["base_out"] for s in seq[i - 10:i + 1]) / sup >= 0.01)
            flow = sum(s["net"] for s in seq[i - 10:i + 1]) > 0
            big = lambda a, z: sum(1 for s in seq[a:z] for x in s["buys"] if x * usd >= 2000)
            bigbuys = big(i - 10, i + 1) >= 5 and big(i - 10, i + 1) > big(i - 21, i - 10)
            c0 = t["c"]
            if not c0:
                continue
            fwd = seq[i + 1:i + 1 + H]
            fmax = max(s["h"] for s in fwd) / c0
            fmin = min(s["l"] for s in fwd) / c0
            # clean: reaches 1.5x before ever trading below 0.7x
            clean = False
            for s in fwd:
                if s["l"] / c0 < 0.7:
                    break
                if s["h"] / c0 >= 1.5:
                    clean = True; break
            mcap = (c0 / 1e18 * sup * usd) if sup else None
            vol7 = sum(vol[i - 6:i + 1]) * usd
            obs.append({"token": token, "d": t["d"], "age": t["d"] - d0, "mcap": mcap,
                        "vol7": vol7, "dry": dry, "ignite": ignite, "hlows": hlows,
                        "coil": coil, "brk": brk, "absorb": bool(absorb), "flow": flow,
                        "bigbuys": bigbuys, "run2x": fmax >= 2, "crash": fmin <= 0.5,
                        "clean": clean})
    print(f"{len(obs):,} token-days with {H}-day outcomes", file=sys.stderr)

    def report(name, sel, pool_):
        # de-duplicate signal events: one per token per H days
        ev, last = [], {}
        for o in sorted((o for o in pool_ if sel(o)), key=lambda o: (o["token"], o["d"])):
            if o["token"] in last and o["d"] - last[o["token"]] < H:
                continue
            last[o["token"]] = o["d"]; ev.append(o)
        out = {"events": len(ev), "tokens": len({o["token"] for o in ev}), "_ev": ev}
        for k in ("run2x", "crash", "clean"):
            out[k] = wilson(sum(o[k] for o in ev), len(ev))
        return out

    def table(title, universe):
        print(f"\n== {title}: {len(universe):,} token-days, "
              f"{len({o['token'] for o in universe}):,} tokens")
        base = {k: wilson(sum(o[k] for o in universe), len(universe)) for k in ("run2x", "crash", "clean")}
        print(f"   {'':34} {'events':>7} {'run2x':>17} {'crash':>17} {'clean':>17}")
        print(f"   {'BASE RATE (all days)':34} {len(universe):>7} "
              + " ".join(f"{base[k][0]:6.1%} [{base[k][1]:4.0%}-{base[k][2]:4.0%}]" for k in ("run2x", "crash", "clean")))
        res = {"base": base}
        sigs = {
            "dry": lambda o: o["dry"], "ignite": lambda o: o["ignite"],
            "hlows": lambda o: o["hlows"], "coil": lambda o: o["coil"],
            "absorb": lambda o: o["absorb"], "flow": lambda o: o["flow"],
            "bigbuys": lambda o: o["bigbuys"],
            "SETUP": lambda o: o["dry"] and o["ignite"] and o["hlows"] and o["coil"],
            "SETUP+F": lambda o: o["dry"] and o["ignite"] and o["hlows"] and o["coil"] and o["absorb"] and o["flow"],
            "ignite+hlows+absorb": lambda o: o["ignite"] and o["hlows"] and o["absorb"],
            "BREAK": lambda o: o["brk"],
            "BREAK+F": lambda o: o["brk"] and o["absorb"] and o["flow"],
        }
        for name, sel in sigs.items():
            r = report(name, sel, universe); res[name] = r
            ev = r.pop("_ev")
            if r["events"]:
                lift = {k: matched_lift(ev, universe, k) for k in ("run2x", "crash", "clean")}
                r["lift_vs_activity"] = lift
                print(f"   {name:34} {r['events']:>7} "
                      + " ".join(f"{r[k][0]:6.1%} [{r[k][1]:4.0%}-{r[k][2]:4.0%}]" for k in ("run2x", "crash", "clean"))
                      + "   lift vs same-activity: " + " ".join(f"{k} {lift[k][2]:.2f}x" for k in ("run2x", "crash", "clean")))
        return res

    results = {}
    results["all"] = table("ALL", obs)
    # robustness splits
    days_sorted = sorted({o["d"] for o in obs}); mid = days_sorted[len(days_sorted) // 2]
    results["early"] = table("TIME SPLIT — first half", [o for o in obs if o["d"] < mid])
    results["late"] = table("TIME SPLIT — second half", [o for o in obs if o["d"] >= mid])
    h = lambda t: int(hashlib.md5(t.encode()).hexdigest(), 16) % 2
    results["tokA"] = table("TOKEN SPLIT — half A", [o for o in obs if h(o["token"]) == 0])
    results["tokB"] = table("TOKEN SPLIT — half B", [o for o in obs if h(o["token"]) == 1])

    # criteria study: base rates by age, market cap, weekly volume
    def bucket_study(title, key, edges, labels):
        print(f"\n== BASE RATES BY {title}")
        print(f"   {'bucket':>14} {'token-days':>10} {'tokens':>7} {'run2x':>8} {'crash':>8} {'clean':>8}")
        res = {}
        for lab, (a, z) in zip(labels, zip(edges, edges[1:])):
            u = [o for o in obs if o[key] is not None and a <= o[key] < z]
            if not u:
                continue
            r = {k: sum(o[k] for o in u) / len(u) for k in ("run2x", "crash", "clean")}
            res[lab] = dict(r, n=len(u), tokens=len({o['token'] for o in u}))
            print(f"   {lab:>14} {len(u):>10,} {res[lab]['tokens']:>7,} {r['run2x']:>8.1%} "
                  f"{r['crash']:>8.1%} {r['clean']:>8.1%}")
        return res
    inf = float("inf")
    results["by_age"] = bucket_study("AGE (days since first trade)", "age",
                                     [0, 3, 7, 14, 30, 60, inf], ["0-2d", "3-6d", "7-13d", "14-29d", "30-59d", "60d+"])
    results["by_mcap"] = bucket_study("MARKET CAP (USD)", "mcap",
                                      [0, 25e3, 1e5, 3e5, 1e6, 5e6, inf],
                                      ["<25k", "25-100k", "100-300k", "300k-1M", "1-5M", "5M+"])
    results["by_vol7"] = bucket_study("7-DAY VOLUME (USD)", "vol7",
                                      [0, 1e3, 1e4, 5e4, 2.5e5, 1e6, inf],
                                      ["<1k", "1-10k", "10-50k", "50-250k", "250k-1M", "1M+"])
    # the pattern inside the most promising filter
    results["active"] = table("ACTIVE ONLY (7d volume >= $1k)", [o for o in obs if o["vol7"] >= 1e3])
    filt = [o for o in obs if o["age"] >= 7 and o["mcap"] and 1e5 <= o["mcap"] < 5e6 and o["vol7"] >= 1e4]
    results["filtered"] = table("FILTERED: age>=7d, mcap $100k-5M, 7d vol>=$10k", filt)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1, default=str))
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
