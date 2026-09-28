# Overnight plan (started 2026-09-27 ~16:40 UTC)

Asked for: build the Tier 1 screen and test the pre-breakout pattern; gather
baseline data on more coins to find which filters (age, market cap, liquidity,
other) cut the noise; do NOT analyse the six watchlist coins until the end,
then refresh and analyse them with the overnight data.

**Resume rule:** on any check-in, read this file, check `ps` for running jobs
and `data/tokens/STATUS.md` / `data/overnight/LOG.md`, commit+push anything
complete, then continue with the first unchecked step. Never run two bulk RPC
scans at once (the node rate-limits globally). Tick steps here as they finish.

## Live state (update as things change)

- Candles: `data/overnight/run_candles.sh` (resumable). Order: 1,839 liquid
  pools, then 1,896 census-only pools, then 1,555 dust. ~11 pools/min.
- Batch build: `data/overnight/run_batch.sh` builds all registered tokens
  except the six (resumable; tokens over 600k transfers/segment are skipped).
- NEVER edit data/tokens/tokens.json while a build runs: the build rewrites it
  from memory after every token.
- Queued after the batch: `track_tokens.py reprice` (the running batch has the
  old per-pool pricing loaded; reprice fixes its ledgers without rescanning).
- RUNNING: data/overnight/run_batch2.sh (builds batch 2 + U, reprices, runs wallet
  backtests; rerun it if it died). Batch 2 (case-control, data/overnight/batch2.json): 20 coins that
  had a 2x run with 14d of history before it, 20 equally active coins that
  never did. After batch 1 + reprice: `track_tokens.py add $(python3 -c
  "import json;d=json.load(open('data/overnight/batch2.json'));print(' '.join(d['cases']+d['controls']))")`
  then data/overnight/run_batch.sh, then reprice. Then wallet_signals_backtest
  --horizon 14 and 7, and a case-vs-control comparison.
- Also queued: `track_tokens.py add U` (now picks up its
  PancakeSwap V3 pool) and rebuild U.
- Launch jobs via the scripts above, not inline: `pkill -f`/`grep` on a
  command line that contains the same text kills the calling shell.

## Findings so far

- Flow backtest (old V2/V3 archive, to 21 Sep): 99% of token-days are dead.
  Among active coins (>= $1k/week), base: 16% reach 2x in 14d, 8.6% halve.
  Volume dry-up: 26% 2x, 6.8% crash (1.58x lift, no extra crash risk),
  consistent across time and token splits. Absorption and breakout days lift
  2x AND crash about equally: they predict size of move, not direction. The
  full WALLET-shaped SETUP almost never occurs (7 events, 0 runs).

- Candle backtest, PARTIAL (598 liquid tokens, survivors only; delisted
  coins still downloading, so base rates are inflated). Outcomes now on
  CLOSES: highs gave a 38.5% "2x in 14d" base, driven by single-fill wicks
  on thin pools. Active coins: base 30% 2x / 18% crash. BREAK (close > 20d
  high on >= 2x volume after a dry-up): 60% 2x, 49% still +50% at day 14,
  lift 1.9x / 1.77x, crash 1.3x; stable 1.80-1.90x across all four splits.
  SETUP (pre-break): 1.3-1.6x 2x with no extra crash, ~38 events. Weekly
  volume $10k-250k is the sweet spot (36-40% 2x, 3-8% crash); above $250k
  crash jumps to 24-26%. RE-RUN after the census-only pools finish.

## Steps

- [x] 1. Six-coin build (track_tokens.py build) finishes; commit archives.
         No analysis yet.
- [x] 2. Universe + daily candles from GeckoTerminal (scripts/gt_history.py,
         running in background, log data/overnight/gt.log; resumable — rerun
         `gt_history.py candles` if it died). REVISED: a raw chain-wide swap
         scan was measured at >430k V3 and >430k V4 swaps/day, far too big;
         GT candles cover every tracked pool incl. V4 at one call per pool.
- [x] 3. Flow backtest on existing per-trade archives (data/parquet/trades*.parquet,
         4,836 V2/V3 pools to 21 Sep): net flow, $2k+ buy clusters,
         absorption (tokens leaving pool) before breakouts vs base rate.
- [x] 4. Supply per token (fdv/price from GT; token_supply.json cache).
- [x] 5. Daily bars per token from the candles (all pools combined).
- [x] 6. Backtest: pre-breakout signals (dry-up, ignition, absorption, higher
         lows, held pullback) vs forward outcomes, against base rates, with a
         token-and-time split. Criteria study: base rates by age, market cap,
         liquidity, volume.
- [x] 7. Live Tier 1 screen on today's data.
- [~] 8. Write docs/25 (drafted with candle + flow results; ADD wallet-level results after batch 2) with results and the recommended filters.
- [ ] 9. Refresh the six coins (track_tokens.py build), run watch_wallets.py
         and analyse_all.py, summarise.
- 2026-09-28: user decided NOT to add a neckline/trendline-reclaim pattern to the screen. Don't propose it again.
- 2026-09-28 02:05Z: hourly keep-alive routine trig_018bm3JnsphnBRCuj41vUpkD (:05 past each hour) replaces overnight resumes 6-8; it restarts run_batch2.sh if dead and disables itself when all steps are done or after 2026-09-29T00:00Z.
- 2026-09-28 04:30Z: TAMPONS transfers FAILED mid-scan (resumable). After run_batch2 finishes, rerun `track_tokens.py build --only TAMPONS` before the wallet backtest results are final, then commit its dir.
