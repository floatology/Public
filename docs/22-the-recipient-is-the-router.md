# 22 — The recipient is the router

Asked to look at wallet accumulation in **WALLET** (Robinhood Wallet,
`0x0339f5459FC690aC85F1782e15782A151b4A9E1b`), the obvious instrument was the
one already built: decode the pool's `Swap` logs, key a ledger on the trader,
rank by net position. That instrument is wrong on this chain, and the way it
fails is worth recording because nothing in the existing feature extraction
would have caught it.

## What the swap ledger said

263,408 swaps from the main WETH pool, `0x9501…5D49`, over 75 days. Keyed on the
`Swap` event's `recipient` topic, the ledger reported:

| | |
|---|---|
| top "accumulator" | 26.44% of supply, $7.4M, 7,817 buys, 0 sells |
| second | 13.55%, 11 buys, 0 sells |
| total net held by buyers | **1,206% of supply** |
| largest net "position" | **−515% of supply** |

A share of supply cannot exceed 100% and cannot be negative. `balanceOf` on the
top six names returns **zero** for five of them and 0.019% for the sixth. They
are routers. Every one is a contract; the largest has 106,805 transfer touches
and keeps nothing.

The decoder's own docstring says `recipient` "is the closer proxy for the
trader", and on a chain where traders send their own transactions it is. On this
one the dominant front-end routes through contracts, so the recipient of the
swap output is the router and the router's onward transfer to the user is
invisible to the swap log. The negative positions come from the mirror of the
same hole: an address that received tokens by transfer and then sold them shows
a sale the ledger never saw a purchase for.

**A recipient-keyed ledger measures router throughput.** It is not a weaker
measure of accumulation; it is a measure of something else.

## What replaces it

`Transfer(address indexed from, address indexed to, uint256 value)`. Every token
movement emits one whatever caused it, so replaying them in order reconstructs
every balance exactly. 607,892 transfers for this token; replayed supply comes
to **100.0000%** of nominal and 25 sampled balances agree with `balanceOf` to
the wei.

The audit has to be **pinned to the scan's last block**. Run against `latest` it
reported one mismatch — the pool, whose balance had moved by 0.015% in the
minutes between the scan finishing and the check running. An audit that flags
elapsed time as corruption trains you to ignore it.

Classifying a transfer still needs a set of market addresses. Pool membership is
known; routers are found by their signature rather than by a list — **moves more
than 2% of supply, keeps less than 0.1%, 50+ touches** finds 78 addresses on
this token, every one a contract, moving 12× supply between them. Receipt from
pool or router is a purchase, receipt from anything else is a movement between
holders, and that second category is exactly the flow the swap ledger cannot
see.

## Scripts

- `scripts/token_transfers.py` — every `Transfer` for one token
- `scripts/token_holder_report.py` — replay, audit, concentration, era cohorts
- `scripts/token_wallets.py` / `token_wallet_report.py` — the swap-keyed version,
  kept because it is the right tool for a pool where traders self-route, and
  because the contrast is the evidence for this note

## The generalisation

Every per-pool feature in `data/parquet/features.parquet` that counts *wallets*
rather than *trades* inherits this. `stealth_accumulator_count`, the wash
screens' unique-buyer measures, `rhc.clusters` co-timing — all are keyed on swap
recipients, so on router-mediated tokens they are counting routers. Trade counts,
volumes, prices and depth are unaffected: those read the amounts, not the
addresses.

This does not invalidate the mini screen (`docs/21`), which uses no wallet
identity at all. It does mean the wallet-identity work in `docs/07` and the
cluster scoring need re-basing on transfers before any of it is trusted, and
that is not a small job: 607,892 transfer logs for one token, against a census
of 3,446 pools.
