# Critical Review of the Master System Document

**Reviewed:** `00-master-system-v1.md` (389 lines, 16 parts)
**Review date:** 2026-09-20
**Method:** every load-bearing external claim independently verified against primary sources (arXiv, chain docs, vendor pricing pages, the prior-art repo itself). Citations checked for fabrication.

---

## 0. Headline

The document is **better than expected**. Every academic citation I spot-checked is real, correctly attributed, and says roughly what the document claims. That is unusual and worth saying plainly — fabricated arXiv IDs are the default failure mode for this kind of research doc, and there are none here.

The problems are not sloppiness. They are of four kinds, in descending order of severity:

1. **One project-blocking external change that post-dates the document** (Dune).
2. **One imported result that does not mean what the document thinks it means** — and it is the result the entire feasibility case rests on.
3. **Four look-ahead/leakage bugs** that, if built as written, will produce a spectacular backtest that is entirely fake.
4. **A strategic gap**: the document never states why this should work, and never defines what result would make it stop.

And one thing the document gets right without noticing: **the single best idea in it is buried in a footnote in the exit section.** See §5.1.

---

## 1. Project-blocking: the data plan is invalid as of ten days ago

Part 7 calls Dune "**likely the most practical historical-data source for backtesting**." Part 14 lists it under *Required to start* with instructions to create a free API key.

**Dune's free tier went view-only on September 10, 2026.** Accounts created before July 21, 2026 lost the ability to run queries entirely. Free accounts can browse dashboards; they cannot execute anything that consumes credits. The cheapest query-capable plan is **Analyst at $65/mo** (annual billing, 4,000 credits/mo); Plus is $349/mo for 25,000 credits.

This is not a minor cost adjustment. The document's entire backtest architecture — the exhaustive ≥10x positive-class filter, the stratified random sample across launchpads and weeks, the July-period completeness check — assumes free SQL access to a 700,000-token population. **None of that is free any more, and 4,000 credits/month will not cover a 700k-token swap-history scan.**

### Remediation (verified available)

| Source | Cost | Fit |
|---|---|---|
| **Blockscout Robinhood API** (`robinhoodchain.blockscout.com`) | Free, keyless | Official explorer for the chain. Etherscan-style + REST. **Rate limits sized for humans, deep pagination slow, no SLA.** Good for per-token detail, bad for population scans. |
| **SQD (Subsquid)** | Open-source SDK + free hosted Portal | Explicit Robinhood Chain support, validated archive of blocks/txs, historical + real-time. **This is the strongest free replacement for Dune's population-scan role.** |
| **Goldsky** | Free tier | Subgraphs + pipelines + low-latency RPC for chain 4663. |
| **Bitquery** | 7-day Pro trial | Pre-decoded DEX trades. Useful to bootstrap/validate, not to run on. |
| **Dune Analyst** | $65/mo | Only if a specific query genuinely needs their curated tables. |

**Recommended architecture change:** invert the plan. Do not scan the population in a hosted SQL warehouse. **Run a local indexer (SQD) over the chain's Swap/Mint/Burn/Transfer logs into local Parquet, and query it with DuckDB.** This is free, reproducible, unlimited, offline-queryable, and — critically — it gives you the raw event logs you need for liquidity-depth reconstruction anyway (which Part 6 correctly identifies as its own engineering task). You were going to have to build this for depth reconstruction regardless. Building it *first* removes the Dune dependency entirely.

This also fixes a survivorship problem the document does not mention: **aggregator APIs prune dead pools.** Dexscreener/GeckoTerminal are unreliable sources for the negative class precisely because the negative class is the stuff they stop indexing. Raw logs do not have this problem.

---

## 2. The feasibility case rests on a misread result

Part 1 grounds the entire feature catalogue in *"a 2026 academic study (6.4M Solana tokens, XGBoost, first-5-min→1-hour prediction, **AUCPRC ~0.80**)."*

