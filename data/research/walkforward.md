# Walk-forward test — retrain weekly on the past, score the next week only


## hourly ledger panel (65 tokens, 2x within 72h): 43,923 out-of-sample rows, base (dedup) 2x 17.5% (n=634)

| selection | events | tokens | weeks with events | 2x (72h) | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|---|
| top 0.2% | 8 | 7 | 3 | 50% | 88% | 50% | 2.86x |
| top 0.5% | 18 | 13 | 7 | 61% | 83% | 33% | 3.49x |
| top 1% | 33 | 19 | 7 | 52% | 73% | 30% | 2.94x |
| top 2% | 47 | 24 | 8 | 47% | 64% | 36% | 2.67x |
| top 5% | 93 | 35 | 10 | 44% | 58% | 35% | 2.52x |
| prob >= 0.3 | 237 | 45 | 10 | 31% | 43% | 28% | 1.78x |
| prob >= 0.4 | 169 | 43 | 10 | 33% | 48% | 28% | 1.86x |
| prob >= 0.5 | 118 | 37 | 10 | 34% | 51% | 31% | 1.94x |
| prob >= 0.6 | 76 | 32 | 10 | 47% | 61% | 26% | 2.71x |

## daily universe (4,029 tokens, 2x within 3 days): 18,167 out-of-sample rows, base (dedup) 2x 8.7% (n=3757)

| selection | events | tokens | weeks with events | 2x (3d) | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|---|
| top 0.2% | 25 | 24 | 6 | 32% | 36% | 52% | 3.69x |
| top 0.5% | 63 | 59 | 9 | 21% | 35% | 49% | 2.38x |
| top 1% | 114 | 103 | 9 | 22% | 34% | 51% | 2.53x |
| top 2% | 223 | 196 | 9 | 20% | 29% | 47% | 2.27x |
| top 5% | 485 | 403 | 9 | 22% | 30% | 41% | 2.50x |
| prob >= 0.3 | 137 | 122 | 9 | 21% | 32% | 47% | 2.44x |
| prob >= 0.4 | 29 | 28 | 6 | 28% | 34% | 55% | 3.18x |
| prob >= 0.5 | 2 | 2 | 1 | 50% | 50% | 0% | 5.76x |
| prob >= 0.6 | 0 | | | | | | |
