#!/usr/bin/env python3
"""Daily-candle universe test of the patterns found in the hourly ledger study.

Uses scripts/candle_backtest.py's token series (every GeckoTerminal-tracked
token, delisted census coins included). Signal at the close of day i uses
only days <= i; outcomes from day i's close: run2x within 3 and 7 days, crash
(<= 0.5x) before any 2x within 7 days, on closes.

Patterns:
  wake(Q, X, Y)   the Q days before day i each had < $X volume, and day i had >= $Y
  surge(M, Y)     day i volume >= M x the median of the 14 days before, and >= $Y
Each result is compared with the base rate of token-days with the same
day-i volume bucket and token age >= 3 days, and split by time and token.
"""
from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from candle_backtest import build_series  # noqa: E402

VOL_EDGES = [0, 1e3, 5e3, 2e4, 1e5, 5e5, float("inf")]


def vb(v: float) -> int:
    for k in range(len(VOL_EDGES) - 1):
        if VOL_EDGES[k] <= v < VOL_EDGES[k + 1]:
            return k
    return len(VOL_EDGES) - 2


def outcome(seq, i):
    c0 = seq[i]["c"]
    if not c0 or i + 7 >= len(seq):
        return None
    cl = [s["c"] / c0 for s in seq[i + 1:i + 8] if s["c"]]
    if not cl:
        return None
    r3 = max(cl[:3]) >= 2
    r7 = max(cl) >= 2
    crash = False
    for r in cl:
        if r >= 2:
            break
        if r <= 0.5:
            crash = True
            break
    return r3, r7, crash


def half(tok):
    return int(hashlib.md5(tok.encode()).hexdigest(), 16) % 2


def main() -> None:
    series = build_series()
    rows = []   # (tok, day, age, vol_i, vol list prior 14, median14, r3, r7, crash)
    for tok, s in series.items():
        seq = s["seq"]
        for i in range(3, len(seq)):
            o = outcome(seq, i)
            if o is None:
                continue
            prior = [x["vol"] for x in seq[max(0, i - 14):i]]
            med = sorted(prior)[len(prior) // 2] if prior else 0
            rows.append((tok, seq[i]["d"], i, seq[i]["vol"], [x["vol"] for x in seq[max(0, i - 7):i]],
                         med, *o, seq[i]["c"], max(x["c"] or 0 for x in seq[max(0, i - 30):i + 1])))
    base = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        b = base[vb(r[3])]
        b[0] += r[6]; b[1] += r[7]; b[2] += 1
    days = sorted(r[1] for r in rows)
    mid = days[len(days) // 2]
    print(f"{len(rows):,} token-days (age>=3d, 7d forward), {len(series)} tokens, time split day {mid}")
    print("base by day-volume bucket (2x in 3d / 7d):",
          {k: (round(v[0] / v[2], 3), round(v[1] / v[2], 3), v[2]) for k, v in sorted(base.items())})

    def evaluate(name, pred):
        ev, last = [], {}
        for r in rows:
            if not pred(r):
                continue
            if r[0] in last and r[1] - last[r[0]] < 7:
                continue
            last[r[0]] = r[1]
            ev.append(r)
        if not ev:
            print(f"| {name} | 0 |"); return

        def st(sub):
            if not sub:
                return "—"
            h = sum(x[6] for x in sub) / len(sub)
            e = sum(base[vb(x[3])][0] / base[vb(x[3])][2] for x in sub) / len(sub)
            return f"{100 * h:.0f}% ({h / e:.1f}x, n={len(sub)})"
        n = len(ev)
        h3 = sum(x[6] for x in ev) / n
        h7 = sum(x[7] for x in ev) / n
        cr = sum(x[8] for x in ev) / n
        e3 = sum(base[vb(x[3])][0] / base[vb(x[3])][2] for x in ev) / n
        print(f"| {name} | {n} | {len({x[0] for x in ev})} | {100 * h3:.0f}% | {100 * h7:.0f}% | {100 * cr:.0f}% | "
              f"{h3 / e3:.2f}x | {st([x for x in ev if x[1] < mid])} | {st([x for x in ev if x[1] >= mid])} | "
              f"{st([x for x in ev if half(x[0]) == 0])} | {st([x for x in ev if half(x[0]) == 1])} |")

    print("\n| pattern | events | tokens | 2x 3d | 2x 7d | crash 7d | lift | time A | time B | tok A | tok B |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    evaluate("all token-days >= $1k", lambda r: r[3] >= 1000)
    for q in (2, 3, 5):
        for x in (200, 500, 1000):
            for y in (2000, 5000, 20000):
                evaluate(f"wake: {q}d < ${x}, then >= ${y}",
                         lambda r, q=q, x=x, y=y: len(r[4]) >= q and all(v < x for v in r[4][-q:]) and r[3] >= y)
    for m in (5, 10, 20, 50):
        for y in (5000, 20000):
            evaluate(f"surge: >= {m}x 14d median, >= ${y}",
                     lambda r, m=m, y=y: r[5] > 0 and r[3] >= m * r[5] and r[3] >= y)
    # wake-up where price is far below its 30-day high (a revival of a faded coin)
    for dd in (0.5, 0.25):
        evaluate(f"wake 3d<$500 then >=$5k, price <= {dd} of 30d high",
                 lambda r, dd=dd: len(r[4]) >= 3 and all(v < 500 for v in r[4][-3:]) and r[3] >= 5000
                 and r[10] and r[9] <= dd * r[10])


if __name__ == "__main__":
    main()
