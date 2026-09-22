#!/usr/bin/env python3
"""What are these coins, in one line each?

Fetches whatever descriptive metadata the aggregators hold for a screen's
passing tokens: a project description, a website, socials, and the DexScreener
link for anything that has to be looked at by eye.

**Expect most of it to be empty, and treat what is there with suspicion.**
A memecoin does not usually *do* anything, and where a description exists it was
written by the deployer to sell the token. It is marketing copy retrieved from a
third party, not a fact about the asset. The only two things here that are
verifiable from the chain are the contract address and the deployer, and neither
tells you what the coin is for.

Where nothing is served, the ticker and the pool name are the only signal, and
guessing beyond them would be inventing information about something the user may
put money into.

Usage:
    python scripts/describe_tokens.py
    python scripts/describe_tokens.py --results data/screen_results/....json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.dexscreener import DexScreener, flatten


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("data/token_descriptions.json"))
    args = parser.parse_args()

    path = args.results
    if path is None:
        files = sorted(glob.glob("data/screen_results/*.json"))
        if not files:
            print("no screen results found; run scripts/run_screen.py first",
                  file=sys.stderr)
            return 1
        path = Path(files[-1])
    results = json.loads(path.read_text())
    passing = results.get("passed") or []
    print(f"{len(passing)} tokens from {path}\n", file=sys.stderr)

    # GeckoTerminal's token-info endpoint returns nothing for this chain --
    # verified empty even for USDG -- so the pair's own info block is the only
    # place websites and socials exist.
    addresses = [r["pair"] for r in passing if r.get("pair")]
    info: dict[str, dict] = {}
    with DexScreener() as dex:
        for pair in dex.pairs_by_address(addresses):
            row = flatten(pair)
            if row.get("pair"):
                info[row["pair"].lower()] = row

    rows = []
    for row in passing:
        found = info.get((row.get("pair") or "").lower(), {})
        rows.append({
            "symbol": row.get("base_symbol") or "?",
            "address": row.get("base_token"),
            "market_cap": row.get("market_cap_used"),
            "dexscreener": row.get("url"),
            "websites": found.get("websites") or [],
            "socials": found.get("socials") or [],
            "has_image": found.get("has_image", False),
            "pair_created_at": found.get("pair_created_at"),
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2, default=str) + "\n")

    linked = [r for r in rows if r.get("websites") or r.get("socials")]
    print(f"  {len(linked)}/{len(rows)} carry a website or social link\n",
          file=sys.stderr)

    for row in rows:
        bits = list(row.get("websites") or []) + list(row.get("socials") or [])
        if bits:
            print(f"  {row['symbol']:<14} {' | '.join(b[:60] for b in bits)}",
                  file=sys.stderr)
        else:
            marker = "image only" if row.get("has_image") else "nothing at all"
            print(f"  {row['symbol']:<14} — {marker} —", file=sys.stderr)

    print(f"\nwrote {args.out}", file=sys.stderr)
    print("\n  Descriptions are deployer-written marketing retrieved from a third "
          "party,\n  not facts about the asset. Only the contract address is "
          "verifiable here.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
