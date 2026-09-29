#!/usr/bin/env python3
"""What does the model actually pick? Top out-of-sample events + a readable rule tree.

1. Retrains the time-split model and lists the top-2% test events (de-duplicated)
   with their key features and outcomes.
2. Fits a depth-3 decision tree on the TRAIN half only (min 300 samples/leaf),
   prints its rules, and scores each leaf on the TEST half — readable rules
   that can be checked out of sample.
3. Age check: the base rate by token age, so the model's reliance on age is
   visible.
Appends to data/research/model.md.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.tree import DecisionTreeClassifier, export_text

import research_model as rm

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    con = duckdb.connect(str(rm.DB), read_only=True)
    con.execute("SET enable_progress_bar=false")
    arr, X = rm.load(con)
    y, y7, cr = np.array(arr["y"]), np.array(arr["y7"]), np.array(arr["cr"])
    tok, hour = arr["token"], arr["hour"]
    hr = np.array(hour)
    mid = sorted(hour)[len(hour) // 2]
    tr, te = hr < mid, hr >= mid
    sym = {t: e.get("symbol") for t, e in json.load(open(ROOT / "data/tokens/tokens.json")).items()}
    fi = {f: i for i, f in enumerate(rm.FEATS)}
    out = ["\n## Inspection (scripts/research_model_inspect.py)\n"]

    # 3. age base rates
    out.append("Base rate by token age (all established token-hours, 2x within 72h):\n")
    out.append("| age | token-hours | 2x 72h | crash 7d |")
    out.append("|---|---|---|---|")
    age = X[:, fi["age_h"]]
    for a, b in ((48, 96), (96, 168), (168, 336), (336, 720), (720, 1e9)):
        m = (age >= a) & (age < b)
        out.append(f"| {a}-{b if b < 1e9 else '+'}h | {m.sum():,} | {100 * y[m].mean():.0f}% | {100 * cr[m].mean():.0f}% |")

    clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05,
                                         min_samples_leaf=200, l2_regularization=1.0, random_state=0)
    clf.fit(X[tr], y[tr])
    te_idx = np.where(te)[0]
    p = clf.predict_proba(X[te])[:, 1]
    top = te_idx[np.argsort(-p)[:int(0.02 * len(p))]]
    ev = rm.dedup_idx(list(top), tok, hour)
    out.append("\nTop-2% test events (time split), de-duplicated:\n")
    out.append("| token | hour (UTC) | age h | 24h vol | surge6 | r_72 | up off 72h low | breadth24 | heat | 2x 72h | 2x 7d | crash |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i in sorted(ev, key=lambda i: hour[i]):
        f = lambda k: X[i, fi[k]]
        out.append(f"| {sym.get(tok[i], tok[i][:8])} | {dt.datetime.utcfromtimestamp(hour[i]):%m-%d %H} | {f('age_h'):.0f} | "
                   f"{np.expm1(f('lvol_24h')):,.0f} | {f('surge6'):.1f} | {f('r_72'):.2f} | {f('up_from_low72'):.2f} | "
                   f"{f('breadth_24h'):.2f} | {f('heat_d'):.2f} | {'Y' if y[i] else '-'} | {'Y' if y7[i] else '-'} | {'Y' if cr[i] else '-'} |")

    # 2. readable tree, trained on train half; leaves scored on test half
    Xf = np.nan_to_num(X, nan=-1.0)
    tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=300, random_state=0)
    tree.fit(Xf[tr], y[tr])
    out.append("\nDepth-3 rule tree (fit on train half only):\n\n```")
    out.append(export_text(tree, feature_names=rm.FEATS, show_weights=False))
    out.append("```\n\nEach leaf scored on the test half (de-duplicated events):\n")
    out.append("| leaf | train 2x72 | test fires | test events | test 2x 72h | test 2x 7d | test crash |")
    out.append("|---|---|---|---|---|---|---|")
    leaf_tr = tree.apply(Xf[tr])
    leaf_te = tree.apply(Xf[te])
    for leaf in sorted(set(leaf_tr)):
        trm = leaf_tr == leaf
        tem = np.where(leaf_te == leaf)[0]
        if len(tem) == 0:
            continue
        e = rm.dedup_idx(list(te_idx[tem]), tok, hour)
        out.append(f"| {leaf} | {100 * y[tr][trm].mean():.0f}% | {len(tem):,} | {len(e)} | {100 * y[e].mean():.0f}% | "
                   f"{100 * y7[e].mean():.0f}% | {100 * cr[e].mean():.0f}% |")
    text = "\n".join(out) + "\n"
    with open(ROOT / "data/research/model.md", "a") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
