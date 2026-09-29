# Ablation and selection check (walk-forward, hourly ledger panel)

batch-2 cases in panel: 19, controls: 13

| features | tokens | base 2x72 | top 0.5% | top 1% | top 2% |
|---|---|---|---|---|---|
| all | all tokens | 18% (n=634) | 61% / 83% / 33%c (n=18) | 52% / 73% / 30%c (n=33) | 47% / 64% / 36%c (n=47) |
| all | controls only | 9% (n=172) | 33% / 50% / 33%c (n=12) | 38% / 54% / 31%c (n=13) | 35% / 47% / 41%c (n=17) |
| all | cases only | 19% (n=366) | 64% / 82% / 36%c (n=11) | 58% / 84% / 26%c (n=19) | 48% / 63% / 33%c (n=27) |
| price/volume | all tokens | 18% (n=634) | 56% / 72% / 39%c (n=18) | 52% / 72% / 38%c (n=29) | 51% / 67% / 27%c (n=45) |
| price/volume | controls only | 9% (n=172) | 43% / 43% / 43%c (n=7) | 30% / 40% / 40%c (n=10) | 46% / 54% / 23%c (n=13) |
| price/volume | cases only | 19% (n=366) | 50% / 71% / 43%c (n=14) | 56% / 72% / 39%c (n=18) | 43% / 57% / 32%c (n=28) |
| flow only | all tokens | 18% (n=634) | 53% / 63% / 32%c (n=19) | 50% / 68% / 32%c (n=34) | 37% / 55% / 39%c (n=49) |
| flow only | controls only | 9% (n=172) | 60% / 60% / 20%c (n=5) | 45% / 64% / 9%c (n=11) | 35% / 53% / 29%c (n=17) |
| flow only | cases only | 19% (n=366) | 50% / 67% / 33%c (n=12) | 53% / 74% / 42%c (n=19) | 41% / 63% / 37%c (n=27) |
| no age | all tokens | 18% (n=634) | 47% / 68% / 42%c (n=19) | 44% / 59% / 37%c (n=27) | 47% / 62% / 34%c (n=58) |
| no age | controls only | 9% (n=172) | 38% / 50% / 38%c (n=8) | 29% / 43% / 29%c (n=14) | 47% / 59% / 29%c (n=17) |
| no age | cases only | 19% (n=366) | 50% / 75% / 38%c (n=8) | 47% / 60% / 40%c (n=15) | 38% / 53% / 41%c (n=34) |

Cells: 2x within 72h / 2x within 7d / crash-first within 7d (events).
