"""Known-answer tests for the modelling harness.

Every other test in this repo checks that a measurement is computed correctly.
These check the thing that decides whether any of it means anything, and the
negative case is the one that matters: **given pure noise, the harness must say
so.** A pipeline that reports a finding on random data will report a finding on
real data too, and this project has already produced five results that looked
real and were not.

Two planted answers:

1. One genuine feature among nine noise columns. The harness must find it, keep
   it under L1, and produce lift well above the shuffled-label floor.
2. Ten noise columns and nothing else. The harness must fail to beat its own
   control, and `beats_control` must come back False.

The second test is slow-ish and deliberately not skipped. It is the only check
in the repository that the discipline actually works rather than merely being
described in a docstring.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
N = 400


def write_table(path: Path, *, with_signal: bool, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    signal = rng.normal(size=N)
    if with_signal:
        probability = 1 / (1 + np.exp(-(signal * 1.8 - 1.6)))
    else:
        # Same marginal positive rate, no relationship to any column.
        probability = np.full(N, 0.22)
    label = (rng.random(N) < probability).astype(float)

    columns: dict[str, list] = {
        "token": [f"0x{i:040x}" for i in range(N)],
        "pool": [f"0xp{i}" for i in range(N)],
        "real_signal": signal.tolist(),
    }
    for j in range(9):
        columns[f"noise_{j}"] = rng.normal(size=N).tolist()
    # Scaled so the harness's default 10x threshold selects the positives.
    columns["realisable_peak_over_launch"] = (
        label * 20 + rng.random(N) * 2
    ).tolist()
    pq.write_table(pa.table(columns), path)


def run(path: Path, out: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "model_features.py"),
         "--features", str(path), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(out.read_text())


def test_planted_signal_is_found():
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        table = directory / "signal.parquet"
        write_table(table, with_signal=True)
        report = run(table, directory / "out.json")

        assert report["beats_control"], report
        kept = dict(report["lasso_selected"])
        assert "real_signal" in kept, kept
        # The planted feature carries by far the largest coefficient.
        assert abs(kept["real_signal"]) > 5 * max(
            (abs(v) for k, v in kept.items() if k != "real_signal"), default=0.0
        ), kept

        decile = report["lift_top_decile"]
        assert decile["lift"] > 2.0, decile
        assert report["shuffled_lift_top_decile"] < 1.5, report


def test_pure_noise_does_not_beat_its_control():
    """The test this project exists to pass.

    Ten random columns, a label unrelated to all of them. If `beats_control`
    comes back True here, every positive result the pipeline ever reports is
    uninterpretable.
    """
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        table = directory / "noise.parquet"
        write_table(table, with_signal=False, seed=11)
        report = run(table, directory / "out.json")

        assert not report["beats_control"], (
            f"the harness found a signal in pure noise: "
            f"lasso {report['lasso_auc']:.3f}, gbm {report['gbm_auc']:.3f}, "
            f"control {report['shuffled_label_auc']:.3f}"
        )


def test_leaky_columns_are_excluded():
    # The outcome column itself must never reach the feature matrix.
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        table = directory / "signal.parquet"
        write_table(table, with_signal=True)
        report = run(table, directory / "out.json")
        selected = {name for name, _ in report["lasso_selected"]}
        assert "realisable_peak_over_launch" not in selected
        assert report["features"] == 10, report["features"]


def test_the_label_is_never_a_feature():
    """The label column must be excluded whatever it is called.

    Exclusion used to rely on LEAKY happening to contain the default label, so
    any run with a custom --label put the outcome in the feature matrix and
    returned a confirmation AUC of exactly 1.000. That is the tripwire: no
    honest model scores 1.000 on held-out data, and this test exists so the
    next custom label cannot reintroduce it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        table = directory / "signal.parquet"
        write_table(table, with_signal=True)

        # Re-publish the same table with the outcome under a name no exclusion
        # list mentions.
        import pyarrow.parquet as pq_read
        existing = pq_read.read_table(table).to_pydict()
        existing["custom_outcome"] = existing["realisable_peak_over_launch"]
        renamed = directory / "renamed.parquet"
        pq.write_table(pa.table(existing), renamed)

        out = directory / "out.json"
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "model_features.py"),
             "--features", str(renamed), "--label", "custom_outcome",
             "--out", str(out)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(out.read_text())
        selected = {name for name, _ in report["lasso_selected"]}
        assert "custom_outcome" not in selected, selected
        assert report["gbm_auc"] < 0.999, (
            f"AUC {report['gbm_auc']} on held-out data means the label reached "
            f"the feature matrix"
        )


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
