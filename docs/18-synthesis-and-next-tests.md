# Synthesis: what holds, what does not, and what to test next

Everything measured up to 2026-09-21, ranked by how much weight it will bear.

---

## Part 1 — The threshold sweep

Does a lower entry threshold do better? Measured on the census archive
(4,833 tokens, dead included, no left-censoring):

| threshold | crossings | rate | median peak | ≥5x | ≥10x (95% CI) |
|---|---:|---:|---:|---:|---|
| $25k | 1,206 | 24.9% | 2.09x | 18.7% | 9.6% (8.1–11.4%) |
| $50k | 907 | 18.8% | 1.86x | 16.0% | 8.9% (7.2–11.0%) |
| $100k | 470 | 9.7% | 1.78x | 17.2% | 10.6% (8.2–13.8%) |
| **$250k** | 167 | 3.5% | 2.24x | 25.7% | 15.0% (10.4–21.2%) |
| **$500k** | 98 | 2.0% | **2.42x** | 25.5% | **20.4%** (13.6–29.4%) |
| $1M | 64 | 1.3% | 1.83x | **29.7%** | 21.9% (13.5–33.4%) |

**Higher is better, but only up to a point, and the point is below $250k.**

The $25k–$100k band and the $500k band have **non-overlapping** intervals on
≥10x — that difference is real. But $250k, $500k and $1M are not
distinguishable from each other: their intervals overlap heavily. So there is a
genuine step up somewhere between $100k and $250k, and above that you are
trading opportunity count for no measurable gain.

**The $250k–$300k instinct was close to right.** Not because it is optimal —
nothing in this data can tell $250k from $1M — but because it sits just past the
step, where the quality gain has happened and 167 opportunities remain rather
than 64.

---

## Part 2 — The finding that overturns the strategy

If you bought **every** $250k crossing and applied an exit rule, walking each
rule forward along the actual trade sequence:

| rule | median | arithmetic mean | **geometric mean** | profitable | wiped out |
|---|---:|---:|---:|---:|---:|
| 2x target, stop at 0.5x | 0.82x | 1.15x | **0.80x** | 47.3% | 1.2% |
| 3x target, trailing 30% | 0.85x | 1.08x | 0.77x | 35.3% | 1.8% |
| trailing 30% + stop | 0.84x | 2.26x | 0.77x | 33.5% | 2.4% |
| trailing 50% | 0.70x | 2.75x | 0.75x | 32.9% | 3.0% |
| sell at 1.5x | 1.50x | 1.18x | 0.69x | 74.9% | 15.0% |
| sell at 2x | 2.00x | 1.27x | 0.49x | 61.1% | 23.4% |
| sell at 10x | 0.41x | 2.12x | 0.22x | 36.5% | 41.3% |
| hold to the end | 0.13x | 1.86x | 0.13x | 26.9% | 47.3% |

**Not one rule has a geometric mean above 1.0x.** The best loses 20% per trade
compounded. And this is **gross** of execution cost, own-order impact and exit
slippage — all of which push it down further, hardest in exactly the thin pools
where the biggest multiples appear.

**The arithmetic means are the trap.** "Trailing 50%" averages 2.75x and
compounds at 0.75x. A handful of large winners lift the average while the
majority of positions destroy capital, and you cannot compound through a 47%
chance of near-total loss by averaging it away.

**So the threshold is not a strategy.** Crossing $250k is a real filter —
94.3% of tokens never do it, and those that do peak at a 2.24x median — but
mechanically buying all of them loses money under every exit rule tested. Any
viable system needs *selection* on top of the threshold.

---

## Part 3 — What holds, ranked

### Solid: two independent measurements agree

**1. The peak-multiple distribution after crossing $250k.**
Census median 2.24x against aggregator median 2.27x; ≥2x 53.9% vs 54.0%; ≥10x
15.0% vs 17.0%. Two datasets, two supply sources, daily candles against
individual trades. This is the most replicated number in the project.

**2. Runners do not linger, and the base is not the signal.**
`docs/16`: tokens lingering ≥5 days in the $200k–$500k band reached $2M 13.7% of
the time against 77.9% for those passing through; the median runner spent zero
days there. `docs/13`, separate sample and method: being inside a detected base
scored 15.5% against 23.8% for the impulse alone. Both point the same way.
Caveat: time-in-zone is partly an inverse measure of velocity, so part of this
is mechanical — but no part of it supports accumulation.

**3. Survivorship inflates "share that made it" by about 2.3x.**
18.0% of census crossers reached $2M against 42.0% of listed ones. Halve any
such figure read off an aggregator.

**4. The chain is a graveyard, and the numbers are specific.**
Median V2 token trades for ~15 minutes; 0.58% of sampled V2 pools trade for more
than a day. 94.3% of census tokens never reach $250k.

**5. More than half the busiest pools fail a wash screen.**
32 of the top 60 by volume. AIForce turned over 1,139x its $3,709 of reserves in
a day.

### Probable: one measurement, survived hard tests

**6. A multivariate model beats its control on ranking.**
Under the strictest split available — unseen tokens *and* a later period — AUC
0.69–0.79 against a 0.52–0.64 control across five seeds, consistently.
`sniper_buy_count` carries the largest coefficient, negative.
**But lift does not survive**: in one seed of five it falls below the shuffled
floor. Ranking is established; a tradeable top-decile edge is not.

**7. Momentum, not shape.**
A recent 3x takes the 5x rate from 6.3% to 23.8%. Breakouts add something over
that (2.24x) but on fifteen observations.

### Unproven or refuted

**8. Launch liquidity** — refuted, an arithmetic identity (`docs/08`).
**9. Stock-token premium arbitrage** — refuted, AP-only minting.
**10. Accumulation at a level** — refuted twice, see above.
**11. Bull flags as a standalone signal** — mostly the impulse they require.
**12. Float lockup (H1)** — still unresolved; needs the forward series.

---

## Part 4 — What to test next, in priority order

**1. Does the model's ranking rescue the threshold?**
The single highest-value test. The threshold loses money applied to everything;
the model ranks at AUC ~0.75 out-of-token-and-time. Score every crossing with
the model, take the top quartile, and re-run the exit grid. If the geometric
mean crosses 1.0x, there is a system. If it does not, there is not, and that is
worth knowing in one run.

**2. Execution-cost-adjusted returns.**
Every number above is gross. `v3_depth_1pct` gives the quote needed to move the
price 1% at each trade, so a realistic fill can be priced per entry and exit and
the grid re-run net. Expect this to remove a large fraction of what is left.

**3. Path dependency: what drawdown do you have to survive?**
A position that reaches 5x after first falling 60% is not one most people hold.
Measuring maximum drawdown *before* the peak turns the multiples above into
something a human could actually have captured.

**4. The exit grid at every threshold.**
Done at $250k only. The interaction may matter: a higher threshold with a
tighter target may compound above 1.0x where neither does alone.

**5. Time-to-peak conditioning.**
Median 5 days to the high at $250k, p75 20. A rule that exits on time rather
than on price is cheap to test and was the worst family here — worth confirming
that holds at other thresholds.

**6. V4, still entirely unmeasured.**
18 of the top 60 pools, $141M daily, deeper than V2, and invisible to every
number in this document. `scripts/discover_v4.py` is written and unrun.

**7. H1 float lockup.**
The original hypothesis. The daily capture has one day of data; it needs weeks.
Nothing to do but let it accrue — which is an argument for keeping the workflow
alive.
