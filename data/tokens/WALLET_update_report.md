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
6. **Answer whatever the user specifically flagged** (a chart, a wallet, a
   trade pattern) on top of the above, not instead of it.

## SUMMARY tier (default)

- Price, market cap, 24h % change, liquidity.
- Net flow: last 1h and last 24h, one line each (buy $ / sell $ / net).
- Watchlist one-liner: "X of Y watched wallets active: N bought (+$total),
  M sold (–$total), rest held."
- New-buyer snapshot: how many new $25k+ buyers were added this update, and
  the one-line volume split (new / returning / watched, whale / mid / small).
- Anything the user flagged, answered directly.
- Any newly-detected anomaly (bot pattern, unusual concentration) in one line.

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
