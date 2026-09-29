#!/usr/bin/env python3
"""Second feature pass: market regime, profit-based smart wallets, buyer breadth.

Adds to `panel` (in place), all computed from data before the signal hour:

  heat_d           market regime from the daily-candle universe: among tokens
                   with >= $1k volume that day, the share whose close is >= 1.5x
                   the close 3 days earlier, averaged over the 3 days ending
                   YESTERDAY (so it is known at any hour of today)
  pro_n_6h         distinct wallets net-buying >= $250 in the last 6h whose
                   realised profit on OTHER tokens, before that hour, is >= $5k
  pro_big_6h       same with realised profit >= $25k
  breadth_6h       (wallets net-buying - wallets net-selling) / (both), last 6h,
                   wallets with |net| >= $50
  breadth_24h      same over 24h
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
DB = ROOT / "data/research/cache/rd.duckdb"


def market_heat() -> dict[int, float]:
    from candle_backtest import build_series
    series = build_series()
    up = defaultdict(int)
    act = defaultdict(int)
    for s in series.values():
        seq = s["seq"]
        for i in range(3, len(seq)):
            if seq[i]["vol"] < 1000 or not seq[i - 3]["c"]:
                continue
            act[seq[i]["d"]] += 1
            if seq[i]["c"] >= 1.5 * seq[i - 3]["c"]:
                up[seq[i]["d"]] += 1
    daily = {d: up[d] / act[d] for d in act if act[d] >= 20}
    heat = {}
    for d in daily:
        prev = [daily[x] for x in (d - 1, d - 2, d - 3) if x in daily]
        if prev:
            heat[d] = sum(prev) / len(prev)
    return heat


def main() -> None:
    heat = market_heat()
    con = duckdb.connect(str(DB))
    con.execute("SET enable_progress_bar=false")
    con.execute("create or replace table heat (day bigint, heat_d double)")
    con.executemany("insert into heat values (?, ?)", list(heat.items()))
    print("heat days:", len(heat), flush=True)

    glob = str(ROOT / "data/tokens/0x*/ledger.parquet")
    con.execute(f"""
        create or replace table real as
        select regexp_extract(filename, '0x[0-9a-f]{{40}}') as token, trader, ts, realised_usd
        from read_parquet('{glob}', filename=true, union_by_name=true)
        where trader is not null and realised_usd is not null and realised_usd <> 0
    """)
    # realised profit per wallet-token-hour, then cumulative per wallet over time
    con.execute("""
        create or replace table real_h as
        select trader, token, (ts // 3600) * 3600 as hour, sum(realised_usd) as r
        from real group by 1, 2, 3
    """)
    con.execute("""
        create or replace table wbuy2 as
        select token, trader, hour, net from wbuy where net >= 250
    """)
    # prior realised profit on other tokens: total prior - prior on this token
    con.execute("""
        create or replace table wpro as
        with tot as (
            select b.token, b.trader, b.hour,
                   coalesce(sum(r.r), 0) as prior_all,
                   coalesce(sum(case when r.token = b.token then r.r end), 0) as prior_same
            from wbuy2 b left join real_h r on r.trader = b.trader and r.hour < b.hour
            group by 1, 2, 3
        )
        select token, trader, hour, prior_all - prior_same as prior_other from tot
    """)
    con.execute("""
        create or replace table pro_h as
        select token, hour,
               count(distinct case when prior_other >= 5000 then trader end) as pro_n,
               count(distinct case when prior_other >= 25000 then trader end) as pro_big
        from wpro group by 1, 2
    """)
    print("pro wallet-hours:", con.execute(
        "select sum(pro_n), sum(pro_big) from pro_h").fetchone(), flush=True)

    # buyer breadth: wallet net over trailing windows, via wallet-hour nets
    con.execute("""
        create or replace table wnet_h as
        select token, trader, (ts // 3600) * 3600 as hour,
               sum(case when side = 'buy' then usd else -usd end) as net
        from trades where trader is not null group by 1, 2, 3
    """)
    for w in (6, 24):
        con.execute(f"""
            create or replace table breadth_{w} as
            with g as (
                select h.token, h.hour, n.trader, sum(n.net) as net
                from hourly h join wnet_h n on n.token = h.token
                  and n.hour between h.hour - {(w - 1) * 3600} and h.hour
                group by 1, 2, 3
            )
            select token, hour,
                   (count(*) filter (where net >= 50) - count(*) filter (where net <= -50)) * 1.0
                   / nullif(count(*) filter (where abs(net) >= 50), 0) as breadth,
                   count(*) filter (where abs(net) >= 50) as n_active
            from g group by 1, 2
        """)
        print(f"breadth_{w} done", flush=True)

    con.execute("""
        create or replace table panel_new as
        select p.*, ht.heat_d,
               coalesce((select sum(pro_n) from pro_h x where x.token = p.token
                         and x.hour between p.hour - 18000 and p.hour), 0) as pro_n_6h,
               coalesce((select sum(pro_big) from pro_h x where x.token = p.token
                         and x.hour between p.hour - 18000 and p.hour), 0) as pro_big_6h,
               b6.breadth as breadth_6h, b6.n_active as active_6h,
               b24.breadth as breadth_24h, b24.n_active as active_24h
        from panel p
        left join heat ht on ht.day = p.hour // 86400
        left join breadth_6 b6 on b6.token = p.token and b6.hour = p.hour
        left join breadth_24 b24 on b24.token = p.token and b24.hour = p.hour
    """)
    con.execute("drop table panel")
    con.execute("alter table panel_new rename to panel")
    print(con.execute("""select count(*), avg(heat_d), avg((pro_n_6h>0)::int), avg(breadth_6h)
                         from panel where age_h >= 48""").fetchone())
    con.close()


if __name__ == "__main__":
    main()
