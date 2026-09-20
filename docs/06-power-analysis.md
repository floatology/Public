# H0 Power Analysis

**Date:** 2026-09-20
**Input:** `data/positive_rate.json` — 1,200 quote-paired V2 pools, seed `rhc-h0-v1`.

The critique (`01-critique-and-revision.md` §4.7) flagged that the project had extensive
multiple-testing defences and **no sample-size calculation anywhere**, so it could not know whether
its confirmation half was capable of confirming anything. This is that calculation. It could not
be run until the archive RPC made the population reachable.

---

## 1. Measured base rates

| Quantity | Value |
|---|---|
| Pools sampled | 1,200 |
| Never traded meaningfully (<10 real trades) | **1,142 — 95.2%** |
| Measurable | 57 — 4.75% |
| Implausible ratio, excluded as artefact | 1 |
| Reached ≥10× launch VWAP | **12** |
| **Rate among pools that traded** | **21.05%** |
| **Rate among all pools sampled** | **1.001%**  (95% CI **0.574% – 1.741%**, Wilson) |

Peak-over-launch distribution among measurable pools: **p50 4.08×, p90 49.4×, p99 373×, max 373×.**

The ~1% figure lands squarely on the master document's cited base rate that "under 1% of new
launches ever graduate to real trading status" — reached here from primary chain data rather than
from news coverage.

---

## 2. What this costs to sample

At roughly 2.5 seconds per pool (one `eth_getLogs` call plus parsing, against the free archive
RPC):

| Target positives | Pools to sample | Scan time |
|---:|---:|---:|
| 30 | 2,998 | ~2.1 h |
| 50 | 4,996 | ~3.5 h |
| 100 | 9,992 | ~6.9 h |
| 200 | 19,983 | ~13.9 h |

`PREREGISTRATION.md` requires a discovery half and an untouched confirmation half:

- **50 positives per half → ~10,000 pools, ~7 hours.**
- **100 positives per half → ~20,000 pools, ~14 hours.**

Both are overnight jobs on free infrastructure. **Sample size is not a binding constraint on this
project**, which is worth stating plainly because the original plan assumed it would be and budgeted
paid Dune access against it.

---

## 3. What can actually be detected

Minimum detectable difference for a two-proportion test against a 21% base rate
(α = 0.05, power = 0.80):

| n per group | MDD (absolute) |
|---:|---:|
| 57 (current sample) | **±21.4 pp** |
| 200 | ±11.4 pp |
| 500 | ±7.2 pp |

**The current sample can only detect an effect that roughly doubles the base rate.** Any signal
subtler than that is invisible at n=57 — it would fail to reach significance whether or not it is
real. This is the concrete answer to "is the confirmation half capable of confirming anything":
not yet.

For context, the effect sizes in the literature this project draws on are far smaller than 21pp.
The sniper-cohort paper (arXiv 2607.02795) reports a **+16.1% relative** lift in first-30-minute
buyer count — which against a 21% base is about 3.4pp absolute, **well under even the n=500 floor**.

**Implication for H0:** to detect literature-scale effects, the sample must be in the thousands of
*measurable* pools, i.e. tens of thousands sampled. That is ~14h of scanning per arm and remains
feasible — but it must be planned for rather than discovered after an underpowered null result is
misread as evidence of no effect.

---

## 4. Two caveats that bound all of the above

### 4.1 These are printed prices, not tradable ones

The ≥10× label here is computed on price alone. `docs/04-execution-and-data-findings.md` measured
round-trip execution cost at **0.90% on a $2.4M pool and 96.10% on a $20k pool**. Most pools in
this sample are far closer to the latter.

**So an unknown but probably large fraction of these 12 "winners" could not have been traded at
anything like the price that labelled them.** The execution gate from `PREREGISTRATION.md` must be
applied before this rate is used as a *strategy* base rate. As a *population* base rate it stands.

Expect the tradable rate to be materially lower than 1.001%, which makes the sample-size
requirements above optimistic.

### 4.2 V2 stratum only

V2 pools are 268,151 of 715,343 creations (37%). V3 encodes price as `sqrtPriceX96` and needs
separate decoding; V4 hooks can alter swap maths arbitrarily. Whether the V2 rate generalises to
the other 63% is **an open question, not an assumption**. The V3 stratum is the obvious next
measurement.

---

## 5. Methodological notes

Three bugs were found and fixed while producing this number, all of which inflated it before being
caught. They are recorded because each would have produced a confident, wrong answer:

1. **Inverted prices.** Taking `token1/token0` by position ignores that Uniswap orders pairs by
   address, not role. Half the series were inverted, and an inverted collapse is indistinguishable
   from an enormous runner. First output: median peak-over-launch **22,668×**.
2. **Dust-contaminated launch prices.** A one-wei quote leg drives launch price to ~0 and the ratio
   explodes. First fix anchored the dust floor to the pool's *median* trade — which fails exactly
   where it matters, since in a pool where most trades are dust the median is dust. That version
   still produced a p99 of **8.8e18** at n=1,200 **while passing a 60-pool smoke test**. Anchoring
   to the p90 trade fixed it.
3. **No sanity bound.** An artefact ratio was silently booked as the sample's biggest winner.
   Ratios above 1e6 are now counted separately as unmeasurable.

The lesson worth carrying: **a clean smoke test on a small sample proved nothing here.** The
pathological cases are rare by construction, so they only appear at scale — which is precisely
when a wrong number is most likely to be believed.
