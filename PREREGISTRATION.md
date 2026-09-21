# Pre-Registration

Committed **before** the confirmatory data pull. Its purpose is to make later
self-deception auditable: the git history of this file is the record of what was
claimed in advance versus what was decided after seeing results.

Amendments are permitted and expected. They must be made as **new commits that
state what changed and why** — never by silently editing a prior claim.

---

## H1 — Float lockup predicts paired-memecoin returns

**Claim.** A rising float-lockup ratio on a Robinhood Stock Token predicts
positive forward returns in the memecoin(s) driving that lockup.

**Independent variable.** `lockup_ratio` = memecoin-paired pool reserves as a
share of total pooled reserves for a Stock Token (`src/rhc/premium.py`),
measured daily. Signal fires on the *change* in lockup over a trailing window,
not the level — a high static level may merely mark a token that already ran.

**Dependent variable.** Forward return of the paired memecoin, measured as
**simulated round-trip P&L on a $500 clip** against reconstructed pool reserves,
net of price impact on both legs, pool fees, sell-side token tax, gas, and an
MEV/sandwich haircut. Not printed price. A move that cannot be transacted is
not an outcome.

**Benchmark.** Excess return over a chain-wide memecoin index constructed from
the same data, with a paired same-day / same-age control group.

**Control group must be gate-matched.** The control is drawn only from tokens
that *pass the same liquidity and tradability gates* as the signal group, and
differ solely in the signal being tested. This is not a refinement — the prior
art's rebuild found its own control invalid for exactly this reason: 2,711 of
2,754 control rows failed gates the alerted tiers had passed, so the comparison
measured the gates rather than the signal.

**Tradability gate (measured, not assumed).** A token enters the universe only
if its measured round-trip cost at the test clip is under 5%. Pool reserves are
*not* an adequate proxy: measured costs run 0.90% at $2.4M of reserves and
96.10% at $20k, and two tokens $10k apart in depth differed by 3 percentage
points in cost. The prior art's ≥$10k liquidity floor is far too permissive and
admits tokens that cannot be traded at all.

**Horizon.** 7 days from signal.

**Universe.** Memecoins paired against a canonical Stock Token (identity
verified per `src/rhc/stocktokens.py`; ticker lookup alone is never sufficient).

**Inference.** Block bootstrap by launch week. Tokens on this chain co-move, so
i.i.d. standard errors are invalid and will not be used.

**Signals tested.** Exactly three, fixed here in advance: (1) 7-day change in
lockup ratio, (2) 7-day change in the count of distinct memecoins pairing
against the Stock Token, (3) the interaction of (1) with stable-pool depth.
Testing beyond this list requires a committed amendment stating the addition
before results are examined.

**Multiple-testing correction.** Romano–Wolf stepdown with a block bootstrap.

**Success criterion.** Mean excess return significantly positive at the 5% level
after correction, **and** the point estimate exceeds modelled round-trip costs.
Statistical significance below the cost floor is a null result.

**Stopping rule.** If H1 fails, it is not re-specified with a different horizon,
a different lockup definition, or a different universe in search of significance.
It is recorded as falsified and the project moves on.

---

## H0 — The multi-day runner thesis

**Claim.** Conditional on a token surviving to day 3 with defined forensic
markers, forward 30-day excess returns exceed a same-day/same-age control.

**Prior.** Explicitly negative. The closest comparable public system measured
entry-classifier AUC 0.541–0.546, 0 of 16 top-tier alerts positive at 7 days,
and no exit policy beating instant liquidation (itself −3.45%). This hypothesis
is being tested *against* a measured negative result, not in a vacuum.

**Label.** ≥10× within a **fixed 30-day window from each token's own launch**,
on simulated round-trip P&L as above. Tokens with under 30 days of history are
excluded from the labelled set — not scored as negatives. Launch price is a
short VWAP over the first minutes of real trading, not the first transaction.

**Leakage controls.** Wallet scores are bitemporal: scoring token T at time t
may only join wallet records derived from tokens whose outcomes **resolved**
before t. Accumulation windows are detected causally from trailing data only —
never located retrospectively across the full series.

Independently corroborated: the prior art's 2026-09-12 rebuild dropped its
"proven dev" screener outright, citing look-ahead bias in that tier alongside
deployers rotating wallets. The failure mode in §3.1 of the critique is not
hypothetical — it has already sunk one implementation of this idea.

