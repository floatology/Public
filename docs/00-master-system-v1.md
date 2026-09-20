# Robinhood Chain Monitoring System — Master Document

Single evolving reference. Update this in place as ideas develop — don't fork into new docs. Supersedes the earlier separate files (criteria doc, signals deep-dive, prior-art doc).

---

## 0. What this system is

Two related engines sharing one feature-computation layer:
1. **Watchlist monitor** — continuous tracking of coins already held, for buy/sell/hold signal.
2. **New-launch scanner** — scans new Robinhood Chain token launches for ones worth watching.

**Core strategic choice (settled):** this is NOT a fast-scalp, get-in-first-30-minutes system. It's a **multi-day accumulation-to-breakout read** — willing to wait days of data before deciding. This distinction matters a lot for which prior art applies (see Part 5) and which signals are primary vs. secondary (see Part 3).

**Chain context:** Robinhood Chain = Arbitrum-based EVM L2, chain ID 4663, launched July 1, 2026, built for tokenized stocks but hijacked by memecoin speculation. Gas-fee subsidy (covers swap costs >$5) ends **Sept 29, 2026** — treat pre/post as different data regimes. Major reference case studies: CASHCAT (organic first-mover, thin liquidity, 1,700%+ move on a few million $ of liquidity), PONS (launchpad token, not a memecoin itself — reflexive buyback-burn tied to its own platform volume), Artificial Inu/AI (narrative pairing with tokenized NVDA + a tracked KOL buy as catalyst).

---

## 1. Feature catalogue — what to compute per token, per time window

Grounded in a 2026 academic study (6.4M Solana tokens, XGBoost, first-5-min→1-hour prediction, AUCPRC ~0.80):

| Feature | Captures |
|---|---|
| `count_tx`, `unique_buyers`, `unique_sellers` | Activity level & breadth |
| `purchase_percentage` / `sale_percentage` | Buy/sell tx share |
| `buy_sell_cnt_ratio` vs `buy_sell_value_ratio` | Count-weighted vs size-weighted pressure — use both (see Part 2, USD-share-vs-count-share) |
| `total_sol_value` / `buy_sol_value` / `sell_sol_value` | Value flow (ETH/WETH on this chain) |
| `price_change_first_to_3_blocks` | Bundling/sniping tell |
| `price_change_first_to_last`, `max_price`, `min_price`, `min_price_after_max` | Drawdown-from-peak shape — rug/dump detector |
| `buy_price_std` / `sell_price_std` | Dispersion — thin/choppy market indicator |
| `first_buy_time` / `first_sell_time` | Discovery latency |

**Rug labels (steal directly for backtest labeling):**
- TVL-drop: `MDD_t = (TVL_t − max(TVL up to t)) / max(TVL up to t)`, flag if breach threshold (paper used −99%; a −50% "warning" tier is reasonable too).
- Idle: flag if zero trading volume for a rolling window exceeding X% of lifetime (paper used 80%).
- Combine both (OR) — Idle worked better for high-speculation venues (this chain), TVL-drop for maturer markets. Track separately.

**Runner label — must be defined as carefully as the rug label, before looking at results** (e.g., "reached Nx price within Y hours without an intervening MDD below Z%"). Given the multi-day strategic choice, this horizon should be days, not hours.

---

## 2. On-chain forensics (the primary layer for this project)

### Wallet behavior
- **Bundle detection**: token-creation tx followed same-block by buys from other wallets; trace buyer funding sources — multiple "different" wallets tracing to one funding source = one entity fragmenting supply. Dev buying its own token in the same block is near-universal (98.7% in one study) and NOT itself a signal; *other* wallets doing so, tracing to shared funding, is.
- **Sniper detection**: wallets buying within 1–5 blocks of every pool creation they touch, across many tokens — filtered by speed, not profitability.
- **Wash-trading detection**: self-trades (one entity, two wallets), matched trades (A↔B repeatedly), circular trades (A→B→C→A) — inflate volume without real capital. Check before trusting any volume spike. (~3.8hr mean lead time before a rug in one BSC study using these patterns.)
- **Smart-money / cross-token whale scoring (core ask, refined)**: score wallets by *realized, repeated* profit and *entry-timing percentile* across multiple tokens — not by wallet size. Concrete build: maintain a per-wallet record of (token, entry percentile, realized outcome) across every token it's touched; flag wallets with 2+ prior early entries into tokens that later multiplied; when a new token appears, check its buyer list against that flagged list. This is buyer-identity tracking, which is NOT gamed the way deployer-identity is (see Part 5 — deployer-based tracking was tried and abandoned by prior art because devs rotate wallets deliberately; buyers have less incentive to hide).

### LP / AMM microstructure
- **Price impact / depth**: for constant-product pools, price impact of a trade is directly derivable from reserves (`x*y=k`); for Uniswap V3-style concentrated liquidity, depth is range-specific — thin depth near current price = large impact from modest size = the CASHCAT fragility pattern (1,700%+ move on a few million $ of liquidity).
- **LVR (Loss-Versus-Rebalancing)**: for constant-product pools, instantaneous LVR normalized to pool value ≈ σ²/8 (σ = volatility). High-volatility memecoin pools bleed LP value to arbitrageurs fast — a pool's LVR rate is itself a fragility/stability signal.
- **USD-share vs. count-share of buys** (clean accumulation/distribution forensic, AMM-appropriate — better fit than Wyckoff for this asset class, see Part 3): few wallets buying big while many sell small (USD share high, count share low) = accumulation. Many small buys against big sells (count share high, USD share low) = distribution-into-hype. Compute as a time series over days, not a snapshot.
- **LP-depth-as-support/resistance (novel, untested)**: concentrated liquidity zones in a V3-style pool mechanically resist price movement (large depth = small impact per $ traded) — this is a *mechanical*, not psychological, analog to support/resistance, worth testing as its own signal independent of traditional TA.
- **Holder count, properly filtered**: exclude LP contract and bonding-curve addresses from any concentration/count calc (otherwise the pool itself gets counted as a whale). Track the *shape* of the holder-growth curve over days — smooth sustained growth vs. spike-then-flatline (bot/bundle burst).

### Contract-level forensics (distinct from wallet-behavior and LP-microstructure signals above)
- **Privileged function scan**: check the contract source directly for `mint` (unlimited supply creation), `blacklist` (address-blocking), `pause` (trading halt), adjustable buy/sell tax, and `withdrawAll`/owner-fund-sweep functions. Any of these present *and* still controllable (owner not renounced) is a structural rug vector independent of any wallet-behavior signal.
- **Ownership/proxy status**: is the contract upgradeable (proxy pattern with a live admin wallet)? A renounced, non-proxy contract is structurally safer regardless of what its wallet activity looks like — "renounced" moots most of the function-level risks above.
- **LP lock verification via named lockers**: check whether LP tokens sit in a recognized locker contract (UNCX, Team Finance, Onlymoons, Pinksale-equivalent on this chain) rather than just checking "is liquidity present" — a claimed "LP burned" needs the burn address confirmed, not taken on faith from a project's own claim (CASHCAT's LP-burn claim, cited earlier, is exactly the kind of claim worth verifying on-chain rather than trusting).
- **LP token holder distribution itself**: is the LP token (representing pool ownership) held by one wallet or spread across several genuine liquidity providers? A single-LP-holder pool is a single point of failure even if that LP is technically "locked," since lock duration/terms vary and a single holder concentrates the unlock risk.
- **Deployer/wallet age and serial-deployer flag**: wallet age in days (a wallet funded and used within minutes is a different risk profile than one with real history), and a direct check for serial deployment (has this wallet, or one linked to it, deployed many prior tokens — a documented rug-proxy signal distinct from the bundle/funding-source tracing above).
- **Mixer-interaction flag**: has the deployer or a major early wallet interacted with a mixing service — a standalone red flag some wallet-screening tools already compute directly.

