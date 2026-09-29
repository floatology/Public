#!/usr/bin/env python3
"""Case-study digests for the biggest breakouts in established coins.

For each selected leg (data/research/events.csv, token age >= 48h at the trough):
  1. The lead-up, in 12-hour blocks from 72h before the trough to 12h after:
     price vs trough, volume, buy share, unique buyers, first-time buyers,
     $1k+ buys.
  2. The top net buyers from 72h before to 6h after the trough, each with:
     how long they had held/traded this token before, how many other tokens
     they have traded, and how many *earlier* 2x legs (confirmed before this
     trough) they were early into — the "smart wallet" question, no lookahead.
  3. Coordination: first-time buyers in the window that bought in the same
     block as another first-time buyer, and repeat-size buys.
Writes data/research/case_studies_raw.md.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/research/cache/rd.duckdb"
OUT = ROOT / "data/research/case_studies_raw.md"
EARLY_BEFORE, EARLY_AFTER = 24 * 3600, 6 * 3600


def fmt_t(ts: int) -> str:
    return dt.datetime.utcfromtimestamp(ts).strftime("%m-%d %H:00")


def build_leg_tables(con, legs: list[dict]) -> None:
    """legs: every >=2x leg, with the hour its 2x was first confirmed."""
    con.execute("create or replace temp table legs (token varchar, trough bigint, peak bigint, mult double, confirm bigint)")
    rows = []
    for r in legs:
        tok, tr, pk = r["token"], int(r["trough_hour"]), int(r["peak_hour"])
        c = con.execute("""select min(hour) from hourly where token = ? and hour > ? and hour <= ?
                           and price >= 2 * (select price from hourly where token = ? and hour = ?)""",
                        [tok, tr, pk, tok, tr]).fetchone()[0]
        rows.append((tok, tr, pk, float(r["multiple"]), c or pk))
    con.executemany("insert into legs values (?, ?, ?, ?, ?)", rows)
    # early entrants of each leg: net buyers from 24h before the trough to 6h after
    con.execute(f"""
        create or replace temp table early as
        select l.token, l.trough, l.confirm, l.mult, t.trader, sum(case when side='buy' then usd else -usd end) as net
        from legs l join trades t on t.token = l.token
          and t.ts between l.trough - {EARLY_BEFORE} and l.trough + {EARLY_AFTER}
        where t.trader is not null
        group by 1, 2, 3, 4, 5 having net > 100
    """)


def digest(con, leg: dict, out: list[str]) -> None:
    tok, sym = leg["token"], leg["symbol"]
    tr, pk = int(leg["trough_hour"]), int(leg["peak_hour"])
    out.append(f"\n## {sym} — {leg['multiple']}x in {leg['hours_to_peak']}h, trough {fmt_t(tr)} "
               f"(token age {leg['age_h_at_trough']}h)\n")
    out.append("| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |")
    out.append("|---|---|---|---|---|---|---|---|")
    trough_px = float(leg["trough_px"])
    for a in range(-72, 12 + 1, 12):
        b = a + 12
        r = con.execute("""select avg(price), sum(vol), sum(buy_usd), sum(n_buyers), sum(n_new_buyers),
                                  sum(new_buy_usd), sum(big_buy_usd)
                           from hourly where token = ? and hour >= ? and hour < ?""",
                        [tok, tr + a * 3600, tr + b * 3600]).fetchone()
        if r[1] is None:
            continue
        px, vol, buy, nb, nn, nbu, big = r
        out.append(f"| {a:+d}..{b:+d}h | {px / trough_px:.2f} | {vol:,.0f} | {100 * buy / vol if vol else 0:.0f}% "
                   f"| {nb} | {nn} | {nbu:,.0f} | {big:,.0f} |")

    lo, hi = tr - 72 * 3600, tr + 6 * 3600
    top = con.execute("""
        select trader, sum(case when side='buy' then usd else -usd end) as net, count(*) as n, min(ts) as first_in_win
        from trades where token = ? and ts between ? and ? and trader is not null
        group by 1 order by net desc limit 8
    """, [tok, lo, hi]).fetchall()
    out.append("\nTop net buyers, 72h before to 6h after the trough:\n")
    out.append("| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |")
    out.append("|---|---|---|---|---|---|---|")
    for w, net, n, _ in top:
        first = con.execute("select first_ts from first_seen where token = ? and trader = ?", [tok, w]).fetchone()[0]
        age_h = (tr - first) / 3600
        others = con.execute("select count(distinct token) from first_seen where trader = ? and token <> ?", [w, tok]).fetchone()[0]
        prior = con.execute("select count(*) from early where trader = ? and confirm < ? and not (token = ? and trough = ?)",
                            [w, tr, tok, tr]).fetchone()[0]
        sold = con.execute("""select sum(usd) from trades where token = ? and trader = ? and side = 'sell'
                              and ts between ? and ?""", [tok, w, tr, pk + 24 * 3600]).fetchone()[0] or 0
        seen = f"{age_h:+.0f}h before trough" if age_h >= 0 else f"{-age_h:.0f}h after trough"
        out.append(f"| {w[:6]}…{w[-4:]} | {net:,.0f} | {n} | {seen} | {others} | {prior} | ${sold:,.0f} |")

    # coordination among first-time buyers in the 72h before the trough
    r = con.execute("""
        with nb as (
            select t.trader, t.block, t.usd from trades t join first_seen f
              on f.token = t.token and f.trader = t.trader and f.first_ts = t.ts
            where t.token = ? and t.side = 'buy' and t.ts between ? and ?
        )
        select count(distinct trader),
               count(distinct case when block in (select block from nb group by block having count(distinct trader) > 1)
                                   then trader end),
               count(distinct case when round(usd, 0) in (select round(usd, 0) from nb group by 1 having count(*) >= 3)
                                   then trader end)
        from nb
    """, [tok, lo, tr]).fetchone()
    out.append(f"\nFirst-time buyers in the 72h before: {r[0]}; sharing a block with another first-timer: {r[1]}; "
               f"same-size (rounded $) as 2+ others: {r[2]}.")


def main() -> None:
    con = duckdb.connect(str(DB))
    con.execute("SET enable_progress_bar=false")
    legs = list(csv.DictReader(open(ROOT / "data/research/events.csv")))
    build_leg_tables(con, legs)
    est = [r for r in legs if int(r["age_h_at_trough"]) >= 48]
    est.sort(key=lambda r: -float(r["multiple"]))
    picked, seen = [], set()
    for r in est:  # biggest leg per token first, then second legs, up to 14 cases
        if r["token"] in seen:
            continue
        seen.add(r["token"])
        picked.append(r)
        if len(picked) == 14:
            break
    out = ["# Case studies — raw digests (scripts/research_cases.py)\n",
           "Blocks are 12h windows relative to the trough hour; 'px vs trough' is the average hourly VWAP "
           "in the block over the trough VWAP. 'Earlier 2x legs caught early' counts other legs (any token) "
           "whose 2x was confirmed before this trough where the wallet net-bought within 24h before to 6h "
           "after that leg's trough."]
    for leg in picked:
        digest(con, leg, out)
    OUT.write_text("\n".join(out) + "\n")
    print(f"{len(picked)} cases -> {OUT}")


if __name__ == "__main__":
    main()
