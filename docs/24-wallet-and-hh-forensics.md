# 24 — WALLET and HH: the story behind the charts

Full-history forensics from `data/tokens/<token>/ledger.parquet`. Raw section
output is in `data/tokens/<token>/analysis.txt`, produced by
`scripts/ledger_analysis.py`. USD figures use a single ETH price ($2,691) and are
approximate across time; ratios computed in ETH are exact.

## WALLET — an open launch, a crowd top, and a whale-led collapse

**Launch (10 Jul).** All 1B tokens went into the pool in the mint block, with
nothing held back. Sniping was immediate — four addresses bought exactly
20,000,000 tokens each within two blocks — but every one of the first hour's top
15 buyers had sold out within hours for $300–$7k. Only `0xb336…` converted a
launch position into real money ($2.9k in, $150.6k out). No launch-era insider
still holds supply.

**Distribution.** 8,996 holders; the largest private holder has 3.04%, top 10
hold 15.5%. It is one of the flattest distributions on the chain. The largest
holder built its entire position after the crash, through a hot contract that
forwarded to a cold address.

**Who made money.** 61% of 31,751 traders are up on realised plus open-at-today.
Profit is widely spread: the top 10 took only 10% of realised profit. The loss
sits with the late crowd: the cohorts that first bought from 4 Sep onward, about
10,000 wallets arriving near the top, are down $1.66M combined, while the
first-week cohort of 12,453 is up $18.5M on paper.

**The 17 Sep collapse.** Price rose from $0.047 to $0.090 in three hours, then
fell 96% at the wick. The sequence, all measured:

1. 07:40 — `0x02f5…` pulled 16.48 ETH of bid-side liquidity from a wide range
   below the price. It had pulled 1M tokens twice on 15–16 Sep, and over its life
   it has sent 2.9% of supply to the market. It holds nothing now.
2. 14:00–17:30 — in-range liquidity fell a third, from ~104k to ~69k.
3. 17:00 — `0xa600…` pulled 9.14 ETH from just below the price. It is the week's
   top one-directional seller (15 sells, no buys, holds nothing).
4. 17:34 onward — July-era whales (`0x5364…`, `0x5173…`, `0xc7a0…`, `0x5a7a…`)
   sold in $30–95k chunks within minutes of one another, into the thinned book.
   21,475 trades in 90 minutes; 2,728 addresses bought below $0.015, turning over
   39.7% of supply.

In the six hours before, no one exited in size: the largest pre-crash seller moved
0.06% of supply. So this was not a rug. The pattern is a blow-off top, bid
liquidity withdrawn by two persistent distributors, and a whale cascade into the
resulting hole. The printed low of $0.0034 was one $216 trade in an empty tick.

**Bots.** Strictly mechanical traders (repeat sizes, metronomic timing,
same-block flips) are 499 wallets and 8.4% of volume. A broader set of swing
traders round-trip heavily; that is active trading, not automation. Custodial
intermediaries account for another 6.3%, including one contract that settles
trades and pays out to 3,648 addresses.

**Now.** Whales are net sellers over 7 days (−$85k) and retail too (−$45k). The
buyers are the same whales who led the crash — `0x5364…`, `0xc7a0…`, `0x1988…` —
re-accumulating 40–80% below where they sold. `0x5173…`, the largest profit-taker
on the token ($328k), is still distributing.

## HH — a protocol token, not a whale coin

**Launch (27–28 Aug).** The deployer minted 21M and seeded the pool with 10,500
tokens (0.05%). On 28 Aug at 03:00 it sold 17.9% of supply for $6.7k into that
near-empty pool and added 72% as liquidity. That reset the price to ~$0.0004, a
market cap near $8k. It also sent 10% to an EOA, `0xd2f8…`, which has never moved
a token ($108k today).

**Mechanics that look like players but are not:**

| Address | What it is | Evidence |
|---|---|---|
| token contract | **5% buy and sell tax**, auto-sold | 21.7% of supply collected in fees; 207 sells, $29.6k |
| `0xf9ab…` 28.3% | staking or lock contract | deposits from ~70 addresses since 7 Sep; 10 withdrawals |
| `0x00a7…` | verified `GameLock` contract | identical 0.51% payouts to 19 holders |
| `0x9e60…` 4.7% | distributor contract | passed 19.5% from one source to 19 holders |
| `0x1b37…` | deployer-funded contract, likely a buyback | 329 identical-size buys since 22 Sep, zero sells |

Top 10 hold 63.5% on paper, but staking, treasury and distributor contracts make
up 43% of that.

**Early winners.** `0xf24d…` bought 17% of supply for $6.2k on 31 Aug, staked
about half, took $15.7k out and still sits on ~$159k. The 28 Aug buyers at
$0.00034–0.00037 are up 13,000–15,000%. They arrived 30–80 minutes after the
reset, which is not sniper timing.

**Campaign waves.** On 12, 13, 15, 17 and 21 Sep, 250–516 new wallets appeared
within one or two hours each time, with a median first buy of $11–14 and varied
sizes. That pattern points to people responding to a trigger (a promotion, quest
or game event) rather than to a bot farm. Those cohorts churned: of the 1,201
wallets that first bought in the week of 10 Sep, 6% still hold.

**Bots.** 3.2% of volume is mechanical. Real volume is small: $2.01M two-way over
a month, and $1.3k today.

**Now.** Price is down 50% from the 21 Sep high of $0.103. August buyers are
taking profit (`0x773d…`, `0x36f9…`, `0xf268…`). The buyback contract and two
new whales who entered at $0.068–0.079 are absorbing, and those two whales are
25–34% underwater. Volume is drying up.

## What this data cannot see

- The trigger behind HH's waves, which happens off-chain.
- ETH funding links between wallets: the ETH transfer graph was not scanned, so
  cluster detection covers token transfers only.
- Bid-side liquidity on WALLET outside the crash window. The V3 Mint/Burn scan
  covered 14–17 Sep only.
- WALLET's V4 pool (~4% of liquidity). HH's V4 pool holds $37.
- What `0xf9ab…` and `0x9e60…` are for certain; both are unverified contracts,
  identified from behaviour.