---

## 3. Where technical analysis fits — demoted, not discarded

**Wyckoff/TA critique (settled):** Wyckoff assumes a pre-existing, distributed float being quietly accumulated by a "Composite Man" over weeks/months. A new memecoin's entire fixed supply exists at block one, concentrated in deployer/insider/bundle wallets — there's no distributed prior holder base to accumulate *from*. The early "story" of a memecoin is initial-concentration-dispersing-outward (or failing to), which is structurally closer to the mirror image of accumulation than a copy of it.

**Role TA still plays**: a **secondary, later-stage confirmation layer** once real multi-day trading history exists — not a primary signal for freshly-launched tokens. If the on-chain forensics (Part 2) already say "this looks like healthy accumulation" AND a TA pattern (Wyckoff-style range/spring/breakout) is also playing out, that's stronger confluence than either alone. Never lead with TA on this asset class.

---

## 4. Social signals

- **Skip the raw X API** — it moved to pay-per-use in Feb 2026 with no free tier ($0.005/read); workable but needlessly expensive/complex to build against directly for this.
- **Use LunarCrush** instead — purpose-built crypto social-intelligence API, free tier available, aggregates X + Reddit + YouTube + TikTok into: social volume (mention count over time), Galaxy Score (composite social-influence score), sentiment, social dominance. Directly gives the "is attention on this token rising over days" read without building a scraper.
- **Social-price decoupling** (from anomaly-detection research) is a more refined version of raw social volume: track whether sentiment/social volume and price are moving unusually *in sync* or unusually *decoupled* relative to their own recent history (one framework used a 3-std-dev-over-30-days threshold) — sudden decoupling (hype rising, price flat) may be more informative than either metric alone, and fits the "accumulation before the move" thesis directly: rising social + flat price = building narrative before markup.

---

## 5. Prior art — what's already been built (and its honest results)

