#!/usr/bin/env python3
"""Run the ledger analysis for every registered token, across all its pools.

Reads `data/tokens/tokens.json` (from track_tokens.py) and each token's
`quotes.json`, and writes `data/tokens/<token>/analysis.txt` and `.json`.

Supply is read from `totalSupply()` at the head rather than summed from mint
events, because at least one token here (ERHA) mints into its pool on some
sells, so its supply is not fixed at launch. The current price is the base
price in USD of the token's deepest registered pool.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rhc.rpc import V4_POOL_MANAGER, Rpc

PY = str(ROOT / ".venv/bin/python")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--only", nargs="*")
    args = p.parse_args()
    reg = json.loads((ROOT / "data/tokens/tokens.json").read_text())
    with Rpc() as rpc:
        for token, e in reg.items():
            if args.only and e["symbol"].upper() not in {x.upper() for x in args.only}:
                continue
            d = ROOT / "data/tokens" / token
            if not (d / "ledger.parquet").exists():
                print(f"{e['symbol']}: no ledger yet, skipped"); continue
            q = json.loads((d / "quotes.json").read_text())
            supply = int(rpc.call("eth_call", [{"to": token, "data": "0x18160ddd"}, "latest"]), 16)
            supply /= 10 ** e.get("decimals", 18)
            deepest = max(e["pools"], key=lambda k: e["pools"][k]["liq_at_add"])
            px = q["pools"].get(deepest, {}).get("base_usd") or 0
            market = sorted({V4_POOL_MANAGER if v["kind"] == "v4" else k
                             for k, v in e["pools"].items()})
            cmd = [PY, str(ROOT / "scripts/ledger_analysis.py"), "--dir", str(d),
                   "--name", e["symbol"], "--supply", str(supply),
                   "--price-now", str(px), "--eth-usd", str(q["eth_usd"]),
                   "--out", str(d / "analysis.json")]
            for m in market:
                cmd += ["--pool", m]
            with (d / "analysis.txt").open("w") as f:
                r = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
            print(f"{e['symbol']}: {'ok' if r.returncode == 0 else 'FAILED'} "
                  f"(supply {supply:,.0f}, price ${px:.6g}) -> {d/'analysis.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
