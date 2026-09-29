*Interim trial on the first 12 fetched tokens — superseded when the full fetch completes.*

# Unbiased hourly test — 23,564 live token-hours (>= $1k in 24h), 12 tokens

Base (de-duplicated events): 2x within 72h 16.6% (n=337), within 7d 30.6%, crash-first 18.1%.

## Base rate by token age

| age | token-hours | 2x 72h | crash 7d |
|---|---|---|---|
| 24-48h | 265 | 66% | 29% |
| 48-168h | 1,320 | 61% | 22% |
| 168-336h | 2,013 | 32% | 45% |
| 336-720h | 4,608 | 11% | 39% |
| 720-+h | 15,358 | 10% | 11% |

## Simple rules (all ages >= 24h)

| rule | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|
| volume surge >= 10x, 6h >= $5k | 37 | 12 | 51% | 59% | 14% | 3.09x |
| volume surge >= 20x, 6h >= $5k | 20 | 9 | 45% | 60% | 45% | 2.71x |
| momentum +50% in 24h | 125 | 11 | 30% | 43% | 30% | 1.78x |
| pullback reversal (<= 0.7 of 7d high, +20% off 72h low) + surge5 | 32 | 11 | 41% | 56% | 25% | 2.44x |
| young (48-168h) + surge10 | 9 | 9 | 78% | 89% | 44% | 4.68x |

## Walk-forward model (weekly retrain), 18,232 out-of-sample rows, base 11.0%

| selection | events | tokens | 2x 72h | 2x 7d | crash 7d | lift |
|---|---|---|---|---|---|---|
| top 0.1% | 4 | 3 | 50% | 50% | 0% | 4.55x |
| top 0.2% | 7 | 4 | 43% | 57% | 14% | 3.90x |
| top 0.5% | 10 | 6 | 30% | 40% | 20% | 2.73x |
| top 1% | 13 | 7 | 23% | 38% | 15% | 2.10x |
| top 2% | 29 | 11 | 17% | 34% | 14% | 1.57x |
| top 5% | 54 | 11 | 20% | 39% | 17% | 1.85x |
| prob >= 0.3 | 78 | 12 | 18% | 32% | 17% | 1.63x |
| prob >= 0.4 | 50 | 11 | 22% | 40% | 18% | 2.00x |
| prob >= 0.5 | 29 | 11 | 17% | 34% | 14% | 1.57x |
| prob >= 0.6 | 17 | 9 | 24% | 35% | 6% | 2.14x |
