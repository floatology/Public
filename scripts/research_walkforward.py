#!/usr/bin/env python3
"""Walk-forward test: how the model would actually have performed if used live.

For the hourly ledger panel and the daily-candle universe: starting after the
first 3 weeks, retrain every 7 days on everything before the cut and score the
next 7 days only. All out-of-sample scores are pooled; then, for score
thresholds (top 0.5/1/2/5% of all out-of-sample rows, and absolute
probability cut-offs), de-duplicated events are counted with their realised
2x and crash rates, plus how those events spread across the test weeks.
Writes data/research/walkforward.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_daily_model as rdm  # noqa: E402
import research_model as rm  # noqa: E402

OUT = ROOT / "data/research/walkforward.md"


def walk(X, y, t, step, warm):
    """Out-of-sample probability for each row (nan where never tested)."""
    p = np.full(len(y), np.nan)
    t0 = t.min() + warm
    cut = t0
    while cut <= t.max():
        tr = t < cut
        te = (t >= cut) & (t < cut + step)
        if tr.sum() > 2000 and te.sum() and y[tr].sum() > 50:
            clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
                                                 min_samples_leaf=150, l2_regularization=1.0, random_state=0)
            clf.fit(X[tr], y[tr])
            p[te] = clf.predict_proba(X[te])[:, 1]
        cut += step
    return p


def report(name, p, y, y7, cr, tok, t, cool, week, unit):
    idx = np.where(~np.isnan(p))[0]

    def dedup(ii):
        out, last = [], {}
        for i in sorted(ii, key=lambda i: (tok[i], t[i])):
            if tok[i] in last and t[i] - last[tok[i]] < cool:
                continue
            last[tok[i]] = t[i]
            out.append(i)
        return out

    base = dedup(list(idx))
    b = np.mean(y[base])
    lines = [f"\n## {name}: {len(idx):,} out-of-sample rows, base (dedup) 2x {100 * b:.1f}% (n={len(base)})\n",
             f"| selection | events | tokens | weeks with events | 2x ({unit}) | 2x 7d | crash 7d | lift |",
             "|---|---|---|---|---|---|---|---|"]
    order = idx[np.argsort(-p[idx])]
    sels = [(f"top {100 * f:g}%", order[:max(1, int(f * len(idx)))]) for f in (0.002, 0.005, 0.01, 0.02, 0.05)]
    sels += [(f"prob >= {c}", idx[p[idx] >= c]) for c in (0.3, 0.4, 0.5, 0.6)]
    for label, sel in sels:
        ev = dedup(list(sel))
        if not ev:
            lines.append(f"| {label} | 0 | | | | | | |")
            continue
        h = np.mean(y[ev])
        lines.append(f"| {label} | {len(ev)} | {len({tok[i] for i in ev})} | {len({t[i] // week for i in ev})} | "
                     f"{100 * h:.0f}% | {100 * np.mean(y7[ev]):.0f}% | {100 * np.mean(cr[ev]):.0f}% | {h / b:.2f}x |")
    return lines


def main() -> None:
    lines = ["# Walk-forward test — retrain weekly on the past, score the next week only\n"]
    # hourly ledger panel
    con = duckdb.connect(str(rm.DB), read_only=True)
    con.execute("SET enable_progress_bar=false")
    arr, X = rm.load(con)
    y, y7, cr = np.array(arr["y"]), np.array(arr["y7"]), np.array(arr["cr"])
    t = np.array(arr["hour"])
    p = walk(X, y, t, step=7 * 86400, warm=21 * 86400)
    lines += report("hourly ledger panel (65 tokens, 2x within 72h)", p, y, y7, cr, arr["token"], t,
                    cool=72 * 3600, week=7 * 86400, unit="72h")
    # daily universe
    rows = rdm.build_rows()
    tok = [r[0] for r in rows]
    td = np.array([r[1] for r in rows])
    Xd = np.array([r[2] for r in rows], dtype=float)
    Xd[~np.isfinite(Xd)] = np.nan
    y3 = np.array([r[3] for r in rows], dtype=int)
    y7d = np.array([r[4] for r in rows], dtype=int)
    crd = np.array([r[5] for r in rows], dtype=int)
    pd_ = walk(Xd, y3, td, step=7, warm=21)
    lines += report("daily universe (4,029 tokens, 2x within 3 days)", pd_, y3, y7d, crd, tok, td,
                    cool=7, week=7, unit="3d")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
