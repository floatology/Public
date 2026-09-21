# What crossing $250k is worth, measured on a sample that includes the dead

**Measured 2026-09-21** on the extraction archives: 4,833 tokens sampled from
the chain's census of pool creations, with `totalSupply()` read per token and
market cap reconstructed from trade-level prices. Dead tokens are present in
their true proportion, and every crossing is observed rather than inferred.

## The headline

Of 4,833 census-sampled tokens:

| | count | share |
|---|---:|---:|
| Never reached $250k | 4,559 | **94.3%** |
| Crossed $250k | 167 | **3.46%** |
| …and went on to $2M | 30 | **18.0% of crossers** |

Crossing $250k is rare. It happens to about one token in twenty-nine.

## The part that validates the method

Peak multiple from the crossing, census sample against the aggregator sample
measured separately in `docs/16`:

| | census (n=167) | aggregator (n=100) |
|---|---:|---:|
| median | **2.24x** | **2.27x** |
| ≥2x | 53.9% | 54.0% |
| ≥3x | 37.1% | 42.0% |
| ≥5x | 25.7% | 30.0% |
| ≥10x | 15.0% | 17.0% |
| ≥20x | 12.0% | 11.0% |

Two datasets, two reconstruction methods, two sources of supply, one built from
daily candles and the other from individual trades — and the distributions land
on top of each other. **Survivorship does not distort the peak-multiple
distribution.** That is the independent agreement this project holds results to,
and it is the first time two measurements here have agreed this closely.

## The part survivorship *does* distort

| | census | aggregator |
|---|---:|---:|
| Crossers reaching $2M | **18.0%** | 42.0% |

A factor of **2.3x**. The aggregator sample cannot see the tokens that crossed
$250k and died, and that is exactly the population that fails to reach $2M. So
the survivorship correction is large and now measured rather than guessed: when
reading any "share that made it" figure from listed pools, **divide by about
two**.

## The number that should change how you trade this

Where those 167 tokens **ended up**, against their crossing price:

| | multiple |
|---|---:|
| p10 | 0.01x |
| p25 | **0.01x** |
| **median** | **0.13x** |
| p75 | 1.12x |
| p90 | 2.38x |
| max | 128x |

Only **12.6%** are currently above 2x. A quarter are down **99%**.

Read the two distributions together: the median token that crosses $250k **peaks
at 2.24x and ends at 0.13x**. The upside is real and the round trip is
catastrophic. Everything in this result lives in the exit, not the entry —
identifying a token that will run is roughly half the problem, and the smaller
half.

## What this does to the entry thesis

It supports the premise and moves the difficulty. Reaching $250k does filter:
94.3% of tokens never get there, and those that do produce a 2.24x median peak
with a 26% chance of 5x and a 15% chance of 10x. That is a real edge over the
unconditional population.

But it is not the edge the "$300k sweet spot" framing implies, for two reasons
already measured elsewhere. **`docs/16`: runners do not linger** — the median
runner spent zero days in the $200k–$500k band, and tokens that sat there
reached $2M 13.7% of the time against 77.9% for those that passed through.
**`docs/13`: the impulse carries the signal, not the base.** Buying into a
consolidation at $250k is the specific behaviour all three measurements point
away from.

## Caveats

**Supply is read once, at the current block.** A token that minted after launch
has its early cap overstated and its multiple understated. `rhc.contracts` finds
mint functions routinely.

**A pool that never traded never enters the archive.** Those never approached
$250k, so it does not bite here, but the denominator is "tokens that traded at
least ten times", not "all tokens".

**One chain, twelve weeks, one regime.**

**"Where it ended" is the last trade in the archive**, which for a dead token is
its final trade and for a live one is the present. It is not a claim about what
any of them will do next.
