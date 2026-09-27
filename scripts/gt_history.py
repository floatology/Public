#!/usr/bin/env python3
"""Daily price and volume history for every pool GeckoTerminal tracks here.

The chain-wide alternative does not fit: Robinhood Chain carries over 400,000
V3 swaps and as many V4 swaps a day, mostly arbitrage on a handful of pools,
across 715,000 created pools. A raw archive of that is tens of millions of logs.
GeckoTerminal already aggregates it into daily candles, one call per pool, V4
included, and each candle response names the pool's base and quote tokens.

Two steps, both resumable:

    gt_history.py universe   # list pools on every DEX, plus new and trending
    gt_history.py candles    # daily OHLCV for each, appended to candles.jsonl

**The universe is the union of today's listing and the September census.**
Pools that were listed then and have since dropped off are exactly the dead
coins a survivor-only sample misses; `docs/17` measured that bias at 2.3x on
the rate of reaching $2M. Their candles are fetched too, where GeckoTerminal
still serves them.

**Checkpointing is per pool.** `candles.jsonl` gains one line per pool as it
completes; a rerun skips every pool already present, so an interruption costs
at most one call.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rhc.premium import GeckoTerminal, PremiumError

OUT = ROOT / "data/chain"


def cmd_universe(args) -> int:
    gt = GeckoTerminal()
    pools: dict[str, dict] = {}

    def take(items, source):
        for it in items or []:
            a = it.get("attributes") or {}
            addr = (a.get("address") or "").lower()
            if not addr:
                continue
            rel = it.get("relationships") or {}
            rid = lambda k: ((rel.get(k) or {}).get("data") or {}).get("id", "")
            pools.setdefault(addr, {
                "name": a.get("name"), "created": a.get("pool_created_at"),
                "reserve_usd": a.get("reserve_in_usd"), "fdv_usd": a.get("fdv_usd"),
                "mcap_usd": a.get("market_cap_usd"), "price_usd": a.get("base_token_price_usd"),
                "vol24": (a.get("volume_usd") or {}).get("h24"),
                "base": rid("base_token").split("_")[-1].lower(),
                "quote": rid("quote_token").split("_")[-1].lower(),
                "dex": rid("dex"), "source": source})

    dexes = [d["id"] for d in (gt.get("/networks/robinhood/dexes").get("data") or [])]
    print(f"{len(dexes)} DEXes: {', '.join(dexes)}", flush=True)
    sources = (["/networks/robinhood/pools", "/networks/robinhood/new_pools",
                "/networks/robinhood/trending_pools"]
               + [f"/networks/robinhood/dexes/{d}/pools" for d in dexes])
    for src in sources:
        for page in range(1, args.pages + 1):
            try:
                items = (gt.get(src, page=page).get("data") or [])
            except PremiumError:
                break
            if not items:
                break
            take(items, src.split("/")[-1] if "dexes" not in src else src.split("/")[-2])
        print(f"  {src:<55} total {len(pools):,}", flush=True)

    old = ROOT / "data/gt_pools.json"
    added = 0
    if old.exists():
        for addr, a in json.loads(old.read_text()).items():
            if addr.lower() not in pools:
                pools[addr.lower()] = {"name": a.get("name"), "created": a.get("pool_created_at"),
                                       "reserve_usd": a.get("reserve_in_usd"),
                                       "fdv_usd": a.get("fdv_usd"), "base": "", "quote": "",
                                       "dex": "", "source": "sept-census (no longer listed)"}
                added += 1
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "universe.json").write_text(json.dumps(pools))
    print(f"universe: {len(pools):,} pools ({added:,} only in the September census)")
    return 0


def cmd_candles(args) -> int:
    gt = GeckoTerminal()
    uni = json.loads((OUT / "universe.json").read_text())
    path = OUT / "candles.jsonl"
    done = set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                done.add(json.loads(line)["pool"])
            except Exception:
                pass
    todo = [p for p in uni if p not in done]
    print(f"{len(done):,} pools done, {len(todo):,} to fetch", flush=True)
    t0 = time.time()
    with path.open("a") as f:
        for k, pool in enumerate(todo, 1):
            rec = {"pool": pool}
            try:
                r = gt.get(f"/networks/robinhood/pools/{pool}/ohlcv/day",
                           aggregate="1", limit=1000, currency="usd")
                a = (r.get("data") or {}).get("attributes") or {}
                meta = r.get("meta") or {}
                rec["candles"] = a.get("ohlcv_list") or []
                rec["base"] = ((meta.get("base") or {}).get("address") or "").lower()
                rec["base_symbol"] = (meta.get("base") or {}).get("symbol")
                rec["quote"] = ((meta.get("quote") or {}).get("address") or "").lower()
                rec["quote_symbol"] = (meta.get("quote") or {}).get("symbol")
            except PremiumError as e:
                rec["error"] = str(e)[:200]
            f.write(json.dumps(rec) + "\n")
            f.flush()
            if k % 100 == 0:
                rate = k / (time.time() - t0)
                print(f"  {k:,}/{len(todo):,}  {rate*60:.0f}/min  eta {(len(todo)-k)/rate/60:.0f} min",
                      flush=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("universe"); u.add_argument("--pages", type=int, default=10)
    sub.add_parser("candles")
    a = p.parse_args()
    return cmd_universe(a) if a.cmd == "universe" else cmd_candles(a)


if __name__ == "__main__":
    raise SystemExit(main())
