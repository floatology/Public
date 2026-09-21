# Robinhood Chain Monitoring System

Research and tooling for Robinhood Chain (Arbitrum Orbit L2, chain ID 4663,
mainnet 2026-07-01).

## Status

**Measurement complete, prediction unproven.** The pipeline computes ~110
columns per token across seven metric domains and runs end to end on real chain
data. Nothing has yet been shown to predict anything: the modelling stage is
built, tested against known answers, and waiting on a full extraction.

The one number that will decide whether any of this is real is whether the
confirmation-half AUC beats a shuffled-label control. The harness is tested to
return "no" when given pure noise (`tests/test_model_harness.py`), which is the
only check here that the discipline works rather than merely being described.

## Documents

| File | Purpose |
|---|---|
| `docs/10-where-things-stand.md` | **Start here.** Plain-language summary, readable cold |
| `PREREGISTRATION.md` | Hypotheses, labels and stopping rules fixed in advance, plus amendments |
| `STATUS.md` | Running build log and every measured constraint |
| `docs/09-metric-catalogue.md` | The research deliverable: 61 metrics across 7 domains, each rated for evidence and feasibility |
| `docs/00-master-system-v1.md` | Original research document, unedited baseline |
| `docs/01-critique-and-revision.md` | Critical review of that document with verified sources |
| `docs/02-stock-token-premium-findings.md` | Retraction of the premium-arbitrage idea, with measurements |
| `docs/03-open-questions.md` | What is verified, what is withdrawn, what still blocks |
| `docs/04-execution-and-data-findings.md` | RPC discovery and the measured liquidity floor |
| `docs/06-power-analysis.md` | Why sample size, not cost, is the binding constraint |
| `docs/08-h2-result.md` | A significant, replicated result that was still wrong |

## What it measures

| Module | Catalogue domain |
|---|---|
| `rhc.features` | Flow and activity (§3), liquidity (§4), holder distribution (§2), time shape (§3.5–3.6), holding duration (§2.8–2.9), sniping and wash tells (§7.2, 7.4, 7.5) |
| `rhc.manipulation` | Bundle bots (§7.1) and bump bots (§7.3) |
| `rhc.wallets` | Cross-token wallet ledger with point-in-time scoring (§1) |
| `rhc.clusters` | Coordination clustering (§1.8) |
| `rhc.contracts` | Structural risk, following proxies to implementation (§6) |
| `rhc.social` | Telegram audience and engagement (§5.1–5.2) |
| `rhc.premium` | Stock-token premium and float lockup |

## Key findings so far

- **Stock-token premium arbitrage is not available to retail.** Minting is
  restricted to a single Authorised Participant (BBVI), so only that party can
  sell supply into a premium. Measured premiums across 10 major stock tokens on
  a closed-market Saturday: all within ±1.5%, mostly small discounts.
- **More than half of the chain's busiest pools fail a wash screen.** 32 of the
  top 60 by volume. AIForce traded 1,139x its $3,709 of reserves in a day;
  TYPING 1,129x its $15,949. No organic flow does that in a pool that thin.
- **98.9% of tokens have exactly one pool.** Across 644,581 tokens with a WETH-
  or USDG-quoted pool. The chain's 272 factories fragment the population, not
  the individual token.
- **Launch liquidity is an arithmetic identity, not a signal** — see
  `docs/08-h2-result.md`. It replicated and passed a clustering check while the
  conclusion was still wrong.
- **Float lockup is the salvageable stock-token signal.** NVDA sits at ~77% of
  its pooled value locked in memecoin-paired pools; SPY at 6%. Measured on live
  pools only: 114 of 175 tokens carry >50% dormant liquidity and would have been
  false positives on raw reserves.
- **Execution cost varies four orders of magnitude** and dominates everything
  below roughly $50k of pool reserves, where a $500 trade can cost 96%.
- **Gas was never the problem.** Median fee $0.011; 0% of transactions reach the
  $0.50 threshold the original document assumed would bite.
- **Data access is solved and free.** `rpc.mainnet.chain.robinhood.com` serves
  unauthenticated archive `eth_getLogs` back to block 1. No database, no vendor.
  It rate-limits **globally**, not per query, so bulk scans are exclusive.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env    # optional: FINNHUB_API_KEY for an independent equity feed
```

## Usage

```bash
# Everything, in the only order that works (see the script's header for why)
scripts/run_pipeline.sh --extract   # includes the ~90-minute RPC stage
scripts/run_pipeline.sh             # offline stages only, seconds

# Tests
.venv/bin/python tests/run_all.py
```

Individual stages:

```bash
python scripts/pool_census.py          # every pool creation from genesis, ~10 min
python scripts/extract_features.py     # features + trade archive (RPC, exclusive)
python scripts/recompute_features.py   # rebuild features offline from the archive
python scripts/wallet_ledger.py        # cross-token wallet features, leak-audited
python scripts/wallet_clusters.py      # entity map from a training window
python scripts/describe_features.py    # column diagnostics, run before modelling
python scripts/model_features.py       # the number that matters
python scripts/scan_premiums.py        # daily stock-token lockup snapshot
python scripts/daily_movers.py         # daily memecoin activity snapshot
python scripts/screen_movers.py        # wash screen over the movers series
```

The two daily captures run automatically from `.github/workflows/`. Start them
early and do not miss days: no free source carries historical liquidity
composition, so an uncaptured day is permanently gone.

## Operating rules

These are in the repository because each one was learned by getting it wrong.

- **Assume a striking result is an artefact until an independent measurement
  agrees.** Five results here looked like findings and were not. In the worst
  case the result replicated *and* passed a clustering check and was still wrong.
- **Wallet scores are point-in-time.** A wallet may only be credited with
  outcomes that had *resolved* before the moment being scored, not merely
  launched. There is a test that builds the trap deliberately.
- **Score hits against activity.** On a chain with 675,438 tokens, raw hit counts
  measure spraying. Three wins from eight entries beats five from nine hundred.
- **An outcome that could not have been realised at size is not an outcome.**
  See the 2026-09-21 pre-registration amendment.
- **Tokens are resolved by canonical contract identity, never by ticker.** There
  are 24 impostor contracts claiming `NVDA` and 24 claiming `TSLA`.
- **Negative results are committed with the same prominence as positive ones.**

## Notes

- Blockscout sits behind Cloudflare; the client sends a browser User-Agent and
  same-origin Referer.
- LunarCrush and Santiment free tiers are now market-data only. Telegram's
  public channel previews remain scrapeable without a key, which is why §5 of
  the catalogue is thinner than the original plan assumed.
