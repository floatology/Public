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

- [ ] 1. Six-coin build (track_tokens.py build) finishes; commit archives.
         No analysis yet.
- [ ] 2. Pool registry: every V2/V3 pool creation (extend pool_creations to
         head) and every V4 pool (PoolManager Initialize events), with tokens.
- [ ] 3. Chain-wide swap archive: all V2, V3, V4 Swap logs from genesis to
         head, segmented and committed per segment (data/chain/swaps/).
- [ ] 4. Token supplies (totalSupply) and an ETH/USD daily series from the
         WETH/USDG pool.
- [ ] 5. Daily bars per token (all WETH/ETH/USDG-quoted pools combined).
- [ ] 6. Backtest: pre-breakout signals (dry-up, ignition, absorption, higher
         lows, held pullback) vs forward outcomes, against base rates, with a
         token-and-time split. Criteria study: base rates by age, market cap,
         liquidity, volume.
- [ ] 7. Live Tier 1 screen on today's data.
- [ ] 8. Write docs/25 with results and the recommended filters.
- [ ] 9. Refresh the six coins (track_tokens.py build), run watch_wallets.py
         and analyse_all.py, summarise.
