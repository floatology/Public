# Metric Catalogue: what is worth tracking, and what the evidence says

**Date:** 2026-09-21
**Purpose:** the research deliverable — a prioritised list of signals worth building, with evidence
strength and feasibility on this chain assessed separately for each.

**Why this exists:** the project had tested two signals, launch liquidity and float lockup. The
first resolved as an arithmetic identity; the second cannot be tested for weeks. Neither is where
the value was expected to be. This catalogue is the corrective — a systematic sweep of what the
literature and the tooling ecosystem actually measure, filtered through what has been established
about *this* chain.

Each metric carries three judgements, kept separate on purpose:

- **Evidence** — Published (a paper quantifies it) / Industry (tools use it, unquantified) / Untested.
- **Feasibility** — Built / Buildable now / Needs work / Blocked.
- **Priority** — reflects evidence × feasibility × how much it is *not* already priced in.

---

## 0. The headline finding from the research

**Trader profitability is predictable, and this is now a published result rather than an instinct.**

*Resisting Manipulative Bots in Meme Coin Copy Trading* (arXiv 2601.08641) builds a wallet-level
feature space and reports:

- **AUC ≈ 0.70–0.72** predicting whether a trader's next position is profitable.
- **Smart-money wallets average 14% return** per trade.
- **Copiers net ~3% per trade after market frictions** — positive, but frictions eat most of it.
- Concrete selection thresholds: **t-statistic of mean returns > 1.645**, trade count above the
  25th percentile, purchase size *below* the 75th percentile, and **no bundle bot present**.

This matters enormously for context. The nearest prior art to this project reported an entry
classifier at **AUC 0.54** — barely better than a coin flip. A published wallet-based approach at
**0.70** is a different league, and it is evidence that the whale-tracking instinct in the original
document was aimed at the right target.

Two cautions attach. The 3% net figure is *before* this chain's capacity ceiling, which caps
positions around $500–2,000. And the paper's frictions are Solana's, which are lighter than the
ones measured here.

---

## 1. Wallet forensics — highest priority

The domain with the strongest published evidence and the least of it already public.

| # | Metric | What it is | Evidence | Feasibility |
|---|---|---|---|---|
| 1.1 | **Per-wallet realised P&L** | Matched buys and sells per wallet per token | **Published** (2601.08641) | Buildable now |
| 1.2 | **t-statistic of a wallet's returns** | Mean return ÷ standard error, across its trades | **Published** — threshold 1.645 | Buildable now |
| 1.3 | **Entry-timing percentile** | How early in a token's life a wallet bought | **Published** | Buildable now |
| 1.4 | **Trade count / experience** | Number of prior positions | **Published** — >25th pctile | Buildable now |
| 1.5 | **Purchase size percentile** | Position size relative to peers | **Published** — *below* 75th pctile | Buildable now |
| 1.6 | **Cross-token hit rate vs activity-matched null** | Wins per token touched, against what chance predicts | Industry | Buildable now |
| 1.7 | **Stealth accumulation** | Sustained buying at low pool-share per trade | Untested — **your original idea** | Buildable now |
| 1.8 | **Coordination clustering** | Wallets that co-trade far beyond chance = one entity | **Published** (MELT, 2602.13480) | **Built** — by co-occurrence, not funding |
| 1.9 | **Time since last / first trade** | Recency and longevity | **Published** | Buildable now |
| 1.10 | **Wallet age at first buy** | Fresh wallet vs established | Industry | Buildable now |

**1.5 is counter-intuitive and worth dwelling on.** The paper finds profitable traders buy *below*
the 75th percentile of size. Large buyers are not the smart ones. That contradicts the naive
"follow the whale" framing and points directly at your 1.7 instinct — accumulating quietly rather
than moving price.

**Demonstrated working already.** A live pull on $WALLET found the top six buys over 20 hours, with
wallet addresses, and `0x8f10b468…` appearing twice ($22,348 then $9,068) — a wallet accumulating
across separate entries. The raw capability is proven.

**1.8 was built differently from how this catalogue specified it.** Funding-graph clustering needs
one explorer call per wallet to read its first inbound transfer, which does not scale to the tens of
thousands of wallets in the trade archive. Co-occurrence is free, already on disk, and is the better
evidence: a shared funder says two wallets were once touched by the same hand, while two wallets
buying the same nine obscure tokens in the same blocks are being operated by the same hand *now*.
The point of either is the same — to stop counting addresses as participants, because nine early
buyers might be nine people or one operator with nine wallets, and every crowd metric here assumed
the first without checking.

