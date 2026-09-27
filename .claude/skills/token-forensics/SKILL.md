---
name: token-forensics
description: Analyse who is actually buying, selling, accumulating or distributing a token on Robinhood Chain, from chain data rather than aggregator summaries. Use when asked about a ticker's holders, wallets, whales, bots, wash trading, accumulation, distribution, or "what's really happening" with a coin. Also use when asked to refresh or extend a token archive the project already holds.
---

# Token forensics on Robinhood Chain

Answers "who is doing what to this token" from `eth_getLogs`, not from a
screenshot or an aggregator's summary table. Everything the DexScreener mobile
UI shows — holders, transactions, trader addresses, liquidity events — is
reachable from the free endpoints below, in more detail and over the full
history.

## Order of work

1. **Resolve the token.** Never trust the ticker: tickers are unpoliced here and
   duplicates are common (WALLET has two, one a honeypot). Search DexScreener,
   take the contract with real liquidity, and record the address.
2. **Find its pools** and the main one by liquidity. Look up the pool's creation
   block and `quote_is_token0` in `data/parquet/pool_creations.parquet`.
3. **Fill the archive** with `scripts/token_archive.py` (below). Resume, never
   rescan.
4. **Analyse** with `scripts/token_forensics.py`.
5. **State what the data cannot see** alongside what it can. The limits section
   is not boilerplate; each entry is a real hole that has produced a wrong
   answer in this project.

## The three lessons that cost the most

**The swap log's `recipient` is the router, not the trader.** A ledger keyed on
it once reported a wallet holding 26% of supply whose `balanceOf` is zero, and
gave other addresses net positions below −100% of supply. On a week of WALLET
swaps, `tx.from` differed from the recipient on **83%** of trades. For holdings
use Transfer logs; for trader identity resolve `tx.from` per swap.

**The node rate-limits globally, not per query.** Two bulk scans at once kills
one of them — this is documented in `src/rhc/rpc.py` and it happened anyway.
Run one scan at a time. `--resolve-senders` uses `min_interval=0.2` and falls
back to the recipient on a failed lookup rather than throwing away the run, but
it still must not share the node.

**Audit balances at a pinned block, never `latest`.** The pool's balance moves
every trade, so a replay checked against a head that has advanced reports a
mismatch that is only elapsed time.

## Commands

Fill or extend the archive (one token per directory under `data/tokens/`):

```bash
.venv/bin/python scripts/token_archive.py \
  --token 0x... --pool 0x... --protocol v3 \
  --transfers --swaps --resolve-senders 20000
```

It stores **scanned block ranges**, not a last-block number, so it can tell a
gap from a fresh start and refuses a scan that would leave a hole. It re-reads
the last 5,000 blocks for reorgs, and rows are keyed on `(block, log_index)` so
the re-read replaces rather than duplicates. Resolved senders are stored and
never recomputed — that is the expensive part, about 0.2s per swap, and it
checkpoints every 1,000 so a kill loses seconds rather than an hour.

Then analyse:

```bash
.venv/bin/python scripts/token_forensics.py \
  --trades data/tokens/<token>/swaps.parquet \
  --transfers data/tokens/<token>/transfers.parquet \
  --pool 0x... --eth-usd <price> --price-now <price> --price-week-ago <price>
```

## Costs, so you can plan the run

Measured on WALLET, 64M blocks, 75 days:

| Step | Cost |
|---|---|
| Transfer scan, full history | ~6 min, 628k logs |
| Swap scan, full history | ~4 min, 263k logs |
| Swap scan, one week | ~15s, 12.7k logs |
| Sender resolution | **~0.2s per swap** — 12.7k swaps is ~45 min |
| Holders via Blockscout | seconds |

Sender resolution dominates. Resolve a window, not a history: the archive keeps
what it has, so a week today plus a week next week costs two weeks, not two
histories. Start it in the background and do other work; do not chain sleeps.

## Data sources

| Source | Gives | Notes |
|---|---|---|
| `rpc.mainnet.chain.robinhood.com` (`src/rhc/rpc.py`) | Transfer and Swap logs, `tx.from`, `balanceOf`, `totalSupply` | archive depth to block 1, unauthenticated, 10k logs/call cap |
| Blockscout (`src/rhc/chain.py`) | holder list and count, contract metadata | matches the DexScreener Holders tab exactly |
| DexScreener (`src/rhc/dexscreener.py`) | price, mcap, liquidity split, txn counts, socials | `/latest/dex/search?q=` resolves a ticker |
| GeckoTerminal (`src/rhc/premium.py`) | OHLCV history, **distinct** buyer/seller counts | serves no token descriptions for this chain |

## What the data cannot see

- **V4 pools.** Undecoded. On WALLET that is $107k of $2.6M liquidity. Check
  whether a token's second pool is V4 (64-hex pool id) before calling a
  single-pool picture complete.
- **One person across many addresses.** Two-address structures are routine —
  buy through a hot contract, park in a cold EOA. `rhc.clusters` scores
  co-timing against a chance-overlap null; the transfer graph finds funding
  links directly. Neither is automatic.
- **Cost basis before the window.** Exact only for a wallet that started the
  window flat. Report which, never assume.
- **USD at the time of the trade.** A single ETH price across a long window is
  an approximation; token-denominated shares are exact. Say which you are using.

## Reading the output

Signals are reported separately, never fused into one score, so a reader can see
which fired. Bot signatures: repeated identical trade sizes, inter-trade gaps
with near-zero variance, both sides of the book inside one block, and a
round-trip ratio near 1 on high trade counts. **High trade count alone is not a
bot** and never a flag on its own.

Round-tripping at a crash is arbitrage, not conviction: after WALLET's −96% hour
the same addresses topped both the buy and sell lists, 83% of supply each way.
Reading either side as demand would have been wrong.
