# 25 — What precedes a breakout, tested across the market

**Question.** WALLET's 3–4 September breakout came after a volume dry-up, an
ignition day, higher lows while tokens left the pool, and a pullback that held.
Does that shape predict breakouts on other coins, and which filters (age, market
cap, activity) separate coins worth watching from noise?

**Data.**
- **Candles:** daily closes and volume for 3,169 tokens across 42 DEXes, V4
  included (`scripts/gt_history.py`). The universe is today's GeckoTerminal
  listing plus 1,896 pools from the September census that have since been
  delisted.
- **Flow:** per-trade histories for 4,211 tokens from the older V2/V3 archive
  (`scripts/flow_backtest.py`).
- **Wallets:** full attributed histories for 43 coins (case-control batch,
  `data/overnight/batch2.json`) — 20 that had a 2x run with 14 days of prior
  history, 20 equally active coins that never did
  (`scripts/wallet_signals_backtest.py`).

Outcomes are measured over the 14 days after each signal:

| Outcome | Definition |
|---|---|
| `run2x` | some close in the window reaches 2× the entry close |
| `crash` | some close falls to half the entry close |
| `clean` | a close of 1.5× comes before any close of 0.7× |
| `held` | still up 50% or more at day 14 |

Events are de-duplicated to one per token per 14 days. Each signal's rate is
compared to the base rate of coins with the **same weekly volume**. Every result
is repeated on two halves split by time and two halves split by token.

## Four measurement traps, each of which produced a false result first

1. **Dead coins dominate.** 99% of token-days in the flow archive had under $1k
   of weekly volume. A signal that fires only on live coins therefore beats the
   all-days base rate by 20× while predicting nothing. Fix: compare each signal
   with coins of the same activity level.
2. **Wicks are not prices.** Measured on candle highs, 38.5% of token-days
   "reached 2x within 14 days". On thin pools a single stray fill prints a
   wick nobody could sell into. Fix: measure outcomes on closes.
3. **Survivorship more than doubles the base rate.** Using only coins still
   listed today, 27.6% of token-days hit 2x within 14 days. Adding back the
   delisted census coins brings it to 11.9%.
4. **Unpriced pools.** DexScreener's per-token endpoint returns only a token's
   single best pair, so every other pool went unpriced: 152k of ORBIO's 202k
   trades had a USD value of zero. Fix: price by quote asset.

## Results (survivor-corrected candles, final run: 39,771 token-days, 1,235 tokens)

The final run adds the last 1,555 small pools. It confirms the earlier run
on 26,684 token-days, and the numbers below are the final ones.

| Signal | Events | 2x in 14d | Crash | Held +50% | 2x lift | Crash lift |
|---|---|---|---|---|---|---|
| base, all | 39,771 | 9.1% | 6.6% | 8.7% | | |
| base, weekly vol >= $10k | 8,930 | 27.3% | 23.6% | 21.5% | | |
| dry-up alone (earlier run) | 1,372 | 15.7% | 11.2% | 13.8% | 1.05x | 1.09x |
| ignition alone (earlier run) | 702 | 22.5% | 20.9% | 17.9% | 1.02x | 1.18x |
| higher lows alone (earlier run) | 773 | 21.1% | 18.6% | 16.6% | 1.08x | 1.15x |
| coil alone (earlier run) | 837 | 8.1% | 5.3% | 7.4% | 0.99x | 0.85x |
| **SETUP** (dry + ignite + higher lows + coil) | 103 | 20.4% | 11.7% | 16.5% | **1.41x** | 0.96x |
| **BREAK** (close > 20d high on >= 2x volume after a dry-up) | 169 | 37.9% | 24.9% | 30.2% | **1.84x** | 1.41x |

The 2x lift holds across every split:

| Signal | Time, 1st half | Time, 2nd half | Tokens A | Tokens B |
|---|---|---|---|---|
| BREAK | 2.04x | 1.86x | 1.98x | 1.68x |
| SETUP | 1.27x | 1.36x | 1.63x | 1.22x |

**Reading.**
- **No single signal has an edge.** Dry-ups, ignition days, higher lows and
  coiling each sit near 1.0x once matched on activity. The pattern only carries
  information in combination.
- **BREAK is the strongest signal**, and also the most volatile: it raises the
  crash rate by 1.41x. It confirms a move rather than anticipating it.
- **SETUP is the cleaner early signal**, at about 1.5x upside with roughly neutral
  crash risk, but it is rare (103 events across 1,235 tokens).
- **The flow test agreed on direction and was too small to add much.**
  Absorption and breakout days predicted large moves in *both* directions. The
  full WALLET-shaped composite with on-chain flow fired only 7 times.

## Wallet-level results (case-control batch, 43 tokens)

Same de-duplication and same-activity comparison as above, tested at two
horizons on the case-control batch (20 coins with a prior 2x run, 20 equally
active coins that never had one). `n_accum`/breadth counts distinct wallets;
`whale_accum` is net tokens bought over 10 days by wallets that end the day
holding >= 0.5% of supply, as a share of supply.

