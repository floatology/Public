#!/usr/bin/env python3
"""Evaluate candidate 2x signals on the token-hour panel, honestly.

For each condition (a SQL predicate on `panel`), over established coins
(age >= 48h) unless the condition says otherwise:
  fires      token-hours where the condition is true
  events     de-duplicated: first firing per token, then none for 72h
  tokens     distinct tokens with an event
  hit72/hit7d  share of events followed by a 2x (from the next hour's VWAP)
               within 72h / 7 days
  crash7d    share of events that halve before any 2x within 7 days
  lift       hit72 / the rate expected for the same age x 24h-volume buckets
  time A/B, token A/B   hit72 (and lift) on each half, split by time (median
               hour) and by token (hash parity) — a real signal holds on both.
Usage: research_eval.py [--launch] [--out FILE] [--extra "name|predicate" ...]
"""
from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/research/cache/rd.duckdb"

CONDS = [
    ("all established (base)", "true"),
    ("A dormant wake-up: prev48 < $500, last 6h >= $2k", "vol_prev48 < 500 and vol_6h >= 2000"),
    ("A2 quiet wake-up: prev48 < $2k, last 6h >= $5k", "vol_prev48 < 2000 and vol_6h >= 5000"),
    ("B volume surge >= 5x (6h >= $5k)", "surge6 >= 5 and vol_6h >= 5000"),
    ("B volume surge >= 10x (6h >= $5k)", "surge6 >= 10 and vol_6h >= 5000"),
    ("B volume surge >= 20x (6h >= $5k)", "surge6 >= 20 and vol_6h >= 5000"),
    ("C new-wallet surge >= 5x (>= 20 new)", "newb_surge >= 5 and newb_6h >= 20"),
    ("C new-wallet surge >= 10x (>= 50 new)", "newb_surge >= 10 and newb_6h >= 50"),
    ("D pullback reversal: <= 0.7 of 7d high, +20% off 72h low", "dd_7d <= 0.7 and up_from_low72 >= 1.2"),
    ("D2 deep pullback reversal: <= 0.5 of 7d high, +30% off low", "dd_7d <= 0.5 and up_from_low72 >= 1.3"),
    ("E smart wallets >= 1 (6h)", "smart_n_6h >= 1"),
    ("E smart wallets >= 3", "smart_n_6h >= 3"),
    ("E smart wallets >= 5", "smart_n_6h >= 5"),
    ("E smart wallets >= 10", "smart_n_6h >= 10"),
    ("E quality smart >= 1", "smart_q_6h >= 1"),
    ("E quality smart >= 2", "smart_q_6h >= 2"),
    ("E quality smart >= 3", "smart_q_6h >= 3"),
    ("F bundled new buyers >= 15% (>= 20 new)", "bundle_6h >= 0.15 and nb_6h >= 20"),
    ("F bundled new buyers >= 25% (>= 20 new)", "bundle_6h >= 0.25 and nb_6h >= 20"),
    ("M momentum: +50% in 24h", "r_24 >= 1.5"),
    ("M momentum: +100% in 24h", "r_24 >= 2"),
    ("G A + new-wallet surge", "vol_prev48 < 2000 and vol_6h >= 5000 and newb_surge >= 5"),
    ("G surge10 + bundled", "surge6 >= 10 and vol_6h >= 5000 and bundle_6h >= 0.15 and nb_6h >= 20"),
    ("G surge10 + smart>=3", "surge6 >= 10 and vol_6h >= 5000 and smart_n_6h >= 3"),
    ("G pullback reversal + surge5", "dd_7d <= 0.7 and up_from_low72 >= 1.2 and surge6 >= 5 and vol_6h >= 5000"),
    ("G pullback reversal + smart>=3", "dd_7d <= 0.7 and up_from_low72 >= 1.2 and smart_n_6h >= 3"),
    ("G new-wallet surge + smart q>=2", "newb_surge >= 5 and newb_6h >= 20 and smart_q_6h >= 2"),
]

AGE_EDGES = [48, 168, 720, 10**9]
VOL_EDGES = [0, 1e3, 1e4, 5e4, 2.5e5, 1e6, float("inf")]


