# Trade simulation — entry next hour, hourly VWAP path, 4% round-trip cost

| signal | exit rule | trades | TP hit | mean | median | losing | total per $1 |
|---|---|---|---|---|---|---|---|
| surge10 + breadth6 >= 0.3 | TP 2x / SL -30% / 72h | 27 | 44% | +28% | +37% | 48% | 1.28 |
| surge10 + breadth6 >= 0.3 | TP 2x / SL -50% / 7d | 27 | 67% | +50% | +96% | 33% | 1.50 |
| surge10 + breadth6 >= 0.3 | TP 3x / SL -40% / 7d | 27 | 44% | +68% | -9% | 52% | 1.68 |
| surge10 + breadth6 >= 0.3 | hold 72h | 27 |  | +336% | +44% | 37% | 4.36 |
| surge >= 20x | TP 2x / SL -30% / 72h | 41 | 32% | +12% | -34% | 61% | 1.12 |
| surge >= 20x | TP 2x / SL -50% / 7d | 41 | 51% | +26% | +96% | 49% | 1.26 |
| surge >= 20x | TP 3x / SL -40% / 7d | 41 | 41% | +62% | -18% | 54% | 1.62 |
| surge >= 20x | hold 72h | 41 |  | +225% | +32% | 44% | 3.25 |
| model top 0.5% (walk-forward) | TP 2x / SL -30% / 72h | 18 | 61% | +48% | +96% | 33% | 1.48 |
| model top 0.5% (walk-forward) | TP 2x / SL -50% / 7d | 18 | 67% | +45% | +96% | 33% | 1.45 |
| model top 0.5% (walk-forward) | TP 3x / SL -40% / 7d | 18 | 39% | +57% | -7% | 50% | 1.57 |
| model top 0.5% (walk-forward) | hold 72h | 18 |  | +256% | +4% | 44% | 3.56 |
| model top 1% (walk-forward) | TP 2x / SL -30% / 72h | 33 | 39% | +22% | -1% | 52% | 1.22 |
| model top 1% (walk-forward) | TP 2x / SL -50% / 7d | 33 | 61% | +40% | +96% | 36% | 1.40 |
| model top 1% (walk-forward) | TP 3x / SL -40% / 7d | 33 | 39% | +62% | +19% | 48% | 1.62 |
| model top 1% (walk-forward) | hold 72h | 33 |  | +381% | +5% | 42% | 4.81 |
| model top 2% (walk-forward) | TP 2x / SL -30% / 72h | 47 | 38% | +21% | -4% | 51% | 1.21 |
| model top 2% (walk-forward) | TP 2x / SL -50% / 7d | 47 | 55% | +32% | +96% | 43% | 1.32 |
| model top 2% (walk-forward) | TP 3x / SL -40% / 7d | 47 | 38% | +54% | -20% | 53% | 1.54 |
| model top 2% (walk-forward) | hold 72h | 47 |  | +334% | +17% | 40% | 4.34 |
