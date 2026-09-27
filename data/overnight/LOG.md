# Overnight log
2026-09-27T16:19:30Z plan written
2026-09-27T16:22:13Z started GT universe+candles
2026-09-27T16:23:35Z step 1 done: six-coin build finished
2026-09-27T16:42:36Z universe 5,290 pools; candles fetch started (~3h). flow backtest first pass done; rerunning with activity-matched lift
2026-09-27T16:44:08Z step 3b: registered 30 active memecoins (batch1) and started their full-history build (log data/overnight/build_batch1.log). PancakeSwap V3 Swap topic differs -> those pools skipped.
2026-09-27T16:47:00Z batch1 build restarted with a 1.5M-logs-per-segment cap (musebook ~2.7 transfers/block)
2026-09-27T17:51:38Z check-in 1: batch 7/30 built (musebook skipped heavy), candles 831/5290
2026-09-27T17:53:18Z partial candle backtest run (outcomes switched to closes); findings in PLAN.md
2026-09-27T19:21:02Z check-in 2: batch 14/30 built, candles 1785/5290
2026-09-27T19:24:34Z fixed quote pricing (by asset, not per pool): 152k of ORBIO's 202k trades had been unpriced; repriced all built tokens
2026-09-27T19:26:00Z batch2 case-control list chosen (20 cases, 20 controls); queued after batch1
