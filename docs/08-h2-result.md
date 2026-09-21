# H2 Result: launch liquidity is a mechanical relationship, not a signal

**Date:** 2026-09-21
**Pre-registered:** `PREREGISTRATION.md`, committed before the test ran.
**Verdict:** the relationship is **real and replicates**, and is **largely an arithmetic identity**.
It does **not** tell you which token will run.

---

## 1. What was found

Launch liquidity is the quote-side reserve at a pool's **first `Sync` event** — the liquidity the
deployer seeded, observable at launch with no look-ahead.

Two independent 4,000-pool samples, different seeds:

| q | Median launch liquidity | 10× rate, seed 1 | 10× rate, seed 2 |
|---|---:|---:|---:|
| 1 | ~$1,100 | 16.9% | 31.9% |
| 2 | **$2,576 (1 WETH)** | **44.1%** | **45.8%** |
| 3 | ~$5,000 | 13.6% | 22.2% |
| 4 | $12,880 | 3.2% | 6.8% |

χ² = 35.05 then 29.96 on 3 df, against a 7.81 critical value. Both p < 0.001. The peak sits at
exactly 1 WETH in both samples and the floor at the top bucket in both. q1 is the unstable bucket,
moving 15 points between seeds.

## 2. Why it is mostly not a signal

If the effect were mechanical — *bigger pools need proportionally more capital to reach a given
multiple* — then **lowering the multiple should flatten the gradient**, because a smaller move
needs less capital and the size penalty shrinks. If the effect were informational, the gradient
should persist.

Re-running the identical pools at a 2× threshold:

| q | Median liquidity | 2× rate | 10× rate | 10×/2× |
|---|---:|---:|---:|---:|
| 1 | $1,030 | 91.5% | 31.9% | 0.35 |
| 2 | $2,576 | 94.4% | 45.8% | 0.49 |
| 3 | $5,095 | 57.7% | 22.2% | 0.38 |
| 4 | $12,880 | **75.7%** | **6.8%** | **0.09** |

**The gradient collapses.** Measured as the top bucket relative to the peak bucket:

- at **10×**: q4 reaches **15%** of q2's rate (45.8% → 6.8%)
- at **2×**: q4 reaches **80%** of q2's rate (94.4% → 75.7%)

That is the signature of mechanism, not information. A 10× price move requires the quote reserve
to grow by roughly √10 ≈ 3.16×, so a 5-WETH pool needs about ten times the net buying a 0.5-WETH
pool does. "Small pools reach high multiples more often" is substantially true **by construction**.

**H2 is therefore confirmed in a way that is not useful.** Launch liquidity predicts *which pools
are cheap to move*, not *which tokens will run*. Anyone reading the 10× table alone would conclude
"seed-size is a powerful predictor" and be wrong about what it predicts.

### The part arithmetic does not explain

One residual is real: **arithmetic predicts q1 should beat q2**, since q1 pools are smaller still
and cheaper to move. Both seeds show the opposite at 10×, and q1 is also the least stable bucket.
Something sits near the 1-WETH level that pool size alone does not account for — plausibly that
sub-1-WETH pools are too thin to attract any real participation. It is not established, and is
recorded as an open question rather than a finding.

---

## 3. The practically important result is the inversion

The tradable column points the **opposite way** to the raw signal. At the 2× threshold, converting
price wins into reachable ones at a $500 clip:

| q | Median liquidity | 2× price wins | 2× tradable | **Conversion** |
|---|---:|---:|---:|---:|
| 1 | $1,030 | 91.5% | 11.3% | **12%** |
| 2 | $2,576 | 94.4% | 59.2% | 63% |
| 3 | $5,095 | 57.7% | 53.5% | 93% |
| 4 | $12,880 | 75.7% | 74.3% | **98%** |

**The smallest pools convert 12% of their price wins into tradable ones. The largest convert 98%.**

So the two effects run against each other:

- Small pools **print** high multiples more often — mechanically.
- Large pools **deliver** what they print — almost always.

The raw 10× table says "hunt tiny pools." The tradable table says those wins are mostly
unreachable. Combining them, the practical read is the reverse of the naive one:

> **Chasing large multiples in thin pools is chasing prices that cannot be filled. Moderate
> multiples in deeper pools are actually capturable.**

That is consistent with everything else measured: the capacity ceiling (`docs/07` §1b), the
liquidity floor (`docs/04` §2), and the prior art's finding that its best exit policy was
liquidating immediately.

---

## 4. Process note

This result was believed only after it survived three checks, in this order:

1. **Replication on a fresh seed** — it held (χ² 35.05 → 29.96, same shape).
2. **Clustering check** — 24% of V2 pools are created in a block alongside others, at most 13 per
   block. χ² assumes independence and the critique's §4.2 warns about exactly this, so the
   statistic is somewhat inflated, though not enough to explain the effect.
3. **Threshold test** — the decisive one, and the only check that changed the interpretation.

**Steps 1 and 2 both passed while the conclusion was still wrong.** Replication confirmed the
pattern was real; it said nothing about whether the pattern was informative. Only asking *what
else would produce this shape* — and testing that directly — separated mechanism from signal.

This is the sharpest version of the session's recurring lesson. The earlier artefacts (inverted
prices at 22,668×, a p99 of 8.8e18, a dead pool ranked first on lockup) were all caught by noticing
an implausible number. **This one had entirely plausible numbers and still meant something other
than it appeared to.** A replicated, significant, well-behaved result was still not the finding it
looked like.
