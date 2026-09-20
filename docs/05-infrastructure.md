# Infrastructure: what runs, where data lives, what accounts are needed

**Date:** 2026-09-20

---

## Short answer

**You do not need Supabase, and you do not need any new account.** The master
document (Part 10, Part 14) specified Supabase as "the actual data store" for the alert ledger,
wallet scores and per-token feature history. That was reasonable when the plan assumed paid Dune
access and a hosted pipeline. It is now the wrong shape for every category of data this project
actually produces.

---

## What data this project produces, and where it belongs

| Data | Volume | Store | Why |
|---|---|---|---|
| **Daily lockup/premium series** | ~79 KB/day, **~29 MB/year** | **Git, partitioned monthly** | Small, append-only, needs versioning and diffing more than querying. Free, no account, survives forever. |
| **Pool census** | 26 MB | **Not stored** | Regenerates from the free archive RPC in ~10 minutes. The script is the artifact. |
| **Bulk swap history** (for H0) | Est. **0.5–2 GB** | **Local Parquet + DuckDB** | Too big for git *and* too big for Supabase's 500 MB free tier. Also regenerable. |
| **Execution-cost measurements** | ~KB/day | **Git, alongside the series** | Same shape as the lockup series. |

### Why Supabase specifically does not fit

- **Free tier is 500 MB.** The swap history alone would exceed it, and that is the only dataset
  large enough to justify a database in the first place.
- **Free projects pause after 7 days of inactivity.** This project's entire premise is continuous
  gap-free logging (`PREREGISTRATION.md`, and the drift engine the master document specified in
  Part 14.5). A store that silently pauses is the worst possible fit for that requirement.
- **The small data does not need a database.** 29 MB/year of append-only JSONL is a file, not a
  workload. Putting it in Postgres adds an account, a secret, a network dependency and a failure
  mode, and buys nothing that `duckdb.read_json('data/premiums/*.jsonl')` does not already give.

**Revisit this if** the daily series grows past a few hundred MB, or if something other than this
repository needs to read it live (a dashboard, a bot, a second machine). Neither is true today.

---

## What is running now

### Daily lockup scan — `.github/workflows/daily-lockup-scan.yml`

- **Schedule:** 21:20 UTC daily, after US market close.
- **What it does:** discovers the canonical stock-token universe (~176 tokens), measures premium
  and live float lockup for each, appends to `data/premiums/YYYY-MM.jsonl`, commits and pushes.
- **Verified working:** manually dispatched 2026-09-20 and confirmed to run.

**The critical configuration detail:** GitHub only fires `on: schedule` workflows from the
repository's **default branch**. This repo's default branch is
`claude/document-analysis-review-dkjfu4`, which is also the working branch, so the schedule fires.
**If the default branch is ever changed** — for example by creating `main` and making it default,
or by merging and deleting this branch — **the scan silently stops running.** There is no error;
it simply never fires again. Anything that changes the default branch must move this workflow with
it.

### Known risk: the 60-day inactivity disable

GitHub automatically disables scheduled workflows in a repository after **60 days without
activity**, and commits pushed by `GITHUB_TOKEN` (which is what this workflow uses) generally do
**not** count as activity for that purpose. The owner receives an email and can re-enable with one
click.

Mitigations, in order of preference:

1. **Push something yourself occasionally** — any manual commit resets the timer. Given this is an
   active project, this will happen naturally.
2. **Watch for the email.** GitHub warns before disabling.
3. If the project goes dormant but the series must keep accruing, switch the workflow's push to a
   fine-grained PAT stored as a secret, since pushes authenticated that way count as user activity.

This is recorded because a silently-stopped scan is indistinguishable from a quiet market, and the
whole point of the series is that gaps in it are unrecoverable.

### Optional: dead-man's switch

Set a `HEALTHCHECK_URL` repository secret (free tier at healthchecks.io, 20 jobs, no card) and the
scan will ping it on start, success and failure. Without it, a failing workflow is only visible if
you look at the Actions tab.

**This is the one account worth creating** — not for storage, but so that a broken pipeline tells
you rather than quietly producing nothing.

---

## Accounts: what you actually need

| Service | Needed? | Note |
|---|---|---|
| **GitHub** | Already have it | Hosts code, runs the schedule, stores the series. Public repo = free unlimited Actions minutes. |
| **Healthchecks.io** | **Recommended** | Free. The only genuinely useful addition. Tells you when the pipeline breaks. |
| Supabase | **No** | See above. Wrong shape for every dataset here. |
| Dune | **No** | Went view-only 2026-09-10; the free archive RPC replaced it entirely. |
| Alchemy / RPC provider | **No** | `rpc.mainnet.chain.robinhood.com` serves free unauthenticated archive access. |
| Finnhub | **Not yet** | Only needed if the reference equity price from Blockscout proves unreliable. It has cross-checked correctly so far. |
| LunarCrush | **Not yet** | Social signals are not part of H1 or H0 as currently specified. |

The master document listed Supabase, Dune, Alchemy, Finnhub, Healthchecks and LunarCrush as
"required to start." **Measurement has reduced that to one optional monitoring account.**

---

## Reading the data back

```bash
# Whole series across all months
duckdb -c "SELECT * FROM read_json_auto('data/premiums/*.jsonl')"

# Lockup trend for one token
duckdb -c "
  SELECT captured_at, live_lockup_ratio, live_memecoin_pool_reserve_usd
  FROM read_json_auto('data/premiums/*.jsonl')
  WHERE symbol = 'NVDA' ORDER BY captured_at"
```

No database, no credentials, no network call.
