# Stock tokens are one contract behind 175 proxies

**Measured 2026-09-21** over all 175 Robinhood Stock Tokens, via Blockscout's
verified-source and ABI endpoints. Every figure below is a complete census of
that universe, not a sample.

## The result

| Property | Value | Coverage |
|---|---|---|
| Verified source | yes | 175 / 175 |
| Proxy | yes (`eip1967_beacon`) | 175 / 175 |
| **Distinct implementations behind those proxies** | **1** | — |
| **Distinct deployers** | **1** (`0x4783C67b63dE2B358Ac5951a7D41F47A38F3C046`) | — |
| ABI functions on the implementation | 36 | identical for all |
| `mint` | present | 175 / 175 |
| `pause` | present | 175 / 175 |
| `blacklist` / `fee control` / `withdraw all` / `burnFrom` | absent | 175 / 175 |
| Privileged capability count | 2 | identical for all |

## What follows from it

**The contract-risk module cannot discriminate here, by construction.** Every
column it produces is constant across the entire stock-token universe. That is
not a failure of the module — it is the correct answer, and worth stating
plainly because a risk screen returning "all clear, uniformly" is easy to
mistake for a screen that did not run. `rhc.contracts` is a memecoin filter.
Pointed at stock tokens it measures Robinhood's deployment template.

**The issuer retains mint and pause authority over every stock token.** This is
structural rather than alarming: a tokenised-equity wrapper has to be able to
mint against new deposits and halt on a corporate action. It does mean the
tokens are not trust-minimised in the way a renounced memecoin contract is, and
anyone holding them is holding issuer risk as well as equity risk. Ownership is
not renounced on any of them, which is the only configuration consistent with
the redemption mechanism working at all.

**A single deployer and a single implementation make ticker impersonation
trivially detectable.** There are 24 contracts claiming `NVDA` on this chain and
24 claiming `TSLA`. Exactly one of each is deployed by
`0x4783C67b…` behind the beacon proxy. The canonical-identity check in
`rhc.stocktokens` uses a CDN icon marker and arrives at the same answer
independently — two unrelated signals agreeing is the standard this project
holds a result to, and here they do.

## What GeckoTerminal adds, and what it does not

| Field | Coverage | Note |
|---|---|---|
| `holder_count` | 174 / 175 | usable |
| `top_10` concentration | 174 / 175 | usable |
| `gt_score` | 174 / 175 | vendor composite, unvalidated |
| `is_honeypot` | 21 / 175 | mostly absent; treat missing as unknown, never as clean |
| `mint_authority`, `freeze_authority`, `dev_holding_pct` | 0 / 175 | Solana-only fields, empty on an EVM chain |
| Telegram / Discord links | 0 / 175 | stock tokens have no community channels, as expected |

The social module therefore contributes nothing on this half of the universe.
That was predictable in hindsight — these are issuer products, not community
tokens — but it is recorded because "the scraper returned nothing" and "there is
nothing to scrape" are different states and only one of them is a bug.

## Operational cost

175 tokens took **2,222 seconds** — about 12.7 seconds each, dominated by
Blockscout rate limiting rather than by anything computed. Two consequences:

- Contract enrichment over a memecoin feature table of ~600 rows will take
  roughly two hours. Budget for it; do not assume it rides along with anything.
- It hits Blockscout and GeckoTerminal, **not** the archive RPC, so unlike the
  feature extraction it can run concurrently with a bulk scan. It did, here.

## A dead field this exposed

`ContractRisk` carried a `creator` attribute that `inspect()` never populated,
so it read as `None` for all 175 tokens while the deployer was one endpoint
away and was in fact being captured correctly in a different column. An absent
value that means "never asked" is indistinguishable in the output from one that
means "unknown", which is the same failure mode as an unverified contract
reading as clean. The field has been removed; `creator_of()` is the way to ask.
