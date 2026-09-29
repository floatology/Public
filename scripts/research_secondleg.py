#!/usr/bin/env python3
"""Second-leg hypothesis: coins that already ran once, faded, and re-ignite.

Case studies showed many tokens with several big legs (HOODRAT, JUGGERNAUT,
KITSU, INJOH, GIWA, WOJAK, TAMPONS, TYGR ...). A coin that has already drawn
a crowd once may be likelier to run again than a random coin.

Adds to `panel`:
  prior_mult     largest leg multiple among legs whose PEAK is >= 24h before
                 hour t and within the last 30 days (known at t)
  from_peak      price now / that leg's peak price
Then evaluates second-leg conditions with research_eval's method.
Writes data/research/secondleg.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_eval as ev  # noqa: E402

DB = ROOT / "data/research/cache/rd.duckdb"


def main() -> None:
    con = duckdb.connect(str(DB))
    con.execute("SET enable_progress_bar=false")
    con.execute(f"""
        create or replace table legs_pk as
        select e.token, e.trough_hour as trough, e.peak_hour as peak, e.multiple as mult, h.price as peak_px
        from read_csv_auto('{ROOT / "data/research/events.csv"}') e
        join hourly h on h.token = e.token and h.hour = e.peak_hour
    """)
    con.execute("""
        create or replace table panel_sl as
        select p.*,
               (select max(l.mult) from legs_pk l where l.token = p.token
                  and l.peak <= p.hour - 86400 and l.peak >= p.hour - 30 * 86400) as prior_mult,
               p.price / nullif((select max(l.peak_px) from legs_pk l where l.token = p.token
                  and l.peak <= p.hour - 86400 and l.peak >= p.hour - 30 * 86400 and l.mult >= 3), 0) as from_peak
        from panel p
    """)
    con.execute("drop table panel")
    con.execute("alter table panel_sl rename to panel")
    con.close()

    s = "surge6 >= 5 and vol_6h >= 5000"
    ev.CONDS = [
        ("all established (base)", "true"),
        ("had a >= 3x leg in last 30d", "prior_mult >= 3"),
        ("had a >= 5x leg in last 30d", "prior_mult >= 5"),
        ("no 2x leg in last 30d", "prior_mult is null"),
        (">=3x leg, now <= 0.5 of its peak", "prior_mult >= 3 and from_peak <= 0.5"),
        (">=3x leg, now <= 0.3 of its peak", "prior_mult >= 3 and from_peak <= 0.3"),
        (">=3x leg, <= 0.5 of peak, + surge5", f"prior_mult >= 3 and from_peak <= 0.5 and {s}"),
        (">=3x leg, <= 0.5 of peak, + breadth6 >= 0.3", "prior_mult >= 3 and from_peak <= 0.5 and breadth_6h >= 0.3 and active_6h >= 20"),
        (">=3x leg, <= 0.5 of peak, +20% off 72h low", "prior_mult >= 3 and from_peak <= 0.5 and up_from_low72 >= 1.2"),
        (">=5x leg, <= 0.4 of peak, + surge5", f"prior_mult >= 5 and from_peak <= 0.4 and {s}"),
        ("no prior leg + surge5", f"prior_mult is null and {s}"),
    ]
    sys.argv = [sys.argv[0], "--out", str(ROOT / "data/research/secondleg.md")]
    ev.main()


if __name__ == "__main__":
    main()
