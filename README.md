# Robinhood Chain Monitoring System

Research and tooling for Robinhood Chain (Arbitrum Orbit L2, chain ID 4663).

## Status

Phase 0. Chain access, canonical token identity, and the stock-token premium /
float-lockup scanner are live and verified against mainnet. No trading logic.

## Documents

| File | Purpose |
|---|---|
| `PREREGISTRATION.md` | Hypotheses, labels, and stopping rules fixed in advance |
| `docs/00-master-system-v1.md` | Original research document (baseline, unedited) |
| `docs/01-critique-and-revision.md` | Critical review with verified sources and revised build order |
| `docs/02-stock-token-premium-findings.md` | Retraction of the premium-arbitrage idea, with measurements |

## Key findings so far

- **Stock-token premium arbitrage is not available to retail.** Minting is
  restricted to a single Authorised Participant (BBVI), so only that party can
  sell supply into a premium. Measured premiums across 10 major stock tokens on
  a closed-market Saturday: all within ±1.5%, mostly small discounts.
- **Float lockup is the salvageable signal.** NVDA sits at ~76% of its pooled
  value locked in memecoin-paired pools; SPY at 6%. This is the mechanism that
  drove the BONER/HIMS episode, it is measurable in real time, and no surveyed
  vendor computes it.
- **Dune's free tier went view-only on 2026-09-10**, invalidating the original
  data plan. Replacement path is Blockscout + GeckoTerminal now, a local SQD
  indexer into Parquet/DuckDB for population scans.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env    # add FINNHUB_API_KEY for an independent equity feed
```

## Usage

```bash
# Snapshot premiums + float lockup for the default stock-token universe
python scripts/scan_premiums.py

# Specific tickers
python scripts/scan_premiums.py NVDA HIMS SPY
```

Run daily. The gas subsidy ends **2026-09-29**; data captured before that date
is from a different economic regime and cannot be pooled with later data
without an explicit test.

## Notes

- Blockscout sits behind Cloudflare; the client sends a browser User-Agent and
  same-origin Referer. Verified working 2026-09-20.
- Tokens are resolved by canonical contract identity, never by ticker. There are
  currently 24 impostor contracts claiming `NVDA` and 24 claiming `TSLA`.
