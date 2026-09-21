# The impulse is the signal; the base is not

**Measured 2026-09-21** on 66 currently-listed pools, 2,948 daily decision
points. Survivorship-biased, small, and preliminary — see the caveats, which are
load-bearing. But the direction is clear enough to act on now, because it points
away from something.

## The headline number, and why it was wrong

The first scan reported that a breakout from a bull flag is followed by a 5x
within a fortnight **53% of the time against a 6% base rate** — an 8.4x lift.
Taken at face value: buy flag breakouts.

The problem is that a flag, by construction, **requires a 3x impulse**. Tokens
that just tripled are more likely to run again whatever shape they traced
afterwards. So "flag versus everything" was really "recently tripled versus
everything", and the base might be contributing nothing at all.

## The control

Add one group: periods following a 3x impulse where **no base formed**.

| group | n | hits | rate | 95% CI | vs all |
|---|---|---|---|---|---|
| all periods | 2,948 | 187 | 6.3% | 5.5–7.3% | 1.00x |
| no impulse | 2,439 | 75 | 3.1% | 2.5–3.8% | 0.48x |
| **impulse, no base** | 399 | 95 | **23.8%** | 19.9–28.2% | **3.75x** |
| impulse, in a base | 110 | 17 | 15.5% | 9.9–23.4% | 2.44x |
| **breakout from a base** | 15 | 8 | **53.3%** | 30.1–75.2% | **8.41x** |

## What it says

**Most of the effect is momentum, not accumulation.** A recent 3x takes the run
rate from 6.3% to 23.8%. That single fact accounts for the bulk of the original
8.4x, and it has nothing to do with chart shape.

**Sitting in a base does not improve on the impulse — it looks worse.** 15.5%
against 23.8%, a ratio of **0.65x**. The intervals overlap, so this is not
distinguishable at this sample size and should not be stated as a finding. What
can be said is that there is **no evidence the base helps**, and the point
estimate runs the wrong way for the accumulation thesis. Mechanically this is
unsurprising: a token that tripled and is still moving is more likely to keep
moving than one that has stalled.

**The breakout does appear to add something.** 53.3% against 23.8% for impulse
alone is a 2.24x improvement, and the confidence intervals separate — the
breakout's lower bound (30.1%) sits above impulse-alone's upper bound (28.2%).
Marginally. On fifteen observations.

## What this means for a strategy that waits

The instinct to buy the base and wait for the move is the thing this
contradicts. On this evidence:

- Buying *into* a base after an impulse is not better than buying the impulse,
  and may be worse — you wait, and the waiting appears to cost rather than gain.
- Buying the *breakout* is better than both, which is a different behaviour from
  accumulating alongside the token.
- Buying anything with no recent impulse is worse than the unconditional base
  rate: 3.1% against 6.3%.

That last line is the most useful one here and the least ambiguous, since it
rests on 2,439 observations rather than fifteen.

## Caveats, all of which could overturn this

**Fifteen breakouts.** The interval is 30–75%. That is compatible with the
breakout adding a lot, or with it adding nothing beyond the impulse.

**Survivorship.** Every pool is one an aggregator lists today. Bases that formed
and died are absent by construction, which biases the base and breakout groups
upward — the direction that would *favour* the accumulation thesis, and it still
did not appear.

**Overlapping windows.** Forward windows overlap by thirteen of fourteen days,
so the effective sample is 66 pools, not 2,948 periods. Every interval above is
narrower than the truth.

**Several groups were compared.** Five, on one dataset. The breakout's marginal
separation is exactly the sort of thing that survives one comparison and not a
correction for five.

## What would settle it

The V3 extraction, which samples by census rather than by current prominence and
carries no survivorship bias. It is in flight. The same three questions asked of
that sample — impulse alone, impulse plus base, breakout — with the token-level
splitting the panel already enforces, is the test this deserves.

Until then the honest summary is: **the momentum is real and large, the base is
unproven and possibly negative, and the breakout is promising on fifteen
observations.**
