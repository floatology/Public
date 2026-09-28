# WALLET update report — standing template

Read this file at the start of every "wallet update" / "give me a wallet
update" request for $WALLET (0x0339f5459fc690ac85f1782e15782a151b4a9e1b) and
follow it exactly. Give the SUMMARY tier by default; give the DETAILED tier
only if asked, or if something in it is unusual enough to be worth surfacing
unprompted (e.g. a whale distributing, a new whale-size buyer, a fresh bot
pattern).

## Steps, every time, no skipping

1. **Refresh the archive.** `.venv/bin/python scripts/track_tokens.py build --only WALLET`.
   Confirm coverage, don't assume it: compare `meta.json`'s `transfers.ranges`
   upper block against the chain head (`eth_blockNumber` via `src/rhc/rpc.py`,
   or note if STATUS.md's last "ledger DONE" line is from this run). One line
   in the report: archive current through block N, M blocks behind head (or
   "fully synced").
2. **Run the full watchlist**, every wallet, not a subset:
   `.venv/bin/python scripts/watch_wallets.py`. This is mandatory even when
   the user's question is about something else — it's the only way to catch
   a watched wallet moving without being asked about it directly.
3. **Classify every trader active since the last update** (not just the
   watchlist) into:
   - **New wallet** — this trade is the first WALLET trade in its history
     (`min(ts)` across the whole ledger for that trader falls inside the
     report window).
   - **Returning/known, unwatched** — traded before, but isn't on
     `watchlist.json`.
   - **Watched** — already on `watchlist.json`.
   Within each, size-bucket by **net USD in the window**: Whale ≥ $10k,
   Mid $1k–$10k, Small < $1k. Report the split of buy volume across these
   buckets (e.g. "62% of buy volume from new wallets, 30% whale, 8% mid").
4. **Check for a funding/identity link on any new whale-size buyer**: does it
   have a direct transfer (in `transfers.parquet`) to or from a
   `watchlist.json` address or another address already flagged this session?
   Note it if found ("funded by / sent to <known wallet>"); say "no link
   found" rather than omitting the check.
5. **Auto-add new $25k+ net buyers** per the token-forensics skill's standing
   rule — same as always, no need to ask first.
5a. **Check for rapid repeat buying from one wallet**, every time, even
   below the $25k threshold: any trader with 2+ separate buy transactions
   (distinct `tx_hash`, not just multiple ledger rows from one multi-hop
   swap) inside the last ~15-20 minutes. Flag it in the report — who it is
   (new vs long-time trader, from its full history), how many buys, total
   size, whether each buy's multiple ledger rows are one multi-hop swap
   (same `ts`) rather than genuinely separate purchases. This is what got
   missed once already: a repeat buyer inside a short window is worth
   surfacing on its own even when it's not whale-sized.
6. **Answer whatever the user specifically flagged** (a chart, a wallet, a
   trade pattern) on top of the above, not instead of it.

## SUMMARY tier (default)

Format for a phone screen — **no wide tables that force horizontal
scrolling.** Two short tables (price/change, then size/volume), not one wide
row. No flow/buy-sell $ breakdown by default — the user said they don't care
about it. Structure, in order:

1. **Price/change table** — narrow, 4 columns max:
   `Price | 1h | 4h | 24h`. Compute 4h change from the ledger (price now vs.
   price ~4h ago) since DexScreener doesn't expose it directly; 1h/24h come
   straight from DexScreener.
2. **Size table** — separate, narrow: `Market cap | Liquidity | 24h volume`.
   Follow it with **one brief line** on whether volume and liquidity are
   moving meaningfully: compare this run's reading against the last entry
   in `data/tokens/WALLET_stats_log.csv` (append this run's reading to that
   log after reading it — timestamp, price, mcap, liquidity, volume_h24).
   Liquidity: flag a move of roughly 5%+ since the last logged entry either
   way ("liquidity has grown/shrunk since last check") or say "liquidity
   steady" if not. Volume: compare the last-1h ledger volume against the
   preceding 1h (both computable fresh from `ledger.parquet` every time, no
   log needed) — "picking up" / "slowing" / "steady". If the stats log has
   no prior entry yet (first run), say so in one line instead of guessing.
3. **What's happened since the last update** — a short narrative paragraph
   or a couple of bullets, anchored to `watchlist.json`'s per-token
   `last_checked` timestamp (that's the actual "since I last asked" boundary
   — `watch_wallets.py` advances it every run). Cover the shape of the move
   in plain terms (drifted sideways / pushed up / pulled back / broke a
   level), not a bucketed table, unless they ask to see the play-by-play.
3a. **Buyer/seller mix table — standing, every report, not just when
   unusual.** Over the same since-last-update window, split buy $ and sell
   $ each into: **New** (first-ever trade in the window), **Whale** (on
   `watchlist.json`, or net ≥ $10k in the window), **Mid** ($1k–$10k net,
   not new/whale), **Small** (<$1k net). One narrow table, columns
   `Bucket | Buy % | Sell %`. If the window is too short/quiet to have
   meaningful volume, say so in one line instead of forcing an empty table.
4. **Whalelist** (call it this in the report — the underlying file/script
   are still `watchlist.json` / `watch_wallets.py`, don't rename those) —
   one line: which whales moved since last check and what they did, or
   "none of the whales traded since last check." Name specifics briefly if
   something happened (who, how much, bought or sold), otherwise keep it to
   the one line.
4a. **Significant recent action** — standing section, every report. Cover
   any single trade or short burst worth a sentence, even off the
   whalelist and below auto-add size: a large single buy or sell (say,
   $5k+), a wallet's repeat buying (2+ buys in ~15-20 min, per step 5a), or
   a sell that stands out against the recent pattern (e.g. one wallet
   dumping heavily in just the last few minutes). For each one, give a
   sentence of story pulled from the wallet's full trade history — new vs.
   long-time trader, net lifetime P&L, whether this looks like profit-
   taking, panic, or routine rotation — not just the address and amount.
   When it's a wallet that's been selling down a position over time (not a
   one-off), always add its **remaining balance** — tokens, $ value, and %
   of supply, from `transfers.parquet`'s net-in-minus-out (the real
   post-transfer balance, not just pool position) — so it's clear whether
   they're nearly out or could keep pressuring price for a while.
   Omit the section entirely if nothing since the last update clears the
   bar; don't pad the report with routine small trades.
5. **Support/resistance** — simple, one line each: where support sits and
   whether it's been defended, where resistance sits and whether it's capped
   a push. Only include when there's an actual level worth naming.
6. **Closing read** — one or two sentences: is this normal or a real signal,
   what would change the picture.

No flow section, no new-buyer origin/size segmentation, no funding-link
callouts in this tier by default — those are detailed-tier only now. Keep
the whole thing short enough to read without scrolling past a couple of
screens on a phone.

## DETAILED tier (on request, or when something's unusual)

- Full watchlist table: wallet, holdings + % supply, delta since last check,
  lifetime P&L.
- New/notable buyer table: address, size bucket, new vs returning, amount,
  avg price, funding link if found.
- Trade-size distribution if a bot check was run.
- Phase-by-phase flow table if there's been a notable price move worth
  breaking down.
- Full reasoning for any watchlist additions made this update.

## Notes

- This file is git-tracked, so it survives context compaction the same way
  `watchlist.json` and `STATUS.md` do — re-read it, don't rely on memory of
  what a past update covered.
- The user's own personal position (wallets, avg buy price) is tracked
  separately in the session scratchpad by their choice, not here — see
  `scratchpad/user_wallet_position.md` when it exists in the current session.
