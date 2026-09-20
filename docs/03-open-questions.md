# Open Questions Before Build

**Date:** 2026-09-20
**Purpose:** what is verified, what is corrected, and what remains genuinely unresolved.

---

## 0. A pattern worth naming

Three claims in `01-critique-and-revision.md` have now been withdrawn after measurement:
the gas cliff, the MEV haircut, and the SQD remediation. All three failed the same way —
**I trusted a vendor page or a plausible mechanism instead of testing the endpoint.**
That is the identical error I criticised the master document for making with Dune.

Everything below that is asserted rather than measured is marked as such.

---

## 1. Corrections from measurement (2026-09-20)

### 1.1 MEV / sandwich risk — overstated, in your favour

I specified an MEV haircut in the execution model on the grounds that this is "a public-mempool
L2 with 100ms blocks."

**Arbitrum Orbit does not have a public mempool.** It uses FCFS sequencing with a private
mempool, which removes the pending-transaction window sandwich bots require. Published research
on rollups finds sandwiching "rare, unprofitable, and largely absent in rollups with private
mempools," with no instances found of sequencers performing sandwich trades.

**Effect:** the execution model gets *cheaper*, not dearer. Drop the sandwich haircut for
ordinary swaps. Retain a note for two residual cases: cross-layer sandwiching via L1→L2 bridge
transactions, and Arbitrum Timeboost (an express-lane auction that does affect ordering).

### 1.2 SQD does not support this chain — my §1 remediation was wrong

I recommended SQD as "the strongest free replacement for Dune's population-scan role," on the
basis of a vendor page stating Robinhood Chain support.

**Tested:** `GET portal.sqd.dev/datasets` returns **138 datasets and zero matches** for
Robinhood Chain (`ethereum-hoodi` is a false positive — an Ethereum testnet).
`datasets/robinhood/head` returns `unknown_dataset`.

The Dune replacement is therefore **still unresolved.** See §2.1.

### 1.3 The DEX landscape is eight protocols, not one

The master document treats liquidity reconstruction as a single engineering task
("reconstruct from raw Mint/Burn/Swap event logs"), and I endorsed that framing.

**Measured across just two stock tokens**, pools span:

| Protocol | Class |
|---|---|
| `uniswap-v3-robinhood` | V3 concentrated liquidity |
| `uniswap-v4-robinhood` | V4 singleton + **hooks** |
| `bankr-robinhood` | unknown, 32-byte pool IDs |
| `pons-v2-dex` | V2-style constant product |
| `up-v3`, `ramses-v3-robinhood`, `giga-v3`, `alandale-cl` | V3/CL forks |

Consequences the original plan does not account for:

- **Depth reconstruction is eight implementations**, with different event signatures and
  different pricing maths (constant product vs. concentrated liquidity vs. singleton).
- **Uniswap V4 hooks can arbitrarily alter swap behaviour** — dynamic fees, custom curves, even
  blocking swaps. You cannot assume standard V3 maths for a V4 pool without reading its hook.
- **A token's real liquidity is fragmented across venues**, so a single-pool price is wrong and
  a single-pool depth figure understates true executable size.

This substantially enlarges the execution-model task, which was already the load-bearing item.

### 1.4 Historical liquidity composition does not exist in any free source found

**This is the most consequential finding, and it governs the schedule.**

GeckoTerminal for the deepest HIMS/USDG V3 pool returns:
- **26 daily candles, 2026-08-21 → 2026-09-20.** The chain launched **2026-07-01**, so roughly
  **the first seven weeks of chain history are simply absent.**
- **OHLCV is price only.** There is no historical reserve or liquidity-composition series
  anywhere in the API — only current-state reserve fields.

**Therefore the H1 independent variable (float-lockup ratio) cannot be backtested.** It can only
be accumulated forward from the day capture starts, unless reserve history is reconstructed from
raw logs across all eight protocols in §1.3.

H1 is a **prospective study measured in weeks**, not a backtest measured in days. That is a real
change to the plan and should be decided on deliberately rather than discovered later.

**One useful consequence:** the clock on H1 starts when capture starts. That is a genuine reason
to run the scanner daily beginning now — unlike the gas-cliff deadline, which was not real.

---

## 2. Genuinely unresolved

### 2.1 Population-scan data source — BLOCKING for H0

Dune is paid (§1 of the critique). SQD does not have the chain (§1.2 above). Remaining, all
**untested**:

| Option | Status |
|---|---|
| **Goldsky** | Page returns HTTP 200; free-tier limits and actual chain coverage untested |
| **Bitquery** | 7-day Pro trial; decoded DEX trades. Trial-limited, not a foundation |
| **Blockscout** | Free and working, but "rate limits sized for humans," slow deep pagination, no SLA |
| **Self-hosted archive node** | Full control, no limits; meaningful infra cost and sync time |
| **Dune Analyst** | $65/mo, 4,000 credits — probably insufficient for a 700k-token scan anyway |

**Needs testing before H0 work begins.** I will not recommend one until I have queried it.

### 2.2 Whether retail redemption is live — now relevant

Since you are non-US, the stock-token branch reopens. The discount side is the retail-accessible
direction (redemption caps discounts; minting caps premiums and is AP-only).

**But:** Robinhood's chain docs do not specify redemption mechanics or settlement time, and the
1:1 share redemption announced 2026-09-14 is described as roadmap. Current tokens are tokenized
*debt securities* with cash settlement. **Unknown whether a retail holder can redeem today, and
at what latency.** Latency is decisive — a redemption taking days cannot capture a
1%-and-closing discount.

Also note the measured discounts (§2 of `02-stock-token-premium-findings.md`) are ~1% against
pool fees of 0.3–1% per leg. Even with instant redemption the edge is marginal.

### 2.3 The prior art has moved

`robinhood-screener` was rebuilt **2026-09-12**, after the master document was written. I have
read only its published results, not the new implementation. It is the closest comparable system
and may have findings that change the plan.

### 2.4 H0 positive-class size is unknown

The critique flagged the absence of a power analysis. That analysis cannot be run until the
population is queryable (§2.1). Until then it is unknown whether H0 has enough positives to test
at all.

### 2.5 Execution model: two incompatible regimes

- **Forward testing:** a live routing-aggregator quote (KyberSwap, already in the master
  document's tooling list) gives an *exact* executable price across all eight venues, free. This
  is strictly better than reconstructing depth.
- **Backtesting:** aggregator quotes do not exist historically. This requires the full
  eight-protocol reconstruction.

Given §1.4, forward testing is the near-term path regardless. **Recommendation: build the
aggregator-quote execution model first** (small, exact, immediately useful), and defer log
reconstruction until a backtest is actually unblocked.

---

## 3. Revised ordering

1. **Run the lockup scanner daily, starting now.** Already built and verified. H1's clock starts
   when capture starts, and no historical substitute exists (§1.4).
2. **Execution model via aggregator quotes** (§2.5) — small, exact, unblocks honest labelling.
3. **Test Goldsky and Bitquery** (§2.1) — decides whether H0 is feasible at all.
4. **Read the rebuilt `robinhood-screener`** (§2.3) — cheap, may change everything downstream.
5. **Check retail redemption latency** (§2.2) — decides whether the discount side is real.
6. H0 work only after (3) resolves.

Items 2–5 are independent and can proceed in any order.
