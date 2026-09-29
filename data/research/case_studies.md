# Step 4 — case studies: what the 14 biggest breakouts in established coins looked like beforehand

Raw per-case tables: `case_studies_raw.md` (scripts/research_cases.py). Each
case is the biggest >=2x leg in its token where the token was at least 48h old
at the trough (launch-hour legs are a different game, analysed separately).

## The recurring shapes

**1. The lead-in is usually a decline, not a base.** In 10 of 14 cases the
72h before the trough was a slide: price 72h earlier was 1.2x-4x the trough
(HOODRAT 4.0x, KITSU 1.9x, HOOKR 2.0x, JUGGERNAUT 1.8x, HMM, POOH, TAMPONS,
CPU, GIWA 1.4x). The breakouts start from a fresh local low after a
multi-day fade, not from a tight coil near the highs. Only Agrippa, POOLS and
WOOF rose into the trough window (POOLS was already up ~3x off its prior low).

**2. Two very different volume archetypes.**

- **Dormant wake-up** (WOJAK, CPU, GIWA, KITSU, POOH late): 24-72h of
  near-zero volume (WOJAK literally $0 for 60h, GIWA under $700 per 12h),
  then volume reappears. The move follows the first sign of life. GIWA:
  $291 -> $14.7k -> $146k per 12h; price 1.03x -> 1.17x -> 10.8x.
- **Active-coin ignition** (POOLS, WOOF, TYGR, Agrippa): a volume explosion of
  10-40x the trailing rate right at the trough, driven by first-time buyers
  (POOLS: 1,774 of 2,139 buyers in the 12h at the trough were new; TYGR: 1,672
  of 2,203). The surge is coincident with the start of the move, but the move
  is so large (18x-380x) that catching it hours late still leaves 2x+.
- A third group (HMM, HOODRAT, HOOKR, JUGGERNAUT) had steady, heavy two-way
  volume with no clear change before the turn — no flow signature at all.

**3. Buy share is useless.** Buy % of volume sat at 44-56% before almost every
breakout; routers and bots trade both sides, so the $ split carries no signal.

**4. New-wallet inflow is the most visible flow change** — but mostly at, not
before, the trough. Where it leads (WOOF: new buyers 15 -> 113 -> 359 per 12h
into the trough; TAMPONS: 8 -> 72 -> 213 after), it leads by 12-24h.

**5. "Smart" wallets show up, but so do busy ones.** Several top pre-breakout
buyers had caught earlier 2x legs early: Agrippa's top buyers had 8, 5, 4
earlier catches; HOODRAT's had 3 and 2; TAMPONS's top 8 all had 1-2; HMM's
had 1-6. But a wallet that trades 50 tokens will "catch" many by chance
(HMM's 0x0000…031c traded 51 tokens). Catches must be normalised by how
many tokens the wallet touches — tested in step 6.

**6. Early buyers sell into the run.** Most top pre-trough buyers sold 2-30x
their buy size during the leg (JUGGERNAUT's 0x6d8a bought $2.7k, sold $281k).
They are position traders with a thesis, not bag-holders — and their selling
is what caps later legs (the WALLET pattern of the last two days).

**7. Coordinated first-time buyers.** In the active ignitions a large share of
first-time buyers bought in the same block as another first-timer (POOLS
575/2,042 = 28%; Agrippa 390/1,848 = 21%; TYGR 140/688 = 20%), far above the
0-3% seen in the steady coins (HMM 0/374, HOODRAT 4/573, WOOF 4/639). At ~10
blocks/second, independent buyers rarely share a block; this looks like
bundled buys (bots or one operator spreading across wallets) — the
"engineered run" signature from the literature (H5).

## Hypotheses carried into steps 5-6

| id | hypothesis (all computed at hour t from data up to t) |
|---|---|
| A | Dormant wake-up: <$500 volume in the prior 48h, then >= $2k in the last 6h |
| B | Volume surge: last-6h volume >= 5x (and 10x) the trailing 72h hourly rate |
| C | New-wallet surge: first-time buyers in the last 6h >= 5x trailing rate |
| D | Pullback reversal: price 30%+ below its 7-day high, then +20% off the 72h low |
| E | Smart-wallet entry: >= N wallets with prior early catches (normalised) net-buying in the last 6h |
| F | Bundled first-time buyers: >= 15% of first-time buyers in the last 6h share a block |
| G | Combinations of the above, plus activity/age filters |
