#!/usr/bin/env python3
"""Cross-token wallet ledger and the point-in-time features it yields.

This is catalogue section 1, the domain with the strongest published evidence
behind it, and it is the one thing the per-pool feature extraction cannot
produce. Every other feature describes a single pool. A wallet's track record is
by definition *across* pools, so it needs the trade archive rather than the
feature table, and it could not be built at all until trades were persisted.

**The output is not a leaderboard.** A ranked list of profitable wallets is
trivially produced and worth nothing, because it is built from the same history
it would be tested against: rank wallets by how often they bought winners, then
observe that tokens bought by those wallets tend to win, and you have measured
your own sorting. The prior-art project deleted an entire deployer-tracking tier
after discovering exactly this.

What this produces instead is a **per-token feature computed at that token's own
launch block**, using only wallet history that had already *resolved* by then.
Not "launched before" — resolved before. A token that launched in January and
ran in March tells a February observer nothing, and crediting a wallet in
February for a March win is the leak in its purest form.

Two guards against the obvious ways to get this wrong:

**The sweep is checked against the reference scorer.** The incremental
accumulator here is fast because it never rescans history; `rhc.wallets.score_at`
is slow because it filters every position from scratch, and is therefore much
harder to get subtly wrong. A sample of wallet-block pairs is scored both ways
and the run aborts if they disagree. A fast path that silently sees one extra
resolution is a leak that no amount of downstream discipline recovers from.

**Hits are scored against activity.** With hundreds of thousands of tokens on
this chain, a wallet that buys 500 of them accumulates wins by spraying. The
binomial tail asks whether a wallet did better than its own trade count predicts,
so 3 hits from 8 entries outranks 5 from 900.

Usage:
    python scripts/wallet_ledger.py --threshold 10
"""
from __future__ import annotations

import argparse
import glob
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from rhc.features import Trade
from rhc.wallets import Position, binomial_tail, build_positions, score_at


def load_trades(path: str) -> dict[str, list[Trade]]:
    """Read the archive back into per-token trade lists.

    Amounts were stored as strings because they are raw 256-bit integers that
    no fixed-width numeric type holds exactly, and the exactness is load-bearing
    for repeated-amount detection.
    """
    con = duckdb.connect()
    rows = con.execute(
        "SELECT token, block, log_index, wallet, is_buy, quote_amount, base_amount "
        "FROM read_parquet(?) ORDER BY token, block, log_index",
        [str(path)],
    ).fetchall()
    by_token: dict[str, list[Trade]] = defaultdict(list)
    for token, block, log_index, wallet, is_buy, quote, base in rows:
        by_token[token].append(
            Trade(block=int(block), wallet=(wallet or "").lower(), is_buy=bool(is_buy),
                  quote_amount=int(quote), base_amount=int(base), log_index=int(log_index))
        )
    return dict(by_token)


