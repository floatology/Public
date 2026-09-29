# Unbiased hourly test — 426,962 live token-hours (>= $1k in 24h), 870 tokens

Base (de-duplicated events): 2x within 72h 15.9% (n=6919), within 7d 25.7%, crash-first 22.9%.

## Base rate by token age

| age | token-hours | 2x 72h | crash 7d |
|---|---|---|---|
| 24-48h | 17,918 | 30% | 42% |
| 48-168h | 72,619 | 23% | 35% |
| 168-336h | 74,003 | 15% | 30% |
| 336-720h | 117,976 | 15% | 19% |
| 720-+h | 144,446 | 10% | 15% |

## Simple rules (all ages >= 24h)

| rule | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|
| volume surge >= 10x, 6h >= $5k | 1015 | 487 | 24% | 32% | 26% | 1.50x |
| volume surge >= 20x, 6h >= $5k | 645 | 380 | 26% | 33% | 26% | 1.63x |
| momentum +50% in 24h | 2533 | 704 | 27% | 39% | 39% | 1.69x |
| pullback reversal (<= 0.7 of 7d high, +20% off 72h low) + surge5 | 735 | 389 | 29% | 37% | 36% | 1.80x |
| young (48-168h) + surge10 | 183 | 174 | 30% | 36% | 32% | 1.89x |

## Walk-forward model (weekly retrain), 410,629 out-of-sample rows, base 15.1%

| selection | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|
| top 0.1% | 23 | 18 | 26% | 35% | 61% | 1.73x |
| top 0.2% | 67 | 55 | 30% | 37% | 55% | 1.98x |
| top 0.5% | 162 | 134 | 35% | 41% | 56% | 2.29x |
| top 1% | 249 | 202 | 32% | 39% | 53% | 2.10x |
| top 2% | 445 | 325 | 32% | 41% | 49% | 2.14x |
| top 5% | 1046 | 604 | 30% | 39% | 47% | 1.99x |
| prob >= 0.3 | 1477 | 693 | 29% | 38% | 44% | 1.92x |
| prob >= 0.4 | 670 | 452 | 32% | 41% | 47% | 2.09x |
| prob >= 0.5 | 290 | 229 | 34% | 41% | 53% | 2.24x |
| prob >= 0.6 | 127 | 101 | 35% | 42% | 54% | 2.29x |

## Trade simulation (entry next hour's close, 4% round-trip cost)

| signal | exit rule | trades | mean | mean w/o top 1% | median | losing | TP hit |
|---|---|---|---|---|---|---|---|
| volume surge >= 10x, 6h >= $5k | TP 2x / SL -30% / 72h | 1014 | +1% | +0% | -15% | 69% | 19% |
| volume surge >= 10x, 6h >= $5k | TP 2x / SL -50% / 7d | 1014 | +7% | +7% | -9% | 61% | 29% |
| volume surge >= 10x, 6h >= $5k | hold 72h | 1014 | +235% | +23% | -9% | 67% |  |
| volume surge >= 20x, 6h >= $5k | TP 2x / SL -30% / 72h | 645 | +1% | +1% | -16% | 69% | 20% |
| volume surge >= 20x, 6h >= $5k | TP 2x / SL -50% / 7d | 645 | +8% | +7% | -11% | 61% | 30% |
| volume surge >= 20x, 6h >= $5k | hold 72h | 645 | +404% | +37% | -10% | 67% |  |
| model top 0.5% | TP 2x / SL -30% / 72h | 162 | -6% | -6% | -36% | 74% | 24% |
| model top 0.5% | TP 2x / SL -50% / 7d | 162 | -5% | -5% | -55% | 67% | 32% |
| model top 0.5% | hold 72h | 162 | +38% | +18% | -35% | 69% |  |
| model top 1% | TP 2x / SL -30% / 72h | 249 | -5% | -6% | -36% | 74% | 23% |
| model top 1% | TP 2x / SL -50% / 7d | 249 | -2% | -3% | -54% | 65% | 33% |
| model top 1% | hold 72h | 249 | +879% | +24% | -35% | 72% |  |
| model top 2% | TP 2x / SL -30% / 72h | 445 | -6% | -6% | -35% | 73% | 22% |
| model top 2% | TP 2x / SL -50% / 7d | 445 | -1% | -2% | -47% | 63% | 32% |
| model top 2% | hold 72h | 445 | +790% | +76% | -26% | 67% |  |
| every live token-hour (baseline) | TP 2x / SL -30% / 72h | 6916 | -0% | -1% | -10% | 68% | 13% |
| every live token-hour (baseline) | TP 2x / SL -50% / 7d | 6916 | +5% | +4% | -8% | 61% | 24% |
| every live token-hour (baseline) | hold 72h | 6916 | +82% | +7% | -7% | 65% |  |
