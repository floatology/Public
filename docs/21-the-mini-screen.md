# The mini screen

A small, self-contained filter for the $100k–$400k band. Separate from the
trading work in `docs/13–19`, and much simpler than any of it.

**What it does:** takes the ~24% of coins in that band that hold at least half
their value over a fortnight, and raises that to **73%**.

**What it does not do:** tell you which of the survivors goes up. Nothing
measured in this project does that, and `docs/18` says so at length.

---

## The screen, in full

| # | Criterion | Threshold | Why |
|---|---|---|---|
| 1 | Market cap | **$100k – $400k** | the band asked for |
| 2 | **Liquidity ÷ market cap** | **≥ 0.20**, and higher is better | the entire screen |
| 3 | Absolute liquidity | **≥ $25k** | at $20k of depth a $500 trade cost 96% |

That is the whole thing. Criterion 2 does essentially all the work, and
criterion 3 matters only because the ratio can be satisfied by a very small pool
against a very small cap.

### Criterion 2, swept rather than chosen

| liquidity ÷ cap | coins kept (of 328) | survived | 95% CI |
|---|---:|---:|---|
| ≥ 0.05 | 321 | 23.1% | 18.8–28.0% |
| ≥ 0.15 | 318 | 23.0% | 18.7–27.9% |
| **≥ 0.20** | **92** | **72.8%** | 63.0–80.9% |
| ≥ 0.25 | 89 | 73.0% | 63.0–81.2% |
| ≥ 0.30 | 84 | 76.2% | 66.1–84.0% |
| ≥ 0.35 | 76 | 78.9% | 68.5–86.6% |
| ≥ 0.40 | 50 | 86.0% | 73.8–93.0% |
| ≥ 0.50 | 31 | 87.1% | 71.1–94.9% |

**There is a cliff between 0.15 and 0.20.** Below it the screen does nothing at
all — 23% survival is the base rate. At 0.20 it triples.

Above the cliff the gain continues smoothly: 72.8% → 76.2% → 78.9% → 86.0%. That
smoothness is what makes it credible. A criterion that spiked at one cut and fell
away either side would be fitting noise; a cliff followed by a monotone slope is
a real relationship with a real threshold in it.

**So: 0.20 is the gate. 0.25 is a fine round number and costs three coins out of
92. Above 0.40 you are buying survival with opportunity — 86% but only 50 coins
of 328.**

### What "liquidity ÷ market cap" actually means

It reduces algebraically to **the fraction of total supply sitting in the pool**.
A coin at 0.18 has 82% of its supply held outside the pool — an overhang that can
be sold into it. A coin at 0.40 has far less available to dump.

That is why the threshold is sharp rather than gradual: it is measuring
something structural about how the token was launched, not a market mood.

---

## A correction: round-tripping does not work as a criterion

I previously flagged "are holders round-tripping?" as a second filter, on a
68.8%-against-14.3% split. **Tested properly, it does not hold.**

| round-trip share ≤ | coins kept | survived |
|---|---:|---:|
| 0.05 | 304 | 25.7% |
| 0.10 | 324 | 24.1% |
| 0.15 | 326 | 23.9% |
| 0.30 | 328 | 23.8% |

Every cut returns the base rate. The reason is in the distribution: **median
round-trip share is 0.007 and the 90th percentile is 0.045.** Essentially every
coin is already below any sensible gate, so there is nothing for it to exclude.
The earlier figure came from a median split inside a small subgroup, where the
"high" half was fourteen coins sitting above 0.007 — which is not a threshold
anyone could screen on.

Combined with criterion 2 it removes **zero** coins: 92 pass at any round-trip
cut.

---

## What else was tested and does not add

Inside the 92 coins that pass criterion 2, only liquidity keeps separating:

| metric | low half | high half | gap |
|---|---:|---:|---:|
| **liquidity ÷ cap** | 61.7% | **84.4%** | **+22.7pp** |
| trade count | 78.7% | 66.7% | −12.1 |
| repeated amounts | 76.6% | 68.9% | −7.7 |
| wash score | 70.2% | 75.6% | +5.3 |
| median trade size | 70.2% | 75.6% | +5.3 |
| market cap within band | 70.2% | 75.6% | +5.3 |

None of these has a separated confidence interval. They looked strong in the
raw comparison because they are all correlated with liquidity; once it is
controlled they are noise.

**This includes the counterintuitive trade-count effect.** Across all 328 coins,
high trade count predicted death (56.4% → 3.6%). Inside the passing group it is
−12pp and not significant. Trade count was measuring thin pools, not churn
directly.

---

## Sanity checks to run anyway

These are not survival criteria — none of them separated — but each prevents a
specific, expensive mistake and costs one look:

- **Volume ÷ liquidity above ~10.** The wash signature. 32 of the 60 busiest
  pools on this chain fail it, one at 1,139× its $3,709 of reserves.
- **Contract not verified, or holding live mint/pause.** A filter, never a
  predictor.
- **Ticker matches a stock token.** 24 contracts claim `NVDA`; one is real.

---

## Limits

**The liquidity figure is derived from V3 pool depth, not an aggregator's
"Liquidity" field.** They are the same order of magnitude and not the same
number. Before using 0.20 against DexScreener, calibrate on a handful of coins
visible in both — the threshold may move.

**V3 only, twelve weeks, one chain, 328 coins.** V2 has no archived reserves and
V4 is unmeasured.

**Survival is ≥0.5× after 14 days.** A different horizon or a different bar
would move the numbers, though the cliff at 0.20 is a structural feature and
unlikely to move much.
