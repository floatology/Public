# Stock-Token Premium: Correction and Empirical Findings

**Date:** 2026-09-20
**Status:** the §5.1 recommendation in `01-critique-and-revision.md` is **retracted** in its original form.

---

## 0. What I got wrong

In `01-critique-and-revision.md` §5.1 I called the stock-paired premium "the best idea in the whole document" and led with *"known cause, known magnitude, known trigger, known resolution latency."* All four of those are true. I then caveated execution in a single clause and moved on.

That framing was wrong, and wrong in the direction that matters. **I identified a real, recurring, predictable dislocation and failed to ask who is structurally positioned to harvest it.** The answer turns out to be decisive, and it is not you.

The correct statement is: *the premium is real, observable, and structurally uncapturable by a retail participant.*

---

## 1. Why the premium cannot be captured

To profit from an asset trading **above** fair value you must create supply and sell it. For a Stock Token, creating supply means minting. From Robinhood's own chain documentation:

> "Only Authorised Participants (at issuance, the only Authorised Participant is BBVI) may subscribe for Stock Tokens directly from RHJ after KYB onboarding."

**Minting is restricted to Authorised Participants, and there is exactly one: BBVI.** That is the same entity that resolved the BONER/HIMS episode by minting ~4,000 tokens into the premium within an hour of the NYSE reopening. It did not happen to capture that spread — it is the only party that *could*. The mint authority **is** the arbitrage mechanism.

The remaining routes all close:

| Route | Status |
|---|---|
| **Mint and sell into the premium** | AP-only. Single AP (BBVI). Closed. |
| **Borrow the token and short it** | No borrow market found for Stock Tokens. Ethosis, the lending venue on this chain, lets you *post* stock tokens as collateral to borrow USDG — the opposite direction. And in a cornered-float situation the borrow is precisely what becomes unavailable; that is what a squeeze *is*. Closed. |
| **Redeem at NAV** | Redemption caps **discounts**, not premiums. Buying at $132 and redeeming for $28.84 of value is a guaranteed $103 loss. Wrong direction. |
| **Hold it beforehand and sell into the spike** | Not arbitrage — this requires predicting the corner in advance, which is the hard prediction problem, not a risk-free trade. |

There is also a hard gating fact regardless of mechanism:

> "Stock Tokens may not be offered, sold, or delivered, directly or indirectly, in the United States or to, or for the account or benefit of, U.S. persons."

And a structural note: these are currently **tokenized debt securities with cash settlement and no shareholder rights** — not stocks. Robinhood announced 1:1 share redemption and voting rights on 2026-09-14, but that is roadmap, not live.

**The asymmetry to remember:** redemption caps discounts (retail-accessible in principle), minting caps premiums (AP-only). The BONER/HIMS event was a *premium*. It was therefore always going to be harvested by BBVI and nobody else.

---

## 2. Empirical measurement — how often does this actually happen?

Rather than reason about frequency, I measured it. `src/rhc/premium.py` computes, from live pool state, each Stock Token's on-chain price against its real equity price.

**Measured 2026-09-20, a Saturday with US markets closed** — i.e. the exact market condition that produced the 360% BONER/HIMS dislocation.

| Ticker | On-chain | Real | Premium | Stable pools | Memecoin pools | **Lockup** |
|---|---:|---:|---:|---:|---:|---:|
| NVDA | 220.79 | 220.45 | **+0.15%** | $8.6M | $27.0M | **75.8%** |
| AAPL | 334.26 | 334.06 | **+0.06%** | $2.4M | $3.1M | **56.6%** |
| SPY | 762.68 | 762.63 | **+0.01%** | $10.8M | $0.7M | 6.3% |
| AMC | 2.71 | 2.70 | **+0.46%** | $2.0M | $0.3M | 12.9% |
| MSTR | 151.37 | 151.47 | **−0.06%** | $2.6M | $1.9M | 41.4% |
| HIMS | 27.71 | 27.75 | **−0.16%** | $2.3M | $2.9M | **55.3%** |
| TSLA | 362.11 | 363.04 | **−0.26%** | $2.3M | $1.7M | 42.1% |
| COIN | 191.69 | 192.45 | **−0.39%** | $0.8M | $0.3M | 26.3% |
| GME | 22.21 | 22.38 | **−0.78%** | $1.2M | $0.7M | 36.6% |
| PLTR | 174.62 | 176.43 | **−1.02%** | $1.1M | $1.4M | **55.3%** |

Cross-checked against independent equity sources: HIMS closed **$28.00** (on-chain −1.04%), PLTR closed **$177.32** (on-chain −1.52%). This confirms the reference feed is genuinely independent of on-chain pricing and the comparison is not circular.

### What this says

