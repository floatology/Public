# 23 — Three layers of identity, and a finding that wasn't

`docs/22` replaced a swap-keyed wallet ledger with a transfer-keyed one, because
the `Swap` event's `recipient` topic is the router on a routed trade. That fixed
*holdings*. It did not fix *who traded*, and fixing that turned out to need two
more corrections, the first of which I nearly published as a discovery.

## The layers

On this chain an address can be any of three things, and each answers a
different question:

| Layer | Where it comes from | Answers |
|---|---|---|
| **Token holder** | `Transfer` logs replayed to balances | who owns the float |
| **Transaction signer** | `tx.from` | who pressed the button |
| **Smart account** | `UserOperationEvent.sender` | who owns the position a bundled trade belongs to |

They coincide often enough to be dangerous. On a week of WALLET swaps, `tx.from`
differed from the swap recipient on **86%** of 12,758 trades. Of the remainder,
**1,074** were sent by a bundler rather than by a person.

## The finding that wasn't

Ranking the week's sellers by "many small sells, no buys" produced twelve
addresses, of which **ten shared the prefix `0x4337`**. A shared six-character
prefix is a 1-in-65,536 coincidence per address; ten of them is not a
coincidence at all, and it reads immediately as one entity distributing through
a fleet of vanity addresses while the price falls.

`4337` is the **ERC number for account abstraction**. Those addresses are
bundlers, and the prefix is a vanity choice advertising exactly that. Their
transactions call `handleOps` (`0x765e827f`) on the canonical EntryPoint at
`0x0000000071727De22E5E9d8BAf0edAc6f37da032`, one of them carrying 33 logs —
dozens of unrelated users batched into a single transaction and collapsed, by a
`tx.from` ledger, into one apparent seller.

99 such bundlers, 8.4% of the week's swaps, 5.6% of its volume.

**What made it check out was the thing that made it look like a finding.** A
prefix that improbable is either coordination or a convention, and conventions
are named. Looking up the number took a minute; publishing it would have been a
fabricated cartel.

## The correction

`scripts/unwrap_userops.py` attributes each bundled swap to its smart account.
The EntryPoint emits `UserOperationEvent` *after* each operation executes, so a
swap log belongs to the first such event at a higher log index in the same
transaction. Ordering by log index makes this exact rather than approximate, and
a swap with no later event is left with the bundler and counted rather than
guessed at.

On WALLET: **1,074 reassigned, 0 unmatched, 0 failed.** Distinct traders in the
week rose from 2,725 to 3,160 — the bundlers splitting back into the people
behind them. Every apparent stealth-distribution ring dissolved.

## The layer still unjoined

The week's largest buyers, keyed on `tx.from`, **do not appear in the transfer
ledger at all**: they sign the transaction, and the tokens land at a different
address. So "who bought" and "who holds" are still two lists that cannot be
joined without matching each transaction's swap against the `Transfer` logs
emitted beside it. That join is not built. Until it is, treat trader-side and
holder-side results as describing different populations, and say so.

## Rule

Any address-keyed claim on this chain needs its layer named before it means
anything. A number that is right about signers and reported as though it were
about holders is not approximately right; it is about something else.
