#!/usr/bin/env python3
"""How many independent dimensions do the extracted features actually represent?

Before any model is fitted, this answers a question that changes the whole
multiple-testing picture: several catalogue metrics are different views of one
underlying quantity. Gini, HHI, entropy and top-k concentration all measure
concentration; volume, transaction count and unique buyers all measure activity.

If 49 features collapse to 15 independent dimensions, the effective testing
burden is 15, not 49 — and which metrics are redundant becomes a measurement
rather than a guess.

Method: pairwise Spearman correlation (rank-based, so monotone but non-linear
relationships still register and outliers do not dominate), then greedy
clustering at a correlation threshold. Spearman matters here because these
distributions are extremely skewed — a Pearson correlation would be driven by
the few largest pools.

Usage:
    python scripts/feature_correlations.py --threshold 0.8
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb


MIN_ROWS = 30


def spearman(con, table: str, a: str, b: str) -> tuple[float | None, int]:
    """Rank correlation between two columns, and the row count it rests on.

    Returns the count alongside the coefficient so the caller can distinguish
    "measured as uncorrelated" from "not enough data to tell". Collapsing those
    two into a single None made a 9-row smoke test report "46 independent
    clusters", which reads as a finding and meant the opposite.
    """
    row = con.execute(
        f"""
        WITH d AS (
            SELECT "{a}" AS x, "{b}" AS y FROM read_parquet(?)
            WHERE "{a}" IS NOT NULL AND "{b}" IS NOT NULL
        ), r AS (
            SELECT rank() OVER (ORDER BY x) AS rx, rank() OVER (ORDER BY y) AS ry FROM d
        )
        SELECT corr(rx, ry), count(*) FROM r
        """,
        [table],
    ).fetchone()
    if row is None or row[1] is None:
        return None, 0
    count = int(row[1])
    if count < MIN_ROWS or row[0] is None:
        return None, count
    return row[0], count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("data/parquet/features.parquet"))
    parser.add_argument("--threshold", type=float, default=0.8,
                        help="Absolute correlation at which two features are treated as one")
    parser.add_argument("--out", type=Path, default=Path("data/feature_clusters.json"))
    args = parser.parse_args()

    con = duckdb.connect()
    table = str(args.features)
    described = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{table}')").fetchall()
    numeric = [
        name for name, dtype, *_ in described
        if any(t in dtype.upper() for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "BIGINT"))
    ]
    # Drop columns with no variation; a constant correlates with nothing and
    # only produces nulls that make the matrix look sparser than it is.
    varying = []
    for col in numeric:
        n = con.execute(
            f'SELECT count(DISTINCT "{col}") FROM read_parquet(?)', [table]
        ).fetchone()[0]
        if n > 1:
            varying.append(col)
    dropped = sorted(set(numeric) - set(varying))
    print(f"{len(numeric)} numeric columns, {len(varying)} with variation", file=sys.stderr)
    if dropped:
        print(f"  constant, dropped: {', '.join(dropped)}", file=sys.stderr)

    pairs: list[tuple[str, str, float]] = []
    tested = underpowered = 0
    for i, a in enumerate(varying):
        for b in varying[i + 1:]:
            rho, count = spearman(con, table, a, b)
            if rho is None:
                underpowered += 1
                continue
            tested += 1
            if abs(rho) >= args.threshold:
                pairs.append((a, b, rho))

    if tested == 0:
        print(f"\nINSUFFICIENT DATA: every one of {underpowered} pairs had fewer than "
              f"{MIN_ROWS} complete rows. No clustering is reported, because with this "
              f"little data 'uncorrelated' and 'unmeasurable' are indistinguishable.",
              file=sys.stderr)
        return 1
    if underpowered:
        print(f"  {underpowered} pairs skipped for having under {MIN_ROWS} complete rows",
              file=sys.stderr)

    # Greedy single-linkage clustering: anything correlated above threshold with
    # a cluster member joins that cluster.
    parent: dict[str, str] = {c: c for c in varying}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, _ in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    clusters: dict[str, list[str]] = {}
    for col in varying:
        clusters.setdefault(find(col), []).append(col)
    ordered = sorted(clusters.values(), key=len, reverse=True)

    print(f"\n{len(varying)} features collapse to {len(ordered)} independent clusters "
          f"at |rho| >= {args.threshold}\n", file=sys.stderr)
    for group in ordered:
        if len(group) > 1:
            print(f"  [{len(group)}] {', '.join(sorted(group))}", file=sys.stderr)
    singles = [g[0] for g in ordered if len(g) == 1]
    print(f"\n  {len(singles)} features stand alone: {', '.join(sorted(singles))}",
          file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "threshold": args.threshold,
        "n_features": len(varying),
        "pairs_tested": tested,
        "pairs_underpowered": underpowered,
        "n_clusters": len(ordered),
        "constant_dropped": dropped,
        "clusters": [sorted(g) for g in ordered],
        "correlated_pairs": [{"a": a, "b": b, "rho": rho} for a, b, rho in
                             sorted(pairs, key=lambda p: -abs(p[2]))],
    }, indent=2) + "\n")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
