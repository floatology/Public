# Daily universe model — 20,186 live token-days (>= $1k), 1418 tokens

Outcome: a close >= 2x within 3 days (2x 3d) / 7 days; crash = <= 0.5x first.

## Base rate by token age (days since first candle)

| age | token-days | 2x 3d | 2x 7d | crash 7d |
|---|---|---|---|---|
| 1-3d | 2,096 | 15.9% | 22.5% | 31.5% |
| 3-7d | 2,649 | 14.3% | 21.1% | 32.6% |
| 7-14d | 3,436 | 8.6% | 15.9% | 26.2% |
| 14-30d | 5,014 | 8.4% | 17.0% | 15.0% |
| 30-60d | 5,744 | 7.3% | 15.0% | 12.3% |
| 60-+d | 1,247 | 1.8% | 4.3% | 9.0% |

## split time: train 9,763 / test 10,423; test AUC 0.677; test base (dedup) 2x 3d 7.5% (n=2392)

| top of test | fires | events | tokens | 2x 3d | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|---|
| top 0.5% | 52 | 36 | 36 | 14% | 19% | 50% | 1.86x |
| top 1% | 104 | 69 | 69 | 14% | 20% | 57% | 1.94x |
| top 2% | 208 | 133 | 131 | 21% | 25% | 53% | 2.81x |
| top 5% | 521 | 302 | 280 | 16% | 22% | 43% | 2.17x |
| top 10% | 1042 | 530 | 464 | 15% | 20% | 36% | 2.02x |

Permutation importance (time split): lmcap 0.047, up7 0.042, r7 0.041, r3 0.028, lvol 0.027, r1 0.015, npools 0.014, dd30 0.004

## split tokA: train 9,904 / test 10,282; test AUC 0.739; test base (dedup) 2x 3d 9.3% (n=2087)

| top of test | fires | events | tokens | 2x 3d | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|---|
| top 0.5% | 51 | 13 | 11 | 54% | 100% | 8% | 5.79x |
| top 1% | 102 | 46 | 41 | 41% | 70% | 20% | 4.44x |
| top 2% | 205 | 106 | 93 | 35% | 55% | 31% | 3.76x |
| top 5% | 514 | 247 | 199 | 28% | 40% | 40% | 3.01x |
| top 10% | 1028 | 417 | 293 | 26% | 39% | 36% | 2.76x |

## split tokB: train 10,282 / test 9,904; test AUC 0.718; test base (dedup) 2x 3d 9.6% (n=2015)

| top of test | fires | events | tokens | 2x 3d | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|---|
| top 0.5% | 49 | 19 | 16 | 63% | 79% | 16% | 6.56x |
| top 1% | 99 | 45 | 37 | 51% | 62% | 20% | 5.31x |
| top 2% | 198 | 98 | 80 | 38% | 51% | 36% | 3.92x |
| top 5% | 495 | 219 | 170 | 27% | 40% | 36% | 2.80x |
| top 10% | 990 | 390 | 268 | 25% | 35% | 37% | 2.56x |
