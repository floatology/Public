# Conclusions From the Data So Far

**Date:** 2026-09-20
**Basis:** full-chain census (715,343 pool creations), two 1,200-pool stratified samples, one
full stock-token snapshot (174 tokens), and live execution measurements.

This is what the measurements actually support — separated from what the master document assumed
and from what remains untested.

---

## 1. The single most important finding: execution cost dominates everything

Round-trip cost for a $500 clip, measured live through a routing aggregator:

| Pool reserves | Round-trip cost |
|---:|---:|
| $2,410,406 (BONER) | **0.90%** |
| $36,325 (VIAGRA) | 7.82% |
| $25,546 (WET) | 10.73% |
| $19,544 (INUT) | **96.10%** |

**Four orders of magnitude of variation, and the curve is brutally non-linear.** A token with
$20k of liquidity costs 96% of your stake to enter and exit. No signal, holding period or exit
rule survives that.

This reframes the entire project. The master document defines every outcome on price and never
asks whether the price was reachable. **Most of what looks like a winner on a chart is not a
winner you could have had.** Any base rate quoted below is a *price* rate and an upper bound on
the tradable rate.

It also probably explains the prior art's headline result. `robinhood-screener` found its best
exit policy was "sell immediately" at **−3.45%**, calling that "the round-trip cost." On the thin
tokens a launch screener surfaces, −3.45% is optimistic by an order of magnitude.

---

## 2. The two DEX strata are different populations and must not be pooled

The V2 rate was measured first, with an explicit caveat that generalising to V3 was an open
question. It was right to flag: **the strata differ significantly (z = 3.28, p < 0.01).**

| | V2 | V3 |
|---|---:|---:|
| Quote-paired population | 266,465 | 441,582 |
| **Ever trades meaningfully** | **4.8%** | **43.5%** |
| **Reaches 10× given it trades** | **21.05%** | **7.85%** |
| **Reaches 10× overall** | **1.000%** | **3.420%** |
| 95% CI | 0.573–1.740% | 2.531–4.606% |
| Median peak/launch | 4.08× | 1.38× |
| p90 peak/launch | 49.4× | 7.09× |

The profiles are close to opposite. **V2 pools almost never trade, but moonshot when they do.
V3 pools usually trade, but rarely moonshot.** Why is unknown and worth understanding before any
model is trained across both — it may reflect different launch venues, different deployer
populations, or simply that V3 is where routine liquidity sits and V2 is the memecoin long tail.

**Population-weighted chain-wide positive rate: ~2.5%.** The V2-only figure understated it by
2.5×, which is exactly the error that pooling-by-assumption would have produced in the other
direction.

**Practical consequence for sampling:** V3 yields **435 measurable pools per 1,000 sampled against
V2's 48 — 9.2× more efficient per unit of scan time.** Any future H0 work should sample V3 first.

---

## 3. Most "liquidity" on this chain is not real

Two independent measurements point the same way.

**Stock-token lockup.** Of 174 canonical stock tokens, **113 (65%) carry more than 50% of their
memecoin-paired reserves in pools with zero 24-hour volume.** USAR looked like the strongest
candidate on the chain at 99.0% lockup on $10.2M — until 98% of it turned out to sit in a single
`tornadoes / USAR` pool holding $9.75M at zero volume. Live-filtered: 69.3% on $244k.

**Stock-token pricing.** **95 of 174 (55%) have under $50,000 of stable-pool depth**, which is
below the level at which a quoted price means anything. Before that filter, the universe showed
an apparent **+151% premium on AMAT** — from a pool holding $5,669.

The lesson generalises: **on this chain, a reserve figure is not evidence of a market.** Any
metric that weights by nominal reserves without a liveness check will rank seeded pools first —
which is precisely what happened here before the guard was added.

---

## 4. The stock-token premium thesis is dead; the mechanism behind it survives

Measured across 79 adequately-liquid stock tokens: premiums run **−4.32% to +5.89%, median
−0.04%**. On a Saturday with US markets closed — the exact condition that produced the 360%
BONER/HIMS dislocation.

