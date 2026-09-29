#!/usr/bin/env python3
"""Hourly OHLCV for the main pool of every token that was ever active.

The unbiased hourly test set: the ledger archive covers 65 hand-picked coins;
this covers every token in the daily-candle universe with at least 3 days of
>= $1k volume, via its highest-volume pool. GeckoTerminal serves up to 1,000
hourly candles per call, so tokens older than ~41 days need a second page
(before_timestamp). Resumable: one line per pool in data/chain/hourly.jsonl;
a rerun skips pools already done. Order: most active tokens first.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from candle_backtest import build_series  # noqa: E402
from rhc.premium import GeckoTerminal, PremiumError  # noqa: E402

OUT = ROOT / "data/chain/hourly.jsonl"


def main() -> int:
    series = build_series()
    todo = []
    for tok, s in series.items():
        live = sum(1 for x in s["seq"] if x["vol"] >= 1000)
        if live >= 3:
            first = s["seq"][0]["d"] * 86400
            todo.append((live, tok, s["main_pool"], first, s.get("symbol")))
    # Random order (fixed seed): if the fetch is cut short, what has been fetched
    # is still a fair sample, not the longest-lived survivors first.
    import random
    random.Random(7).shuffle(todo)
    done = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            try:
                done.add(json.loads(line)["pool"])
            except Exception:
                pass
    todo = [t for t in todo if t[2] not in done]
    print(f"{len(done)} done, {len(todo)} to fetch", flush=True)
    gt = GeckoTerminal()
    t0 = time.time()
    with OUT.open("a") as fh:
        for k, (live, tok, pool, first, sym) in enumerate(todo, 1):
            rec = {"pool": pool, "token": tok, "symbol": sym, "candles": []}
            before = None
            try:
                for _ in range(4):   # up to ~166 days
                    params = {"aggregate": "1", "limit": 1000, "currency": "usd"}
                    if before:
                        params["before_timestamp"] = before
                    r = gt.get(f"/networks/robinhood/pools/{pool}/ohlcv/hour", **params)
                    lst = ((r.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
                    rec["candles"] += lst
                    if len(lst) < 1000:
                        break
                    before = min(c[0] for c in lst)
                    if before <= first:
                        break
            except PremiumError as e:
                rec["error"] = str(e)[:200]
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if k % 25 == 0:
                rate = k / (time.time() - t0)
                print(f"  {k}/{len(todo)}  {rate * 60:.1f}/min  eta {(len(todo) - k) / rate / 60:.0f} min", flush=True)
    print("HOURLY_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
