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

MIN_HISTORY = 14   # windows reaching further back are clamped


def _med(vol: list[float], a: int, z: int) -> float:
    a = max(a, 0)
    return statistics.median(vol[a:z]) if z > a else 0.0


def signals(seq: list[dict], i: int) -> dict[str, bool]:
    """Candle-only signals at the close of bar ``i``. Needs ``i >= MIN_HISTORY``."""
    vol = [s["vol"] for s in seq]

    def dried(k: int) -> bool:
        m = _med(vol, k - 23, k - 2)
        return m > 0 and sum(vol[k - 2:k + 1]) / 3 <= 0.5 * m

    dry = any(dried(k) for k in range(max(3, i - 10), i - 1))
    ignite = any(_med(vol, k - 14, k) > 0 and vol[k] >= 2.5 * _med(vol, k - 14, k)
                 and seq[k]["c"] > seq[k]["o"] for k in range(max(1, i - 7), i + 1))
    lo = lambda a, z: min(s["l"] for s in seq[a:z])
    hlows = lo(i - 3, i + 1) > lo(i - 7, i - 3) > lo(i - 11, i - 7)
    hi20 = max(s["h"] for s in seq[max(0, i - 20):i])
    c = seq[i]["c"]
    coil = 0.85 * hi20 <= c < hi20
    brk = (c > hi20 and _med(vol, i - 14, i) > 0 and vol[i] >= 2 * _med(vol, i - 14, i)
           and any(dried(k) for k in range(max(3, i - 20), i - 1)))
    return {"dry": dry, "ignite": ignite, "hlows": hlows, "coil": coil, "brk": brk,
            "SETUP": dry and ignite and hlows and coil, "BREAK": brk}


def outcomes(seq: list[dict], i: int, horizon: int) -> dict[str, bool] | None:
    """Forward outcomes from the close of bar ``i``, measured on closes.

    Measured on daily **closes**, not highs and lows. The first version used
    candle highs and reported that 38.5% of token-days hit 2x within 14 days,
    which is not a market anyone could trade: on thin pools a single stray fill
    prints a wick far above anything that could have been sold into. A close is
    where the day's trading actually settled.

    run2x   some close in the window is >= 2x the entry close
    crash   some close in the window is <= 0.5x
    clean   a close >= 1.5x comes before any close <= 0.7x
    held    the close at the end of the window is still >= 1.5x
    """
    c0 = seq[i]["c"]
    fwd = seq[i + 1:i + 1 + horizon]
    if not c0 or len(fwd) < horizon:
        return None
    closes = [s["c"] / c0 for s in fwd if s["c"]]
    if not closes:
        return None
    clean = False
    for r in closes:
        if r < 0.7:
            break
        if r >= 1.5:
            clean = True
            break
    return {"run2x": max(closes) >= 2, "crash": min(closes) <= 0.5,
            "clean": clean, "held": closes[-1] >= 1.5}
