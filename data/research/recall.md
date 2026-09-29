# Coverage — which patterns flagged the big runs in time

A leg is caught if the pattern fires between 24h before and 12h after the trough while price is still <= half the leg's peak.

| pattern | all legs | 2-5x legs | 5-10x legs | 10x+ legs |
|---|---|---|---|---|
| quiet wake-up (prev48 < $2k, 6h >= $5k) | 3/179 (2%) | 0/118 (0%) | 1/30 (3%) | 2/31 (6%) |
| volume surge >= 5x | 23/179 (13%) | 7/118 (6%) | 7/30 (23%) | 9/31 (29%) |
| volume surge >= 10x | 17/179 (9%) | 5/118 (4%) | 6/30 (20%) | 6/31 (19%) |
| volume surge >= 10x + breadth6 >= 0.3 | 7/179 (4%) | 1/118 (1%) | 3/30 (10%) | 3/31 (10%) |
| new-wallet surge >= 5x | 24/179 (13%) | 6/118 (5%) | 8/30 (27%) | 10/31 (32%) |
| pullback reversal (<= 0.7 of 7d high, +20% off low) | 135/179 (75%) | 81/118 (69%) | 27/30 (90%) | 27/31 (87%) |
| momentum +50% in 24h | 50/179 (28%) | 18/118 (15%) | 15/30 (50%) | 17/31 (55%) |
| breadth24 >= 0.3 | 14/179 (8%) | 4/118 (3%) | 4/30 (13%) | 6/31 (19%) |
| smart wallets >= 3 | 134/179 (75%) | 91/118 (77%) | 24/30 (80%) | 19/31 (61%) |
| any of: wake-up, surge10, new-wallet surge5 | 24/179 (13%) | 6/118 (5%) | 8/30 (27%) | 10/31 (32%) |
