# Execution Costs and the Data-Source Resolution

**Date:** 2026-09-20
**Covers:** build items 2 and 3 from `docs/03-open-questions.md` §3.

---

## 1. The population-scan blocker is resolved

`03-open-questions.md` §2.1 listed this as **blocking for H0**: Dune went paid, SQD does not carry
the chain, and the remaining options were untested.

**Tested, and the answer is better than any of the listed options.**

### Goldsky and Bitquery — both require accounts

- Goldsky public subgraph endpoints return **HTTP 404** without a project ID.
- Bitquery returns **"Unauthorized. Provide Authorization"**.

Neither is usable without signup, and neither is needed.

### The official RPC serves free archive access

`https://rpc.mainnet.chain.robinhood.com` — the endpoint the master document never identified,
and which is not any of the URLs I guessed earlier (`rpc.robinhoodchain.com`,
`mainnet.robinhoodchain.com` and the Caldera pattern all fail). Found via chainlist.

Verified:

| Property | Result |
|---|---|
| `eth_blockNumber` | works, head ≈ 67,997,911 |
| `eth_getBlockByNumber("0x1")` | **works — block 1, 2026-04-30 16:52 UTC** |
| `eth_getLogs` at genesis | **works** — 57 V2 `PairCreated` events in the first 500k blocks |
| Auth required | **none** |
| Limit | 10,000 *results* per call — **not** a block-range cap |

**This is full, free, unauthenticated archive access.** It is strictly better than Dune for this
purpose: no credits, no rate tier, no vendor dependency, and raw event logs rather than someone
else's curated tables.

Compare `robinhood-rpc.publicnode.com`, which serves head-state queries but rejects archive
requests with *"Archive requests require a personal token."* Use the official endpoint.

### Practical scan sizing

V2 `Swap` logs run ≈ 603 per 10,000 blocks, so ~150,000-block spans stay inside the 10k-result
cap. At ~68M blocks that is **roughly 450 requests for the entire chain's V2 swap history.**
Trivial.

Blockscout separately enumerates tokens at **23.1 tokens/second**, which extrapolates to about
**8.4 hours for a 700,000-token census** — an overnight job, not a blocker.

### Incidental finding: the chain predates its own launch

Block 1 is dated **2026-04-30**, but mainnet is described everywhere as launching **2026-07-01**
(block ~1,000,000 is 2026-07-02). There are two months of pre-announcement history on this chain.
The master document's claim that CASHCAT "appeared June 18, 2026, pre-mainnet" is therefore
plausible and, more importantly, **checkable** — that period is inside the archive.

This also means GeckoTerminal's 26-day window (§1.4 of `03-open-questions.md`) omits far more
history than first assumed. Reconstruction from logs is the only route to the early period.

---

## 2. Execution costs: the liquidity floor is brutal, and it is the project's most important number

`01-critique-and-revision.md` §4.1 argued that labelling on price without an execution model makes
outcomes untradable fictions. That was an argument. Here is the measurement.

### Method

KyberSwap's aggregator covers chain 4663 (slug `robinhood`; `robinhoodchain`, `rhc` and `4663`
all 404). It routes across all eight DEX protocols and returns exact executable amounts. A
round trip buys `$N` of a token and immediately sells the *actual* output back.

Accounting is in **raw quote-token units** (USDG in, USDG out), not the aggregator's USD fields.
The token amounts are exact; the USD legs come from its own price oracle and the two legs can be
priced moments apart, which produced spurious sub-percent "profits" on a trade that cannot be
profitable by construction. This was a real bug in the first version of the metric.

### Result — memecoins paired against tokenized HIMS, $500 clip

| Memecoin | Pool reserves | Round-trip cost |
|---|---:|---:|
| BONER | $2,410,406 | **0.90%** |
| SPY | $341,156 | ~0% |
| VIAGRA | $36,325 | **7.82%** |
| HIM | $28,673 | **7.60%** |
| WET | $25,546 | **10.73%** |
| INUT | $19,544 | **96.10%** |

**INUT costs 96% of the clip to enter and exit.** At a $100 clip it still costs 80.8%. There is no
strategy, signal or holding period that recovers from that. A 10x on INUT's chart is not a 10x;
it is not reachable at all.

### What this establishes

1. **The liquidity floor is roughly $50k of pool reserves at a $500 clip**, and the cost curve
   above it is extremely steep — not linear. Between $2.4M and $20k of reserves, round-trip cost
   moves from 0.9% to 96%.
2. **Cost must be measured per token, not inferred from a reserve threshold.** VIAGRA ($36k) and
   WET ($26k) are only $10k apart in depth but 3 percentage points apart in cost, and INUT is an
   order of magnitude worse again.
3. **The H1 universe must be filtered on measured round-trip cost.** `scripts/execution_floor.py`
   does this, writing to `data/execution_costs.jsonl`.
4. **This probably explains a chunk of the prior art's result.** `robinhood-screener` found its
   best exit policy was "sell immediately" at **−3.45%**, described as "the round-trip cost." On
   the thin tokens a launch screener surfaces, that figure is optimistic by an order of magnitude.

### Stock tokens, for contrast

The same measurement on canonical stock tokens gives round-trip costs of **0.01%–0.28% at a
$5,000 clip** (HIMS, NVDA, SPY, GME). These are deep, arbitrage-tight instruments. The contrast
is the point: execution cost is not a small correction applied uniformly, it is the dominant term
and it varies by four orders of magnitude across the assets this system looks at.

### Costs still not modelled

- **Sell-side token tax.** A fee-on-transfer token yields less than quoted. Needs a separate
  simulation check (ScanHood covers this) before any label is trusted.
- **Sandwich/MEV.** Deliberately excluded — Orbit sequences FCFS from a private mempool. See
  `03-open-questions.md` §1.1.
- **Historical quotes.** Aggregator routes do not exist for past blocks. Backtesting needs
  per-protocol reconstruction from the archive RPC above.

---

## 3. Status changes

| Item | Was | Now |
|---|---|---|
| Population-scan source | blocking for H0 | **resolved** — official RPC, free archive |
| Execution model | not started | **built**, forward-testing path working |
| Historical reconstruction | assumed hard | still hard, but now *possible* — archive access exists |

H0 is no longer blocked on data access. It remains blocked on a power analysis, which can now
actually be run.
