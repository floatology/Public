#!/usr/bin/env python3
"""Can a combination of every feature find 2x runs at a high hit rate, out of sample?

Gradient-boosted trees on the established-coin token-hour panel (age >= 48h).
Three honest splits, each trained on one part and scored only on the other:
  time   train before the median hour, test after
  tokA   train on token hash-half 0, test on half 1
  tokB   the reverse
On the test side, token-hours are ranked by predicted probability; for the top
0.5%, 1%, 2%, 5% and 10% we report de-duplicated events (first per token, then
72h cool-off), distinct tokens, hit rate for 2x in 72h and 7d, crash rate, and
the test-side base rate. Writes data/research/model.md.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/research/cache/rd.duckdb"
OUT = ROOT / "data/research/model.md"

FEATS = ["age_h", "lvol_6h", "lvol_24h", "surge6", "newb_surge", "newb_6h", "r_24", "r_72", "dd_7d",
         "up_from_low72", "big_share", "bundle_6h", "smart_n_6h", "smart_q_6h", "heat_d", "pro_n_6h",
         "pro_big_6h", "breadth_6h", "breadth_24h", "active_6h", "active_24h", "hod"]


def load(con):
    q = """
        select token, hour, run2x_72::int as y, run2x_168::int as y7, crash_168::int as cr,
               age_h, ln(1 + vol_6h) as lvol_6h, ln(1 + vol_24h) as lvol_24h, surge6, newb_surge, newb_6h,
               r_24, r_72, dd_7d, up_from_low72, big_buy_6h / nullif(vol_6h, 0) as big_share,
               bundle_6h, smart_n_6h, smart_q_6h, heat_d, pro_n_6h, pro_big_6h,
               breadth_6h, breadth_24h, active_6h, active_24h, (hour % 86400) / 3600 as hod
        from panel where age_h >= 48 and vol_24h > 0
        order by token, hour
    """
    rows = con.execute(q).fetchall()
    cols = [d[0] for d in con.description]
    arr = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
    X = np.array([[np.nan if v is None else float(v) for v in vals]
                  for vals in zip(*[arr[f] for f in FEATS])], dtype=float)
    X[~np.isfinite(X)] = np.nan
    return arr, X


def dedup_idx(idx, tok, hour):
    out, last = [], {}
    for i in sorted(idx, key=lambda i: (tok[i], hour[i])):
        if tok[i] in last and hour[i] - last[tok[i]] < 72 * 3600:
            continue
        last[tok[i]] = hour[i]
        out.append(i)
    return out


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET enable_progress_bar=false")
    arr, X = load(con)
    y = np.array(arr["y"])
    tok, hour = arr["token"], arr["hour"]
    y7, cr = np.array(arr["y7"]), np.array(arr["cr"])
    n = len(y)
    mid = sorted(hour)[n // 2]
    half = np.array([int(hashlib.md5(t.encode()).hexdigest(), 16) % 2 for t in tok])
    hr = np.array(hour)
    splits = {"time": (hr < mid, hr >= mid), "tokA": (half == 0, half == 1), "tokB": (half == 1, half == 0)}

    lines = ["# Model search — can all features together find 2x runs out of sample?\n",
             f"{n:,} established-coin token-hours, {len(set(tok))} tokens. Gradient-boosted trees "
             "(max_depth 3, 200 iterations, min 200 samples per leaf). Test-side results only.\n"]
    imp_lines = []
    for name, (tr, te) in splits.items():
        clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
                                             min_samples_leaf=200, l2_regularization=1.0, random_state=0)
        clf.fit(X[tr], y[tr])
        p = clf.predict_proba(X[te])[:, 1]
        te_idx = np.where(te)[0]
        base_ev = dedup_idx(list(te_idx), tok, hour)
        b72 = np.mean(y[base_ev])
        lines.append(f"\n## split: {name} — train {tr.sum():,} / test {te.sum():,} token-hours; "
                     f"test base (dedup events) 2x-72h {100 * b72:.0f}%, n={len(base_ev)}\n")
        lines.append("| top of test by score | fires | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |")
        lines.append("|---|---|---|---|---|---|---|---|")
        order = np.argsort(-p)
        for frac in (0.005, 0.01, 0.02, 0.05, 0.10):
            k = max(1, int(frac * len(p)))
            sel = te_idx[order[:k]]
            ev = dedup_idx(list(sel), tok, hour)
            h = np.mean(y[ev]); h7 = np.mean(y7[ev]); c = np.mean(cr[ev])
            lines.append(f"| top {100 * frac:g}% | {k} | {len(ev)} | {len({tok[i] for i in ev})} | "
                         f"{100 * h:.0f}% | {100 * h7:.0f}% | {100 * c:.0f}% | {h / b72:.2f}x |")
        if name == "time":
            pi = permutation_importance(clf, X[te], y[te], scoring="roc_auc", n_repeats=3, random_state=0)
            order_f = np.argsort(-pi.importances_mean)
            imp_lines = ["\n## Feature importance (time split, permutation, drop in test AUC)\n",
                         "| feature | importance |", "|---|---|"]
            imp_lines += [f"| {FEATS[j]} | {pi.importances_mean[j]:.4f} |" for j in order_f[:12]]
            from sklearn.metrics import roc_auc_score
            lines.append(f"\nTest AUC (time split): {roc_auc_score(y[te], p):.3f}")
    text = "\n".join(lines + imp_lines) + "\n"
    OUT.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