**`robinhood-screener` (GitHub, public)** — the most rigorous prior art found, built almost exactly this system, but for a **fast-scalp timeframe** (entries within ~90 min of launch, exits within hours) — a different hypothesis than this project's multi-day approach. Its honest, published results (relevant as calibration, not as a verdict on the multi-day approach):
- Its top alert tier beat a control group at 1–6 hours but **lost by 24h and 7 days — 0 of 16 top-tier alerts were positive a week out.**
- Winners peak at a median of ~4 hours; 71% give back >80% of peak by 24h.
- Best-performing exit policy of 16 tested: the negative control **"sell immediately."**
- Entry classifier: AUC ~0.54 (barely better than a coin flip) across two attempts.
- **Deployer-track-record approach abandoned**: devs rotate wallets deliberately, so every major winner came from a previously-unseen deployer — this is *why* this project's cross-token *buyer* (not deployer) wallet tracking (Part 2) is the better-supported version of the same instinct.
- Its statistical toolkit is worth adopting regardless of the timeframe mismatch: **paired comparison against a same-day/same-age control group, Deflated Sharpe Ratio (corrects for multiple-testing luck), forward-only nomination testing (never validate a rule on the data used to invent it), mandatory negative-control baselines ("sell immediately," random exit) that a real strategy must beat, intention-to-treat (a promoted token's earlier control-group data stays in the control forever).**

**`MadeOnSol/robinhood-chain-sdk`** — a paid API/SDK that's already built: bundle detection (`tokenBundle()`), smart-money wallet ranking (`alphaWallets()` — net realized ETH, win rate, memecoin-share filter, bot-flagging), and an LP-removal feed with a pre-computed `provider_is_token_deployer` flag (the rug tell, pre-joined). Useful as a checklist of "what's worth computing" even if not used directly.

**`robinhood_meme_scan` (CryptoHub)** — simpler open CLI heuristic scanner (Blockscout + optional RPC). Explicit and correct in its own docs: this class of tool **filters traps, it does not pick winners** — keep the rug-filter and the runner-predictor as conceptually separate tools in this system, not one conflated score.

---

## 6. Backtest methodology (non-negotiable, adopt in full)

1. **Time-based splits only** — train on strictly earlier tokens, test on strictly later ones. No random shuffling (leaks future regime info backward).
2. **Rolling window retraining** — market dynamics drift fast (new launchpads, the Sept 29 gas-subsidy cliff, etc.).
3. **Imbalance-aware metrics** — F1 on the positive class, MCC, AUCPRC. Not raw accuracy (most tokens die; accuracy alone rewards always-predicting-death).
4. **Explicit runner definition, decided in advance** — with this project's multi-day horizon, define it in days (e.g., "Nx within Y days without an intervening drawdown below Z%"), not hours.
5. **Log negative examples** — every token seen but not flagged is as valuable as every one flagged, for computing false-negative rate and learning what "almost but didn't" looks like.
6. **Test cross-venue generalization explicitly** — a model trained on Pons-launched tokens may not transfer to Long.xyz-launched tokens; verify, don't assume.
7. **Adopt the robinhood-screener statistical toolkit wholesale** (Part 5): paired same-day/same-age control comparison, Deflated Sharpe, forward-only testing, mandatory negative-control baselines, intention-to-treat logging.
8. **Signal-selection holdout, separate from the time-based split above** — with dozens of candidate signals (Part 1's feature table, Part 2's forensics, Part 4's social metrics) tested against a positive class that may only number in the hundreds-to-low-thousands (Part 10), the risk of a signal looking predictive by chance alone (multiple-comparisons) is real even within a single time period. Split the sample itself (not just by time) into a discovery half and a confirmation half: decide which signals appear to matter using only the discovery half, then verify they still hold on the untouched confirmation half before trusting them in the live scorecard. This is a distinct safeguard from the time-based forward-only testing above — that one guards against using future information, this one guards against overfitting to a small sample width-wise across many signals.

**Sell-side / historical liquidity-depth data — available, but requires reconstruction, not a simple pull.** Uniswap V3-style pool depth isn't exposed anywhere as a clean "historical liquidity" column — it has to be reconstructed from the pool's raw Mint/Burn/Swap event logs, which are permanently on-chain and queryable via Dune SQL, just not pre-aggregated. Budget this as its own distinct engineering task for Claude Code, not an assumption that it's as easy as pulling historical price.

**Practical Claude Code workflow**: pull historical data for known cases (CASHCAT, AI, Pons/Long.xyz-launched tokens as "ran," plus a broad sample of tokens that didn't, as contrast) → compute the Part 1 feature table plus Part 2 forensics at multiple daily snapshots (not just launch moment, given the multi-day thesis) → label with the explicit multi-day runner/rug definition → check whether rule-based thresholds correctly separate known cases → only then consider ML over hand-tuned rules.

---

## 7. Tools, APIs & Data Sources — full reference

**On-chain / rug-risk scanners & explorers**
- **Robinscan** (robinscan.io) — the Robinhood Chain block explorer, chain ID 4663. Third-party, not Robinhood-affiliated. Free.
- **Blockscout** — the explorer instance behind Robinhood Chain per multiple open-source tools; sits behind a Cloudflare challenge from some IPs (a browser-UA + Referer workaround is documented in `robinhood-screener`'s source code).
- **GeckoTerminal** — new-pools feed with buyer counts, holder count, top-10% concentration, dev holding, launchpad graduation status, honeypot flag, OHLCV. Free, ~30 req/min per IP.
- **Dexscreener** — market snapshot data, 30 addresses/call, free/keyless. Used by `robinhood-screener` as its only source of forward-return fills for backtesting.
- **ScanHood** — chain-specific verdict + sell-simulation + read-only swap quote + launch feed for Robinhood Chain specifically. Free/keyless.
- **RobinX** — deployer track record (launched/real/dead/score) + insider flags for Robinhood Chain. Free tier.
- **KyberSwap** (aggregator) — route quotes with USD legs + gas; used for paper-fill pricing on tokens without a V2 pair.
- **DeFade** (defade.org) — multi-chain (incl. Robinhood Chain) rug-risk scanner: bundle %, dev wallet status ("fully exited"/"transferred out"), composite risk score. Free daily scans, Pro from $19/mo.
- **`robinhood_meme_scan`** (CryptoHub, GitHub) — open CLI heuristic scanner via Blockscout/RPC; explicitly filters traps, doesn't pick winners.
- **honeypot.is / GoPlus** — noted as poor fits for this chain specifically (honeypot.is rejects the chain; GoPlus covers only ~3% of tokens here) — don't rely on these as gates for Robinhood Chain.

**Wallet / smart-money / bundle analysis**
- **GMGN.ai** — flags dev wallet, insider holdings, sniper-wallet clusters, bundle % per token; surfaces a dev's launch history.
- **Bubblemaps / InsightX / Faster100X** — visual wallet-cluster mapping to check whether "distinct" holders are actually linked.
- **Arkham** — entity-level wallet aggregation; used in the CASHCAT top-holder concentration research (89.1% held by top 1,000 addresses).
- **Lookonchain** — tracks known/notable wallets; source of the Ansem→Artificial Inu buy that preceded a rally leg.
- **Nansen** — the reference methodology for smart-money wallet scoring (win rate, realized PnL, ROI, holding-period consistency; merges known-fund labels with algorithmic top-X% flagging); has a documented API with a PnL leaderboard and flow-intelligence endpoints.
- **WalletFinder.ai** — exports wallet trade history to build custom scoring spreadsheets rather than relying on someone else's ranking.
- **`MadeOnSol/robinhood-chain-sdk`** (and its x402 variant) — paid TS SDK, Robinhood Chain specific: `tokenBundle()` (bundle detection + % supply held), `alphaWallets()` (smart-money ranking by net realized ETH/win rate/memecoin-share/bot-flagging), `lpEvents()` (LP removals with a pre-computed `provider_is_token_deployer` rug-tell flag), tokenized-equities endpoint with beacon-proxy identity verification (filters fake NVDA/GameStop-named contracts).

**Social / sentiment**
- **LunarCrush** — purpose-built crypto social-intelligence API (X + Reddit + YouTube + TikTok combined); free tier. Fields: social volume, Galaxy Score, AltRank, sentiment, social dominance. The practical alternative to the now-paid-only raw X API.
- **Santiment** — anomaly-detection framework with a documented "social-price correlation" anomaly (aligned vs. decoupled detection) and a "social dominance spike" anomaly (3-std-dev-over-30-days threshold).
- Raw **X API** — pay-per-use since Feb 2026, no free tier ($0.005/read, $0.015/post); workable but not the first choice here.

**Query / historical data platforms**
- **Dune Analytics** — has full official support for Robinhood Chain (announced alongside the chain); queryable via SQL, exportable, with several existing public community dashboards ("Robinhood Chain: Analytics, Memecoins & Traders," "Robinhood Chain: The Full Trenches," "Robinhood Chain: Network Overview," a memecoin-volume-by-chain cross-chain dashboard). **This is likely the most practical historical-data source for backtesting** — far easier than reconstructing history from raw RPC.
- **DeFiLlama** — used in prior-art fee/TVL reporting (e.g., the Pons-vs-chain fee comparison).

**Academic studies referenced**
- "Catching the Rug" (arXiv 2608.20271) — 6.4M Solana tokens, first-5-min→1hr XGBoost prediction, the feature table in Part 1.
- MemeTrans (arXiv 2602.13480) — 40k Solana tokens, bundle-level entity resolution, launchpad-phase risk annotation.
- Yaremus et al., TON rug detection (arXiv 2509.01168) — TVL/Idle rug definitions, 5-minute detection window.
- Mazorra et al. — 26,957-token Uniswap scam dataset (2020–2021), Herfindahl-Hirschman distribution metric, found 90% of tokens using lock contracts like Unicrypt still turned malicious.
- Srifa et al. — Uniswap V3 rug-timing prediction (7,450 tokens).
- Cao et al., BSC wash-trading early-warning (arXiv 2603.13830) — self/matched/circular trade patterns, ~3.8hr mean lead time, PR-AUC 0.9185.
- Wu et al., RugScreener — temporal GNN for ERC-20 rug detection.
- "Coordinated Sniper Cohorts on Pump.fun" (arXiv 2607.02795) — 1,012 persistent wallet rings, first-hour buyer-flow causal analysis.
- "Resisting Manipulative Bots in Meme Coin Copy Trading" (arXiv 2601.08641) — bundle-bot/sniper-bot/wash-trading/comment-bot detection algorithms.
- "MemeChain" dataset (arXiv 2601.22185) — 34,988 tokens, cross-chain lifecycle analysis.
- "Measuring Memecoin Fragility" (arXiv 2512.00377) — volatility/social-diffusion/whale-dominance framework; found meme-coin correlations to broader crypto converge toward 1 during stress periods (diversification collapses when it's needed most).
- "Cryptocurrencies and Tokens Lifetime Analysis from 2009 to 2021" (MDPI) — formal **survival analysis / time-to-event modeling** applied to token lifespans — methodologically the right tool for this project's multi-day horizon (models time-to-death or time-to-breakout directly, rather than a binary classifier at a fixed snapshot).
- "Hour-Aware Adaptive Risk Management" (arXiv 2606.08232) — exploratory (underpowered, not pre-registered) UTC time-of-day P&L effects; flagged as a candidate feature needing larger-sample replication, not a confirmed signal.
- a16z LVR research — σ²/8 formula for constant-product-pool value bleed to arbitrageurs.

---

## 8. Additional findings — base rates, nuance, and a better statistical framework

**Base rates (context for calibrating any model's expectations):**
- ~97% of memecoins die or decline to irrelevance; average lifespan ~1 year for the ones that don't (Binance Research, cited 2026).
- Survival rate below 8% at 60 days; under 1% of new launches ever "graduate" to real trading status.
- On Pump.fun specifically, ~98.6% of tokens go to ~0, ~68.7% see their last trade on launch day itself.

**Important nuance from the original `solana_screener` (the project `robinhood-screener` was ported from), worth weighing against the rug-filter logic in Part 2:** its own documentation states plainly that attention-driven winners (its examples: Ansem/TJR-style tokens) "ran on attention, not on anything a safety screen can detect" — and **often had high insider/sniper concentration**. This is a real tension *for a fast-scalp strategy* — but resolved for this project's multi-day approach (see Part 12): rug-filtering and runner-detection are sequential stages of one funnel, not competing objectives, once you're not acting in the first hours anyway.

**Statistical framing recommendation:** given this project's multi-day, "no rush" horizon, **survival analysis (time-to-event modeling, e.g. Cox proportional hazards)** is likely a better-fitting statistical tool than a binary classifier scored at one fixed snapshot time. It directly models "how long until this token dies" or "how long until it breaks out," using every day of data as it arrives, rather than forcing a single yes/no decision at an arbitrary cutoff — which fits "willing to wait days of data before deciding" much more naturally than the fast-scalp classifier approach used in the prior art.

---

## 10. Backtest token list — runners shortlist + random-sample method

**Feasibility context:** Pons alone has produced ~646,000 tokens since July; total across all launchpads (Pons, hood.fun, Pools.trade, TrustSwap, the now-collapsed Noxa) is well over 700,000 and climbing ~10,000/day. ~97%+ die within days, so a full census adds cost without adding much signal — a stratified sample plus the known-outcome shortlist below is the right scope, pulled via Dune's SQL interface rather than crawling RPC token-by-token.

**Important caveat on what follows:** the tickers below are sourced from news/aggregator coverage, which reports names and market context but never publishes contract addresses. Resolving each ticker to its actual verified contract address is a required first step for Claude Code (via GeckoTerminal search, Dexscreener search, or Robinscan) before any backtest can run — treat every entry below as "confirm and resolve," not "ready to query."

### Known runners / notable cases (positive + mixed examples)

| Token | Launch context | Why it's a useful case |
|---|---|---|
| **CASHCAT** | Appeared June 18, 2026, pre-mainnet; "fan fiction with a ticker," 1B fixed supply, 0% tax, LP claimed burned. Peaked >$200M cap in July, fell 60%, rose ~90% after an August Robinhood app listing, new ATH ~$0.3143 on Sept 3, ~39% below that two weeks later. | Best-documented full cycle: organic rise → drawdown → catalyst-driven second leg → fade. Good for testing whether your framework flags both legs, not just the first. |
| **PONS** | Launchpad's own token, ~$300M cap, "graduated out of the meme category" per trackers. | Not a memecoin — a reflexive infrastructure token. Useful as a negative example for "don't classify this as a comparable memecoin launch." |
| **Artificial Inu (AI)** | Paired against tokenized NVDA. ~$280M cap as of early Sept, briefly the #1 chain memecoin by cap. Rally leg tied to a tracked KOL (Ansem) buy. | Best example of narrative-pairing + smart-money-catalyst combination. |
| **BONER** | Paired against tokenized HIMS. | Second stock-pairing example — useful for testing whether the pairing pattern generalizes beyond AI/NVDA. |
| **HMM, TENDIES, STONKBROKER** | Named as the "first wave" alongside CASHCAT and AI by one aggregator's ranking (mixed price performance — TENDIES +17% but HMM and STONKBROKER both down double-digits at that snapshot). | Same cohort/timeframe as the two big winners but with weaker outcomes — useful contrast set within the same launch window. |
| **YOLO** | Explicitly described by one source as showing "no clear story driving its moves" and swinging from all-time-high to all-time-low within days. | A clean "hype without narrative" example — good negative/contrast case precisely because it looks active but isn't sticky. |
| **PIPEDOG** | Launched July 28, 2026, quickly became one of the network's larger memecoins. | Additional mid-cap example outside the CASHCAT/AI duopoly. |
| **DOGO, MOW/MowCat, microduck, Memory Cow Moo, CASHDOG, Little John** | Named across various "top coins" listicles; CASHDOG and Little John specifically flagged for high volume relative to market cap (fast/active trading, not long-term holding). | Broader mid/long-tail set — useful for testing whether your model correctly avoids over-flagging tokens that have volume but not conviction. |
| **Noxa-launched tokens generally** | Noxa was the dominant launchpad in the first two weeks; it collapsed July 11–13. | Any token launched specifically through Noxa is worth flagging as a distinct cohort — the launchpad's own collapse is a natural experiment on what happens to a whole cohort when its launch venue fails. |

### Random-sample method (for the "everything else" comparison population)

Rather than a literal full crawl, have Claude Code pull a **stratified random sample via Dune SQL** (see Part 7 for the Dune Robinhood Chain dashboards/dataset access) using something like:
1. Partition by **launchpad** (Pons, hood.fun, Pools.trade, TrustSwap, Noxa) and by **week since launch** (July 1 – present), since launch conditions shifted a lot week to week (Noxa's collapse, Pons's rise, the approaching Sept 29 gas-subsidy cliff).
2. Within each partition, pull a fixed random N (e.g., 50–100) token-creation events — SQL `ORDER BY random() LIMIT N` per partition, or a seeded hash-of-address sample for reproducibility across reruns.
3. This gives a few thousand tokens total spanning every launchpad and every week — enough for the survival-analysis approach (Part 8) to have real statistical power, without the cost of touching the full 700k+ population.
4. Explicitly include the **Noxa cohort** as its own stratum even though the launchpad is dead — it's a distinct, bounded natural experiment worth keeping separate rather than folding into a generic "July" bucket.

**Next concrete step:** before any of this can run, each shortlisted ticker above needs its verified contract address confirmed (ticker collisions/impostor tokens are a documented problem on this chain — the earlier research flagged copycat tickers and fake "Robinhood Chain" tokens as an active scam pattern), and the Dune query needs to be written and tested for the random-sample partitions.

**Ticker collision — worse than a general caution, needs an explicit safeguard.** The "What If" (IF) token has been documented with **21+ copycat contracts sharing its exact name and ticker** — and critically, screening tools sorted by holder count or liquidity return the *fake* contracts first, since impersonators deliberately seed inflated holder/liquidity numbers to look more legitimate than the real token. Naive lookup-by-ticker is actively unsafe on this chain, not just imprecise. **Required safeguard: every token must be identified and stored by verified contract address from the start (e.g., cross-referenced against the token's own official site/socials, or Robinscan's contract-verification status), never by ticker/name lookup alone** — this applies to every shortlisted token in this document, the random sample, and anything the live scanner discovers.

### Comprehensive positive-class filter (supersedes relying on the hand-curated shortlist alone)
Rather than relying only on the named tickers above (sourced from news coverage, which only covers famous cases), run a single cheap query across the **entire** launched-token population: `MAX(price) / launch_price ≥ 10` — anything that never reached 10x from its launch price at any point is excluded from the "interesting" set entirely. This is far cheaper than the full forensics pipeline (a single aggregate SQL query, not per-token bundle/wallet/contract analysis) and, unlike the news-sourced shortlist, it's **exhaustive** — it catches every token that ever did 10x, including obscure ones no article ever covered.

**Implementation detail:** define "launch price" as a short VWAP over the first few minutes of real trading, not the literal first transaction — a dust trade or a sniping bot in block one can distort a true "first price" badly, making the ratio unreliable.

**Critical caveat — do not skip the random sample because of this filter:** a dataset containing *only* tokens that hit 10x can tell you what winners looked like, but not what makes them different from losers, since there's no loser in it for contrast. This is the exact survivorship-bias trap Part 6's methodology exists to prevent. Use the ≥10x filter to comprehensively build the **positive class** (replacing/upgrading the hand-curated shortlist above), but keep the stratified random sample as the **negative/contrast class** — both are still required together for the system to learn what actually distinguishes the two groups.

**Negative-sample sizing (case-control design):** size the random/negative sample **larger than the positive class, not equal to it** — a reasonable starting ratio is **3–5x the count of tokens that cleared the ≥10x filter**, once that actual count is known. Two reasons this isn't just 1:1: (1) the "everything else" population is far more heterogeneous in *how* it fails (outright rug, idle death, wash-traded fake, never-got-attention) than the winner population is in how it wins, so it needs more examples to adequately represent that diversity; (2) since the negative sample is stratified by launchpad and week (same as above), and winners likely cluster into particular high-activity weeks/launchpads, each stratum needs enough negative examples of its own for a fair within-stratum comparison — not just an equal overall headcount. This is standard practice for rare-event case-control/case-cohort study designs generally.

### Repo & data-store architecture (settled, updated)
- **Code stays in the public repo** — the backtest pipeline (data pull, feature computation, model/survival-analysis code, GitHub Actions workflow) is infrastructure, not sensitive, and benefits from the public repo's unlimited Actions minutes for the heavier batch runs this requires.
- **A second, private GitHub repo holds versioned config** — current scorecard weights, thresholds, and any "what actually works" findings, kept out of the public repo so the tooling stays open while the actual edge (if found) stays private.
- **Supabase (Postgres) is the actual data store** — the alert ledger (every alert plus its forward outcome, feeding the self-recalibration engine in Part 14.5), the wallet-score/smart-money table, and per-token computed feature history all live here rather than as flat files in a repo, since this data grows continuously and needs to be queried, not just archived.
- The public repo's workflow writes to Supabase and to the private config repo via GitHub Secrets (a Supabase service key, and a fine-grained GitHub PAT scoped to the private repo).
- This is a lighter-weight version of the split originally discussed for live trade execution (Part on trading, earlier in this project) — same principle (sensitive/growing stuff isolated from the public repo) but here it's data/output, not funds, so the security bar is lower.

---

## 12. Resolved: runner definition & the decision-gate logic

These two items were open in earlier versions of this doc — resolved here with concrete, backtestable definitions.

### Runner definition (settled)
Empirical grounding: CASHCAT launched June 18, consolidated (a later analysis explicitly describes a "rounded bottom pattern between June and August") for roughly three weeks before its major rally legs beginning around July 9–11 — real evidence the multi-day-accumulation-then-breakout pattern isn't hypothetical on this chain, at least for the best-documented case.

**Definition:**
1. **Detect the accumulation window algorithmically**, not by fixed day-count — a period where ATR (or Bollinger Band width) is contracting, ADX is below ~20 (no strong directional trend), and volume is flat-to-declining. This is standard, well-established consolidation-detection methodology (the "Volatility Contraction Pattern" framework), just applied to memecoin timeframes (likely hours-to-days windows rather than the weeks-to-months typical in equities) rather than invented from scratch.
2. **Compute the accumulation-period reference price as a VWAP** (volume-weighted average price) over that detected window — not a simple average, so it weights toward where real size actually traded.
3. **Runner = price reaches ≥5x that VWAP within a bounded window after accumulation ends** (30 days is a reasonable starting bound — generous enough not to artificially cut off a slow burn like CASHCAT's, tight enough to remain a meaningful test; adjust once early backtests show the actual distribution of time-to-breakout among known runners).

### Lane B clarification (resolved — not literal-speed instant, forensics-primary)
Lane B is **not** about sub-hour or minute-level reaction speed — it covers tokens showing strong price action within hours-to-low-days that never form a classic multi-week accumulation range, evaluated primarily on non-price forensics (Part 2) with price action as one confirming input among many, not the deciding one. A token can begin with a sharp early move and *still* be building the range that later defines its longer consolidation — the two aren't mutually exclusive, and Lane B doesn't require ruling that out. The 5–10 minute GitHub Actions polling cadence already planned is entirely adequate for this — no low-latency/mempool-level infrastructure is needed, since this system is not trying to win a speed race with bots.

### Instant-runner lane (correction — not "out of scope," a second lane with its own criteria)
Earlier framing incorrectly treated tokens with no detectable accumulation window as entirely out of scope. Correction: **price shape is only one input, not the only one** — a token can lack a price-based accumulation window and still show strong *non-price* forensic conviction (smart-money wallet entries, healthy contract/LP structure, genuine holder growth rather than bot bursts, absence of every red flag in Part 2, including its contract-level forensics subsection). Two lanes, not one:

- **Lane A — accumulation-confirmed (above)**: the primary strategy. Normal position sizing, higher confidence, backed by the CASHCAT-style multi-week evidence.
- **Lane B — fast movers (hours-to-days), forensics-qualified**: no classic multi-week accumulation window forms, but the token clears an even *higher* bar on every non-price signal (contract forensics, wallet/whale forensics, LP health) with zero red flags. These are explicitly **small, capped speculative positions** ("even $100, easy risk to accept losing entirely, asymmetric upside") — sized deliberately smaller than Lane A positions, reflecting that Lane B is a higher-variance bet on forensic quality alone, not a full-confidence read. Backtest Lane B separately from Lane A — pooling the two together would hide whether the non-price signals alone actually carry any predictive weight, which is an open empirical question, not an assumption to build in.

**Who finds the actual example tokens for each lane — an honest division of labor:** I can identify plausible *named candidates* from public news/aggregator coverage (as done for the Part 10 shortlist), and flag which lane each one plausibly fits based on how it's been described qualitatively (e.g., CASHCAT's documented multi-week consolidation fits Lane A; a token described as "no clear story, swings ATH to ATL within days" — YOLO — looks more like the anti-pattern below than genuine Lane B). But **rigorously classifying a token into a lane requires the actual price/volume time series and the ATR/ADX/VWAP computation** — that's not something achievable from news coverage, it requires the real historical data pull (Part 7/10). That classification step is Claude Code's job, once it has Dune/RPC data in hand, not something resolvable in this research phase.

### Lane C, Lane D, and two explicit anti-patterns (additional shapes worth watching for)
Beyond "instant runner" and "multi-day accumulation then breakout," the research and the CASHCAT case itself point to further distinct shapes worth tracking as their own categories rather than forcing everything into A or B:

- **Lane C — multi-wave / serial-catalyst re-acceleration**: CASHCAT's own full lifecycle is actually this, not a single clean Lane A cycle — initial rise, a 60% drawdown, a second leg after a distinct catalyst (the August Robinhood app listing), a fade, then a third leg to a new all-time high in September. A token that's already had one full cycle isn't necessarily "done" — it may re-form a genuine second accumulation base at a new level and run again on a fresh catalyst. Worth explicitly re-running the Lane A accumulation-detection logic on tokens *after* a completed cycle, not just once at initial launch — treating "already ran once" as disqualifying would have missed CASHCAT's later legs entirely.
- **Lane D — quiet, steady grind (no violent breakout)**: a token that never forms a sharp parabolic move but steadily compounds — rising holder count, rising volume, gradually rising price over weeks, without ever tripping a "5x from VWAP" threshold quickly. This may still be a genuinely good outcome (steady multi-bagger over a longer horizon) that a system tuned to detect sharp breakouts would systematically miss. Worth tracking with a looser, longer-horizon multiple (e.g., 2–3x over 60–90 days) as its own labeled outcome, separate from the Lane A/B "runner" definition.
- **Anti-pattern 1 — idle death / slow bleed**: distinct from an outright rug (dev exit, LP pull). No dramatic event — the token simply never gains organic traction and decays to near-zero volume over days/weeks (this is exactly the "Idle" rug definition from Part 1's academic sourcing, TON research). Worth explicitly recognizing this as a bland disqualifier, since it looks passively okay in a snapshot check that only screens for active rug behavior.
- **Anti-pattern 2 — hype-without-substance fast fade**: a token that pumps hard on pure attention with no forensic backing (high concentration, no genuine holder growth, wash-trading present) and craters just as fast — the YOLO example above. This can superficially resemble Lane B (instant mover) on price action alone, which is exactly why Lane B's bar is *forensics*, not price — a token failing the forensic checks despite a hot chart gets correctly rejected rather than mistaken for a real Lane B candidate.

These four (Lane A, Lane B, Lane C, Lane D) plus the two anti-patterns give the system six recognizable shapes to classify a token into, rather than a single binary "runner or not" — which fits the "observe for everything" instinct expressed earlier in this project.

### Decision-gate logic (settled — resolves the "rug-avoidance vs. winner-capture" question)
Not a tradeoff — a two-stage funnel, since this system never acts in the first hours anyway:

**Stage 1 — early screening funnel (days 0–2):** kill anything showing rug/dead/wash-trading signatures (Part 2) before it ever reaches accumulation-watching. A genuine rug rarely survives this window regardless, so this stage costs little in terms of true candidates lost.

**Stage 2 — weight-of-evidence scorecard (for whatever survives Stage 1):**

| Bucket | Signal examples | Effect |
|---|---|---|
| **Red flags** (veto power) | bundle detected, dev wallet exited, LP unlocked, wash-trading pattern detected, no accumulation window ever forms | Enough red flags = reject regardless of green score |
| **Green signals** (must clear a minimum) | algorithmically-detected consolidation phase present, tightening volatility with rising (filtered) holder count, USD-share-of-buys rising during the range (accumulation not distribution — Part 2), smart-money/cross-token wallet entries during the range, social volume rising while price stays flat (decoupling — Part 4) | Need to clear a minimum total score before any alert fires |

No alert fires until green signals clear their threshold **and** red flags stay under theirs — directly implementing "enough yeses confirmed, and not too many noes," rather than a single composite score that could hide a bad red flag under a pile of good green ones.

**Still to calibrate (not blocking, but not yet done):** the exact point values/weights within each bucket, and the pass/fail thresholds — these should come from the backtest (Part 10's shortlist + random sample) rather than being guessed upfront; start with an even/simple weighting, then let the statistical rigor in Part 6 (paired controls, forward-only testing) tell you which signals are actually pulling weight.

---

---

## 13.5 Exit strategy (previously missing — the entire system was entry-only)

Everything designed so far addresses when to buy. Nothing addressed when to sell — a real gap, since the strongest finding in the prior art (Part 5) was specifically about exits (best exit policy tested = "sell immediately"). Real case studies on this chain give concrete, checkable sell-side signals:

- **Unverified-narrative collapse**: the token simply named "1" ran from $800K to $15M on a rumor that a Tenev-linked wallet was buying, then collapsed 93% once traders discovered the wallet was a long-compromised demo address with a publicly leaked seed phrase. **Sell trigger: if a pump is attributed to a specific "whale" or narrative, verify that wallet/claim independently — an unverifiable or debunked catalyst is an immediate exit signal**, not just a reason for caution at entry.
- **Volume-during-decline is not a health signal on its own**: "A Meme Coin" (AMC-linked) fell 79% from peak while volume stayed elevated ($70–150M) throughout the decline. **Don't treat sustained volume as reassurance during a drawdown — check the buy/sell ratio within that volume specifically** (Part 2's USD-share-vs-count-share metric applies directly here, just watched for the reverse signal: count-share high/USD-share low during a decline = distribution, not accumulation).
- **Stock-paired token premium/mean-reversion (chain-specific, newly identified)**: BONER cornered ~81% of tokenized HIMS's available on-chain supply, pushing its price ~400% above the real NYSE stock price over a weekend when new token issuance was constrained. **For any stock-paired token, track the live premium between its on-chain price and the real underlying stock's price** (a simple ratio, computable from any stock price feed plus the on-chain price) — an extreme, growing premium during a period of constrained issuance is a predictable mean-reversion sell trigger, especially heading into a market open or an issuance-supply increase.
- **Early-wallet exit tracking (sell-side mirror of Part 2's buy-side whale tracking)**: WHITEWHALE crashed 45% in minutes with early, cheap-cost-basis holders confirmed to have exited first. The same wallet-tracking infrastructure built for entry detection (Part 2) applies directly in reverse — track whether wallets that entered early/cheap in *your own held position* are exiting, not just whether new smart-money wallets are entering elsewhere.

**Recommended exit-signal structure**, mirroring the entry scorecard's two-stage design (Part 12):
1. **Hard triggers (immediate exit regardless of other scoring)**: a previously-verified catalyst wallet/claim is debunked; a top-10/early-cohort wallet exits a large share of its position; contract state changes (a previously-renounced-looking contract turns out to have an active mint/pause path that gets exercised).
2. **Soft scorecard (mirrors the buy-side weight-of-evidence system)**: rising count-share-vs-USD-share of sells, widening LVR/volatility (Part 2) signaling pool fragility, declining smart-money wallet net position, and — for stock-paired tokens specifically — a widening premium against the real underlying stock.

**This needs its own backtest, separate from the entry backtest** — test exit rules against the known-runner population specifically: at what point before each token's peak-to-trough collapse would each candidate exit signal have fired, and how much of the run would it have captured vs. given back. This is exactly the kind of analysis the "1", "A Meme Coin," BONER, and WHITEWHALE cases above make possible once their full price/wallet histories are pulled.

---

## 14. Unsupervised pattern discovery — letting the system find shapes we haven't named

Everything above (Lanes A–D, the two anti-patterns) is **supervised** — hand-labeled categories the system sorts tokens into. This section covers the genuinely different, more powerful capability: letting the system discover its own groupings from the data, without being told the categories in advance. Buildable on the same feature pipeline (Parts 1–2) already designed — not a separate project, a second pass over the same data.

**Methods:**
- **Feature-space clustering** (k-means, or better, HDBSCAN — doesn't require guessing the number of clusters upfront) on the full tabular feature vector (Part 1 + Part 2's forensics) across the whole sampled population. Natural groupings emerge from the data itself.
- **Time-series/trajectory clustering** (dynamic time warping, k-shape) groups tokens by the actual *shape* their price+volume took over time — this is the method that could surface a genuine fifth pattern nobody named, rather than forcing every token into A/B/C/D.
- **Hidden Markov Models** for regime discovery: Wyckoff's phases (accumulation/markup/distribution/markdown) are themselves a hand-designed regime-switching story — an HMM can data-mine phase-like regimes directly from price/volume without hand-defining what the phases are, either validating the lanes already built or surfacing different structure.
- **Anomaly/novelty detection** on top of the clustering — flag any token that doesn't fit well into any existing cluster (hand-labeled or discovered) as "new pattern candidate, flag for review" rather than forcing it into the nearest bucket. This is the direct answer to "can it flag something it doesn't recognize" — yes, this is the mechanism for that.

**Two caveats, not reasons to skip this:**
1. **Class imbalance cuts against discovering rare good patterns.** ~97% of tokens die, so clustering will easily find several ways to fail (abundant examples) but may lack enough genuine multi-x runners to form a distinct winning cluster even if a real one exists — a data-volume limitation, not a methodology flaw.
2. **A discovered cluster still needs the same rigor as a hand-designed lane.** An unlabeled statistical cluster with no story behind it is exactly what the backtest methodology (Part 6 — forward-only testing, negative controls, deflated Sharpe) exists to catch. "The system found a pattern" isn't itself evidence the pattern is real — it must survive the same out-of-sample scrutiny as everything else, or it's overfitting with extra steps.

**Build order:** get the rule-based Lane A–D system working and backtested first — it's interpretable and produces the clean labeled dataset clustering needs as input anyway. Run clustering/HMM analysis as a second pass over that same dataset specifically to (a) check whether the hand-designed lanes match what the data naturally groups into, and (b) surface anything that doesn't fit, for human review of whether it's a real additional pattern or noise.

---

## 14. Accounts & APIs to set up

**Required to start**
- **GitHub** ([github.com/join](https://github.com/join)) — already have this; add a **second, private repo** for code/config (Part 10's repo architecture decision). Use this for versioned config (current scorecard weights, thresholds) — not as the primary data store (see Supabase below).
- **Supabase** ([supabase.com](https://supabase.com) → "Start your project") — free-tier Postgres database. This is the actual data store: the alert ledger (every alert + its forward outcome, feeding the self-recalibration engine in Part 14.5), the wallet-score/smart-money table, and the per-token computed feature history. A private git repo is fine for config; it's the wrong tool for a growing, queryable dataset that needs to be read continuously.
- **Telegram** — no website signup; message **@BotFather** in the Telegram app for a bot token, then message your own bot once to get your chat ID. Both stored as GitHub Secrets.
- **Dune Analytics** ([dune.com](https://dune.com), then Settings → API Keys → Create new key) — primary source for historical Robinhood Chain data (known-runner shortlist + stratified random sample, Part 7/10).
- **Alchemy** ([alchemy.com](https://www.alchemy.com)) — free-tier RPC provider for reliable live Robinhood Chain access, better uptime/rate limits than the public RPC endpoint.
- **Finnhub** ([finnhub.io/register](https://finnhub.io/register)) — free tier, 60 calls/min, no card required. Needed for real equities price data — the stock-paired-token exit signal (Part 13.5, the BONER/HIMS premium check) requires comparing on-chain price against the actual NYSE/underlying stock price, which nothing else in this stack provides. (Alpha Vantage is the well-known alternative but its free tier is only 25 calls/day — too thin for this use.)
- **Healthchecks.io** ([healthchecks.io](https://healthchecks.io)) — free tier, 20 monitored jobs, no card required. This system is entirely dependent on GitHub Actions cron jobs firing reliably; without a dead-man's-switch, a silently failed workflow looks identical to "nothing interesting happened," which is especially dangerous given the self-recalibration engine (Part 14.5) assumes continuous, gap-free logging. Each scheduled job pings it on success; a missed ping triggers an alert.

**Worth setting up, free tier sufficient for now**
- **LunarCrush** ([lunarcrush.com](https://lunarcrush.com)) — free tier for social volume/Galaxy Score data (Part 4); note the free tier is roughly 100 requests/day, worth designing polling frequency around.
- **CoinGecko** ([coingecko.com/en/api](https://www.coingecko.com/en/api)) — free "Demo" API key, covers GeckoTerminal too; mainly for a higher rate limit than the fully keyless tier.
- **Etherscan** ([etherscan.io](https://etherscan.io)) — free API key; unified V2 API covers ~70 EVM chains from one key, but check whether Robinhood Chain is supported yet since it's new.
- **Dexscreener** — no account needed for basic use; keyless public endpoints.

**Optional — paid, contingent on the still-open cost-vs-build-it-yourself decision (Part 16)**
- **`MadeOnSol/robinhood-chain-sdk`** — paid; ready-made bundle-detection and smart-money wallet-ranking endpoints.
- **DeFade** ([defade.org](https://defade.org)) — free daily scans, Pro from $19/mo, for a cross-check against your own contract-forensics logic.
- **GMGN.ai** ([gmgn.ai](https://gmgn.ai)) — check for a public API vs. web-UI-only; useful for cross-validating your own bundle/sniper detection.
- **Nansen** ([nansen.ai](https://www.nansen.ai)) — the professional smart-money wallet-scoring product; likely the most expensive option here, worth evaluating only once your own wallet-scoring logic (Part 2) has been backtested and shown to need it.

**Not needed yet**
- Any funded wallet / private-key management for live execution — that belongs to the separate live-trading decision from earlier in this project (Part on trade execution), not to backtesting, and stays deferred until backtesting has actually produced something worth trading on.

---

## 14.5 Self-recalibration engine (edge decay — built into the system, not a manual chore)

Any real edge found will decay — multiple public prior-art tools already exist doing similar analysis on this exact chain (Part 5), and a pattern that works, once visible (including via this project's own public repo), invites being copied or arbitraged away. Rather than relying on remembering to periodically re-tune things by hand, build drift detection into the system itself:

- **Rolling performance tracking**: log every alert the scorecard fires (both lanes) and its actual forward outcome, continuously — not just during the initial backtest. This is the same "ledger every alert's forward return" discipline the prior art used (Part 5), just kept running permanently rather than as a one-time study.
- **Statistical drift test, not eyeballing**: compare a recent rolling window's real hit-rate against the backtest-expected hit-rate using a formal test (a simple z-test or CUSUM-style control chart against the historical baseline) — this distinguishes genuine drift from ordinary noise, which a casual "does this feel worse lately" check can't reliably do.
- **Per-signal breakdown, not just one overall number**: when drift is detected, the diagnostic should identify *which specific signal(s)* in the Stage 2 scorecard have lost predictive power, not just flag that the composite score overall looks off — this is what lets the system "suggest its own recalibration" concretely (e.g., "the smart-money wallet signal's contribution has degraded over the last N weeks; consider re-weighting or re-deriving the flagged-wallet list") rather than just raising a generic alarm.
- **Re-run the signal-holdout discipline (Part 6, item 8) periodically**, not just once at initial build — as new data accumulates, re-check whether the originally-confirmed signals still hold on the newest data, treating "still works" as something to keep re-verifying rather than a one-time finding.

---

## 15. Decisions log — including paths considered and rejected

For Claude Code's benefit: a consolidated log of choices made through this project's research, and what was explicitly ruled out, so context isn't lost even though the reasoning lives in the fuller sections above.

| Decision | Chosen | Rejected / superseded |
|---|---|---|
| Social data source | LunarCrush (free tier, cross-platform) | Raw X API — moved to pay-per-use Feb 2026, no free tier; workable but needlessly costly/complex for this |
| Primary analysis framework | On-chain forensics (wallet, LP, contract) as the core signal set | Wyckoff/classical TA as the *primary* signal — demoted to a secondary, later-stage confirmation layer only, since its "distributed float being accumulated" assumption doesn't fit a fixed-supply token whose full supply exists at block one |
| Deployer-identity tracking | Not used as a standalone signal | Explicitly abandoned by the prior art (`solana_screener`) because deployers deliberately rotate wallets between launches to evade exactly this kind of tracking — replaced with *buyer*-identity cross-token tracking instead, which isn't similarly gamed |
| Statistical framing | Survival analysis (time-to-event modeling) recommended as the better fit | A fixed-snapshot binary classifier (what all the surveyed prior art used) — still worth building as a simpler v1, but flagged as a worse fit for this project's explicit multi-day, no-rush horizon |
| Rug-filter vs. runner-detection relationship | Sequential two-stage funnel (Part 12) | Originally framed as a tradeoff ("never touch a rug" vs. "never miss a winner") — corrected once it became clear this system never acts in the first hours anyway, which removes the tension that only applies to fast-scalp strategies |
| Tokens with no accumulation window | Lane B — a distinct, smaller-sized speculative category, scored on non-price forensics alone | Originally ruled entirely "out of scope" — corrected; price shape is one input, not the only one |
| Repo architecture | Public repo for code/infrastructure; second private repo for backtest results and any discovered thresholds | Committing results directly into the public repo — rejected once "what actually works" was recognized as worth keeping private even while the tooling stays open |
| Backtest data scope | A comprehensive ≥10x-from-launch-VWAP filter (Dune query across the full population) to build the positive class exhaustively, plus a stratified random sample (by launchpad and week) for the negative/contrast class | A full census of all 700,000+ launched tokens with the entire expensive forensics pipeline run on each — rejected as high cost for little added signal; relying on the hand-curated news-sourced shortlist alone as the only positive-class source — superseded once the cheap exhaustive query was identified as strictly better |
| Live trade execution | Deferred entirely; kept as a separate, later decision gated on backtest results | Executing trades directly from the same public repo as the monitoring/backtest code — rejected outright on security grounds (a wallet private key must never sit in a public repo, even via Secrets, given fork/PR/log-exposure attack surface) |
| Fast-scalp entry timing (act within the first 30–90 minutes) | Not this project's approach | This is what the closest public prior art (`robinhood-screener`/`solana_screener`) actually tested and found weak results for (AUC ~0.54, best exit = sell immediately) — deliberately not this project's strategy, which instead targets multi-day accumulation and Lane B forensics-only conviction |
| Exit strategy | A dedicated hard-trigger + soft-scorecard system (Part 13.5), backtested separately from entry | Originally the system had no exit logic at all — an entry-only design was a genuine gap, corrected once real crash case studies ("1," BONER, WHITEWHALE) made concrete sell-side signals identifiable |
| Portfolio-level risk sizing across concurrent positions | Explicitly out of scope | Raised as a potential gap, but the person has clarified this is speculative capital where total loss is an accepted outcome, so formal portfolio risk modeling isn't needed |
| Token identification method | Verified contract address only, cross-checked against official sources | Ticker/name-based lookup — rejected outright once the "IF" token's 21+ impersonating contracts (with inflated fake holder/liquidity numbers ranking above the real one) showed this is an active, not theoretical, risk on this chain |
| Data store for growing/queryable data | Supabase (Postgres, free tier) for the alert ledger, wallet-score table, and feature history | A private GitHub repo alone — fine for versioned config, but the wrong tool for continuously-growing data that needs to be queried rather than archived |
| Stock-price data source | Finnhub (free, 60 calls/min) for real equities prices, needed for the stock-paired-token exit signal | Alpha Vantage as the primary choice — free tier too thin (25 calls/day) for this use; kept as a fallback only |
| Pipeline reliability monitoring | Healthchecks.io dead-man's-switch on every scheduled GitHub Actions job | No monitoring — rejected once it became clear a silent workflow failure would look identical to "nothing interesting happened," undermining the self-recalibration engine's assumption of continuous logging |

---

## 16. Open items / not yet resolved

- Whether to build the LP-depth-as-support/resistance idea (Part 2) as its own testable signal — flagged as novel and untested, worth a dedicated backtest pass on its own before folding into the composite score.
- Whether any paid data source (LunarCrush tier, MadeOnSol SDK, DeFade Pro) is worth the cost vs. building the equivalent from Dune + raw RPC + free sources — not yet decided.
- Token addresses for the watchlist half of the system — still needed before that engine can be scaffolded.
- Point values/weights and pass/fail thresholds for the Stage 2 scorecard (Part 12) — deliberately left uncalibrated until backtest data can inform them.
- Whether to build the rug/runner logic as a binary classifier (as most prior art does) or as survival analysis (Part 8's recommendation, better fit for the multi-day thesis) — not yet decided.
- **Dune's historical data completeness for the earliest (July) period on Robinhood Chain hasn't been independently verified** — its official chain support is itself new. Before trusting large-scale July queries, Claude Code should sanity-check by cross-referencing a few known reference points (e.g., CASHCAT's documented June 18 launch and its known early price action) against what Dune actually returns for that period, rather than assuming full backfill completeness.
