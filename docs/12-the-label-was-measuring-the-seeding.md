# The cross-sectional label was mostly measuring pool seeding

**Measured 2026-09-21** on 592 Uniswap V2 pools, 446,334 trades, the first full
extraction.

## The number that did not make sense

`realisable_peak_over_launch` — the volume-backed peak price divided by the VWAP
of a pool's first five trades — came back at a **median of 3.58x**, with 69% of
tokens reaching 2x and **16.4% reaching 10x**.

That is not what memecoins do. A universe where one token in six returns 10x is
not a universe anyone needs a model for.

## What it was actually measuring

A freshly deployed pool opens at whatever price the deployer seeded it at, which
need not be anywhere near where the market clears. The first trades are that
repricing, not a market. Any multiple measured against them therefore mostly
captures **how wrong the initial price was**.

Tested directly by moving the reference price and changing nothing else, over
the same 379 tokens with at least 40 trades:

| Reference price | Median multiple | Reached 2x | Reached 10x |
|---|---|---|---|
| **First 5 trades** (the label) | **4.37x** | **87.6%** | **22.7%** |
| Trades 20–30 | 1.57x | 38.8% | 14.0% |
| After the first 10% of trades | 2.50x | 70.2% | 11.9% |

The median multiple falls by **2.8x** from that one change. The artefact is the
majority of the measurement.

It shows up in the covariates too. Splitting the 592 pools at 10x: the winners
have a median of 527 trades, 196 wallets and $94,452 of volume; the rest have
53, 21 and $4,241. "10x from launch VWAP" is close to a restatement of
**"this pool got any real trading at all"** — the same shape of problem as H2,
where launch liquidity turned out to be an arithmetic identity wearing a
signal's clothes.

Note the effect is not uniform. Moving the reference cuts the 2x rate by more
than half (87.6% → 38.8%) but the 10x rate by much less (22.7% → 14.0%). Seeding
manufactures small multiples in bulk; large runs survive the correction. So the
label was not worthless — it was dominated by an artefact at the low end, which
is exactly where a threshold-based positive class lives.

## Why the panel fixes it rather than patching it

`scripts/build_panel.py` scores from an **arbitrary decision block**, using the
volume-weighted price of the last few trades before it as the reference. At any
point past the opening, that is a real market price rather than a seeding
artefact, and the outcome runs forward from there.

Measured on the same data with a 14-day horizon, the 10x rate falls from 16.4%
to **7.5%** — and that number is the one worth betting against, because it is
the question an entry decision actually poses.

## The other thing the panel found, which is worse

Of 17,381 possible decision points, **16,917 had fewer than five trades in the
following two weeks**. Only **29 of 592 V2 pools** have enough sustained life to
be scored at all.

The horizon sweep says the same thing from another angle:

| Horizon | Scoreable tokens | Decision points | 10x rate |
|---|---|---|---|
| 3 days | 32 | 377 | 3.2% |
| 7 days | 31 | 458 | 5.2% |
| 14 days | 29 | 464 | 7.5% |
| 21 days | 25 | 420 | 10.0% |

The longer the horizon the higher the hit rate and the fewer the tokens that
survive censoring, which is the expected shape. But the token count never
escapes the twenties, and a token-level train/test split over 29 tokens is not
a test of anything.

**Uniswap V2 on this chain is a graveyard.** That is a finding, not an obstacle:
it says the accumulation thesis cannot be tested on V2 at all, because almost
nothing on V2 stays alive long enough to accumulate into.

## Where this leaves the analysis

On V3, which is where the chain actually trades. The V3 extraction running at
the time of writing shows a **41% keep rate against V2's 6%** — V3 pools are
roughly seven times more likely to carry enough trading to measure, on a
population twice the size and roughly nineteen times deeper. The panel needs
that population, not this one.

## Two corrections this forces

**The pre-registration's outcome amendment did not go far enough.** It replaced
the peak with a volume-backed peak, which fixed dust spikes. It left the
reference price at the launch VWAP, which was the larger of the two problems.
The panel's forward multiple supersedes it.

**Reserves are not archived, so V2 liquidity cannot be reconstructed at a
decision point.** The extractor now archives `Sync` rows alongside trades, but
the 592-pool run predates that, so every liquidity column is absent in this
panel. Future batches carry it.
