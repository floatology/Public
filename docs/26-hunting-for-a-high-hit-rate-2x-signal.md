# 26 — Hunting for a high-hit-rate 2x signal (overnight study, 29-30 Sep 2026)

*Plan and running log: `data/overnight/RESEARCH_PLAN.md`. Every number here is
reproducible from `scripts/research_*.py`; detailed tables are in
`data/research/`.*

**Question.** docs/25 found price/volume patterns with 1.4-1.8x lift and
wallet signals with 1.05-1.07x. The ask: find something with a genuinely high
hit rate for a 2x or more — study the biggest rallies one by one, find what
came before each, and test every candidate across all coins.

## Data

- **Hourly, with wallets:** 65 tokens with full per-trade ledgers — 6.43M
  attributed trades, Jun-Sep 2026 — turned into hourly VWAP bars
  (`research_build.py`). Caveat: these coins were partly chosen *because*
  they ran (the watchlist coins and the batch-2 "cases"), so their base rates
  are inflated.
- **Daily, unbiased:** 4,029 tokens with daily candles, delisted coins
  included (`candle_backtest.build_series`).
- **Hourly, unbiased** *(fetching overnight)*: GeckoTerminal hourly candles
  for the main pool of all 1,162 tokens that ever had 3+ days of $1k+ volume
  (`gt_hourly.py`).
- **Events:** 252 up-legs of 2x+ (zigzag on hourly VWAP); 185 in coins at
  least two days old, 31 of them 10x+ (`research_events.py`, `events.csv`).

## Method — the honesty rules

- No lookahead: features at hour *t* use trades up to the end of *t*; the
  entry is the **next** hour's VWAP.
- Outcomes on prices people actually traded at (VWAP / closes with volume),
  not single-print wicks. 2x = within 72h (and 7 days); crash = halves first.
- One event per token per 72h (no double counting a single run).
- Lift is measured against coin-hours of the **same age and activity**.
- Hours whose 7-day forward window runs past the archive are excluded (a
  censoring bug that first deflated late-period results; fixed).
- Validation that matches live use: **walk-forward** — retrain weekly on the
  past, score only the next week. Token splits look better but leak
  market-wide days between train and test, so they are not trusted.

## 1. What the literature says

`data/research/literature.md`. The main new lever suggested is *who* is
buying (wallets with a track record; coordinated fresh wallets), rather than
price shape. Also: small illiquid coins mean-revert at short horizons, and
most launches lose money for ordinary buyers.

## 2. What the 14 biggest breakouts looked like beforehand

`data/research/case_studies.md`.
1. The lead-in is usually a **multi-day decline to a fresh low**, not a tight
   base near the highs.
2. Two volume archetypes: **dormant wake-up** (no trading for 1-3 days, then
   the first real volume) and **active-coin ignition** (volume 10-40x its
   trailing rate, driven by a flood of first-time buyers, at the start of the
   move).
3. Buy share of volume sits at ~50% before every move — useless.
4. The best pre-breakout buyers sell into the run; they cap later legs.

## 3. Single signals (hourly ledger panel, established coins)

`data/research/eval.md`, `eval2.md`, `secondleg.md`. Base: 19% of
de-duplicated events see a 2x within 72h.

| signal | events | 2x in 72h | lift | verdict |
|---|---|---|---|---|
| "smart" wallets — earlier early entries (3 definitions incl. $5k/$25k realised profit elsewhere) | 300-630 | 17-23% | 1.0-1.15x | **no edge** |
| bundled first-time buyers (same block) | 95-170 | 23-25% | ~1.0x | no edge, more crashes |
| market regime hot vs cold | — | 23% vs 10% | — | raises crashes as much (38% vs 12%) |
| coin already made a 3x+ run in the last 30 days | 555 | 23% | 1.2x | weak |
| volume surge >= 20x trailing rate | 45 | 47% | 1.95x | holds, weaker after 1 Sep |
| volume surge >= 10x + more net buyers than sellers | 37 | 46% (59% in 7d) | 1.84x | **holds on all 4 splits** |
| quiet-coin wake-up | 9 | 78% | 2.7x | too few; regime-dependent in daily data |

Smart money, however defined, did not predict 2x runs here. That is a firm
negative result.

## 4. Combining everything — the walk-forward model

`data/research/walkforward.md`, `ablation.md`, `daily_model.md`.

| sample | selection | events | 2x within window | 2x in 7d | crash first |
|---|---|---|---|---|---|
| hourly ledger coins (65) | top 0.5% of scores | 18 | **61%** (72h) | 83% | 33% |
| hourly ledger coins (65) | top 1% | 33 | 52% | 73% | 30% |
| — batch-2 controls only (least hand-picked, base 9%) | top 0.5-2% | 12-17 | 33-47% | 47-54% | 31-41% |
| daily universe (4,029 coins) | top 0.5-2% | 63-223 | 20-22% (3d) | 29-35% | 47-51% |

- **Price/volume features alone do as well as everything** on the ledger
  sample; the wallet features add almost nothing. The hourly edge over the
  daily universe comes from **timing resolution**, not from on-chain wallet
  data.
- **Token age dominates**: coins 2-7 days old run far more often (ledger:
  ~40% 2x in 72h; unbiased daily: ~15% 2x in 3 days vs 8% for 2-8 week-old
  coins) — and crash more (~30%).

*(Pending: the unbiased hourly test on all 1,162 active coins decides whether
the 50-60% top-pick hit rate is real or an artefact of the hand-picked
sample. Sections 5-6 — verdict and live screen — follow when it lands.)*
