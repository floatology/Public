# Status

Running log. Updated as work completes so progress survives an interrupted session.

**Branch:** `claude/document-analysis-review-dkjfu4`

---

## Build order (from `docs/03-open-questions.md` §3)

| # | Item | Status |
|---|---|---|
| 1 | Lockup scanner running daily | **done** — 176-token universe, daily workflow |
| 2 | Execution model via aggregator quotes | **done** — KyberSwap, raw-unit accounting |
| 3 | Population-scan data source | **done** — official RPC serves free archive |
| 4 | Read rebuilt `robinhood-screener` (2026-09-12) | **done** — lessons folded into PREREGISTRATION |
| 5 | Check retail redemption latency | **done** — undisclosed; needs a question to Robinhood |
| 6 | H0 population frame | **done** — 715,343 pool creations censused |
| 7 | H0 power analysis | **done** — `docs/06-power-analysis.md` |
| 8 | V3 stratum rate | **done** — differs significantly from V2 (z=3.28) |
| 9 | Execution gate on H0 labels | next |
| 10 | Graduation-threshold RDD | **withdrawn** — infeasible, no bonding curve on this chain |
| 11 | H2: launch liquidity predicts 10x | **resolved** — real but mechanical, not a signal |
| 12 | H1 (lockup) — accruing daily, not testable yet | waiting on data |
| 13 | **Metric catalogue** — 50+ signals researched and prioritised | **done** — `docs/09-metric-catalogue.md` |
| 14 | Wallet ledger + point-in-time scoring | **done** — `rhc.wallets` |
| 15 | Feature engine (49 features/pool) | **done** — `rhc.features` |
| 16 | Contract risk checks | **done** — `rhc.contracts` |
| 17 | Telegram social (free tier) | **done** — `rhc.social` |
| 18 | Enrichment pipeline (84 columns) | **done** — `scripts/enrich_features.py` |
| 19 | Modelling harness + negative control | **done** — `scripts/model_features.py` |
| 20 | Correlation / dimensionality analysis | **done** — `scripts/feature_correlations.py` |
| 21 | 10,000-pool extraction | running |

---

## Done

- Critical review of the master document, every external claim verified
  (`docs/01-critique-and-revision.md`).
- Stock-token premium arbitrage retracted with measurements
  (`docs/02-stock-token-premium-findings.md`).
- Open questions and three withdrawn claims recorded
  (`docs/03-open-questions.md`).
- Working chain access: Blockscout client with Cloudflare workaround,
  canonical token identity verification, premium/lockup scanner.
- `PREREGISTRATION.md` committed ahead of any confirmatory pull.
- Execution model built on KyberSwap aggregator quotes (`src/rhc/execution.py`),
  with the liquidity floor measured (`docs/04-execution-and-data-findings.md`).
- Official archive RPC found and recorded in `src/rhc/chain.py`.
- **Manipulation detection completed** (`src/rhc/manipulation.py`): catalogue
  7.1 bundle bots and 7.3 bump bots, the two metrics the catalogue still listed
  as unbuilt. 7.3 matters most — in the published LASSO model, bump-bot presence
  carried the highest importance of any feature. Eight tests, four of them
  negative cases that must stay silent: eight wallets buying in the launch block
  is also an anticipated launch, and one wallet trading forty times is also an
  active trader.
- **Trades are archived to Parquet** during extraction. Before this the RPC work
  was spent once and thrown away, so every new feature idea cost another
  ninety-minute scan of a node that rate-limits globally — and the cross-token
  wallet ledger could not be built at all.
- **Cross-token wallet ledger built** (`scripts/wallet_ledger.py`), the domain
  with the strongest published evidence and the user's stated priority. It emits
  a per-token feature computed at that token's own launch from wallet history
  that had already **resolved** by then, not merely launched. Guarded two ways:
  the fast forward-only sweep is cross-checked against the slow reference scorer
  and aborts on any disagreement, and a committed test buys a 100x winner at
  block 0, a second token at block 500 before the first resolves, and requires
  the feature to read zero there.
- **Offline feature rebuild** (`scripts/recompute_features.py`): features are a
  pure function of archived trades, so iterating on them no longer needs the node.
- **Coordination clustering built** (`src/rhc/clusters.py`), catalogue 1.8,
  by wallet co-occurrence rather than the funding graph the catalogue assumed —
  funding needs one explorer call per wallet and does not scale. Overlap is
  scored against an `a*b/N` null so it ranks coordination rather than activity,
  and the entity map is trained on a pre-cutoff window so a token is scored with
  links that existed before it launched.
