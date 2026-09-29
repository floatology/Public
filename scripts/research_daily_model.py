#!/usr/bin/env python3
"""The unbiased check: does anything predict 2x on the full daily-candle universe?

The 65 ledger tokens were partly chosen *because* they ran, so effects found
there (token age above all) may be selection. This repeats the search on every
GeckoTerminal-tracked token, delisted census coins included (4,029 tokens).

Per token-day (signal at the day's close, only data up to that day):
  age_d, lvol (log volume today), lvol7 (log mean volume last 7d), vsurge
  (today / 14d median), r1, r3, r7 (close ratios), dd30 (close / 30d max
  close), up7 (close / 7d min close), heat (market regime, 3 days to
  yesterday), lmcap (log price x supply where known), npools.
Outcome: some close within 3 days >= 2x today's close (and 7 days); crash =
close <= 0.5x before any 2x within 7 days.

Reports: base rate by age and by activity; then gradient-boosted trees with
time and token splits, top-k precision on the test side, de-duplicated (one
event per token per 7 days). Writes data/research/daily_model.md.
"""
from __future__ import annotations

import hashlib
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from candle_backtest import build_series  # noqa: E402

FEATS = ["age_d", "lvol", "lvol7", "vsurge", "r1", "r3", "r7", "dd30", "up7", "heat", "lmcap", "npools"]
OUT = ROOT / "data/research/daily_model.md"


