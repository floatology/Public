#!/usr/bin/env python3
"""Every up-leg of 2x or more in the archived tokens (zigzag on hourly VWAP).

A leg starts at a trough and ends at the peak before price gives back 50%
(a reversal of 2x down from the peak, symmetric with the 2x up threshold).
Legs are written to data/research/events.csv with trough/peak hour, multiple,
hours to peak, the token's age at the trough, and trough-side liquidity
(hourly volume over the 24h before the trough).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/research/cache/rd.duckdb"
OUT = ROOT / "data/research/events.csv"
REV = 2.0   # reversal factor that ends a leg (peak / 2 ends an up-leg; trough * 2 ends a down-leg)


def zigzag(hours: list[int], px: list[float], rev: float) -> list[tuple[int, int]]:
    """Return (trough_idx, peak_idx) for every up-leg whose peak/trough >= rev."""
    legs = []
    lo_i = hi_i = 0
    mode = None  # 'up' after a confirmed trough, 'down' after a confirmed peak
    for i in range(1, len(px)):
        p = px[i]
        if mode in (None, "down"):
            if p < px[lo_i]:
                lo_i = i
            if p >= px[lo_i] * rev:
                mode, hi_i = "up", i
        if mode == "up":
            if p > px[hi_i]:
                hi_i = i
            if p <= px[hi_i] / rev:
                legs.append((lo_i, hi_i))
                mode, lo_i = "down", i
    if mode == "up":
        legs.append((lo_i, hi_i))
    return legs


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET enable_progress_bar=false")
    sym = {t: e.get("symbol", "?") for t, e in json.load(open(ROOT / "data/tokens/tokens.json")).items()}
    rows = []
    for (tok,) in con.execute("select distinct token from hourly").fetchall():
        data = con.execute(
            "select hour, price, vol from hourly where token = ? and price > 0 order by hour", [tok]).fetchall()
        if len(data) < 48:
            continue
        hours = [d[0] for d in data]
        px = [d[1] for d in data]
        vol = [d[2] for d in data]
        h0 = hours[0]
        for lo, hi in zigzag(hours, px, REV):
            pre = vol[max(0, lo - 24):lo]
            rows.append({
                "symbol": sym.get(tok, "?"), "token": tok,
                "trough_hour": hours[lo], "peak_hour": hours[hi],
                "trough_px": px[lo], "peak_px": px[hi],
                "multiple": round(px[hi] / px[lo], 2),
                "hours_to_peak": (hours[hi] - hours[lo]) // 3600,
                "age_h_at_trough": (hours[lo] - h0) // 3600,
                "vol_24h_before": round(sum(pre)),
                "vol_24h_after": round(sum(vol[lo:lo + 24])),
            })
    rows.sort(key=lambda r: -r["multiple"])
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} legs >= {REV}x across {len({r['token'] for r in rows})} tokens -> {OUT}")
    for r in rows[:40]:
        print(r["symbol"], r["multiple"], "x in", r["hours_to_peak"], "h, age", r["age_h_at_trough"],
              "h, vol24 before", r["vol_24h_before"])


if __name__ == "__main__":
    main()
