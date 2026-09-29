#!/usr/bin/env python3
"""Second evaluation pass: regime filter, profit-based smart wallets, breadth, combos.

Same method as research_eval.py (it is reused); only the condition list differs.
Run after research_features2.py. Writes data/research/eval2.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_eval as ev  # noqa: E402

SURGE = "surge6 >= 10 and vol_6h >= 5000"
HOT = "heat_d >= 0.22"
COLD = "heat_d < 0.12"

ev.CONDS = [
    ("all established (base)", "true"),
    ("regime HOT (heat >= 22%)", HOT),
    ("regime WARM (12-22%)", "heat_d >= 0.12 and heat_d < 0.22"),
    ("regime COLD (< 12%)", COLD),
    ("pro wallets >= 1 ($5k+ prior profit elsewhere)", "pro_n_6h >= 1"),
    ("pro wallets >= 3", "pro_n_6h >= 3"),
    ("pro wallets >= 5", "pro_n_6h >= 5"),
    ("big pro >= 1 ($25k+ prior profit)", "pro_big_6h >= 1"),
    ("big pro >= 2", "pro_big_6h >= 2"),
    ("big pro >= 3", "pro_big_6h >= 3"),
    ("breadth6 >= +0.3 (>= 20 active)", "breadth_6h >= 0.3 and active_6h >= 20"),
    ("breadth6 >= +0.5 (>= 20 active)", "breadth_6h >= 0.5 and active_6h >= 20"),
    ("breadth24 >= +0.3 (>= 50 active)", "breadth_24h >= 0.3 and active_24h >= 50"),
    ("breadth24 <= -0.2 (net sellers)", "breadth_24h <= -0.2 and active_24h >= 50"),
    ("surge10", SURGE),
    ("surge10 + HOT", f"{SURGE} and {HOT}"),
    ("surge10 + COLD", f"{SURGE} and {COLD}"),
    ("surge10 + big pro >= 1", f"{SURGE} and pro_big_6h >= 1"),
    ("surge10 + breadth6 >= 0.3", f"{SURGE} and breadth_6h >= 0.3"),
    ("surge20 + HOT", f"surge6 >= 20 and vol_6h >= 5000 and {HOT}"),
    ("new-wallet surge10 + HOT", f"newb_surge >= 10 and newb_6h >= 50 and {HOT}"),
    ("quiet wake-up + HOT", f"vol_prev48 < 2000 and vol_6h >= 5000 and {HOT}"),
    ("pullback reversal + surge5 + HOT",
     f"dd_7d <= 0.7 and up_from_low72 >= 1.2 and surge6 >= 5 and vol_6h >= 5000 and {HOT}"),
    ("big pro >= 2 + HOT", f"pro_big_6h >= 2 and {HOT}"),
    ("big pro >= 2 + breadth6 >= 0.3", "pro_big_6h >= 2 and breadth_6h >= 0.3 and active_6h >= 20"),
]

if __name__ == "__main__":
    if "--out" not in sys.argv:
        sys.argv += ["--out", str(ROOT / "data/research/eval2.md")]
    ev.main()
