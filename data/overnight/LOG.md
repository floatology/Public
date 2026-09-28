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
2026-09-27T20:51:07Z check-in 3: batch1 24/30 (OPENAIx1L skipped heavy), candles 2864/5290 (liquid done, census-only ~half)
2026-09-27T22:23:08Z check-in 4: full survivor-corrected candle backtest done; docs/25 drafted; live shortlist = Odin, ai17z
2026-09-28T00:11:17Z batch1 finished; repricing
2026-09-28T00:12:09Z batch2 registered; building
2026-09-28T00:24:17Z check-in 5: add of batch2 had crashed on 'U' (DexScreener 400); fixed, registered 35 of 40 (4 controls now have no pairs = dead; INTC stock skipped; LUTE on undecodable DEX); batch2 build started
2026-09-28T00:24:17Z batch2 build starting: BAG CLOCKIN FLOPS FRIDAY Froggy GME HMM HOODRAT HOOKR INJOH JUGGERNAUT KITSU MANCER MOONCOW NASDANQ PEEPS PEPE POOH POOLS PORK RHPS SNOW TA TAMPONS TUX TYGR U WELOVECATS WEN WOJAK WOOF YOLO wire worth
2026-09-28T01:19:07Z candles complete (5,290); final candle backtest 39,771 token-days / 1,235 tokens: BREAK 1.84x (splits 1.68-2.04x), SETUP 1.41x (1.22-1.63x); docs/25 updated. NOTE: waiter loops using pgrep -f self-match their own bash; the earlier waiter never fired.
2026-09-28T05:06:28Z keep-alive: run_batch2 found dead (last progress FRIDAY 04:34Z); restarted
2026-09-28T05:06:28Z batch2 build starting: BAG CLOCKIN FLOPS FRIDAY Froggy GME HMM HOODRAT HOOKR INJOH JUGGERNAUT KITSU MANCER MOONCOW NASDANQ PEEPS PEPE POOH POOLS PORK RHPS SNOW TA TAMPONS TUX TYGR U WELOVECATS WEN WOJAK WOOF YOLO wire worth
2026-09-28T05:12:50Z run_batch2 found dead again (container restart); restarted
2026-09-28T05:12:50Z batch2 build starting: BAG CLOCKIN FLOPS FRIDAY Froggy GME HMM HOODRAT HOOKR INJOH JUGGERNAUT KITSU MANCER MOONCOW NASDANQ PEEPS PEPE POOH POOLS PORK RHPS SNOW TA TAMPONS TUX TYGR U WELOVECATS WEN WOJAK WOOF YOLO wire worth
2026-09-28T06:06:50Z keep-alive: run_batch2 dead (last progress HOOKR 05:20Z, container restart); restarted
2026-09-28T06:06:50Z batch2 build starting: BAG CLOCKIN FLOPS FRIDAY Froggy GME HMM HOODRAT HOOKR INJOH JUGGERNAUT KITSU MANCER MOONCOW NASDANQ PEEPS PEPE POOH POOLS PORK RHPS SNOW TA TAMPONS TUX TYGR U WELOVECATS WEN WOJAK WOOF YOLO wire worth
