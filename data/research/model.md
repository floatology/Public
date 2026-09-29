# Model search — can all features together find 2x runs out of sample?

47,423 established-coin token-hours, 47 tokens. Gradient-boosted trees (max_depth 3, 200 iterations, min 200 samples per leaf). Test-side results only.


## split: time — train 23,690 / test 23,733 token-hours; test base (dedup events) 2x-72h 13%, n=358

| top of test by score | fires | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|---|
| top 0.5% | 118 | 10 | 8 | 60% | 80% | 0% | 4.57x |
| top 1% | 237 | 17 | 11 | 41% | 59% | 18% | 3.14x |
| top 2% | 474 | 28 | 18 | 25% | 46% | 29% | 1.90x |
| top 5% | 1186 | 40 | 23 | 32% | 48% | 28% | 2.48x |
| top 10% | 2373 | 72 | 31 | 26% | 42% | 25% | 2.01x |

Test AUC (time split): 0.703

## split: tokA — train 26,469 / test 20,954 token-hours; test base (dedup events) 2x-72h 16%, n=305

| top of test by score | fires | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|---|
| top 0.5% | 104 | 9 | 6 | 67% | 67% | 33% | 4.07x |
| top 1% | 209 | 15 | 9 | 67% | 73% | 20% | 4.07x |
| top 2% | 419 | 21 | 11 | 48% | 76% | 19% | 2.90x |
| top 5% | 1047 | 34 | 14 | 41% | 59% | 29% | 2.51x |
| top 10% | 2095 | 56 | 19 | 39% | 62% | 32% | 2.40x |

## split: tokB — train 20,954 / test 26,469 token-hours; test base (dedup events) 2x-72h 21%, n=381

| top of test by score | fires | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|---|
| top 0.5% | 132 | 11 | 8 | 55% | 73% | 27% | 2.57x |
| top 1% | 264 | 20 | 12 | 65% | 75% | 30% | 3.06x |
| top 2% | 529 | 31 | 15 | 61% | 77% | 29% | 2.88x |
| top 5% | 1323 | 62 | 21 | 50% | 60% | 26% | 2.35x |
| top 10% | 2646 | 97 | 26 | 43% | 62% | 25% | 2.04x |

## Feature importance (time split, permutation, drop in test AUC)

| feature | importance |
|---|---|
| age_h | 0.1054 |
| heat_d | 0.0221 |
| dd_7d | 0.0130 |
| active_24h | 0.0112 |
| up_from_low72 | 0.0105 |
| r_72 | 0.0072 |
| breadth_24h | 0.0026 |
| bundle_6h | 0.0023 |
| newb_surge | 0.0023 |
| breadth_6h | 0.0017 |
| pro_n_6h | 0.0006 |
| r_24 | 0.0006 |