I pulled the paper. It is real — *Catching the Rug: Early Prediction of Fraudulent Memecoins on Solana via Machine Learning*, arXiv 2608.20271, submitted 2026-08-20. XGBoost on fused data does hit **AUCPRC 0.8011** on PumpFun. The number is accurate.

**But the positive class is rug pulls, and its prevalence in the test set is ~31%** (43,835 rugs vs 97,119 non-rugs on PumpFun). A random classifier scores AUCPRC ≈ 0.31 on that split. So 0.80 is a genuinely good result **for detecting rugs** — a common, structurally-signposted event.

This project is not trying to detect rugs. It is trying to detect **runners** — by the document's own Part 8 base rates, **under 1% of launches, plausibly ~0.1%** after the ≥10x filter. A random classifier scores AUCPRC ≈ 0.001 there. **The paper contains no evidence whatsoever about the difficulty of that problem**, and the two tasks are not comparable: rugs are the majority-adjacent class with mechanical tells; runners are an ultra-rare class driven by attention dynamics that leave much weaker ex-ante traces.

Three consequences:

- **Delete the 0.80 from the document's framing.** It is not a performance target and not a feasibility argument. Carrying it forward will anchor expectations at roughly 800× the achievable level.
- **Note the paper reports no baselines at all** — no random, no majority-class, no prior-work comparison. Any AUCPRC you compute must be reported against its own prevalence baseline or it is uninterpretable. Make that a hard rule in the eval harness.
- The same critique applies to the **PR-AUC 0.9185** wash-trading figure quoted in Part 7, and to the **"~3.8hr mean lead time"** — a mean lead time with no false-positive rate and no distribution is not a usable number.

### Related: the prior art's result is worse than the document conveys

Part 5 reports the `robinhood-screener` findings fairly but softens the conclusion. From the repo directly:

- Entry classifier AUC **0.546 and 0.541** across two pre-registered rounds — top decile hit **29–33% against a 33.3% gross breakeven**, i.e. *below* breakeven.
- **"0 of 16 A rows are positive at 7d."**
- Best exit policy was the negative control `ctl_exit_immediately` at **−3.45%** — "the round-trip cost." Every real policy did worse.
- Its own stated conclusion: **"The base rate is negative expectancy. A losing scorecard is the screen doing its job — telling you not to scale."**

The document frames "best exit = sell immediately" as a finding about exit timing. It is not. **It means every tested strategy lost money, and the least-losing one was not playing.** That reframing matters because the document's response — "we're doing multi-day instead" — is an untested assertion offered against a measured negative result.

Also: **the repo was rebuilt on 2026-09-12**, after your document was written. The prior art has moved; re-read it before building.

---

## 3. Four leakage bugs that will fake your backtest

These are the ones that will hurt most, because they fail *silently and flatteringly*. A system with any of these produces an exciting backtest and loses money live.

### 3.1 Point-in-time wallet scoring — the most dangerous bug in the design

Part 2's cross-token buyer tracking is the document's best original idea and its biggest leakage risk.

> *"flag wallets with 2+ prior early entries into tokens that later multiplied; when a new token appears, check its buyer list against that flagged list."*

If you build the flagged-wallet list from your full history and then backtest against tokens inside that history, **you are checking whether wallets that bought winners bought winners.** The backtest will look extraordinary. It will mean nothing.

**Required fix:** the wallet-score table must be **bitemporal**. Every row carries `(wallet, score, as_of_block)`. When scoring token T at time t, you may only join against wallet scores computed from tokens that had **fully resolved their outcome before t**. Not "launched before t" — *resolved* before t, since the label requires forward data. This forces a real gap between the scoring window and the evaluation window, and it will shrink your usable sample considerably. That shrinkage is the honest cost of the signal.

Relevant paper the document **missed**: **TMRugPull** (arXiv 2602.21529) — *"A Temporally Sound Multimodal Dataset for Early RugPull Detection."* Its entire thesis is that prior rug-detection datasets embed post-event information and produce "an illusion of predictive performance that cannot generalize." Read it before building the label pipeline. It is directly on point and nowhere in the bibliography.

### 3.2 Wallet scoring is confounded by activity count

