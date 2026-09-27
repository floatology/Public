#!/usr/bin/env python3
"""What else a wallet holds on Robinhood Chain, now and in the past.

A wallet's view of one token says little about who it is. Its other positions
say more: a wallet that holds the same handful of tokens as three others is
probably one trader, and one that is early and large in several tokens that
later ran is either skilled or connected.

**Current holdings come from Blockscout and are valued by DexScreener.** A
smart-contract wallet on this chain routinely holds a hundred or more tokens,
most of them unsolicited airdrops worth nothing. A balance counts as a position
only when the token trades in a pool with at least `--min-liq` of liquidity, so
spam cannot be reported as a holding. The `--min-value` floor then removes dust.

**Past holdings come from the wallet's token-transfer history**: tokens it once
received and no longer holds. These are listed with the number of transfers and
the date range, not a value. Today's price says nothing about what a position
was worth when it was sold, and inventing a historical price would be worse than
leaving it blank.

**Overlap across wallets is the point of running several at once.** A token held
by three of five watched wallets is reported as shared.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.chain import Blockscout
from rhc.dexscreener import DexScreener, flatten


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("wallets", nargs="+")
    p.add_argument("--min-liq", type=float, default=5_000)
    p.add_argument("--min-value", type=float, default=500)
    p.add_argument("--history-pages", type=int, default=20)
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    bs = Blockscout()
    ds = DexScreener()
    wallets = [w.lower() for w in args.wallets]

    holdings: dict[str, dict[str, dict]] = {}
    meta: dict[str, dict] = {}
    for w in wallets:
        rows = list(bs.paginate(f"/api/v2/addresses/{w}/tokens", max_pages=10, type="ERC-20"))
        h = {}
        for r in rows:
            t = r.get("token") or {}
            addr = (t.get("address_hash") or t.get("address") or "").lower()
            if not addr:
                continue
            dec = int(t.get("decimals") or 18)
            h[addr] = {"units": int(r.get("value") or 0) / 10**dec}
            meta[addr] = {"symbol": t.get("symbol"), "name": t.get("name"),
                          "supply": int(t.get("total_supply") or 0) / 10**dec if t.get("total_supply") else None}
        holdings[w] = h
        print(f"{w}: {len(h)} token balances", file=sys.stderr, flush=True)

    # Price every token any wallet holds, keeping each token's deepest pool.
    price: dict[str, dict] = {}
    for pair in ds.pairs_for_tokens(sorted(meta)):
        f = flatten(pair)
        addr = (f.get("base_token") or "").lower()
        liq = f.get("liquidity_usd") or 0
        if addr in meta and liq > price.get(addr, {}).get("liq", -1):
            price[addr] = {"px": float(f.get("price_usd") or 0), "liq": liq,
                           "mcap": f.get("market_cap") or f.get("fdv")}

    report = {"wallets": {}, "shared": {}}
    held_by = defaultdict(list)
    for w in wallets:
        pos = []
        for addr, h in holdings[w].items():
            pr = price.get(addr)
            if not pr or pr["liq"] < args.min_liq:
                continue
            val = h["units"] * pr["px"]
            if val < args.min_value:
                continue
            sup = meta[addr]["supply"]
            pos.append({"token": addr, "symbol": meta[addr]["symbol"], "value": val,
                        "share": (h["units"] / sup) if sup else None,
                        "mcap": pr["mcap"], "liq": pr["liq"]})
            held_by[addr].append(w)
        pos.sort(key=lambda x: -x["value"])
        report["wallets"][w] = {"positions": pos}

        print(f"\n=== {w}")
        tot = sum(x["value"] for x in pos)
        print(f"  {len(pos)} real positions worth ${tot:,.0f} "
              f"(of {len(holdings[w])} balances; the rest are dust or unpriced)")
        for x in pos[:15]:
            sh = f"{x['share']:.3%}" if x["share"] is not None else "   ?"
            print(f"   {str(x['symbol'])[:12]:12} ${x['value']:>10,.0f}  {sh:>8} of supply  "
                  f"mcap ${(x['mcap'] or 0):>12,.0f}  liq ${x['liq']:>10,.0f}")

        # Past positions: received, now gone.
        seen = defaultdict(lambda: {"n": 0, "first": None, "last": None, "symbol": None})
        for tr in bs.paginate(f"/api/v2/addresses/{w}/token-transfers",
                              max_pages=args.history_pages, type="ERC-20"):
            t = tr.get("token") or {}
            addr = (t.get("address_hash") or t.get("address") or "").lower()
            if not addr:
                continue
            s = seen[addr]
            s["n"] += 1; s["symbol"] = t.get("symbol")
            ts = tr.get("timestamp")
            s["first"] = min(s["first"], ts) if s["first"] else ts
            s["last"] = max(s["last"], ts) if s["last"] else ts
        now_tokens = {a for a, h in holdings[w].items() if h["units"] > 0}
        past = [(s["n"], a, s) for a, s in seen.items()
                if a not in now_tokens and s["n"] >= 2]
        past.sort(reverse=True)
        report["wallets"][w]["past"] = [{"token": a, "symbol": s["symbol"], "transfers": n,
                                         "first": s["first"], "last": s["last"]}
                                        for n, a, s in past]
        print(f"  past positions (traded, now zero): {len(past)}")
        for n, a, s in past[:10]:
            print(f"   {str(s['symbol'])[:12]:12} {n:>4} transfers  "
                  f"{(s['first'] or '')[:10]} -> {(s['last'] or '')[:10]}")

    shared = {a: ws for a, ws in held_by.items() if len(ws) >= 2}
    report["shared"] = {a: {"symbol": meta[a]["symbol"], "wallets": ws} for a, ws in shared.items()}
    print(f"\n=== positions held by 2+ of these wallets")
    for a, ws in sorted(shared.items(), key=lambda kv: -len(kv[1])):
        print(f"   {str(meta[a]['symbol'])[:12]:12} held by {len(ws)}: "
              f"{', '.join(x[:6] for x in ws)}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
