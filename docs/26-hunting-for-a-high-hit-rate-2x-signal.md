# 26 — Hunting for a high-hit-rate 2x signal (overnight study, 29-30 Sep 2026)

*Draft — being filled in as the overnight run progresses. Plan and log:
`data/overnight/RESEARCH_PLAN.md`. All numbers reproducible from
`scripts/research_*.py`.*

**Question.** docs/25 found price/volume patterns with 1.4-1.8x lift and
wallet signals with 1.05-1.07x. The ask: find something with a genuinely
high hit rate for a 2x or more — study the biggest rallies one by one, find
what came before each, and test every candidate across all coins.

**Data.**
- 65 tokens with full per-trade ledgers (6.43M attributed trades, Jun-Sep
  2026), turned into 59,355 token-hours of VWAP bars (`research_build.py`).
- The daily-candle universe: 4,029 tokens including delisted census coins
  (`candle_backtest.build_series`).
- 252 up-legs of 2x+ found by zigzag on hourly VWAP; 185 of them in coins at
  least two days old (the rest are launch-hour moves) (`research_events.py`).

**Method (the honesty rules).** Every feature at hour *t* uses only trades up
to the end of hour *t*; outcomes are measured from the **next** hour's VWAP.
Events are de-duplicated (one per token, then 72h cool-off). Each signal is
compared with the base rate of coin-hours with the same age and 24h volume.
Every result is split by time (median hour, 1 Sep) and by token (hash halves)
— a real signal has to hold on both halves.

## What the literature says (step 1)

See `data/research/literature.md`. The main new lever suggested by research
is *who* is buying — wallets with a track record, or coordinated fresh
wallets — rather than the price shape. Also: in small, illiquid coins
short-horizon returns tend to mean-revert, and most launches lose money for
ordinary buyers, so base rates are harsh.

## What the biggest breakouts looked like (step 4)

See `data/research/case_studies.md`. The short version:
1. The lead-in is usually a multi-day **decline** to a fresh low, not a tight
   base near the highs.
2. Two volume archetypes: **dormant wake-up** (no volume for 1-3 days, then
   the first real trading) and **active-coin ignition** (a 10-40x volume
   explosion driven by a flood of first-time buyers, coincident with the
   start of the move).
3. Buy share of volume is ~50% before every move — useless.
4. The best pre-breakout buyers sell into the run.

## Results so far (step 6, first pass)

| signal | events | tokens | 2x within 72h | lift | holds out of sample? |
|---|---|---|---|---|---|
| base (established coins) | 815 | 53 | 18% | 1.0x | — |
| "smart" wallets (>= 2 earlier early catches) | 343-630 | 39-52 | 19-23% | 1.0-1.3x | no edge |
| bundled first-time buyers | 95-170 | 36-42 | 23-25% | ~1.0x | no edge, more crashes (37-40%) |
| volume surge >= 20x trailing rate | 45 | 26 | 47% | 1.95x | yes, weaker after 1 Sep (31%) |
| quiet-coin wake-up (hourly) | 9 | 9 | 78% (89% in 7d, 0% crash) | 2.7x | too few events; 7 of 9 before 1 Sep |

**Daily universe (4,029 tokens):** the wake-up pattern is regime-dependent —
2-3x lift before 31 Aug, 0.2-0.4x after. Volume surges hold at ~1.6x across
both halves.

*(Sections below to be completed: regime filter, profit-based smart wallets,
buyer breadth, combinations, final verdict, live screen.)*
