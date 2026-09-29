# Step 1 — what is known about what precedes a 2x+ run (literature scan, 29 Sep 2026)

Short scan of research and practitioner writing on small-cap / memecoin / new
DEX token runs. What matters here is which claims are testable on our data.

## Claims, and how each becomes a test

| # | Claim | Source | Test on our data |
|---|---|---|---|
| H1 | A small group of "smart" wallets captures most memecoin profit; their entries lead price. But they also sell before followers can react. | Nansen, Bitget Wallet guides; Pump.fun call-channel study | Cross-token: wallets that bought early into *earlier* runners (known at time t, no lookahead) buying a new token now. Measure hit rate of "N smart wallets entered in last X hours". |
| H2 | Activity leads attention: new-wallet growth, rising transaction counts and liquidity growth show up before social mentions. | DEXTools, Bitget "how to find the next memecoin" | Per token-hour: unique buyers, first-time wallets, trade count, vs their own trailing baseline. |
| H3 | Breakouts come on expanding volume (100-200% above average); volume confirms, it does not lead. | altFINS, OSL, trading guides | Already seen: BREAK = 1.84x lift, 1.41x crash. Re-test at hourly resolution. |
| H4 | Seller exhaustion: lower-volume dips / volume dry-up and higher lows precede reversals. | practitioner TA | Our daily test found ~1.0x alone. Re-test hourly and combined with flow. |
| H5 | 82.8% of >100% return memecoins show artificial growth: wash trading and liquidity-pool-based price inflation (small strategic buys into thin pools). High-risk launches: few holders, few but large buys, concentrated early supply. | arXiv 2507.01963 "A Midsummer Meme's Dream"; MemeTrans (arXiv 2602.13480) | Engineered runs may have a signature *before* the run: coordinated fresh wallets (same funder, same block, repeat sizes) accumulating, thin liquidity. If the run is engineered, the pre-run accumulation is the thing to detect. |
| H6 | Recurring automated buyers enter ~100 s before public calls and sell 73% of the time. | Pump.fun call-channel study (770 calls, 2.4M trades) | Bot-signature wallets entering a token as a lead indicator; and a warning that the first leg is often sold into. |
| H7 | In small, illiquid coins, short-horizon returns mean-revert; distance from the 1-week high predicts *negatively*. Momentum works only in large/liquid coins. | Fičura & Colak (SSRN 4378429); crypto factor papers | Split every result by liquidity/market cap; expect chasing highs in thin coins to fail. |
| H8 | Most launches lose money for normal buyers (82% high-risk; ~1% of Pump.fun launches graduate). | MemeTrans; Solana memecoin study (arXiv 2512.11850) | Base rates will be harsh; a "high hit rate" signal has to beat a low base, not just a live-coin base. |

## What this implies for the search

1. The most promising *new* lever is **who** is buying (H1, H5, H6), not the
   price shape. Price/volume shapes were already tested (docs/25) and gave
   1.4-1.8x at best with extra crash risk.
2. Two kinds of "who" are worth separating: (a) wallets with a track record of
   early entries into previous runners; (b) coordinated groups (same funder,
   same block, fresh wallets) — the signature of an engineered run.
3. Hourly resolution matters: memecoin runs start and fade within hours to a
   few days, so daily bars blur the lead-up.
4. Expect the edge, if any, to live in thin/small coins, and expect
   first-leg selling by the same smart wallets (plan exits, not just entries).

Sources:
- [Inside the Economics of Pump.fun Call Channels](https://moneyleavesclues.substack.com/p/inside-the-economics-of-pumpfun-call)
- [A Midsummer Meme's Dream: Market Manipulations in the Meme Coin Ecosystem (arXiv 2507.01963)](https://arxiv.org/abs/2507.01963)
- [MemeTrans: Detecting High-Risk Memecoin Launches on Solana (arXiv 2602.13480)](https://www.arxiv.org/pdf/2602.13480)
- [The Memecoin Phenomenon: Solana's Blockchain Trends (arXiv 2512.11850)](https://arxiv.org/pdf/2512.11850)
- [Impact of Size and Volume on Cryptocurrency Momentum and Reversal (SSRN 4378429)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4378429)
- [Price manipulation schemes of new crypto-tokens in DEXs (arXiv 2502.10512)](https://arxiv.org/pdf/2502.10512)
- [DEXTools: How to spot a good memecoin before it pumps](https://www.dextools.io/tutorials/how-to-spot-a-good-memecoin-before-it-pumps)
- [Bitget: How to find the next memecoin before it pumps](https://www.bitget.com/news/detail/12560605833617)
- [Nansen: memecoin wallets to track](https://nansen.ai/post/top-10-memecoin-wallets-to-track-for-2025)
- [altFINS: crypto volume tracker](https://altfins.com/knowledge-base/crypto-volume-tracker-spot-unusual-volume/)
