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