def build_rows():
    """(tok, day, feature list, run2x_3d, run2x_7d, crash) for every live token-day."""
    series = build_series()
    # market heat, as in research_features2 (share of active tokens up 1.5x over 3 days, lagged)
    up, act = defaultdict(int), defaultdict(int)
    for s in series.values():
        seq = s["seq"]
        for i in range(3, len(seq)):
            if seq[i]["vol"] >= 1000 and seq[i - 3]["c"]:
                act[seq[i]["d"]] += 1
                up[seq[i]["d"]] += seq[i]["c"] >= 1.5 * seq[i - 3]["c"]
    daily = {d: up[d] / act[d] for d in act if act[d] >= 20}
    heat = {d: np.mean([daily[x] for x in (d - 1, d - 2, d - 3) if x in daily])
            for d in daily if any(x in daily for x in (d - 1, d - 2, d - 3))}

    rows = []
    for tok, s in series.items():
        seq = s["seq"]
        sup = s.get("supply")
        for i in range(1, len(seq) - 7):
            c = seq[i]["c"]
            if not c or seq[i]["vol"] < 1000:      # only live token-days
                continue
            fwd = [x["c"] / c for x in seq[i + 1:i + 8] if x["c"]]
            if not fwd:
                continue
            r3 = max(fwd[:3]) >= 2
            r7 = max(fwd) >= 2
            crash = False
            for r in fwd:
                if r >= 2:
                    break
                if r <= 0.5:
                    crash = True
                    break
            vols = [x["vol"] for x in seq[max(0, i - 14):i]]
            med = sorted(vols)[len(vols) // 2] if vols else 0
            cl = lambda k: seq[i - k]["c"] if i - k >= 0 and seq[i - k]["c"] else None
            f = {
                "age_d": i,
                "lvol": math.log1p(seq[i]["vol"]),
                "lvol7": math.log1p(np.mean([x["vol"] for x in seq[max(0, i - 7):i]]) if i else 0),
                "vsurge": seq[i]["vol"] / med if med > 0 else np.nan,
                "r1": c / cl(1) if cl(1) else np.nan,
                "r3": c / cl(3) if cl(3) else np.nan,
                "r7": c / cl(7) if cl(7) else np.nan,
                "dd30": c / max(x["c"] or 0 for x in seq[max(0, i - 30):i + 1]),
                "up7": c / min(x["c"] for x in seq[max(0, i - 7):i + 1] if x["c"]),
                "heat": heat.get(seq[i]["d"], np.nan),
                "lmcap": math.log1p(c * sup) if sup else np.nan,
                "npools": s.get("pools", 1),
            }
            rows.append((tok, seq[i]["d"], [f[k] for k in FEATS], r3, r7, crash))
    return rows


def main() -> None:
    rows = build_rows()
    tok = [r[0] for r in rows]
    day = np.array([r[1] for r in rows])
    X = np.array([r[2] for r in rows], dtype=float)
    X[~np.isfinite(X)] = np.nan
    y3 = np.array([r[3] for r in rows], dtype=int)
    y7 = np.array([r[4] for r in rows], dtype=int)
    cr = np.array([r[5] for r in rows], dtype=int)
    lines = [f"# Daily universe model — {len(rows):,} live token-days (>= $1k), {len(set(tok))} tokens\n",
             "Outcome: a close >= 2x within 3 days (2x 3d) / 7 days; crash = <= 0.5x first.\n",
             "## Base rate by token age (days since first candle)\n",
             "| age | token-days | 2x 3d | 2x 7d | crash 7d |", "|---|---|---|---|---|"]
    age = X[:, 0]
    for a, b in ((1, 3), (3, 7), (7, 14), (14, 30), (30, 60), (60, 10**6)):
        m = (age >= a) & (age < b)
        if m.sum():
            lines.append(f"| {a}-{b if b < 10**6 else '+'}d | {m.sum():,} | {100 * y3[m].mean():.1f}% | "
                         f"{100 * y7[m].mean():.1f}% | {100 * cr[m].mean():.1f}% |")

    def dedup(idx):
        out, last = [], {}
        for i in sorted(idx, key=lambda i: (tok[i], day[i])):
            if tok[i] in last and day[i] - last[tok[i]] < 7:
                continue
            last[tok[i]] = day[i]
            out.append(i)
        return out

    mid = np.median(day)
    half = np.array([int(hashlib.md5(t.encode()).hexdigest(), 16) % 2 for t in tok])
    splits = {"time": (day < mid, day >= mid), "tokA": (half == 0, half == 1), "tokB": (half == 1, half == 0)}
    for name, (tr, te) in splits.items():
        clf = HistGradientBoostingClassifier(max_depth=3, max_iter=250, learning_rate=0.05,
                                             min_samples_leaf=150, l2_regularization=1.0, random_state=0)
        clf.fit(X[tr], y3[tr])
        te_idx = np.where(te)[0]
        p = clf.predict_proba(X[te])[:, 1]
        base = dedup(list(te_idx))
        b3 = y3[base].mean()
        lines.append(f"\n## split {name}: train {tr.sum():,} / test {te.sum():,}; test AUC {roc_auc_score(y3[te], p):.3f}; "
                     f"test base (dedup) 2x 3d {100 * b3:.1f}% (n={len(base)})\n")
        lines.append("| top of test | fires | events | tokens | 2x 3d | 2x 7d | crash 7d | lift |")
        lines.append("|---|---|---|---|---|---|---|---|")
        order = np.argsort(-p)
        for frac in (0.005, 0.01, 0.02, 0.05, 0.10):
            k = max(1, int(frac * len(p)))
            ev = dedup(list(te_idx[order[:k]]))
            h = y3[ev].mean()
            lines.append(f"| top {100 * frac:g}% | {k} | {len(ev)} | {len({tok[i] for i in ev})} | {100 * h:.0f}% | "
                         f"{100 * y7[ev].mean():.0f}% | {100 * cr[ev].mean():.0f}% | {h / b3:.2f}x |")
        if name == "time":
            pi = permutation_importance(clf, X[te], y3[te], scoring="roc_auc", n_repeats=3, random_state=0)
            imp = sorted(zip(FEATS, pi.importances_mean), key=lambda x: -x[1])
            lines.append("\nPermutation importance (time split): " +
                         ", ".join(f"{f} {v:.3f}" for f, v in imp[:8]))
    text = "\n".join(lines) + "\n"
    OUT.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