| Signal | Events (7d / 14d) | 2x lift (7d / 14d) | Crash lift (7d / 14d) |
|---|---|---|---|
| whales net-bought >= 1% (10d) | 226 / 104 | **1.07x / 1.05x** | 0.92x / 0.99x |
| whales net-bought >= 0.5% (10d) | 242 / 113 | 1.04x / 1.03x | 0.97x / 1.00x |
| >= 15 distinct wallets took 0.05%+ | 224 / 107 | 1.07x / 1.04x | 0.96x / 0.99x |
| holders +25% in 7d | 85 / 54 | 1.14x / 0.92x | **1.37x / 1.19x** |
| top-20 share -2 pts (10d, distributing) | 57 / 37 | 1.25x / 0.86x | **1.25x / 1.30x** |

Base rates: 7d horizon 35.3% run2x / 29.3% crash (1,646 token-days, 43 tokens);
14d horizon 48.4% run2x / 44.9% crash (1,373 token-days, 39 tokens).

**Reading.**
- **Whale net-buying is a real but modest edge**, and the only wallet signal
  that holds its sign at both horizons: ~1.05–1.07x more likely to run,
  ~flat-to-slightly-fewer crashes (0.92–0.99x). It confirms the qualitative
  pattern from watching WALLET live all session (0x5364, 0xa9fd and others
  accumulating ahead of moves) generalises across the market — but the edge
  is far smaller here than BREAK/SETUP's 1.4–1.8x, so treat it as a
  confirming signal to stack on a price pattern, not a standalone one.
- **Breadth tracks the whale signal almost exactly** (>=15 wallets each
  taking a stake), which makes sense — a real accumulation phase draws both
  a concentrated buyer and a wider crowd together.
- **Holder-count growth is a false-positive trap, not a green light.** It
  raises the crash rate more than the 2x rate at both horizons (1.19–1.37x
  more crashes vs. 0.92–1.14x more runs) — a fast-growing holder count looks
  like hype/new-speculator inflow more than durable accumulation, and should
  be read as a caution sign, not confirmation.
- **Falling top-20 concentration (known-wallet distribution) is a bad sign
  at 14 days** — lower 2x rate (0.86x) and materially higher crash rate
  (1.30x). This matches what distribution from a token's known sellers has
  looked like live on WALLET: it's the closest thing here to a real
  short-side signal, though the 7-day read is more ambiguous (both rates up
  together, more volatility than direction).
- **New-wallet-share signals had too few qualifying tokens** (1–4) at either
  horizon in this batch to draw a conclusion.

## Filters: what cuts the noise

Base rates by bucket (candles, survivor-corrected):

| Weekly volume | 2x | Crash | Ratio |
|---|---|---|---|
| < $1k | 2.4% | 0.6% | dead |
| $1k–10k | 17.3% | 4.6% | 3.8 |
| **$10k–50k** | **26.3%** | **7.1%** | **3.7** |
| $50k–250k | 32.6% | 21.1% | 1.5 |
| $250k–1M | 30.5% | 34.2% | 0.9 |
| $1M+ | 22.1% | 29.9% | 0.7 |

| Market cap | 2x | Crash |
|---|---|---|
| $25k–100k | 21.0% | 17.2% |
| $100k–300k | 27.0% | 30.3% |
| $300k–1M | 32.8% | 36.7% |
| $1M–5M | 19.8% | 19.3% |
| $5M+ | 21.0% | 19.7% |

| Age | 2x | Crash |
|---|---|---|
| 14–44 days | 12–13% | 7–9% |
| 45–59 days | 9.3% | 11.2% |
| 60+ days | 8.0% | 13.9% |

- **Weekly volume is the filter that matters.** Moderate activity ($1k–50k a
  week) has the best upside-to-downside ratio. Above $250k a week, crashes
  outnumber runs; that is churn and distribution, not accumulation.
- **$100k–$1M is the most volatile market-cap band**, highest on both the
  upside and the crash rate. Above $1M the two are balanced.
- **Age is a weak filter, and older is not safer.** Past about six weeks the
  upside falls and crashes rise. Coins younger than 14 days cannot be tested
  here: they have no history to signal on. Today's busiest coins are mostly
  hours old.
- **Inside the $100k–$5M range with $10k+ of weekly volume**, SETUP hit 2x 43%
  of the time with fewer crashes than comparable coins (0.78x); BREAK hit 2x 51%
  of the time but crashed 37%.

## Live screen

`scripts/candle_backtest.py` flags SETUP and BREAK on the last complete day.
`scripts/live_screen.py` then applies the filters above: SETUP or BREAK, weekly
volume of at least $10k, market cap $100k–$5M, no tokenized stocks, and a
HIGH-CHURN mark above $250k a week. On 27 Sep, 93 raw flags reduced to 2 (on 28 Sep, 140 raw flags reduced to none):

- **Odin** — BREAK, $369k cap, $88k weekly volume
- **ai17z** — BREAK, $252k cap, $323k weekly volume (HIGH-CHURN)

## Limits

- **One market, one quarter.** Everything comes from Robinhood Chain between
  July and September 2026. Lifts of 1.5–1.7x on 76–142 events are consistent
  across splits, but they are not large samples.
- **Market cap is approximate:** price × supply, with supply from fdv/price or
  a cached `totalSupply`. It is wrong for tokens that mint after launch (see
  ERHA).
- **Closes, not execution.** A 2x close is not a 2x fill after slippage and
  fees, particularly on the thin pools where these signals fire.
- **Wallet-level sample is small.** 43 tokens, one case-control batch, one
  quarter. The whale-accumulation edge (1.05–1.07x) is consistent in sign
  across both horizons but is a modest effect on a modest sample — it should
  be read as one input alongside the price-pattern signals above, not tested
  in combination with them yet.
