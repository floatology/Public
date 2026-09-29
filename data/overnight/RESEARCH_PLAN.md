# Overnight research: what precedes a 2x, with a high hit rate (started 2026-09-29 ~17:00 UTC)

**Asked for (user, going to sleep):** research known indicators of big (2x+) runs;
then deep-dive every coin we hold data on — take the big rallies one by one,
work out what the price action and flow looked like before each breakout, then
test each candidate pattern across all coins: how often it appears, how often
it is followed by a 2x, how predictable. Earlier signals only gave 1.05-1.4x
lift over base; the goal is something with a genuinely high hit rate. Several
different patterns are fine; not every one needs to match every coin.

**Resume rule:** on every check-in (hourly routine trig_018bm3JnsphnBRCuj41vUpkD
plus a ~20-min send_later chain), read this file and data/overnight/LOG.md,
commit+push anything finished, then continue with the first unchecked step.
Record progress under "Log" and tick steps as they finish. Keep all research
code in scripts/research_*.py and outputs in data/research/. Commit after each
step. If the send_later chain has lapsed, re-arm it (20 min). When every step
is done: disable the hourly routine and leave the user a morning summary.

## Rules for honest results

- No lookahead: every feature at time t uses only data up to t.
- Compare every signal to the base rate of comparable coins at the same moment
  (same activity bucket), not to all coin-hours.
- Report hit rate (precision), number of events, number of distinct tokens,
  lift, and crash rate side by side. A signal needs >= 20 events on >= 8
  tokens before it counts.
- Validate out of sample: pick patterns on the first half of time (or half the
  tokens), report the numbers on the other half. Many hypotheses are being
  tried, so an in-sample winner that does not hold out of sample is noise.
- Outcome definitions: run2x = some later close >= 2x entry within the window
  (72h and 7d); crash = close <= 0.5x first. Measure on closes, not wicks.

## Steps

- [x] 1. Literature scan: known indicators of memecoin / DEX token 2x+ runs
         (web). Write data/research/literature.md.
- [x] 2. Inventory: which tokens have per-trade ledgers (data/tokens/*/ledger.parquet),
         spans, trade counts; build hourly bars + flow features per token
         (data/research/hourly.parquet).
- [x] 3. Event table: every 2x run in the ledger tokens (start hour, peak,
         size, duration), and in the daily-candle universe.
- [x] 4. Case studies: the 8-12 biggest runs, one by one — price structure,
         volume, buyer mix, whales, new wallets, liquidity adds, bots, and
         cross-token "smart wallets" in the 72h before. data/research/case_studies.md.
- [x] 5. Hypothesis features (from 1 + 4), computed per token-hour with no
         lookahead, including cross-token smart-wallet entry signals.
- [ ] 6. Evaluate each feature and combinations: precision, lift, split
         in/out of sample. data/research/eval.md.
- [ ] 7. Daily-candle universe check for price-only patterns that survive 6.
- [ ] 8. Write docs/26 with the results and a live screen if anything holds.
- [ ] 9. Morning summary for the user; disable the routine.

## Log
- ~16:5xZ step 1 done: data/research/literature.md (8 testable claims; main new lever is WHO buys: cross-token smart wallets, coordinated fresh wallets).
- ~16:5xZ step 2 done: scripts/research_build.py -> data/research/cache/rd.duckdb (gitignored, rebuildable): 6,434,460 trades, 65 tokens, 59,355 token-hours; hourly VWAP bars + forward outcomes. Base: 18.1% of token-hours reach 2x in 72h, 29.3% in 7d; 20.5% crash first in 7d.
- ~16:5xZ step 3 done: scripts/research_events.py -> data/research/events.csv: 252 up-legs >= 2x (zigzag, 50% reversal), 67 at launch (<48h), 185 in established coins across 41 tokens (74 at 2-3x, 48 at 3-5x, 32 at 5-10x, 31 at 10x+).
- ~17:0xZ step 4 done: data/research/case_studies.md (+ _raw.md). 14 biggest established-coin legs. Lead-in usually a multi-day decline, not a coil; two volume archetypes (dormant wake-up; active-coin ignition with 10-40x volume + first-time-buyer flood); buy% useless; early buyers sell into the run; bundled first-time buyers common in active ignitions.
- ~17:0xZ step 5 done: scripts/research_features.py -> panel (features + outcomes from NEXT hour's VWAP).
- ~17:0xZ step 6 pass 1: scripts/research_eval.py -> data/research/eval.md. Smart wallets (>=2 prior early catches) ~1.0-1.1x: no edge. Bundled buyers: no edge, more crashes. Surge >=20x: 47% 2x72h (1.95x). Quiet wake-up: 78% but n=9.
- ~17:0xZ daily universe (scripts/research_daily.py -> data/research/daily_universe.md, 4,029 tokens): wake-up REGIME-DEPENDENT (to 31 Aug 2-3x lift; after 0.2-0.4x). Surge ~1.6x, steadier.
- ~17:1xZ eval pass 2 (scripts/research_features2.py, research_eval2.py -> data/research/eval2.md): profit-based smart wallets ($5k/$25k prior realised profit elsewhere) ~1.0-1.15x = NO EDGE (3rd smart-money definition to fail). Regime (market heat from daily universe) raises both 2x (10%->23%) and crash (12%->38%). Best robust combo: surge10 + breadth6>=0.3 -> 46% 2x72h / 59% 7d / 19% crash, 1.84x, holds on all 4 splits (37 ev, 21 tok).
- ~17:1xZ model (scripts/research_model.py, research_model_inspect.py -> data/research/model.md): GBM top 0.5-2% out of sample = 39-70% 2x72h, 52-83% 7d, lift 2.9-4.7x. BUT (a) CENSORING BUG: hours near data end lack a full forward window and count as misses -> fixing in research_build.py (extend grid to archive end, exclude last 7d); (b) age_h dominates (48-96h coins: 42% 2x72h vs 9% for 720h+) -> may be SELECTION BIAS (ledger tokens partly chosen because they ran). MUST validate age + model on the unbiased daily universe (4,029 tokens) next.
- ~17:3xZ censoring fixed (research_build.py: grid extended to archive coverage end from meta.json; panel keeps only hours with a full 7d forward window). Hourly model re-run: time split top 0.5% = 60% 2x72h / 80% 7d / 0% crash (10 ev) but top 2% only 25%.
- ~17:3xZ daily universe model (research_daily_model.py -> daily_model.md): young coins 1-7d ~15% 2x in 3d (vs 8% at 2-8 weeks), crash ~32%. Token splits look great (41-63% top 1%) but TIME split (the realistic one) only 14-21% with ~50% crash: token splits leak market-wide days.
- ~17:4xZ WALK-FORWARD (research_walkforward.py -> walkforward.md; weekly retrain, score next week): hourly ledger top 0.5% = 61% 2x72h / 83% 7d / 33% crash (18 ev, 13 tok, 7 wks); top 1% = 52/73/30 (33 ev). Daily universe top picks = 20-32% 2x3d, ~50% crash. NEXT: ablation (price/volume-only vs flow features) + controls-only subset to separate selection bias from data richness; second-leg hypothesis; then write docs/26.
