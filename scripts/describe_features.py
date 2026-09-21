#!/usr/bin/env python3
"""Column-by-column diagnostics, run before anything is fitted or believed.

This project has produced at least five results that looked like findings and
were not, and in the sharpest case — H2 — replication passed and a clustering
check passed while the conclusion was still wrong. The cheapest defence against
the next one is to look at the columns before modelling them, because most
artefacts announce themselves in a univariate summary long before they reach an
AUC.

Four failure classes it looks for, in order of how often they have actually
happened here:

**Constant columns.** A feature with one distinct value carries no information
but still consumes a degree of freedom and can be selected by a tree that splits
on nothing. Usually it means a code path never fired.

**Near-total missingness.** A column present for six of six hundred tokens will
be median-imputed into a constant and then, in a small confirmation half, can
still separate classes by accident.

**Implausible extremes.** An inverted price ratio once produced a median of
22,668x and looked like a real distribution until it was compared against
anything. Ratios of max to median are printed for exactly this reason.

**Degenerate spread.** A column whose 99th percentile equals its median is
dust-dominated: the p90-anchored dust filter exists because a median-anchored
one failed in pools where the median *is* dust, and passed a sixty-pool smoke
test while doing so.

Nothing here is a pass/fail gate. It prints what the columns look like, and the
judgement stays with the reader.

Usage:
    python scripts/describe_features.py --features data/parquet/features.parquet
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

NUMERIC = ("INT", "DOUBLE", "FLOAT", "DECIMAL", "BOOL")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("data/parquet/features.parquet"))
    parser.add_argument("--missing-threshold", type=float, default=0.9,
                        help="flag a column missing in at least this fraction of rows")
    parser.add_argument("--extreme-ratio", type=float, default=1e6,
                        help="flag a column whose max exceeds its median by this factor")
    parser.add_argument("--out", type=Path, default=Path("data/feature_diagnostics.json"))
    args = parser.parse_args()

    if not args.features.exists():
        print(f"{args.features} not found", file=sys.stderr)
        return 1

    con = duckdb.connect()
    described = con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{args.features}')"
    ).fetchall()
    total = con.execute(
        f"SELECT count(*) FROM read_parquet('{args.features}')"
    ).fetchone()[0]
    if not total:
        print("table is empty", file=sys.stderr)
        return 1

    numeric = [n for n, d, *_ in described if any(t in d.upper() for t in NUMERIC)]
    other = [n for n, d, *_ in described if n not in numeric]
    print(f"{total:,} rows, {len(described)} columns "
          f"({len(numeric)} numeric, {len(other)} other)\n", file=sys.stderr)

    report: dict[str, dict] = {}
    constant, mostly_missing, extreme, degenerate = [], [], [], []

    for column in numeric:
        stats = con.execute(
            f'''SELECT count("{column}"), count(DISTINCT "{column}"),
                       min(CAST("{column}" AS DOUBLE)),
                       median(CAST("{column}" AS DOUBLE)),
                       quantile_cont(CAST("{column}" AS DOUBLE), 0.99),
                       max(CAST("{column}" AS DOUBLE))
                FROM read_parquet(?)''',
            [str(args.features)],
        ).fetchone()
        present, distinct, low, med, p99, high = stats
        missing = 1.0 - (present / total)
        entry = {
            "present": present, "missing_frac": missing, "distinct": distinct,
            "min": low, "median": med, "p99": p99, "max": high,
        }
        report[column] = entry

        if present == 0:
            mostly_missing.append((column, 1.0))
            continue
        if distinct <= 1:
            constant.append((column, low))
        if missing >= args.missing_threshold:
            mostly_missing.append((column, missing))
        if med is not None and high is not None and med > 0 and high / med > args.extreme_ratio:
            extreme.append((column, high / med))
        if (med is not None and p99 is not None and distinct > 1
                and med == p99):
            degenerate.append((column, med))

    def section(title: str, items: list, formatter) -> None:
        print(f"--- {title} ({len(items)}) ---", file=sys.stderr)
        for name, value in sorted(items, key=lambda pair: str(pair[0]))[:25]:
            print(f"  {formatter(name, value)}", file=sys.stderr)
        if not items:
            print("  none", file=sys.stderr)
        print(file=sys.stderr)

    section("constant columns", constant,
            lambda n, v: f"{n}: every row = {v}")
    section(f"missing in >={args.missing_threshold:.0%} of rows", mostly_missing,
            lambda n, v: f"{n}: {v:.1%} missing")
    section(f"max exceeds median by >{args.extreme_ratio:g}x", extreme,
            lambda n, v: f"{n}: {v:.3g}x")
    section("p99 equals median (dust-dominated)", degenerate,
            lambda n, v: f"{n}: median = p99 = {v}")

    summary = {
        "rows": total, "columns": len(described), "numeric_columns": len(numeric),
        "constant": [n for n, _ in constant],
        "mostly_missing": [n for n, _ in mostly_missing],
        "extreme_range": [n for n, _ in extreme],
        "degenerate_spread": [n for n, _ in degenerate],
        "columns_detail": report,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, default=float) + "\n")

    usable = len(numeric) - len({*(n for n, _ in constant), *(n for n, _ in mostly_missing)})
    print(f"{usable} of {len(numeric)} numeric columns carry usable variation.",
          file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
