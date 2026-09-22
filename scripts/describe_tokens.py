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

from rhc.premium import GeckoTerminal, PremiumError


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

    rows = []
    with GeckoTerminal() as gecko:
        for row in passing:
            address = row.get("base_token")
            symbol = row.get("base_symbol") or "?"
            entry = {
                "symbol": symbol, "address": address,
                "market_cap": row.get("market_cap_used"),
                "dexscreener": row.get("url"),
            }
            if address:
                try:
                    payload = gecko.token_info(address)
                except PremiumError as exc:
                    entry["error"] = str(exc)[:120]
                    rows.append(entry)
                    continue
                attributes = (payload.get("data") or {}).get("attributes") or {}
                entry["name"] = attributes.get("name")
                entry["description"] = (attributes.get("description") or "").strip() or None
                entry["websites"] = attributes.get("websites") or []
                entry["twitter"] = attributes.get("twitter_handle")
                entry["telegram"] = attributes.get("telegram_handle")
                entry["discord"] = attributes.get("discord_url")
                entry["gt_score"] = attributes.get("gt_score")
            rows.append(entry)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2, default=str) + "\n")

    described = [r for r in rows if r.get("description")]
    linked = [r for r in rows if r.get("websites") or r.get("twitter")
              or r.get("telegram")]
    print(f"  {len(described)}/{len(rows)} carry a description", file=sys.stderr)
    print(f"  {len(linked)}/{len(rows)} carry a website or social link\n",
          file=sys.stderr)

    for row in rows:
        bits = []
        if row.get("twitter"):
            bits.append(f"x:@{row['twitter']}")
        if row.get("telegram"):
            bits.append(f"tg:{row['telegram']}")
        if row.get("websites"):
            bits.append(str(row["websites"][0])[:40])
        description = row.get("description")
        text = (description[:140] + "…") if description and len(description) > 140 \
            else (description or "— no description served —")
        print(f"  {row['symbol']:<14} {text}", file=sys.stderr)
        if bits:
            print(f"  {'':<14} {' | '.join(bits)}", file=sys.stderr)

    print(f"\nwrote {args.out}", file=sys.stderr)
    print("\n  Descriptions are deployer-written marketing retrieved from a third "
          "party,\n  not facts about the asset. Only the contract address is "
          "verifiable here.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
