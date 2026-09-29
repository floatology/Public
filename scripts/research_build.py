#!/usr/bin/env python3
"""Build the research database: every archived trade, hourly bars, forward outcomes.

Reads every data/tokens/<token>/ledger.parquet into one DuckDB table (`trades`,
with a `token` column), then builds `hourly`: one row per token-hour from the
token's first trade to its last, gap hours filled with zero volume and the last
price carried forward.

Price per hour is the trade-weighted VWAP of priced trades, not the last print:
thin pools print single-fill wicks nobody could trade (docs/25, trap 2), and
a VWAP of real fills is the price a buyer could have had.

Forward outcomes per token-hour (`fwd`), all from later hours only:
  max_72 / max_168   max VWAP in the next 72 / 168 hours, as a multiple of now
  min_72 / min_168   same for the minimum
  run2x_72, run2x_168  max >= 2
  crash_72, crash_168  min <= 0.5 before any 2x
Writes data/research/cache/rd.duckdb (not committed; rebuildable).
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data/research/cache/rd.duckdb"


def main() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("SET enable_progress_bar=false")
    glob = str(ROOT / "data/tokens/0x*/ledger.parquet")

    print("trades ...", flush=True)
    con.execute(f"""
        create or replace table trades as
        select regexp_extract(filename, '0x[0-9a-f]{{40}}') as token,
               ts, block, tx_hash, trader, side, tokens, usd, price_usd,
               pos_before, pos_after, n_trade
        from read_parquet('{glob}', filename=true, union_by_name=true)
        where usd is not null and usd > 0
    """)
    n = con.execute("select count(*), count(distinct token) from trades").fetchone()
    print(f"  {n[0]:,} trades, {n[1]} tokens", flush=True)

    print("first-seen per wallet-token ...", flush=True)
    con.execute("""
        create or replace table first_seen as
        select token, trader, min(ts) as first_ts
        from trades where trader is not null group by 1, 2
    """)

    print("hourly bars ...", flush=True)
    con.execute("""
        create or replace table bars_raw as
        select t.token, (t.ts // 3600) * 3600 as hour,
               sum(case when t.price_usd > 0 then t.usd end)
                 / nullif(sum(case when t.price_usd > 0 then t.usd / t.price_usd end), 0) as vwap,
               sum(t.usd) as vol,
               sum(case when t.side = 'buy' then t.usd else 0 end) as buy_usd,
               sum(case when t.side = 'sell' then t.usd else 0 end) as sell_usd,
               count(*) as n_trades,
               count(distinct case when t.side = 'buy' then t.trader end) as n_buyers,
               count(distinct case when t.side = 'sell' then t.trader end) as n_sellers,
               count(distinct case when t.side = 'buy' and f.first_ts >= (t.ts // 3600) * 3600
                                   then t.trader end) as n_new_buyers,
               sum(case when t.side = 'buy' and f.first_ts >= (t.ts // 3600) * 3600
                        then t.usd else 0 end) as new_buy_usd,
               sum(case when t.side = 'buy' and t.usd >= 1000 then t.usd else 0 end) as big_buy_usd,
               sum(case when t.side = 'sell' and t.usd >= 1000 then t.usd else 0 end) as big_sell_usd
        from trades t
        left join first_seen f on f.token = t.token and f.trader = t.trader
        group by 1, 2
    """)

    # Archive coverage end per token (meta.json updated_at). A token that stops
    # trading is still covered until then: its hours run on, flat and empty, so
    # a dead coin scores as "no 2x" instead of silently dropping out, and hours
    # whose 7-day forward window runs past coverage can be excluded (censoring).
    import datetime as dt
    import json
    cov = []
    for m in (ROOT / "data/tokens").glob("0x*/meta.json"):
        u = json.loads(m.read_text()).get("updated_at")
        if u:
            ts = int(dt.datetime.fromisoformat(u.replace("Z", "+00:00")).timestamp())
            cov.append((m.parent.name, (ts // 3600) * 3600))
    con.execute("create or replace table cov_end (token varchar, cov_end bigint)")
    con.executemany("insert into cov_end values (?, ?)", cov)

    # Fill every hour in each token's life; carry price forward over empty hours.
    con.execute("""
        create or replace table hourly as
        with span as (
            select b.token, min(b.hour) as h0, greatest(max(b.hour), coalesce(max(c.cov_end), 0)) as h1
            from bars_raw b left join cov_end c using (token) group by 1
        ), grid as (
            select s.token, g.hour
            from span s, generate_series(s.h0, s.h1, 3600) as g(hour)
        ), j as (
            select g.token, g.hour, b.vwap, coalesce(b.vol, 0) as vol,
                   coalesce(b.buy_usd, 0) as buy_usd, coalesce(b.sell_usd, 0) as sell_usd,
                   coalesce(b.n_trades, 0) as n_trades, coalesce(b.n_buyers, 0) as n_buyers,
                   coalesce(b.n_sellers, 0) as n_sellers, coalesce(b.n_new_buyers, 0) as n_new_buyers,
                   coalesce(b.new_buy_usd, 0) as new_buy_usd,
                   coalesce(b.big_buy_usd, 0) as big_buy_usd, coalesce(b.big_sell_usd, 0) as big_sell_usd
            from grid g left join bars_raw b using (token, hour)
        )
        select *, last_value(vwap ignore nulls) over (
                     partition by token order by hour rows between unbounded preceding and current row) as price
        from j
    """)
    n = con.execute("select count(*) from hourly").fetchone()[0]
    print(f"  {n:,} token-hours", flush=True)

    print("forward outcomes ...", flush=True)
    con.execute("""
        create or replace table fwd as
        select token, hour, price,
          max(price) over w72  / price as max_72,
          min(price) over w72  / price as min_72,
          max(price) over w168 / price as max_168,
          min(price) over w168 / price as min_168
        from hourly
        where price > 0
        window w72  as (partition by token order by hour range between 3600 following and 259200 following),
               w168 as (partition by token order by hour range between 3600 following and 604800 following)
    """)
    # crash-before-2x needs order within the window: first hour hitting 2x vs first hitting 0.5x.
    con.execute("""
        create or replace table fwd_order as
        with pairs as (
            select a.token, a.hour,
                   min(case when b.price >= 2 * a.price then b.hour end) as t2x,
                   min(case when b.price <= 0.5 * a.price then b.hour end) as thalf
            from hourly a join hourly b
              on b.token = a.token and b.hour > a.hour and b.hour <= a.hour + 604800
            where a.price > 0 and b.price > 0
            group by 1, 2
        )
        select token, hour,
               hour + 604800 <= (select coalesce(max(c.cov_end), 0) from cov_end c where c.token = pairs.token)
                 as complete,
               (t2x is not null and t2x <= hour + 259200) as run2x_72,
               (t2x is not null) as run2x_168,
               (thalf is not null and thalf <= hour + 259200 and (t2x is null or thalf < t2x)) as crash_72,
               (thalf is not null and (t2x is null or thalf < t2x)) as crash_168,
               (t2x - hour) / 3600 as hours_to_2x
        from pairs
    """)
    print(con.execute("""
        select count(*), avg(run2x_72::int), avg(run2x_168::int), avg(crash_168::int) from fwd_order
    """).fetchone())
    con.close()


if __name__ == "__main__":
    sys.exit(main())