**The non-negotiable constraint:** wallet scores must be **point-in-time**. Scoring a wallet at the
moment it buys token X may only use outcomes from tokens that *resolved before* that moment. The
prior-art project dropped its entire deployer-tracking tier for exactly this failure.

---

## 2. Holder distribution and growth — high priority

| # | Metric | Evidence | Feasibility |
|---|---|---|---|
| 2.1 | **Holder count** | Industry (universal) | **Built** — Blockscout serves it |
| 2.2 | **Holder growth rate and curve shape** | Industry — smooth growth vs spike-then-flat | Buildable now |
| 2.3 | **Top-1 / top-10 / top-100 concentration** | **Published** (2512.00377) | **Built** |
| 2.4 | **Herfindahl-Hirschman Index** | **Published** (Mazorra et al.) | Buildable now |
| 2.5 | **Gini coefficient** | Industry | Buildable now |
| 2.6 | **Holder entropy** | Industry | Buildable now |
| 2.7 | **Dev / deployer holding %** | **Published** (MELT: `dev_hold_pct`) | Buildable now |
| 2.8 | **Early-buyer cohort share** | **Published** (MELT: `early_buyer` shares) | **Built** — from trades, no replay needed |
| 2.9 | **Average holding duration** | Industry — "Asset Level Belief" | **Built** — with a stated limitation |

**Critical implementation detail, verified today:** $WALLET's largest holder at **6.82% is the
liquidity pool itself**, and the second at 5.48% is the burn address. Every concentration metric
must exclude LP contracts, burn addresses and known bridges, or it measures the pool rather than
the holders. Your original document flagged this and it is confirmed live.

**2.9 needed less work than this catalogue assumed, and 2.8 needed none.** Both were marked as
requiring a Transfer replay. A wallet's hold is the span from its first buy to its last sell, and
both are in the swap logs already archived. The limitation is that this measures holding *in the
pool*: a wallet that moved its tokens to another address reads as never having sold, so a diamond
hand and an exit through a side door look identical. That is why `never_sold_share` is reported
beside the durations rather than folded into them — the column should not pretend to know which
it saw.

**A caution on interpretation:** *Measuring Memecoin Fragility* finds top-100 concentration above
70% is *common* and sometimes exceeds 90%. Concentration is close to the norm, not a
discriminator — so treat it as a feature with an unknown shape, not a veto.

---

## 3. Volume, flow and market activity — high priority