And even where a dislocation exists, it is not capturable: Robinhood's documentation restricts
minting to Authorised Participants, of which **there is exactly one (BBVI)**. Profiting from a
premium requires creating and selling supply. That is structurally closed to a retail participant,
which is why BBVI — not a trader — collected the BONER/HIMS spread.

**What survives is the causal direction.** BONER did not rise because HIMS went to a premium; it
locked HIMS in its own pool and *caused* the premium, and BONER ran ~1,000%. So float lockup is
worth tracking as a leading signal on the *memecoin*, not as an arbitrage on the stock token.
Current genuine leaders: **NVDA 77.3%** (11 pairs, 0% dormant), MU 73.4%, QQQ, AAPL, HIMS 55.5%.
Control: SPY at 5.1%.

That hypothesis (H1) is now accruing data and **cannot be backtested** — no free source carries
historical liquidity composition, so the series only exists forward from 2026-09-20.

---

## 5. What is now known about feasibility

**Data access is solved and free.** The official RPC serves unauthenticated archive `eth_getLogs`
back to block 1. The full 715,343-pool census takes ten minutes. Dune's paywall and SQD's absence
turned out not to matter, and **no database or paid service is required** for anything this
project produces.

**Sample size does not bind.** 50 positives per discovery/confirmation half needs roughly 10,000
V2 pools (~7h) — or far fewer V3 pools given the 9.2× efficiency.

**Statistical power does bind, and this is the binding constraint.** At the current V2 n=57 the
minimum detectable difference is **±21 percentage points** — a doubling of the base rate. The V3
sample at n=522 is far better placed. For reference, the sniper-cohort paper's **+16.1% relative**
lift is roughly 3.4pp absolute against a 21% base — **below even an n=500 floor**. Literature-scale
effects need thousands of measurable pools, which is now affordable but must be planned rather
than discovered after an underpowered null is misread as "no effect".

---

## 6. What this does not show

Stated plainly, because the temptation to over-read a good-looking number is the main risk here:

- **Nothing about whether any signal predicts anything.** Every number above is a base rate or a
  cost. H0 and H1 are both untested.
- **Nothing tradable.** All positive rates are computed on printed prices. Given §1, the tradable
  rate is materially lower by an unknown factor.
- **Nothing about V4 or the other protocols.** The census found **272 distinct factories**, not
  the eight visible through aggregators. V2 and V3 are the two measured; V4 hooks can alter swap
  maths arbitrarily and are unhandled.
- **Nothing about causation anywhere.** No causal design has been run. The graduation-threshold
  regression discontinuity proposed in the critique remains the best available and is unbuilt.

---

## 7. Honest assessment of the original thesis

The master document's core bet is **multi-day accumulation-to-breakout on memecoins**. Nothing
measured so far supports or refutes it, but three findings make it harder than the document
assumes:

1. **Execution cost on thin tokens is catastrophic**, and thin tokens are where a launch screener
   looks. The document has no execution model at all.
2. **The population is more heterogeneous than one model can span.** Two strata differ
   significantly; there are 272 factories; V4 hooks are arbitrary.
3. **The prior art measured negative expectancy on the nearest comparable system**, and its
   rebuild independently hit the same look-ahead bias this project was warned about.

Against that, the document's instincts hold up well: forensics over TA, buyer-identity over
deployer-identity, rug-filter and runner-predictor as separate tools, statistical rigour as
non-negotiable. Those were right.

**The most valuable thing built so far is not a signal — it is the measurement apparatus that can
tell a real one from an artefact.** Three separate bugs in this session each produced a confident,
wrong, *exciting* number: inverted prices (median 22,668×), dust-contaminated launch prices (p99
8.8e18, which passed a 60-pool smoke test), and reserve-weighted lockup ranking a dead pool first.
Every one would have been believed without a cross-check.

That is the actual lesson for what comes next: on this chain, **assume any striking result is an
artefact until a second, independent measurement agrees.**