- **Venue fragmentation measured** (catalogue 4.7): across 644,581 tokens,
  **98.9% have exactly one pool**. The chain's 272 factories fragment the
  population, not the token, which retroactively validates the single-pool
  extraction.
- **Movers screen built** (`scripts/screen_movers.py`). On the first capture,
  **32 of the 60 busiest pools fail a two-tell wash screen** — turnover that is
  not physically possible at their depth, or trades far outnumbering traders.
  AIForce turned over 1,139x its $3,709 of reserves in a day; TYPING 1,129x its
  $15,949. The clean list is mostly stock tokens plus a handful of real
  memecoins (PONS, CASHCAT).

## Research deliverable: what to actually track

`docs/09-metric-catalogue.md` — 50+ metrics across seven domains, each rated for evidence
strength, feasibility on this chain, and how much is already public.

**The headline:** trader profitability is a *published* result, not an instinct. arXiv 2601.08641
reports **AUC 0.70–0.72** predicting whether a wallet's next trade profits, smart-money wallets
averaging **14%** per trade, copiers netting **~3%** after frictions. The nearest prior art to this
project managed AUC 0.54. The whale-tracking instinct was aimed at the right target.

Two counter-intuitive findings from the literature:
- **Profitable traders buy *below* the 75th percentile of size.** Large buyers are not the smart
  ones — which points straight at the stealth-accumulation idea.
- **Bump-bot presence carried the highest feature importance of any variable** in the published
  LASSO model, above every historical-performance feature.

**Two vendor changes since the original document:** LunarCrush's free tier is now market-data only
(social requires payment), as is Santiment. **Telegram is the exception** — public channel member
counts and view counts scrape over plain HTTP with no key.

## Conclusions so far

Write-ups in `docs/07-conclusions.md` and `docs/08-h2-result.md`. Headlines:

0. **H2 resolved: launch liquidity is an arithmetic identity, not a signal.**
   It replicates (chi-square 35.05 then 29.96, p<0.001, peak at exactly 1 WETH)
   but the gradient collapses at a lower multiple — at 10x the top bucket
   reaches 15% of the peak bucket's rate, at 2x it reaches 80%. That is
   mechanism, not information: a 10x move needs the quote reserve to grow
   ~3.16x, so a 5-WETH pool needs ~10x the buying a 0.5-WETH pool does. It
   predicts which pools are *cheap to move*, not which tokens will run.
   **The practical inversion matters more:** at 2x, the smallest pools convert
   just **12%** of price wins into tradable ones; the largest convert **98%**.
   Chasing big multiples in thin pools is chasing unfillable prices.

1. **Execution cost dominates.** $500 round trip costs 0.90% on a $2.4M pool
   and **96.10% on a $20k pool**. Most chart winners were never reachable.
2. **V2 and V3 are different populations** (z=3.28, p<0.01) and must not be
   pooled. Chain-wide positive rate ~2.5%, not the 1% V2 alone suggested.
3. **Most liquidity is not real.** 65% of stock tokens hold >50% of their
   memecoin reserves in zero-volume pools; 55% lack the depth to price at all.
4. **Data access is solved and free.** No database, no paid service, ten
   minutes for a full-chain census.
5. **Statistical power is the binding constraint**, not sample size or cost.

## H0 base rates (measured, 1,200 pools)

| stratum | population | ever trades | 10x given trades | 10x overall |
|---|---:|---:|---:|---:|
| V2 | 266,465 | 4.8% | 21.05% | **1.000%** |
| V3 | 441,582 | 43.5% | 7.85% | **3.420%** |

Population-weighted chain-wide: **~2.5%**. Opposite profiles — V2 rarely trades
but moonshots (p50 4.08x); V3 usually trades but rarely moonshots (p50 1.38x).

**Sample V3 first:** 435 measurable per 1,000 sampled against V2's 48 — 9.2x
more efficient per unit of scan time.

**Sample size is not a binding constraint.** 50 positives per discovery/
confirmation half needs ~10,000 pools, about 7 hours on the free archive RPC.

**But the current n=57 can only detect a ~21pp effect** — roughly a doubling of
the base rate. Literature effects are far smaller (the sniper-cohort paper's
+16.1% relative is ~3.4pp absolute), so detecting those needs tens of thousands
of pools sampled. Plan for it rather than misread an underpowered null.

