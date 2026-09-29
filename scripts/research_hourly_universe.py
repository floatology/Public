#!/usr/bin/env python3
"""The unbiased hourly test: price/volume signals on every active token.

Input: data/chain/hourly.jsonl (scripts/gt_hourly.py), the main pool of every
token with >= 3 days of >= $1k volume — not hand-picked. Each token's hourly
series is gap-filled (missing hour = no trades: last close carried, volume 0).

Features at hour t (only data up to t): the price/volume set that matched the
full model on the ledger sample — age_h, lvol_6h, lvol_24h, surge6, r_24,
r_72, dd_7d, up_from_low72, heat_d (daily market regime, lagged), hod.
Outcomes from the NEXT hour's close: 2x within 72h / 7d, where a 2x hour must
also carry >= $200 of volume (no single-print wicks); crash = a close <= 0.5x
first. Hours within 7 days of the fetch are excluded (incomplete windows).

Reports: base rates by age; simple rules (volume surge, momentum, rebound);
and the walk-forward model (weekly retrain), top-k de-duplicated.
Writes data/research/hourly_universe.md.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from research_walkforward import walk  # noqa: E402

FEATS = ["age_h", "lvol_6h", "lvol_24h", "surge6", "r_24", "r_72", "dd_7d", "up_from_low72", "heat_d", "hod"]


def heat_by_day():
    from candle_backtest import build_series
    up, act = defaultdict(int), defaultdict(int)
    for s in build_series().values():
        seq = s["seq"]
        for i in range(3, len(seq)):
            if seq[i]["vol"] >= 1000 and seq[i - 3]["c"]:
                act[seq[i]["d"]] += 1
                up[seq[i]["d"]] += seq[i]["c"] >= 1.5 * seq[i - 3]["c"]
    daily = {d: up[d] / act[d] for d in act if act[d] >= 20}
    return {d: np.mean([daily[x] for x in (d - 1, d - 2, d - 3) if x in daily])
            for d in daily if any(x in daily for x in (d - 1, d - 2, d - 3))}


def build():
    heat = heat_by_day()
    rows = []
    fetched_at = 0
    recs = [json.loads(l) for l in open(ROOT / "data/chain/hourly.jsonl")]
    for r in recs:
        if r.get("candles"):
            fetched_at = max(fetched_at, max(c[0] for c in r["candles"]))
    end_ok = fetched_at - 7 * 86400
    for r in recs:
        cs = {int(c[0]): c for c in r.get("candles") or []}
        if len(cs) < 96:
            continue
        h0, h1 = min(cs), max(cs)
        hours = list(range(h0, h1 + 1, 3600))
        close, vol = [], []
        prev = None
        for h in hours:
            c = cs.get(h)
            if c:
                prev = c[4]
            close.append(prev)
            vol.append(c[5] if c else 0.0)
        close = np.array(close, dtype=float)
        vol = np.array(vol, dtype=float)
        n = len(hours)
        cvol = np.concatenate([[0], np.cumsum(vol)])
        wsum = lambda a, b: cvol[max(b, 0)] - cvol[max(a, 0)]   # sum vol[a:b]
        for i in range(24, n - 1):
            if hours[i] > end_ok or not close[i] or wsum(i - 23, i + 1) < 1000:
                continue
            e = close[i + 1]
            if not e:
                continue
            fw = slice(i + 2, min(n, i + 2 + 168))
            fc, fv = close[fw] / e, vol[fw]
            hit = (fc >= 2) & (fv >= 200)
            t2 = np.argmax(hit) if hit.any() else None
            low = np.where(fc <= 0.5)[0]
            crash = bool(len(low)) and (t2 is None or low[0] < t2)
            y72 = t2 is not None and t2 < 71
            y7 = t2 is not None
            v6, v24 = wsum(i - 5, i + 1), wsum(i - 23, i + 1)
            rate72 = wsum(i - 77, i - 5) / 72.0
            c24 = close[i - 24] if i >= 24 else None
            c72 = close[i - 72] if i >= 72 else None
            f = {
                "age_h": i, "lvol_6h": math.log1p(v6), "lvol_24h": math.log1p(v24),
                "surge6": v6 / (6 * rate72) if rate72 > 0 else np.nan,
                "r_24": close[i] / c24 if c24 else np.nan,
                "r_72": close[i] / c72 if c72 else np.nan,
                "dd_7d": close[i] / np.nanmax(close[max(0, i - 167):i + 1]),
                "up_from_low72": close[i] / np.nanmin(close[max(0, i - 71):i + 1]),
                "heat_d": heat.get(hours[i] // 86400, np.nan),
                "hod": (hours[i] % 86400) // 3600,
            }
            rows.append((r["token"], hours[i], [f[k] for k in FEATS], y72, y7, crash, v6))
    return rows


def main() -> None:
    rows = build()
    tok = [r[0] for r in rows]
    t = np.array([r[1] for r in rows])
    X = np.array([r[2] for r in rows], dtype=float)
    X[~np.isfinite(X)] = np.nan
    y = np.array([r[3] for r in rows], dtype=int)
    y7 = np.array([r[4] for r in rows], dtype=int)
    cr = np.array([r[5] for r in rows], dtype=int)
    v6 = np.array([r[6] for r in rows])
    fi = {f: i for i, f in enumerate(FEATS)}

    def dedup(ii):
        out, last = [], {}
        for i in sorted(ii, key=lambda i: (tok[i], t[i])):
            if tok[i] in last and t[i] - last[tok[i]] < 72 * 3600:
                continue
            last[tok[i]] = t[i]
            out.append(i)
        return out

    def row(label, sel, base):
        ev = dedup(list(sel))
        if not ev:
            return f"| {label} | 0 | | | | | |"
        h = y[ev].mean()
        return (f"| {label} | {len(ev)} | {len({tok[i] for i in ev})} | {100 * h:.0f}% | {100 * y7[ev].mean():.0f}% | "
                f"{100 * cr[ev].mean():.0f}% | {h / base:.2f}x |")

    allidx = np.arange(len(y))
    base_ev = dedup(list(allidx))
    b = y[base_ev].mean()
    lines = [f"# Unbiased hourly test — {len(y):,} live token-hours (>= $1k in 24h), {len(set(tok))} tokens\n",
             f"Base (de-duplicated events): 2x within 72h {100 * b:.1f}% (n={len(base_ev)}), "
             f"within 7d {100 * y7[base_ev].mean():.1f}%, crash-first {100 * cr[base_ev].mean():.1f}%.\n",
             "## Base rate by token age\n", "| age | token-hours | 2x 72h | crash 7d |", "|---|---|---|---|"]
    age = X[:, fi["age_h"]]
    for a, z in ((24, 48), (48, 168), (168, 336), (336, 720), (720, 10**7)):
        m = (age >= a) & (age < z)
        if m.sum():
            lines.append(f"| {a}-{z if z < 10**7 else '+'}h | {m.sum():,} | {100 * y[m].mean():.0f}% | {100 * cr[m].mean():.0f}% |")
    lines += ["\n## Simple rules (all ages >= 24h)\n",
              "| rule | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |", "|---|---|---|---|---|---|---|"]
    S, R24, UP = X[:, fi["surge6"]], X[:, fi["r_24"]], X[:, fi["up_from_low72"]]
    DD = X[:, fi["dd_7d"]]
    rules = [("volume surge >= 10x, 6h >= $5k", (S >= 10) & (v6 >= 5000)),
             ("volume surge >= 20x, 6h >= $5k", (S >= 20) & (v6 >= 5000)),
             ("momentum +50% in 24h", R24 >= 1.5),
             ("pullback reversal (<= 0.7 of 7d high, +20% off 72h low) + surge5",
              (DD <= 0.7) & (UP >= 1.2) & (S >= 5) & (v6 >= 5000)),
             ("young (48-168h) + surge10", (age >= 48) & (age < 168) & (S >= 10) & (v6 >= 5000))]
    for label, m in rules:
        lines.append(row(label, np.where(np.nan_to_num(m.astype(float)) > 0)[0], b))
    p = walk(X, y, t, step=7 * 86400, warm=21 * 86400)
    idx = np.where(~np.isnan(p))[0]
    bw = y[dedup(list(idx))].mean()
    lines += [f"\n## Walk-forward model (weekly retrain), {len(idx):,} out-of-sample rows, base {100 * bw:.1f}%\n",
              "| selection | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |", "|---|---|---|---|---|---|---|"]
    order = idx[np.argsort(-p[idx])]
    for f in (0.001, 0.002, 0.005, 0.01, 0.02, 0.05):
        lines.append(row(f"top {100 * f:g}%", order[:max(1, int(f * len(idx)))], bw))
    for c in (0.3, 0.4, 0.5, 0.6):
        lines.append(row(f"prob >= {c}", idx[p[idx] >= c], bw))
    text = "\n".join(lines) + "\n"
    (ROOT / "data/research/hourly_universe.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
