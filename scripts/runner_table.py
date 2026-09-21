#!/usr/bin/env python3
"""Every token that reached a market-cap threshold, and what it did after.

A listing rather than a statistic: one row per token that ever crossed the
threshold, with where it peaked, how far that was from the crossing, and how
much of the move it has since given back.

**Market cap is reconstructed, not looked up.** No free source carries it
historically. GeckoTerminal gives current FDV and current price, so supply is
`fdv_now / price_now`, and `cap(t) = close(t) x supply`. Two consequences,
both of which can move a row several places up or down this table:

- **Supply is assumed constant.** A token that minted after launch has its early
  market cap overstated here, which makes its crossing look earlier and its
  multiple smaller. `rhc.contracts` finds mint functions routinely, so this is
  not hypothetical.
- **This is FDV, not circulating cap.** For a memecoin whose supply is entirely
  in the pool from day one they are the same number. For anything with locked or
  vesting supply they are not.

**Coverage is the honest limit.** The rows come from pools an aggregator tracks
today, filtered to those with a current FDV above a floor. A token that crossed
$250k and then collapsed to nothing is missing — not because it did not happen,
but because nothing lists it now. So this table is **biased toward survivors**,
and the multiples in it are therefore an optimistic sample of what crossing the
threshold leads to. It answers "what did the ones that made it do" and not
"what happens if you buy at $250k".

Usage:
    python scripts/runner_table.py --threshold 250000 --runner-cap 2000000
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


def number(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}k"
    return f"${value:.0f}"


def token_name(pool_name: str | None, quotes=("WETH", "USDG", "USDC", "USDT")) -> str:
    """The non-quote side of a pool name like 'HH / WETH 0.3%'."""
    if not pool_name:
        return "?"
    left = pool_name.split("/")[0].strip()
    right = pool_name.split("/")[-1].strip().split()[0] if "/" in pool_name else ""
    # A pool quoted the other way round names the quote first.
    if left.upper() in quotes and right and right.upper() not in quotes:
        return right
    return left


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool-cache", type=Path, default=Path("data/gt_pools.json"))
    parser.add_argument("--candle-cache", type=Path, default=Path("data/gt_candles.json"))
    parser.add_argument("--threshold", type=float, default=250_000)
    parser.add_argument("--runner-cap", type=float, default=2_000_000)
    parser.add_argument("--out-csv", type=Path, default=Path("data/runners.csv"))
    parser.add_argument("--out-md", type=Path, default=Path("docs/14-runner-table.md"))
    parser.add_argument("--top", type=int, default=60, help="rows in the markdown table")
    args = parser.parse_args()

    for path in (args.pool_cache, args.candle_cache):
        if not path.exists():
            print(f"{path} not found; run scripts/marketcap_study.py first.",
                  file=sys.stderr)
            return 1
    pools = json.loads(args.pool_cache.read_text())
    candles = json.loads(args.candle_cache.read_text())

    # One row per TOKEN, not per pool. A token with several pools would
    # otherwise appear repeatedly, and its deepest pool is the one that
    # represents it.
    by_token: dict[str, dict] = {}
    skipped_no_data = 0

    for address, raw in candles.items():
        attributes = pools.get(address) or {}
        price_now = number(attributes.get("base_token_price_usd"))
        fdv_now = number(attributes.get("fdv_usd"))
        if not raw or len(raw) < 2 or not price_now or not fdv_now:
            skipped_no_data += 1
            continue
        supply = fdv_now / price_now
        series = [
            (ts, close * supply, close, volume)
            for ts, _o, _h, _l, close, volume in raw if close > 0
        ]
        if not series:
            skipped_no_data += 1
            continue

        peak_cap = max(c for _, c, _, _ in series)
        if peak_cap < args.threshold:
            continue

        crossing = next(i for i, (_, c, _, _) in enumerate(series) if c >= args.threshold)
        entry_price = series[crossing][2]
        entry_cap = series[crossing][1]
        forward = series[crossing:]
        peak_row = max(forward, key=lambda r: r[2])

        total_volume = sum(v for _, _, _, v in forward)
        realisable = None
        if total_volume > 0:
            running = 0.0
            for _, _, price, volume in sorted(forward, key=lambda r: -r[2]):
                running += volume
                if running >= total_volume * 0.1:
                    realisable = price / entry_price
                    break

        name = token_name(attributes.get("name"))
        row = {
            "token": name,
            "pool": address,
            "pool_name": attributes.get("name"),
            "crossed_on": datetime.fromtimestamp(
                series[crossing][0], timezone.utc).strftime("%Y-%m-%d"),
            "entry_cap": entry_cap,
            "ath_cap": peak_cap,
            "ath_on": datetime.fromtimestamp(peak_row[0], timezone.utc).strftime("%Y-%m-%d"),
            "days_to_ath": len([r for r in forward if r[0] <= peak_row[0]]) - 1,
            "peak_multiple": peak_row[2] / entry_price,
            "realisable_multiple": realisable,
            "cap_now": series[-1][1],
            "drawdown_from_ath": 1 - (series[-1][1] / peak_cap) if peak_cap else None,
            "is_runner": peak_cap >= args.runner_cap,
            "reserve_now": number(attributes.get("reserve_in_usd")),
        }
        prior = by_token.get(name)
        if prior is None or (row["reserve_now"] or 0) > (prior["reserve_now"] or 0):
            by_token[name] = row

    rows = sorted(by_token.values(), key=lambda r: -r["ath_cap"])
    if not rows:
        print("no token crossed the threshold in the cached history", file=sys.stderr)
        return 1

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    runners = [r for r in rows if r["is_runner"]]
    multiples = [r["peak_multiple"] for r in rows]
    realisables = [r["realisable_multiple"] for r in rows if r["realisable_multiple"]]

    lines = [
        f"# Tokens that reached {money(args.threshold)}",
        "",
        f"Every token in the tracked universe whose reconstructed market cap crossed "
        f"**{money(args.threshold)}**, with where it peaked afterwards. "
        f"Generated by `scripts/runner_table.py`.",
        "",
        f"- **{len(rows)} tokens** crossed {money(args.threshold)}",
        f"- **{len(runners)} ({len(runners)/len(rows):.0%})** went on to "
        f"{money(args.runner_cap)} or more",
        f"- Median peak multiple from the crossing: "
        f"**{statistics.median(multiples):.2f}x**",
        (f"- Median *volume-backed* peak multiple: "
         f"**{statistics.median(realisables):.2f}x** "
         f"(n={len(realisables)})") if realisables else "",
        "",
        "## Read this before reading the table",
        "",
        "**Survivorship.** These are pools an aggregator lists *today*. A token "
        "that crossed the threshold and collapsed into obscurity is absent — not "
        "because it did not happen, but because nothing tracks it now. The "
        "multiples below are therefore an optimistic sample. This table answers "
        "*what did the ones that made it do*, not *what happens if you buy at "
        f"{money(args.threshold)}*.",
        "",
        "**Reconstructed cap.** Supply is inferred as `fdv_now / price_now` and "
        "assumed constant. A token that minted after launch has its early cap "
        "overstated, which makes its crossing look earlier and its multiple "
        "smaller. This is FDV, not circulating.",
        "",
        "**Peak vs realisable.** *Peak* is the highest close. *Realisable* is the "
        "highest price at or above which a tenth of the post-crossing volume "
        "traded — a price the market demonstrably absorbed size at. Where the two "
        "diverge sharply, the peak was a wick nobody could have sold into.",
        "",
        f"## The table (top {min(args.top, len(rows))} by all-time high)",
        "",
        "| # | Token | Crossed | ATH cap | ATH date | Peak x | Realisable x | "
        f"Days to ATH | Now | {money(args.runner_cap)}+ |",
        "|---:|---|---|---:|---|---:|---:|---:|---:|:--:|",
    ]
    for index, row in enumerate(rows[: args.top], start=1):
        realisable = (f"{row['realisable_multiple']:.1f}x"
                      if row["realisable_multiple"] else "—")
        lines.append(
            f"| {index} | **{row['token']}** | {row['crossed_on']} | "
            f"{money(row['ath_cap'])} | {row['ath_on']} | "
            f"{row['peak_multiple']:.1f}x | {realisable} | "
            f"{row['days_to_ath']} | {money(row['cap_now'])} | "
            f"{'yes' if row['is_runner'] else 'no'} |"
        )
    lines += [
        "",
        f"Full listing, all {len(rows)} tokens: `data/runners.csv`.",
    ]
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(l for l in lines if l is not None) + "\n")

    print(f"\n  {len(rows)} tokens crossed {money(args.threshold)}; "
          f"{len(runners)} reached {money(args.runner_cap)}+ "
          f"({len(runners)/len(rows):.0%})", file=sys.stderr)
    print(f"  median peak multiple {statistics.median(multiples):.2f}x", file=sys.stderr)
    if realisables:
        print(f"  median realisable    {statistics.median(realisables):.2f}x",
              file=sys.stderr)
    print(f"  skipped {skipped_no_data} pools without usable data", file=sys.stderr)
    print(f"\nwrote {args.out_csv} and {args.out_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
