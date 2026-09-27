#!/usr/bin/env python3
"""Turn the raw pattern flags into a shortlist, using the filters the backtest supports.

The candle backtest flags every token whose last complete day shows the
pre-breakout SETUP or a BREAK. Unfiltered, most of those are dead coins firing
on noise, tokenized stocks, or caps far outside the range that was studied. The
filters below come from the survivor-corrected backtest (docs/25):

- SETUP or BREAK only. Single signals (dry, ignite, higher lows, coil) showed
  no edge once matched on activity.
- 7-day volume >= $10k: below it closes barely move and nothing is tradeable.
- 7-day volume <= $250k preferred: above it the crash rate exceeds the 2x rate.
  Coins above it are kept but marked HIGH-CHURN.
- Market cap $100k-$5M, the range asked about.
- Tokenized stocks and wrapped assets are dropped by name.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rhc.dexscreener import DexScreener

d = json.loads((ROOT / "data/overnight/live_screen.json").read_text())
cands = [x for x in d["live"] if ("SETUP" in x["signals"] or "BREAK" in x["signals"])
         and (x["vol7"] or 0) >= 1e4 and x["mcap"] and 1e5 <= x["mcap"] <= 5e6]
ds = DexScreener()
names = {}
for pair in ds.pairs_for_tokens([c["token"] for c in cands]):
    names[pair["baseToken"]["address"].lower()] = (pair["baseToken"].get("name") or "",
                                                  (pair.get("liquidity") or {}).get("usd"))
out = []
for c in cands:
    nm, liq = names.get(c["token"], ("", None))
    if nm.lower().endswith("robinhood token") or c["symbol"] in ("cbBTC", "WBTC", "USDC"):
        continue
    c["name"], c["liq"] = nm, liq
    c["flag"] = "HIGH-CHURN" if c["vol7"] > 2.5e5 else ""
    out.append(c)
out.sort(key=lambda c: ("BREAK" not in c["signals"], c["flag"] != "", -c["vol7"]))
print(f"{len(out)} coins pass the backtest filters (of {len(d['live'])} raw flags)\n")
for c in out:
    kind = "BREAK" if "BREAK" in c["signals"] else "SETUP"
    print(f"  {kind:5} {str(c['symbol'])[:12]:12} {c['token']}  mcap ${c['mcap']:>11,.0f}  "
          f"7d vol ${c['vol7']:>10,.0f}  liq ${(c['liq'] or 0):>9,.0f}  age {c['age_days']}d  {c['flag']}")
(ROOT / "data/overnight/shortlist.json").write_text(json.dumps(out, indent=1))