class Sweep:
    """Running per-wallet totals, advanced strictly forward in block order.

    The accumulator is only correct if nothing is ever applied out of order, so
    `advance` refuses to move backwards rather than quietly producing a state
    that includes the future.
    """

    def __init__(self, base_rate: float) -> None:
        self.base_rate = base_rate
        self.block = -1
        self.resolved: dict[str, int] = defaultdict(int)
        self.wins: dict[str, int] = defaultdict(int)
        self.returns: dict[str, list[float]] = defaultdict(list)
        self.sizes: dict[str, list[float]] = defaultdict(list)
        self._pending: list[tuple[int, list[Position], bool]] = []

    def schedule(self, resolution_block: int, positions: list[Position], won: bool) -> None:
        self._pending.append((resolution_block, positions, won))

    def prepare(self) -> None:
        self._pending.sort(key=lambda item: item[0])
        self._cursor = 0

    def advance(self, to_block: int) -> None:
        if to_block < self.block:
            raise RuntimeError(
                f"sweep asked to move backwards ({self.block} -> {to_block}); "
                "the evaluation order is wrong and the result would include "
                "resolutions from the future"
            )
        self.block = to_block
        while self._cursor < len(self._pending) and self._pending[self._cursor][0] <= to_block:
            _, positions, won = self._pending[self._cursor]
            for position in positions:
                wallet = position.wallet
                self.resolved[wallet] += 1
                if won:
                    self.wins[wallet] += 1
                realised = position.realised_return
                if realised is not None:
                    self.returns[wallet].append(realised)
                if position.quote_in > 0:
                    self.sizes[wallet].append(float(position.quote_in))
            self._cursor += 1

    def stats(self, wallet: str) -> dict[str, float | int | None]:
        n = self.resolved.get(wallet, 0)
        if n == 0:
            return {"resolved": 0, "wins": 0, "win_rate": None, "binomial_p": None,
                    "t_stat": None, "mean_return": None}
        wins = self.wins.get(wallet, 0)
        returns = self.returns.get(wallet, [])
        t_stat = mean = None
        if len(returns) >= 2:
            mean = sum(returns) / len(returns)
            variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
            stdev = variance**0.5
            if stdev > 0:
                t_stat = mean / (stdev / len(returns) ** 0.5)
        elif len(returns) == 1:
            mean = returns[0]
        return {
            "resolved": n, "wins": wins, "win_rate": wins / n,
            "binomial_p": binomial_tail(wins, n, self.base_rate),
            "t_stat": t_stat, "mean_return": mean,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades", type=str, default="data/parquet/trades*.parquet",
                        help="a path or a glob. Batched extractions write "
                             "one file each and are read together.")
    parser.add_argument("--features", type=Path, default=Path("data/parquet/features.parquet"))
    parser.add_argument("--label", default="realisable_peak_over_launch")
    parser.add_argument("--threshold", type=float, default=10.0)
    parser.add_argument("--horizon-blocks", type=int, default=250_000,
                        help="blocks after first trade at which a token's outcome "
                             "counts as known. At ~100ms blocks this is about a week.")
    parser.add_argument("--early-percentile", type=float, default=0.2,
                        help="which buyers count as early, as a fraction of a "
                             "token's buyer sequence")
    parser.add_argument("--min-prior", type=int, default=3,
                        help="resolved prior positions before a wallet's record "
                             "is treated as informative at all")
    parser.add_argument("--out", type=Path, default=Path("data/parquet/wallet_features.parquet"))
    parser.add_argument("--summary", type=Path, default=Path("data/wallet_ledger.json"))
    parser.add_argument("--audit-sample", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260921)
    args = parser.parse_args()

    matches = sorted(glob.glob(args.trades))
    if not matches:
        print(f"no trade archive matches {args.trades!r}. Run "
              f"scripts/extract_features.py first; it writes the archive these "
              f"stages read.", file=sys.stderr)
        return 1
    print(f"reading {len(matches)} trade file(s)", file=sys.stderr)

    token_trades = load_trades(args.trades)
    print(f"{len(token_trades):,} tokens, "
          f"{sum(len(v) for v in token_trades.values()):,} trades", file=sys.stderr)

    con = duckdb.connect()
    available = {
        name for name, *_ in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{args.features}')").fetchall()
    }
    if args.label not in available:
        # Feature tables written before the outcome amendment carry only the
        # naive peak, so say which label is missing rather than surfacing a
        # binder error from three frames down.
        print(f"{args.features} has no column '{args.label}'. Tables written "
              f"before the 2026-09-21 outcome amendment carry 'peak_over_launch' "
              f"only; rebuild with scripts/recompute_features.py or pass "
              f"--label explicitly.", file=sys.stderr)
        return 1
    outcomes = dict(con.execute(
        f'SELECT token, "{args.label}" FROM read_parquet(?) WHERE "{args.label}" IS NOT NULL',
        [str(args.features)],
    ).fetchall())
    winners = {t for t, v in outcomes.items() if float(v) >= args.threshold}
    labelled = [t for t in token_trades if t in outcomes]
    if not labelled:
        print("no tokens have both trades and an outcome", file=sys.stderr)
        return 1
    base_rate = len([t for t in labelled if t in winners]) / len(labelled)
    print(f"{len(labelled):,} labelled tokens, {len(winners & set(labelled)):,} winners "
          f"(base rate {base_rate:.2%})", file=sys.stderr)
    if base_rate <= 0:
        print("no winners at this threshold; every score would be degenerate",
              file=sys.stderr)
        return 1

    positions_by_token = {t: build_positions(t, tr) for t, tr in token_trades.items()}
    all_positions = [p for ps in positions_by_token.values() for p in ps]
    first_block = {t: min(x.block for x in tr) for t, tr in token_trades.items() if tr}
    resolved_by = {t: b + args.horizon_blocks for t, b in first_block.items()}

    sweep = Sweep(base_rate)
    for token, positions in positions_by_token.items():
        if token in outcomes and token in resolved_by:
            sweep.schedule(resolved_by[token], positions, token in winners)
    sweep.prepare()

    # Tokens are evaluated in launch order so the sweep only ever moves forward.
    order = sorted((b, t) for t, b in first_block.items() if t in outcomes)
    rows: list[dict] = []
    audit_points: list[tuple[str, int, dict]] = []
    rng = random.Random(args.seed)

    for block, token in order:
        sweep.advance(block)
        positions = positions_by_token.get(token, [])
        early = [
            p for p in positions
            if p.entry_percentile is not None and p.entry_percentile <= args.early_percentile
        ]
        priors = [(p.wallet, sweep.stats(p.wallet)) for p in early]
        informative = [(w, s) for w, s in priors if s["resolved"] >= args.min_prior]

        row: dict = {
            "token": token,
            "early_buyer_count": len(early),
            "early_buyers_with_record": len(informative),
            "early_buyer_record_share": (len(informative) / len(early)) if early else None,
        }
        if informative:
            win_rates = [s["win_rate"] for _, s in informative if s["win_rate"] is not None]
            p_values = [s["binomial_p"] for _, s in informative if s["binomial_p"] is not None]
            t_stats = [s["t_stat"] for _, s in informative if s["t_stat"] is not None]
            row["early_buyer_mean_win_rate"] = (
                sum(win_rates) / len(win_rates) if win_rates else None
            )
            row["early_buyer_max_win_rate"] = max(win_rates) if win_rates else None
            row["early_buyer_min_binomial_p"] = min(p_values) if p_values else None
            # How many early buyers beat their own activity level at the
            # conventional 5% tail. This is the activity-matched count, and it
            # is the number the catalogue's section 1 is really about.
            row["early_buyer_skilled_count"] = sum(1 for p in p_values if p < 0.05)
            row["early_buyer_max_t_stat"] = max(t_stats) if t_stats else None
            row["early_buyer_mean_prior_positions"] = (
                sum(s["resolved"] for _, s in informative) / len(informative)
            )
        else:
            for key in ("early_buyer_mean_win_rate", "early_buyer_max_win_rate",
                        "early_buyer_min_binomial_p", "early_buyer_max_t_stat",
                        "early_buyer_mean_prior_positions"):
                row[key] = None
            row["early_buyer_skilled_count"] = 0
        rows.append(row)

        if early and len(audit_points) < args.audit_sample and rng.random() < 0.05:
            # The sweep is destructive -- by the end of the loop it has advanced
            # past every audit block -- so its state has to be captured here,
            # while it is still the state the feature was computed from.
            candidate = rng.choice(early).wallet
            audit_points.append((candidate, block, dict(sweep.stats(candidate))))

    # --- audit: the fast sweep against the slow reference ------------------
    # `score_at` recomputes from the full position list every time, which makes
    # it far too slow to run over every token but much harder to get subtly
    # wrong. If the two disagree anywhere, the sweep is seeing resolutions it
    # should not, and every feature above is contaminated.
    mismatches = []
    for wallet, block, snapshot in audit_points:
        reference = score_at(
            wallet, all_positions, as_of_block=block, resolved_by=resolved_by,
            winners=winners, base_rate=base_rate,
        )
        if (snapshot["resolved"] != reference.positions_resolved
                or snapshot["wins"] != reference.win_count):
            mismatches.append({
                "wallet": wallet, "block": block,
                "sweep_resolved": snapshot["resolved"],
                "reference_resolved": reference.positions_resolved,
                "sweep_wins": snapshot["wins"],
                "reference_wins": reference.win_count,
            })
    if mismatches:
        print(f"AUDIT FAILED: {len(mismatches)} of {len(audit_points)} wallet-block "
              f"pairs disagree with the reference scorer. The sweep is leaking; "
              f"no output written.", file=sys.stderr)
        for m in mismatches[:5]:
            print(f"  {m}", file=sys.stderr)
        return 1

    keys = sorted({k for r in rows for k in r})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({k: [r.get(k) for r in rows] for k in keys}),
                   args.out, compression="zstd")

    with_record = [r for r in rows if r["early_buyers_with_record"]]
    summary = {
        "tokens": len(rows),
        "labelled_tokens": len(labelled),
        "winners": len(winners & set(labelled)),
        "base_rate": base_rate,
        "threshold": args.threshold,
        "horizon_blocks": args.horizon_blocks,
        "tokens_with_any_early_buyer_record": len(with_record),
        "audit_pairs_checked": len(audit_points),
        "distinct_wallets": len({p.wallet for p in all_positions}),
        "positions": len(all_positions),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\n  distinct wallets     : {summary['distinct_wallets']:,}", file=sys.stderr)
    print(f"  positions            : {summary['positions']:,}", file=sys.stderr)
    print(f"  tokens with a prior  : {len(with_record):,} of {len(rows):,}", file=sys.stderr)
    print(f"  audit pairs agreed   : {len(audit_points)}", file=sys.stderr)
    if not with_record:
        print("\n  No token had an early buyer with a resolved prior record. That is "
              "\n  a real answer, not a failure: at this sample size the wallet "
              "\n  overlap between tokens is too thin for the feature to exist.",
              file=sys.stderr)
    print(f"\nwrote {args.out} and {args.summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
