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

- [ ] 1. Literature scan: known indicators of memecoin / DEX token 2x+ runs
         (web). Write data/research/literature.md.
- [ ] 2. Inventory: which tokens have per-trade ledgers (data/tokens/*/ledger.parquet),
         spans, trade counts; build hourly bars + flow features per token
         (data/research/hourly.parquet).
- [ ] 3. Event table: every 2x run in the ledger tokens (start hour, peak,
         size, duration), and in the daily-candle universe.
- [ ] 4. Case studies: the 8-12 biggest runs, one by one — price structure,
         volume, buyer mix, whales, new wallets, liquidity adds, bots, and
         cross-token "smart wallets" in the 72h before. data/research/case_studies.md.
- [ ] 5. Hypothesis features (from 1 + 4), computed per token-hour with no
         lookahead, including cross-token smart-wallet entry signals.
- [ ] 6. Evaluate each feature and combinations: precision, lift, split
         in/out of sample. data/research/eval.md.
- [ ] 7. Daily-candle universe check for price-only patterns that survive 6.
- [ ] 8. Write docs/26 with the results and a live screen if anything holds.
- [ ] 9. Morning summary for the user; disable the routine.

## Log
