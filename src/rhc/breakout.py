"""Pre-breakout signals on daily bars, shared by the backtest and the live screen.

The definitions mirror `scripts/flow_backtest.py` for the parts that need only
price and volume, so a pattern found in the backtest is the exact pattern the
screen looks for. A bar is a dict with o, h, l, c, vol (USD); days without
trading carry the previous close with zero volume.

Everything here reads bars up to and including index ``i`` and nothing after
it. `outcomes` is the only function that looks forward, and it is never called
by the live screen.
"""
from __future__ import annotations

import statistics

MIN_HISTORY = 24


def _med(vol: list[float], a: int, z: int) -> float:
    a = max(a, 0)
    return statistics.median(vol[a:z]) if z > a else 0.0


def signals(seq: list[dict], i: int) -> dict[str, bool]:
    """Candle-only signals at the close of bar ``i``. Needs ``i >= MIN_HISTORY``."""
    vol = [s["vol"] for s in seq]

    def dried(k: int) -> bool:
        m = _med(vol, k - 23, k - 2)
        return m > 0 and sum(vol[k - 2:k + 1]) / 3 <= 0.5 * m

    dry = any(dried(k) for k in range(i - 10, i - 1))
    ignite = any(_med(vol, k - 14, k) > 0 and vol[k] >= 2.5 * _med(vol, k - 14, k)
                 and seq[k]["c"] > seq[k]["o"] for k in range(i - 7, i + 1))
    lo = lambda a, z: min(s["l"] for s in seq[a:z])
    hlows = lo(i - 3, i + 1) > lo(i - 7, i - 3) > lo(i - 11, i - 7)
    hi20 = max(s["h"] for s in seq[i - 20:i])
    c = seq[i]["c"]
    coil = 0.85 * hi20 <= c < hi20
    brk = (c > hi20 and _med(vol, i - 14, i) > 0 and vol[i] >= 2 * _med(vol, i - 14, i)
           and any(dried(k) for k in range(i - 20, i - 1)))
    return {"dry": dry, "ignite": ignite, "hlows": hlows, "coil": coil, "brk": brk,
            "SETUP": dry and ignite and hlows and coil, "BREAK": brk}


def outcomes(seq: list[dict], i: int, horizon: int) -> dict[str, bool] | None:
    c0 = seq[i]["c"]
    fwd = seq[i + 1:i + 1 + horizon]
    if not c0 or len(fwd) < horizon:
        return None
    clean = False
    for s in fwd:
        if s["l"] / c0 < 0.7:
            break
        if s["h"] / c0 >= 1.5:
            clean = True
            break
    return {"run2x": max(s["h"] for s in fwd) / c0 >= 2,
            "crash": min(s["l"] for s in fwd) / c0 <= 0.5,
            "clean": clean}