| # | Metric | Evidence | Feasibility |
|---|---|---|---|
| 3.1 | **Unique buyers / sellers per window** | **Published** + used by DexScreener | Buildable now |
| 3.2 | **Buy/sell count ratio** | **Published** (2608.20271) | Buildable now |
| 3.3 | **Buy/sell *value* ratio** | **Published** — differs from 3.2, use both | Buildable now |
| 3.4 | **USD-share vs count-share of buys** | Industry — the accumulation/distribution tell | Buildable now |
| 3.5 | **Relative volume (RVOL)** | Industry — current vs own trailing average | Buildable now |
| 3.6 | **Volume velocity** | Industry — DexScreener weights acceleration | Buildable now |
| 3.7 | **Volume-to-market-cap ratio** | Industry — >10% cited as a threshold | Buildable now |
| 3.8 | **Transaction count** | **Published** | Buildable now |
| 3.9 | **Net flow (Beck's "Flows")** | Industry framework | Buildable now |
| 3.10 | **Trade-size distribution** | Industry — many small vs few large | Buildable now |

**3.1 deserves emphasis.** DexScreener's own documentation says unique wallet count exists
specifically *to distinguish genuine interest from a few wallets trading back and forth*. It is
the cheapest wash-trading defence available and it feeds a ranking that itself drives attention.

---

## 4. Liquidity and execution — mostly built

| # | Metric | Evidence | Feasibility |
|---|---|---|---|
| 4.1 | **Price impact per dollar (Beck's "Asset Weight")** | Industry | **Built** |
| 4.2 | **Pool reserves, historical** | — | **Built** (via `Sync`) |
| 4.3 | **Live vs dormant liquidity split** | Original finding | **Built** |
| 4.4 | **Liquidity added / removed events** | **Published** (rug detection) | Buildable now |
| 4.5 | **LP token concentration** | Industry | Buildable now |
| 4.6 | **LP lock status via known lockers** | Industry | Needs work |
| 4.7 | **Liquidity fragmentation across venues** | Original finding | **Built** — and mostly absent |

**4.7 measured, and the answer is the useful kind of boring.** Across 644,581 tokens with a
WETH- or USDG-quoted pool, **only 1.1% have more than one pool at all**. The chain's 272
factories fragment the *population* without fragmenting individual tokens: almost every token
lives in exactly one pool. That matters because it retroactively validates the single-pool
feature extraction — the worry that per-pool metrics understate a token whose liquidity sits
elsewhere applies to about one token in ninety. The tail is real, though: one token has 58
pools across 28 factories, and for those the single-pool view is close to meaningless.

Pool *count* is not liquidity. The census records creations, not reserves, so a token with
nine pools might hold $9M or $9. Reserve-weighted fragmentation needs a per-pool reserve read
and therefore the node; it is the next step, not something to approximate from counts.

**Why 4.3 matters more than it sounds:** 113 of 174 stock tokens hold over half their paired
liquidity in **zero-volume pools**. A reserve figure on this chain is not evidence of a market. Any
metric that weights by nominal reserves without a liveness filter will rank seeded pools first.

---

## 5. Social — genuinely harder than the original plan assumed

**The plan in your document is out of date.** It specified LunarCrush's free tier for social
volume and Galaxy Score. **LunarCrush's free tier is now market-data only — social, creator and AI
endpoints require a paid plan.** Santiment is the same. And X killed free API access in 2023.

| # | Metric | Evidence | Feasibility |
|---|---|---|---|
| 5.1 | **Telegram channel members and growth** | Industry | **Buildable free** — public channels scrape over plain HTTP, no key |
| 5.2 | **Telegram post view counts / engagement** | Industry | **Buildable free** — same route |
| 5.3 | **X follower count and growth** | Industry | Paid or scraped |
| 5.4 | **Social volume / mention count** | **Published** (2608.20271 cites social dynamics) | Paid |
| 5.5 | **Social dominance** — share of total crypto conversation | Industry (Santiment) | Paid |
| 5.6 | **Galaxy Score / AltRank composites** | Industry | Paid |
| 5.7 | **Social–price decoupling** | Industry (3σ over 30d) | Paid inputs |
| 5.8 | **Whale-alert bot posts as a feed** | Original observation | **Buildable free** |
| 5.9 | **Presence and quality of official links** | Industry | Buildable now |

**Telegram is the exception and should be exploited.** Public channel member counts and post view
counts are retrievable over plain HTTP with no key and no account. That gives a real, free social
signal with a growth derivative — which is closer to what matters than a static follower count.

**5.8 is worth building and cheap.** Public bots already tweet whale entries on this chain in real
time. Treat them as a *free labelled dataset* rather than a signal: they are asserting which
wallets are whales, which can be cross-checked against your own P&L ledger. Their classification
is what they don't publish; you can rebuild it and validate against their alerts.

**Strategic caveat on all social:** if a bot tweets it, it is public and largely priced by the time
you read it. Social's value here is more plausibly as a *confirmation* layer or a *decoupling*
detector (attention rising while price is flat) than as an entry trigger.

---

## 6. Contract and structural risk — screening, not prediction

| # | Metric | Evidence | Feasibility |
|---|---|---|---|
| 6.1 | **Mint / pause / blacklist functions present and live** | Industry | Needs work |
| 6.2 | **Ownership renounced** | Industry | Buildable now |
| 6.3 | **Proxy / upgradeable** | Industry | Buildable now |
| 6.4 | **Sell simulation (honeypot / fee-on-transfer)** | Industry | Needs work |
| 6.5 | **Deployer wallet age** | Industry | Buildable now |
| 6.6 | **Serial deployer flag** | **Abandoned by prior art** — devs rotate wallets | Low value |
| 6.7 | **Mixer interaction** | Industry | Needs work |

Keep this as a **filter, not a predictor** — the open-source tool your document cited is explicit
that this class of check "filters traps, it does not pick winners."

**6.4 is the gap that touches every label.** A fee-on-transfer token yields less than any quote
implies, and nothing in the system currently models it.

---

## 7. Manipulation detection — required, because it invalidates other metrics

| # | Metric | Evidence | Feasibility |
|---|---|---|---|
| 7.1 | **Bundle-bot detection** | **Published** — a *required-FALSE* gate in 2601.08641 | **Built** |
| 7.2 | **Sniper-bot detection** | **Published** | **Built** |
| 7.3 | **Bump-bot detection** | **Published** — *highest* LASSO importance (0.2333) | **Built** |
| 7.4 | **Wash trading: self, matched, circular trades** | **Published** | **Built** |
| 7.5 | **Same-block coordinated buys** | **Published** (MELT bundle stats) | **Built** |
| 7.6 | **Dormant-pool detection** | Original finding | **Built** |

**Section 7 is now complete.** 7.1 and 7.3 live in `src/rhc.manipulation`, and the detectors
are deliberately conservative because the naive form of each fires on something ordinary.
Eight wallets buying in the launch block is *also* what an anticipated launch looks like, so
bundling additionally requires the amounts to match to within a low coefficient of variation —
a bundler's contract splits a fixed budget, a crowd does not. One wallet trading forty times is
*also* an active trader, so bumping additionally requires a near-flat net position and
metronomic inter-trade gaps. Four of the eight committed tests are negative cases that must
stay silent.

**7.3 is the single most surprising research finding.** In the copy-trading paper's LASSO model,
**bump-bot presence carried the highest normalised feature importance of any variable** — above
every historical-performance feature. Manipulation signatures are not just noise to filter; they
are among the strongest predictors in the published model.

---

## 8. Composite frameworks worth testing as units

| # | Framework | Components | Notes |
|---|---|---|---|
| 8.1 | **Asset Weight × Flows × Belief × Memetics** | 4.1, 3.9, 2.1+2.9, §5 | Three of four on-chain. But *price change ≈ flows ÷ weight* is close to an identity — the predictive version is anticipating flows, or spotting weight about to change |
| 8.2 | **DexScreener trending score replica** | 3.1, 3.5, 3.6, 3.8, 4.1 | Rebuilding it predicts *attention*, which itself drives flows. Attention is the mechanism, not a proxy for it |
| 8.3 | **MELT-style feature block** | 122 features across 5 groups | AUPRC 0.5729, cuts loss by 34pp — a template, not a result to copy |

---

## 8b. Build status as of 2026-09-21

Everything buildable without further input has been built. The pipeline produces
**84 columns per token** across four modules.

| Module | Covers | Status |
|---|---|---|
| `rhc.features` | §3 flow, §4 liquidity, §7 manipulation, parts of §1 | **built, verified** |
| `rhc.features` holder block | §2 via Transfer replay | **built, tested offline**; not yet run against the chain |
| `rhc.contracts` | §6 structural risk | **built, verified** |
| `rhc.social` | §5.1, §5.2 Telegram | **built, verified** |
| `rhc.wallets` | §1 ledger + point-in-time scoring | **built, verified** |
| `rhc.manipulation` | §7.1 bundle bots, §7.3 bump bots | **built, verified** |
| `rhc.clusters` | §1.8 coordination clustering | **built, verified** |
| `scripts/wallet_clusters.py` | §1.8 as training-window features | **built, verified** |
| `scripts/fragmentation.py` | §4.7 venue counts | **built, measured** |
| `scripts/wallet_ledger.py` | §1 as per-token features, leak-audited | **built, verified** |
| `scripts/recompute_features.py` | offline feature rebuild from archived trades | **built, verified** |
| `scripts/describe_features.py` | pre-model column diagnostics | **built, verified** |
| `scripts/daily_movers.py` | forward memecoin activity series | **built, running daily** |
| `scripts/enrich_features.py` | joins all of the above + GeckoTerminal info | **built, verified** |
| `scripts/model_features.py` | regularised selection + negative control | **built** |
| `scripts/feature_correlations.py` | independent-dimension analysis | **built** |

### The architectural mistake this catalogue caused

The first extraction decoded every trade, computed features from them, and then
**threw the trades away**. That made the catalogue look more expensive than it is: any
new metric appeared to cost another ninety minutes of a node that rate-limits globally,
which is a strong incentive to stop adding metrics. It also made section 1 impossible,
because a wallet's record is by definition across pools and a per-pool pass never has more
than one pool in hand.

Trades are now archived to Parquet. Features became a pure function of a file on disk,
section 1 became reachable, and the marginal cost of a new metric fell from ninety minutes
to seconds. This should have been true from the first run.

### Three corrections to this catalogue, found by building it

**§2.3 concentration is cheaper than stated.** GeckoTerminal's token-info
endpoint returns a nested holders object with a top-10 / 11-30 / 31-50 / rest
breakdown. That yields holder count and concentration **without** replaying
Transfer logs. Measured spread across nine sampled tokens: 19.8% to 99.9999% in
the top ten.

**§6.4 honeypot is partially free.** The same endpoint carries an `is_honeypot`
flag, plus `mint_authority` and `freeze_authority`. It is tri-state — boolean for
some tokens, `"unknown"` for others — so absence must be preserved rather than
read as "safe".

**§5 social is worse than stated, for a reason that is not a coverage gap.**
None of nine sampled memecoins had *any* Telegram or Twitter handle registered.
Social data may exist only for tokens that already have attention, which makes
it a **selection problem**: conditioning on having social data may already
condition on the outcome.

## 9. Recommended build order

Ordered by evidence strength × feasibility × how little of it is already public.

**Phase 1 — the wallet ledger (unblocks the most)**
1. Per-wallet buy/sell ledger, chain-wide (1.1)
2. Point-in-time scoring table (1.2, 1.4, 1.9)
3. Activity-matched hit rate (1.6)
4. Stealth accumulation detector (1.7) — your original idea

*Why first: strongest published evidence (AUC 0.70), and one scan produces the inputs for a dozen
metrics. It also yields Flows (3.9) and trade-size distribution (3.10) for free.*

**Phase 2 — flow and holder metrics (same scans)**
5. Unique buyers/sellers, buy/sell ratios by count and value (3.1–3.4)
6. RVOL and volume velocity (3.5, 3.6)
7. Holder count, growth curve, concentration with LP/burn exclusion (2.1–2.5)

**Phase 3 — manipulation gates**
8. Wash trading (7.4), same-block coordination (7.5), sniper detection (7.2)

*Why here: these invalidate Phase 2 metrics if ignored, so they must land before anything is
trusted, but they need Phase 1's ledger to compute.*

**Phase 4 — social**
9. Telegram members and view counts (5.1, 5.2) — the free one
10. Whale-bot feed as a labelled cross-check (5.8)

**Phase 5 — structural filters**
11. Sell simulation (6.4) — closes the label gap
12. Ownership and proxy status (6.2, 6.3)

---

## 10. Honest framing

This catalogue lists **fifty-odd metrics**. Building them is not the hard part; most fall out of
two or three scans over data already reachable.

The hard part is that the power analysis says the current sample can only detect effects around
**21 percentage points**, while published effects run nearer **3**. Fifty metrics tested against an
underpowered sample will produce several that look significant and are not — which is precisely how
the launch-liquidity result looked significant, replicated, and still meant nothing.

So the build order above deliberately front-loads **one domain with strong published evidence**
rather than sweeping all fifty at once. Breadth without power manufactures false positives, and
this project has already produced five artefacts that each looked like a finding.

The catalogue is the map. It should be worked through in order, not all at once.

---

## Sources

Academic:
- [Resisting Manipulative Bots in Meme Coin Copy Trading (arXiv 2601.08641)](https://arxiv.org/html/2601.08641v2) — wallet feature space, AUC 0.70–0.72, thresholds
- [MELT: Behavioral Trace Dataset for High-Risk Memecoin Launch Detection (arXiv 2602.13480)](https://arxiv.org/html/2602.13480) — 122 features, five trace groups
- [Catching the Rug (arXiv 2608.20271)](https://arxiv.org/abs/2608.20271) — activity and flow features
- [Measuring Memecoin Fragility (arXiv 2512.00377)](https://arxiv.org/pdf/2512.00377) — concentration base rates

Industry:
- [DexScreener trending documentation](https://docs.dexscreener.com/trending) — unique wallets, volume velocity, liquidity depth
- [Nansen: analysing blockchain data for smart money](https://www.nansen.ai/post/how-to-analyze-blockchain-data-for-smart-money-movements)
- [LunarCrush pricing](https://lunarcrush.com/pricing/) — free tier now market-data only
- [Best crypto sentiment APIs 2026](https://adanos.org/insights/blog/best-crypto-sentiment-apis-2026/) — social now paid across providers
- [Token holder concentration metrics and limits](https://www.veritasprotocol.com/blog/token-holder-concentration-analysis-metrics-and-limits)

Live measurements on chain 4663, 2026-09-21: $WALLET holder distribution (LP at 6.82%, burn at
5.48%), wallet-level buy extraction from V3 swap logs, Blockscout token and holder endpoints.
