#!/usr/bin/env python3
"""Why does the hourly model beat the daily one? Ablation and a selection-bias check.

Walk-forward (weekly retrain, next week scored) on the hourly ledger panel with
feature subsets:
  all            every feature
  price/volume   only what the daily universe also has (age, volume, surge,
                 returns, drawdown, rebound, regime, hour of day)
  flow only      wallet/flow features plus age
  no age         everything except token age
and each scored on token subsets:
  all tokens
  batch-2 CONTROLS only: coins picked for being as active as the cases but
                 never having had a 2x run with 14d of history before selection
                 — the least hand-picked part of the ledger sample
  batch-2 CASES only
Top 0.5 / 1 / 2 % of out-of-sample rows, de-duplicated (72h cool-off).
Writes data/research/ablation.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_model as rm  # noqa: E402
from research_walkforward import walk  # noqa: E402

PV = ["age_h", "lvol_6h", "lvol_24h", "surge6", "r_24", "r_72", "dd_7d", "up_from_low72", "heat_d", "hod"]
FLOW = ["age_h", "newb_surge", "newb_6h", "big_share", "bundle_6h", "smart_n_6h", "smart_q_6h", "pro_n_6h",
        "pro_big_6h", "breadth_6h", "breadth_24h", "active_6h", "active_24h"]


def main() -> None:
    con = duckdb.connect(str(rm.DB), read_only=True)
    con.execute("SET enable_progress_bar=false")
    arr, X = rm.load(con)
    y, y7, cr = np.array(arr["y"]), np.array(arr["y7"]), np.array(arr["cr"])
    tok, t = arr["token"], np.array(arr["hour"])
    b2 = json.load(open(ROOT / "data/overnight/batch2.json"))
    cases, controls = {a.lower() for a in b2["cases"]}, {a.lower() for a in b2["controls"]}
    sets = {"all": rm.FEATS, "price/volume": PV, "flow only": FLOW,
            "no age": [f for f in rm.FEATS if f != "age_h"]}
    subsets = {"all tokens": lambda k: True, "controls only": lambda k: k in controls,
               "cases only": lambda k: k in cases}

    def dedup(ii):
        out, last = [], {}
        for i in sorted(ii, key=lambda i: (tok[i], t[i])):
            if tok[i] in last and t[i] - last[tok[i]] < 72 * 3600:
                continue
            last[tok[i]] = t[i]
            out.append(i)
        return out

    lines = ["# Ablation and selection check (walk-forward, hourly ledger panel)\n",
             f"batch-2 cases in panel: {len({k for k in tok if k in cases})}, controls: {len({k for k in tok if k in controls})}\n",
             "| features | tokens | base 2x72 | top 0.5% | top 1% | top 2% |", "|---|---|---|---|---|---|"]
    for sname, feats in sets.items():
        cols = [rm.FEATS.index(f) for f in feats]
        p = walk(X[:, cols], y, t, step=7 * 86400, warm=21 * 86400)
        for uname, keep in subsets.items():
            idx = np.array([i for i in np.where(~np.isnan(p))[0] if keep(tok[i])])
            if len(idx) == 0:
                continue
            base = dedup(list(idx))
            cells = []
            order = idx[np.argsort(-p[idx])]
            for f in (0.005, 0.01, 0.02):
                ev = dedup(list(order[:max(1, int(f * len(idx)))]))
                cells.append(f"{100 * np.mean(y[ev]):.0f}% / {100 * np.mean(y7[ev]):.0f}% / "
                             f"{100 * np.mean(cr[ev]):.0f}%c (n={len(ev)})")
            lines.append(f"| {sname} | {uname} | {100 * np.mean(y[base]):.0f}% (n={len(base)}) | " + " | ".join(cells) + " |")
    lines.append("\nCells: 2x within 72h / 2x within 7d / crash-first within 7d (events).")
    text = "\n".join(lines) + "\n"
    (ROOT / "data/research/ablation.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
