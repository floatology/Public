# Runners do not linger. They blow straight through.

**Measured 2026-09-21** over 3,446 pools collected across all 42 DEXes on the
chain, with daily candles for 1,000 of them and market cap reconstructed from
FDV and price.

## The question

Does a token that consolidates around $250k–$500k — absorbing supply before the
move — go on to run? The alternative is that time spent at a level means
nothing, and that runners simply pass through on their way up.

## The answer

| | n | P(reached $2M) | 95% CI |
|---|---|---|---|
| **Lingered ≥5 days in the zone** | 73 | **13.7%** | 7.6–23.4% |
| **Passed straight through** | 842 | **77.9%** | 75.0–80.6% |

The intervals do not overlap and are nowhere near overlapping. Days spent in the
$200k–$500k band:

| | median | p75 | p90 | max |
|---|---|---|---|---|
| Runners | **0d** | 0d | 0d | 21d |
| Everything else | 0d | 5d | 13d | 35d |

**The median runner spent zero days in the zone.** Ninety percent of them spent
zero days. The tokens that sat there are the ones that went nowhere.

## The confound, which is large and must be stated

**Time in a zone is partly an inverse measure of velocity, by construction.** A
token that 10x's in a day passes through $200k–$500k in hours and scores zero
days. So "lingering predicts failure" is partly a restatement of "fast movers
run", and the effect size above is inflated by that mechanical relationship.

What it is *not* is evidence for accumulation. Whatever share of this is
mechanical, none of it points the other way, and the hypothesis predicted the
opposite sign.

This is the **second independent dataset** to say so. `docs/13` measured, on a
different sample with a different method, that being inside a detected base
scored *worse* than the impulse alone — 15.5% against 23.8%. Two unrelated
measurements agreeing is the standard this project holds a result to, and here
they agree.

## What crossing $250k is actually worth

Restricted to the 100 tokens whose crossing is **observed** — below the
threshold, then above it, both inside the candle window — the run from that
crossing:

| | peak (wick) | volume-backed |
|---|---|---|
| p25 | 1.28x | 1.17x |
| **median** | **2.27x** | **2.19x** |
| p75 | 6.68x | 5.98x |
| p90 | 28.76x | 27.54x |
| max | 115.7x | 91.6x |

| outcome | share |
|---|---|
| ≥2x | 54% |
| ≥3x | 42% |
| ≥5x | 30% |
| ≥10x | 17% |
| ≥20x | 11% |
| reached $2M | 42% |

**The peak and the volume-backed peak are nearly identical** — 2.27x against
2.19x. That is worth noticing. On the V2 memecoin tail the same comparison
differed by 2.8x, meaning those peaks were wicks nobody could sell into. Here
they were real: a token that crosses $250k and runs is one you could have sold.

**Median days from crossing to the high: 5.** p75 is 20 days, max 57. The move
is fast, which is consistent with everything above and inconsistent with a
thesis built on weeks of accumulation.

## Why the naive version of this number is wrong

Measured over all 865 crossings without filtering, the median multiple is
**1.14x**, not 2.27x. The difference is **left-censoring**: two thirds of these
tokens were already above $250k on their first candle, so their "crossing" is
detected at day zero and the multiple measures the tail of a move that had
already happened. Excluding them roughly doubles the median.

## Survivorship, which cuts the other way

Every pool here is one an aggregator lists today. A token that crossed $250k and
died into obscurity is absent. That inflates the headline rates — the 77.9% and
the 42% in particular — and it inflates them in the direction that flatters the
strategy. The correct reading of "42% reached $2M" is **"42% of the ones still
listed"**, and the true figure is lower by an unknown amount.

It does **not** rescue the linger finding. Survivorship would have to act
selectively against lingering tokens to explain a 13.7% against 77.9% gap, and
there is no mechanism for that: both groups are drawn from the same listing.
