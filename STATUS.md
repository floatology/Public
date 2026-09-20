# Status

Running log. Updated as work completes so progress survives an interrupted session.

**Branch:** `claude/document-analysis-review-dkjfu4`

---

## Build order (from `docs/03-open-questions.md` §3)

| # | Item | Status |
|---|---|---|
| 1 | Lockup scanner running daily | **in progress** |
| 2 | Execution model via aggregator quotes | not started |
| 3 | Test Goldsky / Bitquery for population scans | not started |
| 4 | Read rebuilt `robinhood-screener` (2026-09-12) | not started |
| 5 | Check retail redemption latency | not started |
| 6 | H0 work | blocked on #3 |

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
- **Population-scan data source is unresolved** — blocks H0.
- User is **non-US**, so stock tokens are holdable; the premium side remains
  AP-only regardless.