Separate from leakage: with 700,000+ tokens on this chain, **a wallet that sprays 500 random tokens will accumulate "2+ early entries into 10x-ers" by pure chance.** The document explicitly says to score by realized profit and entry percentile "not by wallet size" — correct instinct, wrong confounder. The confounder is **number of tokens touched**, not balance.

**Fix:** score on *precision against an activity-matched null*, not raw hit count. For each wallet, compute a binomial p-value: given it made N early entries and the population 10x base rate is p, how surprising are its k hits? Then FDR-correct across all wallets. A wallet with 3 hits on 8 entries is a signal; a wallet with 5 hits on 900 entries is noise wearing a costume.

Also worth adding: smart money uses fresh wallets too. You already need funding-graph clustering for bundle detection — **reuse it for wallet identity resolution** so a rotating operator doesn't reset their own track record.

### 3.3 The Lane A runner definition detects its window retrospectively

Part 12 defines the accumulation window by ATR contraction + ADX < 20 + flat volume, computes a VWAP over it, and calls a runner ≥5× that VWAP within 30 days.

**At live decision time you cannot know the window has ended.** You only know it is still going. Detecting the window across the full series and then measuring forward return from its end is look-ahead: you have used the breakout itself to locate the reference point you claim predicted the breakout.

**Fix:** make the detector causal. At each time t, evaluate only the trailing k bars. The entry condition becomes *"as of t, the trailing window satisfies contraction criteria"* — which fires many times, including on ranges that never break out. That is correct and necessary: **those false fires are your false-positive rate**, and the retrospective version deletes them from the sample.

### 3.4 The ≥10x filter is right-censored, which corrupts the time split

Part 10's exhaustive positive-class filter is `MAX(price) / launch_price ≥ 10` over all available history.

A token launched in July has had ~80 days to reach 10×. A token launched last week has had 7. **The label is mechanically less attainable for later tokens** — so your time-based test split (Part 6, item 1) has a systematically lower positive rate than your train split, for reasons that have nothing to do with the model. You will read this as regime decay or edge decay. It is neither. It will also poison the Part 14.5 drift detector, which compares recent hit-rate against backtest-expected hit-rate — guaranteeing a false "drift detected" signal forever.

**Fix:** define the label over a **fixed observation window from each token's own launch** — "≥10× within 30 days of launch" — and **exclude any token with less than 30 days of history** from the labeled set entirely. This is textbook right-censoring, and it is the strongest argument yet for the Part 8 survival-analysis recommendation: censoring is precisely what time-to-event models handle natively and what binary classifiers handle by silently corrupting themselves.

---

## 4. Methodological gaps

### 4.1 There is no execution model — the labels are not tradable

This is the largest structural omission. **Every outcome in the document is defined on price.** Nothing anywhere models whether you could have transacted at that price.

A token that goes 10× on $3,000 of liquidity is not a 10× for you. It is a screenshot. Your $500 buy moves it, your exit moves it more, and the printed high may represent a $40 fill.

The document *has* the pieces — constant-product impact math and V3 depth reconstruction are both in Part 2 — but never connects them to labelling. **Connect them:**

