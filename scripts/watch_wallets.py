#!/usr/bin/env python3
"""Report every watched wallet's activity since the last check.

Reads `data/tokens/watchlist.json`, and for each token with an up-to-date ledger
reports, per watched wallet: current holdings, what it bought and sold since
`last_checked`, at what average price, and its lifetime position. Then it
advances `last_checked`, so the next run reports only what is new.

This runs on every token-forensics rerun (see the skill). A wallet stays on the
list while it is relevant; retiring one sets `active: false` with a reason
rather than deleting it, so the record of why it was watched survives.

Holdings are the wallet's real balance from the transfer replay, so tokens it
received or sent by transfer are counted even though they are not trades.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

ZERO = "0x0000000000000000000000000000000000000000"


def load(path: Path) -> dict[str, list]:
    t = pq.read_table(path)
    return {n: t.column(n).to_pylist() for n in t.column_names}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--watchlist", type=Path, default=Path("data/tokens/watchlist.json"))
    p.add_argument("--root", type=Path, default=Path("data/tokens"))
    p.add_argument("--since", help="override: ISO date to report from")
    p.add_argument("--no-advance", action="store_true",
                   help="report without moving last_checked forward")
    args = p.parse_args()

    wl = json.loads(args.watchlist.read_text())
    for token, entry in wl.items():
        if token.startswith("_"):
            continue
        d = args.root / token
        if not (d / "ledger.parquet").exists():
            print(f"\n{entry['name']}: no ledger yet — build the archive first")
            continue
        L = load(d / "ledger.parquet")
        T = load(d / "transfers.parquet")
        supply = None
        bal = defaultdict(int)
        minted = 0
        for i in range(len(T["block"])):
            v = int(T["value"][i])
            if not v:
                continue
            if T["src"][i] == ZERO:
                minted += v
            else:
                bal[T["src"][i]] -= v
            if T["dst"][i] != ZERO:
                bal[T["dst"][i]] += v
        supply = minted / 1e18 or 1.0

        order = sorted(range(len(L["ts"])), key=lambda i: (L["block"][i], L["log_index"][i]))
        last_px = next((L["price_usd"][i] for i in reversed(order) if L["price_usd"][i]), 0)
        latest = L["ts"][order[-1]]
        since = (int(dt.datetime.fromisoformat(args.since).replace(tzinfo=dt.timezone.utc).timestamp())
                 if args.since else entry.get("last_checked") or (latest - 7 * 86400))

        print(f"\n{'='*74}\n{entry['name']} watchlist — activity since "
              f"{dt.datetime.utcfromtimestamp(since):%d %b %H:%M} UTC, "
              f"price now ${last_px:.5f}\n{'='*74}")
        for w in entry["wallets"]:
            if not w.get("active", True):
                continue
            a = w["address"].lower()
            rows = [i for i in order if L["trader"][i] == a]
            new = [i for i in rows if L["ts"][i] >= since]
            bt = sum(L["tokens"][i] for i in new if L["side"][i] == "buy")
            bu = sum(L["usd"][i] for i in new if L["side"][i] == "buy")
            st = sum(L["tokens"][i] for i in new if L["side"][i] == "sell")
            su = sum(L["usd"][i] for i in new if L["side"][i] == "sell")
            tin = sum(L["usd"][i] for i in rows if L["side"][i] == "buy")
            tout = sum(L["usd"][i] for i in rows if L["side"][i] == "sell")
            hold = bal.get(a, 0) / 1e18
            if new:
                verdict = ("ACCUMULATING" if bt > st * 1.2 else
                           "DISTRIBUTING" if st > bt * 1.2 else "two-way")
            else:
                verdict = "no trades"
            print(f"\n  {a[:6]}…{a[-4:]}  {w['label']}")
            print(f"    holds {hold/supply:.3%} of supply = ${hold*last_px:,.0f}   [{verdict}]")
            if new:
                print(f"    since last check: bought {bt/supply:.3%} (${bu:,.0f}"
                      f"{f' @ {bu/bt:.5f}' if bt else ''}), sold {st/supply:.3%} (${su:,.0f}"
                      f"{f' @ {su/st:.5f}' if st else ''}) in {len(new)} trades")
            print(f"    lifetime: in ${tin:,.0f}, out ${tout:,.0f}, "
                  f"overall ${tout + hold*last_px - tin:+,.0f} at today's price")

        if not args.no_advance:
            entry["last_checked"] = latest
    if not args.no_advance:
        args.watchlist.write_text(json.dumps(wl, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
