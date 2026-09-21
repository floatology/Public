"""The leak trap for the point-in-time wallet sweep.

Look-ahead is the failure mode that makes wallet forensics produce a
spectacular, meaningless result, and it is invisible in the output: a leaked
feature looks like a strong feature. So it gets a test with a hand-built
counterexample rather than a plausibility check.

The fixture:

    token A launches at block 0    and resolves at 1000   (a 100x winner)
    token B launches at block 500  -- before A resolves
    token C launches at block 2000 -- after A resolves

One wallet buys all three, first in each. At B's launch it must show **zero**
prior resolved positions, because A had launched but its outcome was not yet
knowable. At C's launch it must show two, one of them a win. A leaking
implementation credits the A win at B and the feature becomes prophecy.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from rhc.wallets import Position
sys.path.insert(0, str(ROOT / "scripts"))
from wallet_ledger import Sweep

HORIZON = 1000
LAUNCHES = [("0xA", 0), ("0xB", 500), ("0xC", 2000)]


def write_fixture(directory: Path) -> tuple[Path, Path]:
    rows = []

    def add(token, block, wallet, is_buy, quote, li):
        rows.append({"pool": "0xp" + token, "token": token, "quote_asset": "0xq",
                     "block": block, "log_index": li, "wallet": wallet,
                     "is_buy": is_buy, "quote_amount": str(quote),
                     "base_amount": str(10**18)})

    for token, start in LAUNCHES:
        add(token, start, "0xw1", True, 10**18, 0)
        for j in range(2, 12):
            add(token, start + j, f"0xo{j:03d}", True, 10**17 * j, j)
        add(token, start + 50, "0xw1", False, 3 * 10**18, 1)

    trades = directory / "trades.parquet"
    pq.write_table(pa.table({k: [r[k] for r in rows] for k in rows[0]}), trades)

    features = directory / "features.parquet"
    pq.write_table(pa.table({
        "token": [t for t, _ in LAUNCHES],
        "pool": ["0xp" + t for t, _ in LAUNCHES],
        "peak_over_launch": [100.0, 1.2, 1.1],
        "realisable_peak_over_launch": [100.0, 1.2, 1.1],
    }), features)
    return trades, features


def test_no_lookahead():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        trades, features = write_fixture(directory)
        out = directory / "wf.parquet"
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "wallet_ledger.py"),
             "--trades", str(trades), "--features", str(features),
             "--horizon-blocks", str(HORIZON), "--min-prior", "1",
             "--threshold", "10", "--audit-sample", "200",
             "--out", str(out), "--summary", str(directory / "s.json")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

        got = dict(duckdb.connect().execute(
            "SELECT token, early_buyers_with_record FROM read_parquet(?)", [str(out)]
        ).fetchall())
        # A: nothing has resolved at all. B: A launched but has not resolved.
        assert got["0xA"] == 0, got
        assert got["0xB"] == 0, f"LOOK-AHEAD: {got} -- A's outcome leaked into B"
        assert got["0xC"] == 3, got

        priors = dict(duckdb.connect().execute(
            "SELECT token, early_buyer_mean_prior_positions FROM read_parquet(?)", [str(out)]
        ).fetchall())
        assert priors["0xC"] == 2.0, priors


def test_unlabelled_tokens_do_not_break_the_audit():
    """A token in the archive with no outcome must resolve into nothing.

    The archive and the feature table come from the same extraction but need
    not agree row for row: a token whose label is null is in one and not the
    other. If such a token is still given a resolution block, the slow
    reference scorer counts positions in it that the forward sweep never
    schedules, and the audit reports a mismatch that is its own doing --
    aborting a run that was correct. That happened, and this is the fixture
    that reproduces it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        rows = []

        def add(token, block, wallet, is_buy, quote, li):
            rows.append({"pool": "0xp" + token, "token": token, "quote_asset": "0xq",
                         "block": block, "log_index": li, "wallet": wallet,
                         "is_buy": is_buy, "quote_amount": str(quote),
                         "base_amount": str(10**18)})

        launches = LAUNCHES + [("0xUNLABELLED", 100)]
        for token, start in launches:
            add(token, start, "0xw1", True, 10**18, 0)
            for j in range(2, 12):
                add(token, start + j, f"0xo{j:03d}", True, 10**17 * j, j)
            add(token, start + 50, "0xw1", False, 3 * 10**18, 1)

        trades = directory / "trades.parquet"
        pq.write_table(pa.table({k: [r[k] for r in rows] for k in rows[0]}), trades)
        features = directory / "features.parquet"
        pq.write_table(pa.table({
            "token": [t for t, _ in launches],
            "pool": ["0xp" + t for t, _ in launches],
            "peak_over_launch": [100.0, 1.2, 1.1, None],
            "realisable_peak_over_launch": [100.0, 1.2, 1.1, None],
        }), features)

        out = directory / "wf.parquet"
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "wallet_ledger.py"),
             "--trades", str(trades), "--features", str(features),
             "--horizon-blocks", str(HORIZON), "--min-prior", "1",
             "--threshold", "10", "--audit-sample", "500",
             "--out", str(out), "--summary", str(directory / "s.json")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "AUDIT FAILED" not in result.stderr, result.stderr

        priors = dict(duckdb.connect().execute(
            "SELECT token, early_buyer_mean_prior_positions FROM read_parquet(?)",
            [str(out)]).fetchall())
        # Two resolved priors at 0xC: 0xA and 0xB. The unlabelled token has no
        # outcome, so it contributes nothing however early it launched.
        assert priors["0xC"] == 2.0, priors


def test_sweep_refuses_to_move_backwards():
    sweep = Sweep(base_rate=0.1)
    sweep.prepare()
    sweep.advance(500)
    try:
        sweep.advance(100)
    except RuntimeError as exc:
        assert "backwards" in str(exc)
    else:
        raise AssertionError("sweep accepted a backwards advance; evaluation order "
                             "could silently include future resolutions")


def test_sweep_applies_only_resolved():
    sweep = Sweep(base_rate=0.1)
    position = Position(wallet="0xw", token="0xt", first_buy_block=0, last_block=10,
                        quote_in=10**18, quote_out=3 * 10**18, base_bought=10**18,
                        base_sold=10**18, buy_count=1, sell_count=1, entry_percentile=0.0)
    sweep.schedule(1000, [position], won=True)
    sweep.prepare()
    sweep.advance(999)
    assert sweep.stats("0xw")["resolved"] == 0
    sweep.advance(1000)
    stats = sweep.stats("0xw")
    assert stats["resolved"] == 1 and stats["wins"] == 1, stats
    assert abs(stats["mean_return"] - 2.0) < 1e-9, stats


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  pass  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {name}: {exc}")
    print(f"\n{failures} failures")
    raise SystemExit(1 if failures else 0)