- **Every premium sits within ±1.5%**, and most are *negative* — small discounts, not premiums.
- That is **arbitrage-tight pricing**, and the residual is smaller than the round-trip cost of trading it (pool fees of 0.3–1% per leg, plus price impact, plus gas).
- The measurement was taken under the precise conditions — weekend, minting window closed — that the BONER thesis says should produce dislocation. It produced none.
- **The HIMS float has grown from 58,714 tokens at the time of the squeeze to 136,773 today** — a 2.3× expansion. The issuer widened the float that made the corner possible, which structurally reduces recurrence for that name.

### Answering the question directly

> *How frequently would that provide a hit? Daily gains, or rare? What kind of returns? Is it almost a guarantee?*

- **Frequency: rare, and trending rarer.** One documented extreme event in ~11 weeks of chain history, against a float that has since more than doubled.
- **Returns: not applicable** — the trade cannot be entered from the retail side at all. Frequency is moot when the position is unreachable.
- **"Almost a guarantee": no.** The guarantee belongs to BBVI, which holds the mint authority. What looked like a risk-free convergence was a description of *someone else's* risk-free convergence.

The mechanism I described was accurate. My error was treating an observable regularity as an available one.

---

## 3. What survives — and it is genuinely worth having

The premium is not a trade. But the **cause** of the premium is measurable in real time, and it points at something that *is* tradable.

BONER did not appreciate because HIMS went to a premium. **The causation runs the other way**: BONER paired itself against tokenized HIMS instead of a stablecoin, so every BONER purchase pulled HIMS into the pool and locked it there. The premium was the *symptom*. The corner was the *cause*. And BONER itself surged ~1,000%.

So the usable inversion is:

> **Do not trade the dislocation. Detect the token that is causing it.**

`src/rhc/premium.py` computes a **float-lockup ratio** — the share of a Stock Token's pooled value sitting in memecoin-paired pools rather than stable-paired pools. This is directly measurable right now, needs no history, and leads the premium.

The current readings are striking:

- **NVDA: 75.8% locked up** — $27.0M in memecoin pools against $8.6M in stable pools, across pairs including AI, CEREBRO, DARK, EI.
- **AAPL 56.6%**, **HIMS 55.3%**, **PLTR 55.3%** — all majority-locked.
- **SPY 6.3%** — the control case. A broad-market ETF token attracts almost no memecoin pairing.

This is a **novel, cheap, real-time signal that no vendor in the master document's tooling survey computes**, and it is exactly the kind of cross-domain join (on-chain pool state × tokenized-equity structure) that §5.6 of the critique identified as the only defensible source of edge on this project.

**The testable hypothesis it generates** — and this one is falsifiable, unlike the multi-day runner thesis:

> *A rising float-lockup ratio on a Stock Token predicts forward returns in the memecoin(s) driving that lockup.*

That is a clean, pre-registerable claim with a small, enumerable universe (~190 stock tokens, not 700,000 memecoins), a mechanical causal story, and a measurable independent variable. It is a far better first experiment than anything else currently on the table.

**Caveats to keep honest:** the memecoin leg is still a memecoin, with all the execution problems from §4.1 of the critique (impact, sell tax, MEV). Lockup is observable by anyone who thinks to compute it. And a high lockup ratio may simply mark tokens that already ran rather than ones about to — which is precisely what the backtest is for. This is a hypothesis, not a finding.

---

## 4. Revised recommendation

| Was | Now |
|---|---|
| Build the premium arbitrage as a primary workstream | **Dropped.** Structurally uncapturable. |
| Premium as a trade signal | **Demoted to a diagnostic.** Worth logging; never actionable on its own. |
| — | **New: float-lockup as a leading signal for the paired memecoin.** Promoted to the first falsifiable experiment. |

The Phase 0 work in `01-critique-and-revision.md` §6 is unaffected — the indexer, pre-cliff capture, and pre-registration all stand, and the gas-cliff deadline of 2026-09-29 still governs.

---

## Sources

- [Robinhood Chain — Stock Tokens documentation](https://docs.robinhood.com/chain/stock-tokens/) — AP-only minting, single AP (BBVI), US-person exclusion, Mon 02:00–Sat 02:00 CET tokenization window
- [Robinhood Chain — Contract addresses](https://docs.robinhood.com/chain/contracts/) — canonical WETH/USDG, identity warning
- [Robinhood plans share redemptions and voting rights for stock tokens](https://www.coindesk.com/business/2026/09/14/robinhood-plans-share-redemptions-voting-rights-for-stock-tokens-after-criticism) — 2026-09-14, roadmap
- [A Memecoin Called BONER Has Cornered Half the Tokenized Hims & Hers Float](https://thedefiant.io/news/tokens/a-memecoin-called-boner-has-cornered-half-the-tokenized-hims-and-hers-float)
- [Ethosis — peer-to-peer lending against tokenized stocks](https://www.ethosis.org/) — collateral direction only
- Live measurements: Blockscout v2 API (chain 4663) and GeckoTerminal `robinhood` network, 2026-09-20
