# Where things stand — plain language

Written for reading cold, without scrolling back through anything.

## The short version

The system can now measure about **77 things about a token** from the chain
itself, plus another dozen from public web sources, and it can measure them
across many tokens at once. Roughly half of those were added after you pointed
out that testing two signals — launch liquidity and float lockup — was a badly
narrow reading of what you asked for. You were right; they were two of the
least interesting things on the list.

**Nothing has been proven to predict anything yet.** The measurement machinery
is built and tested. The test that decides whether any of it is real has not run
on enough data, and it is deliberately built to come back "no" if the answer is
no.

## What got built, and why each one matters

**Wallet forensics across tokens.** The thing you actually asked for. It tracks
what every wallet did across every token it touched, and scores it. Two things
make it non-trivial:

- It only ever uses what was knowable *at the time*. If a wallet bought a token
  in January that mooned in March, the system will not credit that wallet in
  February. This sounds obvious and is the single most common way this kind of
  analysis fools itself — the published project nearest to this one deleted a
  whole tier of its system after discovering it had done exactly that. There is
  a test that builds the trap deliberately and checks the code falls for it: it
  does not.
- It scores hits against *activity*. A wallet that buys 500 tokens will hold
  some winners by luck. Three wins from eight buys beats five from nine hundred.

**Coordination clustering.** Nine early buyers might be nine people or one
person with nine wallets. This works out which, by finding wallets that keep
turning up in the same obscure tokens in the same blocks — far more often than
chance allows. Every "how many buyers" number in the system was quietly assuming
one address is one person; now it can check.

**Bot detection, two kinds.** Bundle bots buy across many wallets in a single
block to grab supply while looking like a crowd. Bump bots trade tiny amounts
forever to keep a token visible on trending boards. The second one matters more
than it sounds: in the one published model over a similar feature set, the
presence of a bump bot was the *strongest single predictor of anything* — ahead
of every measure of trader skill. Manipulation is not just noise to filter out.

**Time shape.** Two tokens with identical total volume are completely different
animals depending on whether that volume arrived in ninety seconds or over a
week. Eleven columns measure that shape, including whether the crowd flipped
from buying to selling partway through.

**Wash-trading tells.** The daily activity snapshot immediately turned up pools
trading **400 and 1,128 times their entire liquidity in a day**. No real order
flow does that in a pool that thin. Capturing this daily matters because the
evidence only exists while it is happening.

## The biggest thing found since

**The whole extraction was looking at the wrong third of the chain.**

It was reading Uniswap V2 pools only. Checked against the census and a day of
live trading:

| | pools | share of daily volume | typical pool size |
|---|---|---|---|
| **V3** | 447,343 | $521M (74%) | $1,102,528 |
| **V2** | 268,151 | $182M (26%) | $58,990 |

V2 is the shallow end. It is also, by earlier measurement, the part where a $500
trade can cost 96% to execute — so anything found there would have been
untradable no matter how strong the signal looked. Worse, that failure would
have arrived disguised: the results would have passed every statistical check
and then quietly failed the tradability filter, looking like bad luck rather
than a design error.

V3 reading is now built and tested, and a V3 extraction is queued behind the
running one. Both are kept separate rather than merged, because a test done
earlier showed the two behave as genuinely different populations and mixing them
would let a model learn "which kind of pool is this" instead of anything about
the token.

**V3 needed a different way to measure depth, and the one it got is better.**
V2 pools publish their reserves. V3 pools do not — liquidity sits in ranges
rather than a single pot. But every V3 trade record carries the pool's live
liquidity and price, which gives the cost of moving the price 1% directly, at
the moment of each trade. That tracks liquidity being pulled or moved out of the
way, which a reserve snapshot does not. It only answers small moves honestly,
and the code says so.

**And there is a fourth venue nobody has looked at.** Uniswap V4 is the single
most common venue among the 60 busiest pools — 18 of them, $141M a day, and
typically deeper than V2. It is invisible to all of the above, because a V4
"pool" is not a contract at all but an entry inside one big shared contract, so
none of the existing machinery can address it. A tool to find it has been
written and is waiting for the connection to be free. This is recorded as a gap,
not as something solved.

## Two things measured that changed the plan

**98.9% of tokens have exactly one pool.** The chain has 272 different factories
creating pools, which made it look like a token's liquidity would be scattered
and any single-pool measurement misleading. Checked across 644,581 tokens: it
isn't. Almost every token lives in one pool. The fragmentation worry applies to
about one token in ninety — worth flagging when it happens, not worth redesigning
around.

**An hour is too long a window for this chain.** Most tokens here do not live an
hour, so "volume in the first hour" came back as 100% for three out of four
tokens sampled and measured nothing at all. Replaced with windows scaled to each
token's own lifespan, which separate them cleanly.

## One mistake worth recording

The first full extraction read every trade off the chain, computed its numbers,
and **threw the trades away**. That made every new idea look like it cost another
ninety minutes of a heavily rate-limited connection, which is a strong incentive
to stop having ideas. It also made the cross-token wallet work impossible, since
a wallet's record is by definition spread across pools.

Trades are now saved. New measurements cost seconds instead of an hour and a
half, and the whole wallet layer became possible. This should have been true from
the first run.

## One more thing, about the stock tokens

All 175 of them are the same contract. Every one is a proxy pointing at a single
shared implementation, deployed by a single address, with an identical set of
functions. Two of those functions are `mint` and `pause`, and ownership is not
given up on any of them.

That is not a scandal — a tokenised share has to be mintable against new
deposits and haltable on a corporate action, or redemption cannot work. It does
mean that holding these is holding the issuer as well as the stock. And it means
the contract-safety checks, which are useful on memecoins, tell you nothing here:
they come back identical for all 175, which is easy to mistake for a clean bill
of health rather than a measurement that could not vary.

The useful side effect is that impersonation is trivially detectable. There are
24 contracts on this chain claiming to be NVDA. Exactly one comes from that
deployer.

## What happens next, in order

1. A full extraction is running: 10,000 pools, about ninety minutes, saving every
   trade this time.
2. Then the wallet ledger and clustering run on it — offline, minutes.
3. Then the honest test. The model gets half the data to find patterns in and is
   scored on the other half, which it has never seen. Alongside it, the identical
   procedure runs on **deliberately scrambled data**. Whatever score the scrambled
   version gets is what this method produces from pure noise, and the real model
   has to beat it by a clear margin to count.

That last step is the whole point, and it is built to be able to say no.

## Honest caveat

Five separate results in this project have looked like findings and turned out to
be artefacts. In the worst case the result replicated *and* passed an independent
check and was still wrong. The working rule now is that any striking result is
assumed to be a measurement error until something unrelated agrees with it. That
is why there is a scrambled-data control, a leak test, and a diagnostics pass that
runs before any model does.