**Stopping rule.** If the Phase 1 paired-control test shows no significant
excess return, the project stops pursuing runner prediction and says so.

---

## H2 — Launch liquidity predicts the 10x outcome

**Added by amendment 2026-09-20, before the test was run.** It replaces the
graduation-threshold regression discontinuity proposed in
`01-critique-and-revision.md` §5.2, which is **infeasible on this chain**: the
two dominant factories are a plain UniswapV3Factory (427,640 assets) and
UniswapV2Factory, not a bonding-curve launchpad, and migration between
factories is negligible (largest flow 166 assets). There is no graduation event
to have a discontinuity around, so the only genuine causal design available was
withdrawn rather than forced.

**Claim.** A pool's liquidity shortly after creation predicts whether its token
later reaches 10x its launch VWAP.

**Why this signal.** It is the cheapest honest test available. It is observable
**at launch with no look-ahead** — unlike anything derived from price history —
and it connects directly to the capacity finding: a pool too thin to trade is
also, plausibly, too thin to run.

**Independent variable.** Quote-side reserve in USD at the pool's **first**
`Sync` event, i.e. the liquidity the deployer actually seeded. Taken from the
first Sync only, so no post-launch information enters.

**Dependent variable.** Reached ≥10x launch VWAP, and separately the *tradable*
version of that label at a $500 clip (`scripts/tradable_rate.py`).

**Test.** Compare the 10x rate across launch-liquidity quantiles; report the
trend with a chi-square test for a monotone relationship. Both labels reported.

**Direction is not pre-specified, and this is deliberate.** The plausible story
runs both ways: more seeded liquidity may mean a more committed deployer, or it
may simply mean a larger pool is harder to move 10x. Predicting a direction
after the fact would be exactly the sin this document exists to prevent.

**Falsification.** If the 10x rate is flat across liquidity quantiles, the
signal carries no information and is recorded as such. No re-specification with
a different threshold, quantile count or horizon to find significance.

**Power.** The critique's analysis says n=57 detects only a ~21pp effect. This
test therefore needs the measurable count in the hundreds, which means sampling
in the thousands. An inconclusive result at small n is reported as inconclusive,
never as a null.

## Standing rules

1. Any AUC / AUCPRC is reported **against its own prevalence baseline**. A bare
   figure is uninterpretable and will not be quoted.
2. Negative controls ("sell immediately", random entry, random exit) are
   mandatory. A strategy that does not beat them has not been shown to work.
3. Every token is identified by verified contract address. Never by ticker.
4. Pre-cliff (≤ 2026-09-29) and post-cliff data are never pooled without an
   explicit test that pooling is valid. Free gas made manufactured volume free.
5. Negative results are committed to this repository with the same prominence as
   positive ones.

---

## Amendment 2026-09-21: the outcome is measured against sellable volume

**Made before any model has been fitted to the feature set.** No feature table
existed when this was written — the first full extraction was still running —
so nothing here is a change made after seeing a result.

**The problem.** Every hypothesis above is scored against `peak_over_launch`,
which is the price of **a single trade** divided by the launch VWAP. In a pool
holding a few thousand dollars, that trade can be three dollars of dust. A 10x
that nobody could sell into is not a 10x, and a label built from one carries the
model straight to tokens that print a number rather than tokens that pay.

**The replacement.** `realisable_peak_over_launch`: the highest price at or above
which **a tenth of the token's total volume** traded. That is a price the market
demonstrably absorbed size at. It needs no reserve data, so it survives the
offline rebuild, and it is computed from the same trades as everything else.

Three columns are reported beside it so the difference is always visible rather
than assumed:

- `peak_trade_volume_share` — how much of the token's volume traded at its peak
  price. Near zero means the peak was a rounding error.
- `volume_above_2x_share` and `volume_above_10x_share` — how much volume traded
  at or above those multiples of the launch price.

**What this changes.** `realisable_peak_over_launch` becomes the default label
for `scripts/model_features.py` and `scripts/wallet_ledger.py`. `peak_over_launch`
stays in the feature table and stays available as `--label`, because the gap
between the two is itself informative and suppressing it would hide how often
the old label was measuring dust.

**What it does not change.** All four outcome columns are added to the model's
`LEAKY` exclusion set. They describe where the price went; any of them as an
input predicts the outcome from the outcome and returns an AUC near 1.0 that
means nothing.

**Standing rule 6, added here:** an outcome that could not have been realised at
size is not an outcome. Any future label must state what volume traded at the
price it claims.
