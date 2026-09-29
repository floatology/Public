#!/usr/bin/env python3
"""Would the best signals actually make money? Trade simulation on hourly VWAP.

Entry at the NEXT hour's VWAP after the signal (de-duplicated: one trade per
token, then 72h before another). Exit rules, walked hour by hour on VWAP:
  TP 2x / SL -30% / 72h     take profit at 2x, stop at -30%, else exit at 72h
  TP 2x / SL -50% / 7d
  TP 3x / SL -40% / 7d
  hold 72h (no stops)
Stops are filled at the VWAP of the hour that breaches them (not at the stop
price), take-profits at exactly the target. A flat 4% round-trip cost is
deducted (fees plus slippage on thin pools). Reports trades, win rate (TP
reached), mean and median return per trade, share of losing trades, and total
return per $1 of trades (profit factor style).

Signals: surge10 + breadth, surge >= 20x, and the walk-forward model top 1% /
top 0.5% (ledger panel). Writes data/research/strategy.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_model as rm  # noqa: E402
from research_walkforward import walk  # noqa: E402

COST = 0.04
RULES = [("TP 2x / SL -30% / 72h", 2.0, 0.30, 72), ("TP 2x / SL -50% / 7d", 2.0, 0.50, 168),
         ("TP 3x / SL -40% / 7d", 3.0, 0.40, 168), ("hold 72h", None, None, 72)]


def sim(path, tp, sl, horizon):
    """path: prices after entry (entry = path[0]). Returns net return multiple - 1."""
    e = path[0]
    for p in path[1:horizon + 1]:
        if tp and p >= tp * e:
            return tp - 1 - COST
        if sl and p <= (1 - sl) * e:
            return p / e - 1 - COST
    last = path[min(horizon, len(path) - 1)]
    return last / e - 1 - COST


def main() -> None:
    con = duckdb.connect(str(rm.DB), read_only=True)
    con.execute("SET enable_progress_bar=false")
    price = {}
    for tok, hour, px in con.execute("select token, hour, price from hourly where price > 0 order by token, hour").fetchall():
        price.setdefault(tok, {})[hour] = px
    arr, X = rm.load(con)
    y = np.array(arr["y"])
    tok, hour = arr["token"], np.array(arr["hour"])
    p = walk(X, y, hour, step=7 * 86400, warm=21 * 86400)
    rules_sig = {}
    for name, pred in (("surge10 + breadth6 >= 0.3", "surge6 >= 10 and vol_6h >= 5000 and breadth_6h >= 0.3 and active_6h >= 20"),
                       ("surge >= 20x", "surge6 >= 20 and vol_6h >= 5000")):
        rules_sig[name] = con.execute(f"select token, hour from panel where age_h >= 48 and ({pred}) order by token, hour").fetchall()
    idx = np.where(~np.isnan(p))[0]
    order = idx[np.argsort(-p[idx])]
    for f in (0.005, 0.01, 0.02):
        sel = order[:int(f * len(idx))]
        rules_sig[f"model top {100 * f:g}% (walk-forward)"] = sorted((tok[i], int(hour[i])) for i in sel)

    lines = ["# Trade simulation — entry next hour, hourly VWAP path, 4% round-trip cost\n",
             "| signal | exit rule | trades | TP hit | mean | median | losing | total per $1 |",
             "|---|---|---|---|---|---|---|---|"]
    for sname, sig in rules_sig.items():
        trades, last = [], {}
        for t, h in sig:
            if t in last and h - last[t] < 72 * 3600:
                continue
            last[t] = h
            ph = price.get(t, {})
            path = [ph[x] for x in range(h + 3600, h + 3600 + 169 * 3600, 3600) if x in ph]
            if len(path) >= 24:
                trades.append(path)
        for rname, tp, sl, hz in RULES:
            r = np.array([sim(pth, tp, sl, hz) for pth in trades])
            if not len(r):
                continue
            tph = np.mean([max(pth[1:hz + 1]) >= (tp or 1e9) * pth[0] and
                           (sl is None or not any(q <= (1 - sl) * pth[0] for q in
                                                   pth[1:1 + next((k for k, q in enumerate(pth[1:hz + 1]) if q >= tp * pth[0]), hz)]))
                           for pth in trades]) if tp else float("nan")
            lines.append(f"| {sname} | {rname} | {len(r)} | {'' if tp is None else f'{100 * tph:.0f}%'} | "
                         f"{100 * r.mean():+.0f}% | {100 * np.median(r):+.0f}% | {100 * (r < 0).mean():.0f}% | "
                         f"{1 + r.mean():.2f} |")
    text = "\n".join(lines) + "\n"
    (ROOT / "data/research/strategy.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