def bucket(x: float, edges: list[float]) -> int:
    for k in range(len(edges) - 1):
        if edges[k] <= x < edges[k + 1]:
            return k
    return len(edges) - 2


def tok_half(tok: str) -> int:
    return int(hashlib.md5(tok.encode()).hexdigest(), 16) % 2


def dedup(rows: list[tuple]) -> list[tuple]:
    """rows sorted by token, hour -> first firing per token then a 72h cool-off."""
    out, last = [], {}
    for r in rows:
        tok, hour = r[0], r[1]
        if tok in last and hour - last[tok] < 72 * 3600:
            continue
        last[tok] = hour
        out.append(r)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--launch", action="store_true", help="tokens younger than 48h instead")
    ap.add_argument("--out", default=str(ROOT / "data/research/eval.md"))
    ap.add_argument("--extra", nargs="*", default=[])
    a = ap.parse_args()
    con = duckdb.connect(str(DB), read_only=True)
    con.execute("SET enable_progress_bar=false")
    universe = "age_h < 48" if a.launch else "age_h >= 48"
    conds = CONDS + [tuple(x.split("|", 1)) for x in a.extra]

    base_rows = con.execute(f"""select token, hour, age_h, coalesce(vol_24h,0), run2x_72::int, run2x_168::int,
                                crash_168::int from panel where {universe}""").fetchall()
    rate = defaultdict(lambda: [0, 0])
    for tok, hour, age, v24, r72, *_ in base_rows:
        k = (bucket(age, AGE_EDGES) if not a.launch else 0, bucket(v24, VOL_EDGES))
        rate[k][0] += r72
        rate[k][1] += 1
    hours = sorted(r[1] for r in base_rows)
    mid = hours[len(hours) // 2]

    lines = [f"# Signal evaluation — {'launch window (<48h)' if a.launch else 'established coins (age >= 48h)'}\n",
             f"Panel: {len(base_rows):,} token-hours; time split at "
             f"{__import__('datetime').datetime.utcfromtimestamp(mid):%m-%d %H:00}.\n",
             "| signal | fires | events | tokens | hit72 | hit7d | crash7d | lift | time A | time B | tokens A | tokens B |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, pred in conds:
        rows = con.execute(f"""select token, hour, age_h, coalesce(vol_24h,0), run2x_72::int, run2x_168::int, crash_168::int
                               from panel where {universe} and ({pred}) order by token, hour""").fetchall()
        ev = dedup(rows)
        if not ev:
            lines.append(f"| {name} | 0 | | | | | | | | | | |")
            continue

        def stats(sub):
            if not sub:
                return "—"
            hit = sum(r[4] for r in sub) / len(sub)
            exp = sum(rate[(bucket(r[2], AGE_EDGES) if not a.launch else 0, bucket(r[3], VOL_EDGES))][0] /
                      max(1, rate[(bucket(r[2], AGE_EDGES) if not a.launch else 0, bucket(r[3], VOL_EDGES))][1])
                      for r in sub) / len(sub)
            return f"{100 * hit:.0f}% ({hit / exp:.1f}x, n={len(sub)})" if exp else f"{100 * hit:.0f}%"

        n = len(ev)
        hit72 = sum(r[4] for r in ev) / n
        hit7 = sum(r[5] for r in ev) / n
        crash = sum(r[6] for r in ev) / n
        exp = sum(rate[(bucket(r[2], AGE_EDGES) if not a.launch else 0, bucket(r[3], VOL_EDGES))][0] /
                  max(1, rate[(bucket(r[2], AGE_EDGES) if not a.launch else 0, bucket(r[3], VOL_EDGES))][1])
                  for r in ev) / n
        lines.append(
            f"| {name} | {len(rows):,} | {n} | {len({r[0] for r in ev})} | {100 * hit72:.0f}% | {100 * hit7:.0f}% | "
            f"{100 * crash:.0f}% | {hit72 / exp:.2f}x | {stats([r for r in ev if r[1] < mid])} | "
            f"{stats([r for r in ev if r[1] >= mid])} | {stats([r for r in ev if tok_half(r[0]) == 0])} | "
            f"{stats([r for r in ev if tok_half(r[0]) == 1])} |")
    text = "\n".join(lines) + "\n"
    Path(a.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
