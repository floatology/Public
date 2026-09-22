# Where a system could actually live

Written 2026-09-22, after the selection test came back negative. This is the
strategic reading of everything measured, not another experiment.

---

## The question that has now been answered

**"Can I mechanically pick memecoins on this chain that go up?"**

On the evidence: no, and the negative is reasonably well established.

- Buying every $250k crossing loses money under **all fifteen** exit rules
  tested. Best geometric mean 0.80x, gross of costs.
- Ranking those crossings with a model that beats its control at AUC ~0.75
  does not fix it. Best selected quartile 0.907x, below the 95th percentile of
  a random quartile of the same size.
- The two chart-pattern theses — accumulation at a level, and bull flags —
  were each refuted by two independent measurements.

That is four distinct attempts at the same question, all landing in the same
place. Further variations on "predict the winner" should be expected to fail
too, and the burden is now on a reason to think otherwise.

**What went wrong is not the method. It is the question.** A population where
94.3% of tokens never reach $250k, the median trades for fifteen minutes, and
the median survivor peaks at 2.24x then ends at 0.13x, is one where the
expectation is negative before any skill is applied. Skill has to overcome that,
and AUC 0.75 over 81 features does not.

---

## Four places a system could live instead

### 1. The exit, not the entry

The single most robust asymmetry measured: **median peak 2.24x, median end
0.13x**. A quarter of tokens that cross $250k end down 99%.

That is not a prediction problem. It says: *whatever you are in, the path
usually gives you a multiple and then takes everything back.* A system that
manages exits on positions a human already holds does not need to predict
anything — it needs to notice a peak forming and act faster than a person will.

This inverts the project. Everything built — the trade archive, depth pricing,
velocity features, the wash screen — applies directly, and the hard part
(picking) is handed back to the human.

**What it needs:** the drawdown-before-peak study (untested), so a trailing rule
can be set wide enough to survive the path and tight enough to keep the gain;
and execution cost applied, since exits in thin pools are where cost bites hardest.

### 2. Filtering, not forecasting

Several measured facts are durable, cheap to compute, and largely invisible to
other participants:

- **32 of the 60 busiest pools fail a two-tell wash screen.** One traded 1,139x
  its $3,709 of reserves in a day.
- **Execution cost spans four orders of magnitude.** A $500 trade through a $20k
  pool cost 96%.
- **All 175 stock tokens are one implementation behind one deployer**, so ticker
  impersonation is trivially detectable — 24 contracts claim NVDA, one is real.
- **98.9% of tokens have exactly one pool**, so the depth you see is the depth
  there is.

None of these predicts price. All of them prevent specific, expensive mistakes.
A tool that says *do not touch this, here is why* has a defensible edge precisely
because it makes no forecast.

### 3. H1, the original hypothesis, still untested

Float lockup was the idea this project started from and it has never had a fair
test, because it needs forward data that no source carries historically. **Two
days now exist.** It is also structurally unlike everything that failed:

- Stock tokens are issuer products with a real underlying, not attention assets.
- Their pools are deep — median $1.1M on V3 against $59k for V2 memecoins.
- The mechanism is mechanical, not psychological: lockup measures how much of a
  token's float sits in memecoin-paired pools, which constrains what the float
  can do.
- The universe is 175 tokens, not 675,438, so the multiplicity problem largely
  disappears.

Everything that made the memecoin work hard — population size, survivorship,
thin liquidity, short lives — is absent here. **This is the most promising
untested idea in the project**, and the only thing it needs is time.

### 4. The data gaps that could change conclusions

- **Uniswap V4 is entirely unmeasured**: 18 of the top 60 pools, $141M daily,
  deeper than V2. Every conclusion above is drawn from V2 and V3 only.
  `scripts/discover_v4.py` is written and unrun.
- **Reserves were not archived** until late, so V2 liquidity cannot be
  reconstructed at an arbitrary decision block. Fixed for future batches.
- **The chain is twelve weeks old.** One regime, one market. Nothing here has
  seen conditions change.

---

## What I would not do

**Add features.** The model has 81 and the constraint is not information, it is
that the population's expectation is negative. A 82nd feature does not fix that.

**Lower the threshold to get more data.** The sweep showed $25k–$100k is
measurably *worse*, and more samples of a worse population is not progress.

**Tune the exit rules until one clears 1.0x.** Fifteen were tested on 167
entries. Testing fifty would find one, and it would mean nothing. If the exit
work continues it should be on the drawdown structure, which is a property of
the data, not a search over parameters.

**Trust any backtest that has not had execution cost applied.** Every number in
this project is gross. On a chain where a $500 trade can cost 96%, that is not a
rounding error — it is plausibly the whole result.

---

## The honest summary

The project has produced a lot of solid negative knowledge and one genuinely
replicated distribution. Negative knowledge is worth having: it has cost a day
rather than a funded account, and four separate approaches have been eliminated
with enough rigour that returning to them needs a new argument, not a new
parameter.

The live opportunities are the exit-management system, the filtering toolkit,
and H1. In that order of readiness, and reverse order of how interesting they
are.