- Label on **simulated round-trip P&L for a fixed clip size** (e.g. $500), against reconstructed pool reserves at each timestamp.
- Include: price impact on entry *and* exit, LP fee tier, gas, and **sell-side token tax** (ScanHood's sell-simulation is in Part 7 as a *scanner*; it belongs in the *label*).
- Include **sandwich/MEV cost**. This is a public-mempool L2 with 100ms blocks. A market buy into a thin pool is sandwiched. This is a real, quantifiable haircut on every entry and exit.

I suspect this alone explains a chunk of the prior art's "everything loses" result — and it means the document's positive class is currently contaminated with moves nobody could have captured.

### 4.2 Tokens are not independent observations

Every token on this chain co-moves with chain-wide risk appetite. The document's own bibliography says so: *Measuring Memecoin Fragility* (2512.00377, verified) finds memecoin correlations converge toward 1 during stress. Treating 3,000 tokens as 3,000 independent samples **massively overstates your effective sample size** and will make noise look significant.

**Two fixes, both cheap:**
- **Construct a chain-wide memecoin index** from your own Dune/SQD data and label on **excess return vs. that index.** A 10× during a chain-wide melt-up is a different event from a 10× in a flat week, and right now your label cannot tell them apart.
- **Block-bootstrap by launch week** for all significance testing. Never use i.i.d. standard errors here.

The document's paired same-day/same-age control design (inherited from the prior art) is the right defense and should be stated as **the primary inferential unit**, not one tool among several.

### 4.3 Case-control sampling needs recalibration

Part 10 proposes 3–5× negatives per positive. Sound design. But a model trained at 1:4 **outputs probabilities calibrated to a 20% base rate, when the real base rate is ~0.1%.** Untouched, every score it emits is wrong by ~200×.

**Fix:** apply a prior-correction to the intercept (Prentice–Pyke / King–Zeng rare-events logit) before any threshold is set, and validate with a reliability diagram on a *natural-prevalence* holdout. The document never mentions calibration. Without it the Stage 2 scorecard thresholds are meaningless numbers.

### 4.4 Concentration-as-veto contradicts the document's own evidence

Part 12's Stage 1 kills tokens on bundle detection and concentration. Part 8 then quotes the prior art saying winners *"ran on attention, not on anything a safety screen can detect"* and **"often had high insider/sniper concentration."** Part 10 records CASHCAT at **89.1% held by top 1,000**.

The document asserts this tension is "resolved" by the two-stage funnel. **It is not resolved, it is restated.** If Stage 1 vetoes high concentration on days 0–2, it vetoes CASHCAT. Your single best-documented positive example fails your own first gate.

**Fix — this is an important correction to Part 12:**
- **Vetoes are for structurally unrecoverable conditions only**: active mint path, unrenounced pause/blacklist, failed sell-simulation (honeypot), LP unlocked *and* held by the deployer, deployer already exited.
- **Concentration, bundle %, and sniper share are features with non-monotone relationships to outcome.** Let the backtest find the shape. Do not hard-code a direction you have contradicting evidence for.

Verified relevant: the Fragility paper finds top-100 concentration above 70% is *common* across memecoins and sometimes exceeds 90% — concentration is close to the norm, not a discriminator.

### 4.5 Bar construction is unspecified, and ADX/ATR depend on it entirely

Part 12 leans on ATR, ADX, and Bollinger width. **On bursty, sparse memecoin trading, these indicators are dominated by how you build bars.** A token with 4 trades in an hour has a meaningless 14-period ADX on time bars.

**Fix:** use **dollar bars or volume bars**, not time bars (standard microstructure practice, López de Prado). Bars form when $X of volume has traded, so bar count scales with activity instead of wall-clock. This makes every downstream indicator comparable across tokens with wildly different activity levels — which is the whole point, since you are comparing across tokens.

### 4.6 Six lanes shatter an already-tiny positive class

Lanes A–D plus two anti-patterns is a taxonomy invented before any data exists. With a positive class in the hundreds, **splitting it six ways leaves each lane statistically dead on arrival**, and each lane needs its own threshold calibration, its own control group, and its own multiple-testing budget.

**Fix — invert the build order.** Define **one** continuous, censored outcome (time-to-Nx, or excess-return-over-index with right-censoring), model it once, and treat the lanes as **post-hoc descriptions** of what the model and the Part 14 clustering actually find. The document's own Part 14 build-order note ("get the rule-based system working first, clustering second") has this backwards for exactly this reason: the lanes are hypotheses about cluster structure, and you have a clustering method available to test them rather than assume them.

### 4.7 No power analysis, no stopping rule

The document has extensive multiple-testing defenses (discovery/confirmation split, Deflated Sharpe, forward-only) and no sample-size calculation anywhere. With dozens of candidate signals and a positive class of unknown size, **you cannot know whether your confirmation half can confirm anything.** Run the power calculation before the data pull, and let it determine how many signals you are allowed to test.

Specify the correction concretely too — "multiple testing" is named but no procedure is chosen. Given cross-sectional dependence (§4.2), use **Romano–Wolf stepdown with a block bootstrap**, not Benjamini–Hochberg, which is anti-conservative under correlation.

**And a stopping rule.** Given the prior art measured negative expectancy, the modal outcome here is "no edge." The document has no defined condition under which the project concludes that. **Write one down before you start** — e.g. *"if the v0 paired-control test shows no significant excess return at N=___, stop."* Without it this becomes an unfalsifiable research project that always justifies one more signal.

### 4.8 Drift detection has months of latency — add a fast proxy

Part 14.5's outcome-based drift test (z-test/CUSUM on hit-rate) is correct but slow. At a few alerts a week against a low base rate, **detecting real drift takes months.** By then it has cost you.

**Fix:** add **feature-distribution drift monitoring** (PSI or KL divergence on input feature distributions vs. the training window). It requires **no outcome labels**, so it fires immediately on regime change rather than after enough outcomes accumulate to be significant. The Sept 29 cliff is exactly the event this catches on day one and the outcome-based test catches in December.

---

## 5. Unexplored avenues

### 5.1 The best idea in the document is a footnote in the exit section

Part 13.5 mentions stock-paired premium mean-reversion as a *sell signal*. **It is not a sell signal. It is the only strategy in this entire document with a real economic mechanism and an external price anchor, and it should be its own workstream.**

Verified facts on the BONER/HIMS episode:
- BONER pairs against **tokenized HIMS instead of a stablecoin**, so every BONER buy pulls tokenized HIMS into the pool and **locks it there**.
- Robinhood allows **one authorized partner** to mint new tokenized HIMS, **and only while the NYSE is open**.
- That left **58,714 tokenized shares** against 233M real shares outstanding.
- BONER locked up **53% of the float** (the document says 81% — **incorrect**, or referring to an unsourced different moment).
- Tokenized HIMS hit **$132.64** against a real close of **$28.84** — a **~360% premium** (document says ~400% — close, but the verified figure is 360%).
- **Resolution: within roughly one hour of the NYSE reopening, the authorized minter created ~4,000 new tokens and the price collapsed back to ~$29.**

Read that last line again. This is a dislocation with:
- a **known cause** (mint authority constrained to market hours),
- a **known magnitude** (observable premium vs. a free real-time equity feed),
- a **known resolution trigger** (NYSE open),
- a **known resolution latency** (~1 hour),
- and a **structural reason it recurs** (the minting constraint is permanent, and weekends are 2 days long).

That is not memecoin gambling. That is a **calendar-driven arbitrage against a supply constraint**, and it is categorically higher-quality than anything else in this document. Finnhub (already in Part 14) provides the equity leg. The on-chain leg you already need.

**Recommendation: build this first.** It is cheaper, its hypothesis is falsifiable in days rather than months, and unlike runner-prediction it has a mechanism you can state in one sentence. Caveats to model honestly: the execution leg is the hard part (you need the premium to be capturable net of impact and fees on a thin pool — see §4.1), you are short a token that can keep being cornered, and the strategy is capacity-limited by the same thin float that creates it. Test whether the premium is *tradable*, not just *observable*.

### 5.2 Launchpad graduation is a regression discontinuity

The document mentions graduation status once, as a GeckoTerminal field. It is far more than that.

Bonding-curve → AMM graduation is a **threshold event with a sharp cutoff**. Tokens just above and just below the graduation threshold are near-identical in every respect except that one crossed. **That is a textbook regression discontinuity design** — the cleanest causal identification available in this entire problem space, and the document uses no causal designs at all.

It answers a question the rest of the system can only correlate at: *does graduation itself cause survival, or does it merely mark tokens that were going to survive?* If the former, graduation proximity is a genuine tradable signal. If the latter, it is a useless coincident indicator. Nothing else in the document can distinguish those.

### 5.3 The gas cliff is a natural experiment, and it is in nine days

Part 0 correctly flags Sept 29 as a regime break. It does not follow through on the implication, and it has a stale detail: **the subsidy threshold was lowered from $5 to $0.50**, which widened it substantially. The cliff is therefore a *bigger* break than the document assumes.

The follow-through: **free gas makes wash trading and sniping free.** Every activity-based feature you calibrate on July–September data is calibrated on an economy where fake volume costs nothing. On September 30, fake volume starts costing money.

Two actions:
- **Instrument now.** You have nine days to capture clean pre-cliff baseline data. After the 29th that window is closed permanently.
- **Treat the cliff as an identification strategy, not just a nuisance.** Activity that survives the imposition of real costs is economically genuine; activity that vanishes was not. This is a free, one-shot, chain-wide filter separating real from manufactured behaviour — far stronger than any wash-trading heuristic you could build, and it arrives whether you use it or not.

Add a `regime` flag (pre/post cliff) as a first-class feature and never pool across it without testing.

### 5.4 Exits deserve to be built before entries

The strongest measured finding in the entire prior art is about exits: winners peak at a median ~4h, **71% give back >80% of peak by 24h**, and no exit policy beat instant liquidation. The document added exit logic (Part 13.5) as an acknowledged late patch.

Given a fixed research budget, **exit rules are the better first investment**: they are cheap to backtest (a policy sweep over an existing price series, no forensics pipeline required), they apply to every position regardless of how it was selected, and the evidence says they dominate entry quality. An excellent exit rule with a mediocre entry signal beats the reverse.

### 5.5 Position sizing is not out of scope — at a 97% loss rate it *is* the strategy

Part 15 dismisses portfolio sizing because "this is speculative capital where total loss is an accepted outcome." That reasoning does not follow. With a 97%-loser, fat-tailed payoff distribution, **the decision between equal-weighting 50 small bets and concentrating into 5 dominates signal quality by a wide margin.** Accepting total loss of the *pot* says nothing about how to allocate *within* it.

This is one afternoon of work (fractional-Kelly under parameter uncertainty, or just a sizing sweep against the backtest) and it is likely worth more than several weeks of signal engineering.

### 5.6 The question never asked: where does the edge come from?

The document surveys prior art, tooling, and methodology thoroughly and never states **why this system should have an edge.**

This matters because the document itself lists **paid vendors already selling these exact signals** — MadeOnSol's `alphaWallets()` and `tokenBundle()`, DeFade's composite risk score, GMGN's bundle/sniper flags, Nansen's smart-money scoring. If a signal is computable from public data and already commercially available, **it is already in the price.** Building your own copy of a commodity signal is not an edge.

Three candidate edges that would actually be defensible, and the document should pick one and commit:
1. **Horizon** — willingness to hold multi-day when the ecosystem is optimised for minutes. (Plausible, but the prior art's 7d results actively argue against it.)
2. **Data joins nobody else maintains** — on-chain × social × *real equity prices*. §5.1 is the proof this join is valuable, and no listed vendor does it.
3. **A point-in-time wallet graph accumulated over time** — genuinely hard to replicate because it must be built forward, not backfilled. (This is real, but §3.1 means building it correctly is much harder and slower than the document assumes.)

My read: **(2) is the strongest and §5.1 is its concrete expression.** (1) is the document's implicit bet and it is the weakest supported.

### 5.7 Pre-registration needs a mechanism, not just an intention

Part 6 mandates forward-only testing and a discovery/confirmation split. Good. But nothing enforces it — and the failure mode (quietly revising a hypothesis after seeing results) is invisible in a solo project with no reviewer.

**Concrete fix:** a `PREREGISTRATION.md` committed to git **before the first data pull**, with the commit hash recorded. It fixes: the label definition, the exact signal list to be tested, the thresholds, the stopping rule, and the success criterion. Git timestamps make the discipline auditable by you, later, against yourself. This costs an hour and is the single highest-leverage item on this list.

### 5.8 Architecture: Supabase free tier is the wrong shape for this

Part 10 puts the alert ledger, wallet scores, **and per-token feature history** in Supabase free tier. Feature history is the problem: a few thousand tokens × daily snapshots × dozens of features is an analytical workload that will exceed 500MB faster than expected, and **the free tier pauses after 7 days of inactivity** — which is a silent failure mode for a system whose entire premise is continuous gap-free logging (and which Part 14.5 explicitly depends on).

**Fix — split by access pattern:**
- **Postgres/Supabase**: alert ledger + wallet scores. Small, transactional, queried continuously. Correct tool.
- **Parquet + DuckDB**: feature history and raw event logs. Columnar, compressed, free, versionable, and dramatically faster for the analytical scans you will actually run. Stores in object storage (Cloudflare R2 free tier) or straight in the repo via LFS for smaller sets.

This also pairs naturally with the SQD-based local indexer from §1.

### 5.9 Smaller corrections

- **GitHub Actions cron is unreliable.** Minimum 5-minute interval, but scheduled workflows are routinely delayed 10–30+ minutes under load, and **are disabled automatically after 60 days of repository inactivity.** For a multi-day system this is acceptable — but state it explicitly, and note the Healthchecks.io dead-man's-switch (correctly specified in Part 14) is what makes it survivable.
- **Effect sizes in the cited literature are modest and the document omits them.** The sniper-cohort paper (2607.02795, verified) reports a **+16.1% first-30-min buyer-count lift** (95% CI +13.0% to +19.4%) and only **+6.3%** on SOL inflow. That is a real but small effect. Quoting "1,012 persistent wallet rings" without the effect size overstates what the finding supports.
- **The rug base rates are not interchangeable.** The document cites ~97% "die" and the Catching-the-Rug paper's test set is ~31% "rug" — because TVL-drop/Idle is a narrower definition than "went to zero." Pick one definition per claim and keep them separate; they are not the same population.
- **Document structure has drifted.** Two sections numbered "Part 14" (Accounts & APIs, and Unsupervised pattern discovery); no Part 9, 11, or 13 (but a Part 13.5); Part 10 contains repo architecture, which belongs in its own section; and Part 15 references a "Part on trading, earlier in this project" that does not exist in this document. Worth a renumber, since Part 15's decisions log cross-references these.
- **Confirm the LP-depth-as-support/resistance framing before building it.** Part 2 flags it as novel and untested — fair. But the mechanism as described is incomplete: concentrated liquidity *below* spot acts as bids and is genuine mechanical support, while liquidity *above* spot is the opposite — it is sell-side depth that caps upside. Treat these as two separate signed features, not one symmetric "depth" number. And note LPs can withdraw on any block, so the "support" is revocable precisely when it matters.

---

## 6. What I would build, in order

The document's implicit plan is to build the full system and then test it. Given a measured-negative prior from the closest comparable project, I would invert that: **build the cheapest thing that can falsify the core hypothesis, and only expand if it survives.**

**Phase 0 — nine days, before Sept 29 (time-boxed by the cliff)**
1. `PREREGISTRATION.md` committed with a hash. Label definition, signal list, stopping rule, success criterion. (§5.7)
2. SQD indexer → Parquet → DuckDB over chain 4663 Swap/Mint/Burn/Transfer logs. Removes the Dune dependency. (§1)
3. **Start capturing pre-cliff baseline immediately.** This window does not reopen. (§5.3)

**Phase 1 — the falsification test**
4. Price + liquidity reconstruction from raw logs, with an **execution model** (impact, fees, sell tax, MEV haircut) for a $500 clip. (§4.1)
5. Chain-wide memecoin index; labels as **excess return, right-censored, fixed 30-day window from launch**. (§4.2, §3.4)
6. **One** paired same-day/same-age control test on a small pre-registered signal set, with block-bootstrapped inference. (§4.2, §4.7)

**Gate: if Phase 1 shows no significant excess return, stop and say so.** That is a real result and it saves months.

**Phase 2 — run in parallel, because it is likelier to be real than Phase 1**
7. **Stock-paired premium tracker.** Every stock-paired token's on-chain price vs. its Finnhub equity price, premium time series, weekend/market-hours regime flags. Test whether the dislocation is *capturable* net of execution, not merely observable. (§5.1)

**Phase 3 — only if Phase 1 survives the gate**
8. Exit-policy sweep before entry refinement. (§5.4)
9. Bitemporal wallet-score table, activity-matched scoring. (§3.1, §3.2)
10. Graduation RDD. (§5.2)
11. Position sizing. (§5.5)
12. Clustering / lane discovery — *after* a clean labelled dataset exists, to test the lane taxonomy rather than assume it. (§4.6)

---

## 7. Honest bottom line

The research quality in this document is high and the instincts are mostly right: forensics over TA, buyer-identity over deployer-identity, rug-filter and runner-predictor as separate tools, statistical rigor as non-negotiable. Those are all correct and hard-won.

But the strategic core — *multi-day accumulation-to-breakout on memecoins* — is an **untested assertion offered in response to a measured negative result**, and the one number the document uses to argue feasibility (AUCPRC 0.80) turns out to describe a different, much easier problem. The honest prior is that this does not work.

The stock-paired premium trade is different in kind. It has a mechanism, an anchor, a trigger, and a clock. **If one thing in this document is real, it is that.**

Build the falsification test and the premium tracker. Let the results decide the rest.

---

## Sources

Chain and market facts:
- [Robinhood Chain mainnet is live, built with the Arbitrum Platform](https://blog.arbitrum.io/robinhood-chain-mainnet/)
- [Robinhood Chain RPC, Chain ID 4663 & Official Links](https://trustswap.com/robinhood/network-details)
- [Robinhood Chain Ends Free Gas Subsidy in Late September](https://www.kucoin.com/news/flash/robinhood-chain-ends-free-gas-subsidy-in-late-september-memecoins-face-stress-test)
- [Robinhood lowers the gas fee subsidy threshold to $0.5](https://www.kucoin.com/news/flash/robinhood-lowers-gas-fee-subsidy-threshold-to-0-5-on-robinhood-chain)
- [A Memecoin Called BONER Has Cornered Half the Tokenized Hims & Hers Float](https://thedefiant.io/news/tokens/a-memecoin-called-boner-has-cornered-half-the-tokenized-hims-and-hers-float)
- [BONER Meme Coin Locks 53% of Tokenized HIMS](https://www.kucoin.com/news/flash/boner-meme-coin-locks-53-of-tokenized-hims-on-robinhood-chain)

Data platform pricing:
- [Dune updates free plan to view-only access, cites high costs](https://cryptobriefing.com/dune-free-plan-view-only-access/)
- [Dune Analytics Restricts Free Tier to View-Only Access from September 10](https://www.kucoin.com/news/flash/dune-analytics-restricts-free-tier-to-view-only-access-from-september-10)
- [Blockscout Robinhood API docs](https://docs.blockscout.com/robinhood-api)
- [SQD Robinhood Chain indexing infrastructure](https://sqd.dev/chains/robinhood/)
- [Goldsky Robinhood Chain Indexing & RPC](https://goldsky.com/chains/robinhood)

Academic sources verified:
- [Catching the Rug: Early Prediction of Fraudulent Memecoins on Solana (arXiv 2608.20271)](https://arxiv.org/abs/2608.20271)
- [TMRugPull: A Temporally Sound Multimodal Dataset for Early RugPull Detection (arXiv 2602.21529)](https://arxiv.org/pdf/2602.21529) — **not cited in the original document**
- [Coordinated Sniper Cohorts on Pump.fun (arXiv 2607.02795)](https://arxiv.org/abs/2607.02795)
- [Measuring Memecoin Fragility (arXiv 2512.00377)](https://arxiv.org/abs/2512.00377)

Prior art:
- [yousefjan2007-crypto/robinhood-screener](https://github.com/yousefjan2007-crypto/robinhood-screener) — rebuilt 2026-09-12
- [yousefjan2007-crypto/solana_screener](https://github.com/yousefjan2007-crypto/solana_screener)
