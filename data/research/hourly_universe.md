# Unbiased hourly test — 323,005 live token-hours (>= $1k in 24h), 627 tokens

Base (de-duplicated events): 2x within 72h 16.0% (n=5208), within 7d 26.0%, crash-first 23.1%.

## Base rate by token age

| age | token-hours | 2x 72h | crash 7d |
|---|---|---|---|
| 24-48h | 12,803 | 30% | 42% |
| 48-168h | 52,705 | 23% | 37% |
| 168-336h | 54,912 | 16% | 29% |
| 336-720h | 88,288 | 15% | 20% |
| 720-+h | 114,297 | 10% | 16% |

## Simple rules (all ages >= 24h)

| rule | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|
| volume surge >= 10x, 6h >= $5k | 752 | 356 | 25% | 32% | 26% | 1.55x |
| volume surge >= 20x, 6h >= $5k | 490 | 284 | 26% | 33% | 28% | 1.64x |
| momentum +50% in 24h | 1901 | 513 | 27% | 38% | 39% | 1.66x |
| pullback reversal (<= 0.7 of 7d high, +20% off 72h low) + surge5 | 563 | 290 | 28% | 36% | 36% | 1.74x |
| young (48-168h) + surge10 | 131 | 124 | 34% | 37% | 33% | 2.14x |

## Walk-forward model (weekly retrain), 308,556 out-of-sample rows, base 15.2%

| selection | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|
| top 0.1% | 33 | 27 | 24% | 42% | 58% | 1.59x |
| top 0.2% | 54 | 46 | 28% | 33% | 57% | 1.83x |
| top 0.5% | 118 | 101 | 34% | 41% | 52% | 2.23x |
| top 1% | 209 | 169 | 36% | 43% | 50% | 2.39x |
| top 2% | 328 | 242 | 36% | 44% | 47% | 2.39x |
| top 5% | 755 | 430 | 30% | 39% | 47% | 1.94x |
| prob >= 0.3 | 1056 | 501 | 30% | 39% | 44% | 2.00x |
| prob >= 0.4 | 469 | 314 | 32% | 40% | 48% | 2.13x |
| prob >= 0.5 | 242 | 188 | 35% | 42% | 49% | 2.31x |
| prob >= 0.6 | 91 | 77 | 38% | 42% | 54% | 2.53x |

## Trade simulation (entry next hour's close, 4% round-trip cost)

| signal | exit rule | trades | mean | median | losing | TP hit |
|---|---|---|---|---|---|---|
| volume surge >= 10x, 6h >= $5k | TP 2x / SL -30% / 72h | 752 | +2% | -14% | 68% | 20% |
| volume surge >= 10x, 6h >= $5k | TP 2x / SL -50% / 7d | 752 | +8% | -9% | 60% | 29% |
| volume surge >= 10x, 6h >= $5k | hold 72h | 752 | +306% | -8% | 65% |  |
| volume surge >= 20x, 6h >= $5k | TP 2x / SL -30% / 72h | 490 | +1% | -17% | 70% | 20% |
| volume surge >= 20x, 6h >= $5k | TP 2x / SL -50% / 7d | 490 | +6% | -12% | 61% | 29% |
| volume surge >= 20x, 6h >= $5k | hold 72h | 490 | +516% | -10% | 66% |  |
| model top 0.5% | TP 2x / SL -30% / 72h | 118 | -5% | -35% | 73% | 24% |
| model top 0.5% | TP 2x / SL -50% / 7d | 118 | -2% | -54% | 64% | 33% |
| model top 0.5% | hold 72h | 118 | +31% | -31% | 70% |  |
| model top 1% | TP 2x / SL -30% / 72h | 209 | -2% | -35% | 71% | 25% |
| model top 1% | TP 2x / SL -50% / 7d | 209 | +3% | -54% | 59% | 36% |
| model top 1% | hold 72h | 209 | +1063% | -30% | 67% |  |
| model top 2% | TP 2x / SL -30% / 72h | 327 | +2% | -35% | 66% | 26% |
| model top 2% | TP 2x / SL -50% / 7d | 327 | +5% | -44% | 59% | 36% |
| model top 2% | hold 72h | 327 | +711% | -21% | 62% |  |
| every live token-hour (baseline) | TP 2x / SL -30% / 72h | 5205 | -0% | -9% | 68% | 14% |
| every live token-hour (baseline) | TP 2x / SL -50% / 7d | 5205 | +5% | -9% | 61% | 24% |
| every live token-hour (baseline) | hold 72h | 5205 | +81% | -7% | 65% |  |
