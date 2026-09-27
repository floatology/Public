# Overnight plan (started 2026-09-27 ~16:40 UTC)

Asked for: build the Tier 1 screen and test the pre-breakout pattern; gather
baseline data on more coins to find which filters (age, market cap, liquidity,
other) cut the noise; do NOT analyse the six watchlist coins until the end,
then refresh and analyse them with the overnight data.

**Resume rule:** on any check-in, read this file, check `ps` for running jobs
and `data/tokens/STATUS.md` / `data/overnight/LOG.md`, commit+push anything
complete, then continue with the first unchecked step. Never run two bulk RPC
scans at once (the node rate-limits globally). Tick steps here as they finish.

## Steps

- [x] 1. Six-coin build (track_tokens.py build) finishes; commit archives.
         No analysis yet.
- [ ] 2. Universe + daily candles from GeckoTerminal (scripts/gt_history.py,
         running in background, log data/overnight/gt.log; resumable — rerun
         `gt_history.py candles` if it died). REVISED: a raw chain-wide swap
         scan was measured at >430k V3 and >430k V4 swaps/day, far too big;
         GT candles cover every tracked pool incl. V4 at one call per pool.
- [ ] 3. Flow backtest on existing per-trade archives (data/parquet/trades*.parquet,
         4,836 V2/V3 pools to 21 Sep): net flow, $2k+ buy clusters,
         absorption (tokens leaving pool) before breakouts vs base rate.
- [ ] 4. Supply per token (fdv/price from GT; token_supply.json cache).
- [ ] 5. Daily bars per token from the candles (all pools combined).
- [ ] 6. Backtest: pre-breakout signals (dry-up, ignition, absorption, higher
         lows, held pullback) vs forward outcomes, against base rates, with a
         token-and-time split. Criteria study: base rates by age, market cap,
         liquidity, volume.
- [ ] 7. Live Tier 1 screen on today's data.
- [ ] 8. Write docs/25 with results and the recommended filters.
- [ ] 9. Refresh the six coins (track_tokens.py build), run watch_wallets.py
         and analyse_all.py, summarise.
