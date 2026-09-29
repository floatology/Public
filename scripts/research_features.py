#!/usr/bin/env python3
"""Per token-hour features for the 2x search — no lookahead.

Everything in `feat` at hour h uses trades with ts < h + 3600 (i.e. up to the
end of hour h) and outcomes are measured from the NEXT hour's VWAP, so a
signal that fires at the end of hour h can actually be acted on.

Features:
  age_h                hours since the token's first trade
  vol_6h, vol_24h, vol_prev48  $ volume (last 6h, last 24h, the 48h before the last 6h)
  vol_rate72           mean hourly $ volume over the 72h before the last 6h
  surge6               vol_6h / (6 * vol_rate72)
  newb_6h, newb_rate72, newb_surge   first-time buyers, same construction
  r_24, r_72           price now / price 24h, 72h ago
  dd_7d                price / max price over the last 7d
  up_from_low72        price / min price over the last 72h
  big_buy_6h           $ in single buys >= $1k over the last 6h
  bundle_6h            share of first-time buyers in the last 6h that bought in the
                       same block as another first-time buyer (same token)
  smart_n_6h           distinct wallets net-buying >= $100 in the last 6h that
                       had caught >= 2 earlier legs early (legs confirmed before
                       their buy, any other token) — raw count
  smart_q_6h           same, but only wallets whose catch rate (catches / tokens
                       traded before the buy) is >= 0.25
Outcomes joined from fwd_order at hour h+1: run2x_72, run2x_168, crash_168.
"""
from __future__ import annotations

import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/research/cache/rd.duckdb"


def main() -> None:
    con = duckdb.connect(str(DB))
    con.execute("SET enable_progress_bar=false")

    # legs and their confirmation hour (first hour at >= 2x trough)
    legs = list(csv.DictReader(open(ROOT / "data/research/events.csv")))
    con.execute("create or replace table legs (token varchar, trough bigint, peak bigint, mult double)")
    con.executemany("insert into legs values (?, ?, ?, ?)",
                    [(r["token"], int(r["trough_hour"]), int(r["peak_hour"]), float(r["multiple"])) for r in legs])
    con.execute("""
        create or replace table legs_c as
        select l.*, (select min(h.hour) from hourly h where h.token = l.token and h.hour > l.trough
                     and h.hour <= l.peak and h.price >= 2 * (select price from hourly x
                         where x.token = l.token and x.hour = l.trough)) + 3600 as confirm
        from legs l
    """)
    # early entrants: net buyers from 24h before to 6h after each trough
    con.execute("""
        create or replace table early as
        select l.token, l.trough, l.confirm, t.trader
        from legs_c l join trades t on t.token = l.token
          and t.ts between l.trough - 86400 and l.trough + 21600
        where t.trader is not null
        group by 1, 2, 3, 4
        having sum(case when t.side = 'buy' then t.usd else -t.usd end) > 100
    """)
    print("early entrants:", con.execute("select count(*), count(distinct trader) from early").fetchone(), flush=True)

    # per wallet-token-hour net buying, then prior catches / tokens-traded at that time
    con.execute("""
        create or replace table wbuy as
        select token, trader, (ts // 3600) * 3600 as hour,
               sum(case when side = 'buy' then usd else -usd end) as net, min(ts) as ts0
        from trades where trader is not null
        group by 1, 2, 3 having net >= 100
    """)
    con.execute("""
        create or replace table wbuy_s as
        select w.token, w.trader, w.hour,
               (select count(*) from early e where e.trader = w.trader and e.token <> w.token
                  and e.confirm <= w.hour) as catches,
               (select count(*) from first_seen f where f.trader = w.trader and f.token <> w.token
                  and f.first_ts < w.hour) as ntok
        from wbuy w
    """)
    print("wallet-hours:", con.execute("select count(*), sum((catches>=2)::int) from wbuy_s").fetchone(), flush=True)
    con.execute("""
        create or replace table smart_h as
        select token, hour,
               count(distinct case when catches >= 2 then trader end) as smart_n,
               count(distinct case when catches >= 2 and catches >= 0.25 * ntok then trader end) as smart_q
        from wbuy_s group by 1, 2
    """)

    # bundled first-time buyers per token-hour
    con.execute("""
        create or replace table newb as
        select t.token, t.trader, t.block, (t.ts // 3600) * 3600 as hour
        from trades t join first_seen f on f.token = t.token and f.trader = t.trader and f.first_ts = t.ts
        where t.side = 'buy'
    """)
    con.execute("""
        create or replace table bundle_h as
        with blk as (select token, block, count(distinct trader) as k from newb group by 1, 2)
        select n.token, n.hour, count(distinct n.trader) as newb,
               count(distinct case when b.k > 1 then n.trader end) as bundled
        from newb n join blk b using (token, block) group by 1, 2
    """)

    con.execute("""
        create or replace table feat as
        with base as (
            select h.*, s.smart_n, s.smart_q, b.newb as nb_b, b.bundled,
                   min(hour) over (partition by token) as h0
            from hourly h
            left join smart_h s using (token, hour)
            left join bundle_h b using (token, hour)
        )
        select token, hour, price, vol,
          (hour - h0) / 3600 as age_h,
          sum(vol) over w6 as vol_6h,
          sum(vol) over w24 as vol_24h,
          sum(vol) over wp48 as vol_prev48,
          sum(vol) over wp72 / 72.0 as vol_rate72,
          sum(n_new_buyers) over w6 as newb_6h,
          sum(n_new_buyers) over wp72 / 72.0 as newb_rate72,
          sum(big_buy_usd) over w6 as big_buy_6h,
          price / nullif(lag(price, 24) over (partition by token order by hour), 0) as r_24,
          price / nullif(lag(price, 72) over (partition by token order by hour), 0) as r_72,
          price / nullif(max(price) over w168, 0) as dd_7d,
          price / nullif(min(price) over w72, 0) as up_from_low72,
          coalesce(sum(bundled) over w6, 0) * 1.0 / nullif(sum(nb_b) over w6, 0) as bundle_6h,
          coalesce(sum(nb_b) over w6, 0) as nb_6h,
          coalesce(sum(smart_n) over w6, 0) as smart_n_6h,
          coalesce(sum(smart_q) over w6, 0) as smart_q_6h
        from base
        window w6   as (partition by token order by hour rows between 5 preceding and current row),
               w24  as (partition by token order by hour rows between 23 preceding and current row),
               wp48 as (partition by token order by hour rows between 53 preceding and 6 preceding),
               wp72 as (partition by token order by hour rows between 77 preceding and 6 preceding),
               w72  as (partition by token order by hour rows between 71 preceding and current row),
               w168 as (partition by token order by hour rows between 167 preceding and current row)
    """)
    con.execute("""
        create or replace table panel as
        select f.*, f.vol_6h / nullif(6 * f.vol_rate72, 0) as surge6,
               f.newb_6h / nullif(6 * f.newb_rate72, 0) as newb_surge,
               o.run2x_72, o.run2x_168, o.crash_168, o.hours_to_2x
        from feat f join fwd_order o on o.token = f.token and o.hour = f.hour + 3600
    """)
    print(con.execute("""select count(*), avg(run2x_72::int), avg(run2x_168::int),
                         avg(case when age_h >= 48 then run2x_72::int end) from panel""").fetchone())
    con.close()


if __name__ == "__main__":
    main()
