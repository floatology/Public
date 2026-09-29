#!/usr/bin/env python3
"""Coverage: how many of the big runs did each pattern flag in time?

For every >= 2x leg in an established coin (events.csv, age >= 48h, with a
complete panel), a signal "catches" the leg if it fires at some hour from 24h
before the trough to 12h after it, while the price at that hour is still
<= half the leg's peak (so a 2x was still available from the signal). Reported
per pattern: legs caught / all legs, split by leg size, next to the pattern's
precision (hit rate) from the evaluation — the two numbers together say how
much of the opportunity a pattern covers and how often it is wrong.
Writes data/research/recall.md.
"""
from __future__ import annotations

import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/research/cache/rd.duckdb"

PATTERNS = [
    ("quiet wake-up (prev48 < $2k, 6h >= $5k)", "vol_prev48 < 2000 and vol_6h >= 5000"),
    ("volume surge >= 5x", "surge6 >= 5 and vol_6h >= 5000"),
    ("volume surge >= 10x", "surge6 >= 10 and vol_6h >= 5000"),
    ("volume surge >= 10x + breadth6 >= 0.3", "surge6 >= 10 and vol_6h >= 5000 and breadth_6h >= 0.3"),
    ("new-wallet surge >= 5x", "newb_surge >= 5 and newb_6h >= 20"),
    ("pullback reversal (<= 0.7 of 7d high, +20% off low)", "dd_7d <= 0.7 and up_from_low72 >= 1.2"),
    ("momentum +50% in 24h", "r_24 >= 1.5"),
    ("breadth24 >= 0.3", "breadth_24h >= 0.3 and active_24h >= 50"),
    ("smart wallets >= 3", "smart_n_6h >= 3"),
    ("any of: wake-up, surge10, new-wallet surge5",
     "(vol_prev48 < 2000 and vol_6h >= 5000) or (surge6 >= 10 and vol_6h >= 5000) or (newb_surge >= 5 and newb_6h >= 20)"),
]


def main() -> None:
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET enable_progress_bar=false")
    legs = [r for r in csv.DictReader(open(ROOT / "data/research/events.csv")) if int(r["age_h_at_trough"]) >= 48]
    lines = ["# Coverage — which patterns flagged the big runs in time\n",
             "A leg is caught if the pattern fires between 24h before and 12h after the trough while price is "
             "still <= half the leg's peak.\n",
             "| pattern | all legs | 2-5x legs | 5-10x legs | 10x+ legs |", "|---|---|---|---|---|"]
    usable = []
    for r in legs:
        tok, tr, pk = r["token"], int(r["trough_hour"]), float(r["peak_px"])
        n = con.execute("select count(*) from panel where token = ? and hour between ? and ?",
                        [tok, tr - 86400, tr + 43200]).fetchone()[0]
        if n:
            usable.append(r)
    for name, pred in PATTERNS:
        cnt = {"all": [0, 0], "2-5": [0, 0], "5-10": [0, 0], "10+": [0, 0]}
        for r in usable:
            tok, tr, pk, m = r["token"], int(r["trough_hour"]), float(r["peak_px"]), float(r["multiple"])
            hit = con.execute(f"""select count(*) from panel where token = ? and hour between ? and ?
                                  and price <= ? and ({pred})""", [tok, tr - 86400, tr + 43200, pk / 2]).fetchone()[0] > 0
            k = "2-5" if m < 5 else "5-10" if m < 10 else "10+"
            for key in ("all", k):
                cnt[key][0] += hit
                cnt[key][1] += 1
        cell = lambda c: f"{c[0]}/{c[1]} ({100 * c[0] / c[1]:.0f}%)" if c[1] else "—"
        lines.append(f"| {name} | {cell(cnt['all'])} | {cell(cnt['2-5'])} | {cell(cnt['5-10'])} | {cell(cnt['10+'])} |")
    text = "\n".join(lines) + "\n"
    (ROOT / "data/research/recall.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