**Now measured, and the earlier caution was too pessimistic.** Pricing each
winner's buy at its own peak block: the price rate of 1.402% becomes a tradable
rate of **1.135% at a $500 clip** — a 19% haircut, not the large unknown factor
I warned about. The constraint is capacity, not tradability: see conclusion 1.

## Infrastructure answer

**No Supabase, no new storage account needed.** The daily series is ~79KB/day
(~29MB/year) of append-only JSONL, partitioned monthly in git — a file, not a
workload. Bulk swap history is too big for git *and* for Supabase's 500MB free
tier, and regenerates from the free archive RPC anyway, so it stays local
Parquet. Supabase free also pauses after 7 days idle, which is the worst
possible property for a project whose premise is gap-free logging. Full
reasoning in `docs/05-infrastructure.md`.

**The one account worth creating is Healthchecks.io** (free) — not for storage,
but so a broken pipeline tells you instead of quietly producing nothing. Set
`HEALTHCHECK_URL` as a repo secret and the scan pings it on start/success/fail.

## Keeping the data flowing — two real risks

1. **Scheduled workflows only fire from the repo's DEFAULT branch.** Right now
   the default *is* `claude/document-analysis-review-dkjfu4`, so it works. If
   the default ever changes (e.g. a `main` is created, or this branch is merged
   and deleted), **the scan silently stops** — no error, it just never fires.
2. **GitHub disables scheduled workflows after 60 days of repo inactivity**, and
   `GITHUB_TOKEN` pushes generally do not count as activity. Any manual push
   resets the timer.

## Needs you, not code

- **Ask Robinhood support** whether retail can redeem Stock Tokens directly
  today (BBVI is the acting AP), how long redemption takes end to end, and
  whether there is a minimum size. This decides whether the ~1% discount side
  is capturable. See `docs/02-stock-token-premium-findings.md` §5.

## Claims withdrawn after measurement

Recorded so they are not re-introduced:

1. **Gas cliff matters.** No — median fee $0.011, 0% of txs reach the $0.50
   subsidy threshold.
2. **MEV haircut needed.** No — Orbit uses FCFS private mempool; sandwiching
   is rare-to-absent on such rollups.
3. **SQD replaces Dune.** No — 138 datasets, this chain is not among them.

## Key constraints

- **No historical liquidity composition exists in any free source.** The lockup
  signal accumulates forward only. This is why #1 runs daily starting now.
- **Liquidity spans eight DEX protocols**, including Uniswap V4 with hooks.
- **Population-scan data source resolved**: `rpc.mainnet.chain.robinhood.com`
  serves free unauthenticated archive `eth_getLogs` back to block 1 (2026-04-30).
- **Full chain censused in 10 minutes**: 715,343 pool creations, 638,889 unique
  pools, **675,438 distinct token addresses**, across **272 factories** — far
  more fragmented than the eight DEX protocols visible via aggregators. One
  factory accounts for 434,168 pools (61%). This confirms the master document's
  "well over 700,000 tokens" estimate from primary data.
- **Execution cost is the dominant term**, varying four orders of magnitude:
  BONER ($2.4M reserves) 0.90%; INUT ($20k) **96.10%**. Below roughly $50k of
  pool reserves a token is untradable at any meaningful size.
- **Tradability must be measured one-way, not as a round trip.** A round trip
  cancels itself out in a thin pool: one sampled pool held two cents of WETH
  against a $500 clip and reported **0.00%** round-trip cost for a position
  nobody could take. Use one-way fill impact plus a cap on the share of the
  quote reserve consumed.
- **Over half the stock-token universe is too illiquid to price.** The first
  clean full scan (175 tokens, 2026-09-20) filtered 96 of 175 for stable-pool
  depth under $50k. Premiums among the 79 that survive run -4.69% to +5.89%,
  median +0.11%.
- **Lockup must be measured on live pools only, and this matters far more than
  one token.** USAR looked strongest at 99.0% lockup on $10.2M, but 98% sat in
  one zero-volume pool. A full re-scan then showed **114 of 175 tokens carry
  >50% dormant memecoin liquidity** — the majority of the universe would have
  been false positives. Dormancy concentrates in the small names; every token
  in the live top eight is 0% dormant. `live_lockup_ratio` is the signalling
  metric.
- **Strongest genuine lockup: NVDA at 76.6%** ($28.1M across 11 pairs, 0%
  dormant), then MU 72.4%, QQQ 62.4%, AAPL 56.3%, HIMS 55.4%. Control: SPY at
  6.3%.
- User is **non-US**, so stock tokens are holdable; the premium side remains
  AP-only regardless.
