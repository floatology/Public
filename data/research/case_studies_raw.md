# Case studies — raw digests (scripts/research_cases.py)

Blocks are 12h windows relative to the trough hour; 'px vs trough' is the average hourly VWAP in the block over the trough VWAP. 'Earlier 2x legs caught early' counts other legs (any token) whose 2x was confirmed before this trough where the wallet net-bought within 24h before to 6h after that leg's trough.

## Agrippa — 380.22x in 128h, trough 09-20 02:00 (token age 58h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -60..-48h | 0.45 | 92,649 | 51% | 477 | 433 | 46,355 | 0 |
| -48..-36h | 0.43 | 292 | 9% | 9 | 2 | 24 | 0 |
| -36..-24h | 1.73 | 489,145 | 51% | 2079 | 1294 | 162,470 | 10,161 |
| -24..-12h | 1.59 | 20,495 | 43% | 196 | 43 | 2,438 | 0 |
| -12..+0h | 1.48 | 42,402 | 46% | 217 | 76 | 13,557 | 1,302 |
| +0..+12h | 1.70 | 19,620 | 68% | 105 | 47 | 9,996 | 3,415 |
| +12..+24h | 2.37 | 26,830 | 56% | 78 | 12 | 7,298 | 7,672 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0x0004…c111 | 3,381 | 3 | 1h after trough | 12 | 8 | $437 |
| 0xf86a…7004 | 1,979 | 9 | +31h before trough | 7 | 4 | $11,033 |
| 0x3fdb…9000 | 1,632 | 10 | +31h before trough | 2 | 0 | $0 |
| 0x1f43…b2d3 | 1,547 | 15 | +30h before trough | 0 | 0 | $54,669 |
| 0x9848…79b4 | 1,505 | 18 | +31h before trough | 4 | 2 | $0 |
| 0xf240…2989 | 1,440 | 14 | +31h before trough | 9 | 5 | $1,155 |
| 0x080c…9c68 | 1,197 | 9 | +31h before trough | 1 | 1 | $0 |
| 0xde18…fc6c | 1,184 | 20 | +31h before trough | 5 | 2 | $0 |

First-time buyers in the 72h before: 1848; sharing a block with another first-timer: 390; same-size (rounded $) as 2+ others: 1637.

## TYGR — 216.84x in 83h, trough 07-23 15:00 (token age 70h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 1.24 | 168,446 | 51% | 526 | 436 | 66,405 | 1,351 |
| -60..-48h | 0.92 | 13,061 | 57% | 46 | 32 | 5,226 | 0 |
| -48..-36h | 1.68 | 63,106 | 51% | 152 | 96 | 20,766 | 0 |
| -36..-24h | 1.75 | 21,040 | 49% | 68 | 35 | 5,808 | 0 |
| -24..-12h | 1.01 | 5,556 | 44% | 20 | 12 | 1,230 | 0 |
| -12..+0h | 1.41 | 54,137 | 51% | 140 | 77 | 14,948 | 0 |
| +0..+12h | 21.33 | 1,118,626 | 52% | 2203 | 1672 | 421,398 | 153,816 |
| +12..+24h | 29.55 | 300,115 | 50% | 504 | 243 | 73,070 | 60,481 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0x3db1…2b63 | 5,157 | 5 | 4h after trough | 0 | 0 | $9,691 |
| 0xa11a…f215 | 4,983 | 5 | 6h after trough | 4 | 0 | $773 |
| 0x9ce0…f614 | 4,357 | 2 | 4h after trough | 2 | 0 | $6,977 |
| 0x07a0…da03 | 4,014 | 3 | 4h after trough | 4 | 0 | $5,902 |
| 0xcde4…416a | 4,014 | 3 | 4h after trough | 2 | 0 | $5,921 |
| 0x0cc7…9a7b | 3,630 | 1 | 5h after trough | 5 | 0 | $0 |
| 0x3515…18c2 | 3,315 | 7 | 4h after trough | 8 | 0 | $5,725 |
| 0x06de…f2d1 | 3,252 | 1 | 4h after trough | 5 | 0 | $0 |

First-time buyers in the 72h before: 688; sharing a block with another first-timer: 140; same-size (rounded $) as 2+ others: 530.

## JUGGERNAUT — 148.77x in 112h, trough 07-05 19:00 (token age 355h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 1.77 | 157,016 | 46% | 179 | 54 | 25,165 | 32,774 |
| -60..-48h | 1.82 | 57,338 | 50% | 61 | 18 | 10,120 | 13,606 |
| -48..-36h | 1.75 | 55,245 | 56% | 70 | 17 | 10,164 | 10,370 |
| -36..-24h | 2.20 | 56,292 | 51% | 68 | 22 | 9,753 | 9,241 |
| -24..-12h | 1.86 | 20,882 | 37% | 17 | 2 | 846 | 1,351 |
| -12..+0h | 1.22 | 56,104 | 46% | 62 | 10 | 4,756 | 6,103 |
| +0..+12h | 1.54 | 50,046 | 59% | 54 | 12 | 5,605 | 17,955 |
| +12..+24h | 1.90 | 61,670 | 54% | 60 | 16 | 6,094 | 17,574 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0x452d…b6dd | 4,606 | 4 | +74h before trough | 0 | 0 | $173,506 |
| 0x4f0c…1995 | 4,080 | 2 | +72h before trough | 3 | 0 | $13,819 |
| 0x2822…5a5b | 2,974 | 3 | +64h before trough | 2 | 0 | $23,077 |
| 0x25af…1534 | 2,729 | 1 | +98h before trough | 0 | 0 | $0 |
| 0x7739…f6ae | 2,702 | 1 | +65h before trough | 0 | 0 | $24,132 |
| 0x6d8a…dabc | 2,702 | 2 | +79h before trough | 1 | 0 | $280,710 |
| 0x5638…9192 | 2,702 | 2 | +95h before trough | 14 | 0 | $92,175 |
| 0x5e8e…31e8 | 2,667 | 4 | +54h before trough | 0 | 0 | $4,846 |

First-time buyers in the 72h before: 123; sharing a block with another first-timer: 2; same-size (rounded $) as 2+ others: 43.

## POOH — 126.34x in 168h, trough 07-18 05:00 (token age 52h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -60..-48h | 1.34 | 31,977 | 53% | 207 | 185 | 15,308 | 0 |
| -48..-36h | 1.59 | 26,357 | 53% | 106 | 74 | 10,386 | 2,647 |
| -36..-24h | 1.54 | 10,947 | 47% | 58 | 30 | 2,641 | 0 |
| -24..-12h | 1.27 | 2,094 | 44% | 15 | 3 | 322 | 0 |
| -12..+0h | 1.13 | 1,933 | 36% | 14 | 2 | 51 | 0 |
| +0..+12h | 1.08 | 1,910 | 60% | 16 | 7 | 569 | 0 |
| +12..+24h | 1.09 | 938 | 52% | 7 | 2 | 172 | 0 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0x3e32…7a3b | 470 | 9 | +51h before trough | 1 | 1 | $3,886 |
| 0x6cc9…9a8c | 413 | 12 | +51h before trough | 0 | 1 | $0 |
| 0x9b09…7f4d | 339 | 10 | +51h before trough | 0 | 1 | $0 |
| 0x2838…712a | 313 | 3 | +39h before trough | 1 | 0 | $0 |
| 0x1b5d…e7f1 | 255 | 4 | +44h before trough | 1 | 0 | $0 |
| 0xad59…3d2a | 244 | 2 | +20h before trough | 0 | 0 | $2,149 |
| 0x904a…31e2 | 205 | 2 | +51h before trough | 1 | 1 | $0 |
| 0x0c2b…0b6a | 161 | 25 | +39h before trough | 0 | 0 | $0 |

First-time buyers in the 72h before: 294; sharing a block with another first-timer: 35; same-size (rounded $) as 2+ others: 219.

## WOJAK — 65.15x in 81h, trough 07-08 11:00 (token age 457h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 0.36 | 0 | 0% | 0 | 0 | 0 | 0 |
| -60..-48h | 0.36 | 0 | 0% | 0 | 0 | 0 | 0 |
| -48..-36h | 0.36 | 0 | 0% | 0 | 0 | 0 | 0 |
| -36..-24h | 0.36 | 0 | 0% | 0 | 0 | 0 | 0 |
| -24..-12h | 0.36 | 0 | 0% | 0 | 0 | 0 | 0 |
| -12..+0h | 1.12 | 40,218 | 53% | 124 | 114 | 19,235 | 0 |
| +0..+12h | 1.54 | 39,591 | 52% | 134 | 102 | 16,467 | 0 |
| +12..+24h | 1.90 | 18,695 | 55% | 48 | 35 | 8,709 | 0 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0xc965…9641 | 643 | 9 | +6h before trough | 7 | 0 | $10,129 |
| 0x1ee8…32b6 | 540 | 1 | +6h before trough | 0 | 0 | $2,326 |
| 0x11b6…81aa | 489 | 12 | +6h before trough | 5 | 0 | $6,684 |
| 0x343a…6429 | 405 | 2 | 3h after trough | 6 | 0 | $7,698 |
| 0xece2…97b1 | 405 | 1 | 2h after trough | 4 | 0 | $384 |
| 0x8360…41c0 | 327 | 1 | +4h before trough | 1 | 0 | $451 |
| 0xb0b8…3168 | 273 | 1 | +6h before trough | 1 | 0 | $386 |
| 0x72ab…6a57 | 270 | 2 | +7h before trough | 0 | 0 | $6,338 |

First-time buyers in the 72h before: 114; sharing a block with another first-timer: 27; same-size (rounded $) as 2+ others: 82.

## HOOKR — 55.49x in 342h, trough 08-17 03:00 (token age 263h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 1.99 | 120,921 | 46% | 103 | 11 | 9,490 | 22,483 |
| -60..-48h | 1.77 | 235,227 | 48% | 170 | 38 | 9,447 | 52,624 |
| -48..-36h | 1.52 | 134,760 | 52% | 178 | 59 | 17,519 | 30,330 |
| -36..-24h | 1.39 | 176,414 | 47% | 164 | 21 | 12,127 | 36,155 |
| -24..-12h | 1.22 | 61,585 | 44% | 68 | 7 | 1,660 | 10,462 |
| -12..+0h | 1.20 | 50,828 | 51% | 74 | 14 | 6,383 | 6,864 |
| +0..+12h | 1.09 | 102,261 | 50% | 135 | 28 | 4,938 | 20,787 |
| +12..+24h | 1.26 | 105,066 | 53% | 99 | 24 | 10,214 | 26,648 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0x60a7…7e70 | 7,783 | 9 | +115h before trough | 1 | 0 | $104,022 |
| 0xd9c2…cc28 | 7,047 | 15 | +246h before trough | 0 | 1 | $132,467 |
| 0x8737…de81 | 6,364 | 6 | +195h before trough | 1 | 1 | $27,297 |
| 0xed6d…e3cd | 5,790 | 22 | +104h before trough | 3 | 1 | $1,957 |
| 0x5e72…ecfa | 5,604 | 46 | +250h before trough | 3 | 2 | $23,583 |
| 0xac8b…fb72 | 5,315 | 4 | +27h before trough | 1 | 0 | $6,794 |
| 0x9993…714e | 4,633 | 4 | +11h before trough | 0 | 0 | $8,753 |
| 0x908f…af22 | 4,093 | 1 | +63h before trough | 1 | 0 | $10,128 |

First-time buyers in the 72h before: 150; sharing a block with another first-timer: 4; same-size (rounded $) as 2+ others: 65.

## HMM — 47.33x in 185h, trough 08-05 05:00 (token age 406h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 1.00 | 79,004 | 37% | 133 | 37 | 3,230 | 4,978 |
| -60..-48h | 0.84 | 199,705 | 56% | 239 | 51 | 26,684 | 54,074 |
| -48..-36h | 1.46 | 240,318 | 54% | 262 | 111 | 39,343 | 66,616 |
| -36..-24h | 1.69 | 207,966 | 49% | 246 | 81 | 38,490 | 45,274 |
| -24..-12h | 1.62 | 129,445 | 44% | 162 | 41 | 12,928 | 20,139 |
| -12..+0h | 1.25 | 225,214 | 48% | 284 | 53 | 14,871 | 45,339 |
| +0..+12h | 1.17 | 163,265 | 55% | 191 | 42 | 19,334 | 37,897 |
| +12..+24h | 1.16 | 161,437 | 53% | 182 | 31 | 11,061 | 45,009 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0xdcbf…7d15 | 45,686 | 17 | +51h before trough | 1 | 0 | $108,184 |
| 0xa8e6…d4b4 | 11,987 | 16 | +198h before trough | 1 | 1 | $20,096 |
| 0x0d11…1ba4 | 6,515 | 6 | +26h before trough | 0 | 0 | $0 |
| 0xb541…d980 | 6,288 | 10 | +34h before trough | 1 | 0 | $0 |
| 0x4a50…939b | 6,085 | 6 | +344h before trough | 4 | 2 | $69,919 |
| 0xdae1…c5e5 | 4,778 | 9 | +50h before trough | 4 | 0 | $3,745 |
| 0x267e…21c8 | 4,560 | 12 | +107h before trough | 4 | 1 | $5,895 |
| 0x0000…031c | 4,171 | 17 | +401h before trough | 51 | 6 | $17,092 |

First-time buyers in the 72h before: 374; sharing a block with another first-timer: 0; same-size (rounded $) as 2+ others: 226.

## CPU — 42.21x in 53h, trough 09-15 15:00 (token age 112h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 1.04 | 0 | 0% | 0 | 0 | 0 | 0 |
| -60..-48h | 1.03 | 12 | 0% | 1 | 0 | 0 | 0 |
| -48..-36h | 1.03 | 0 | 0% | 0 | 0 | 0 | 0 |
| -36..-24h | 1.03 | 0 | 0% | 0 | 0 | 0 | 0 |
| -24..-12h | 1.04 | 764 | 24% | 6 | 0 | 0 | 0 |
| -12..+0h | 1.02 | 11 | 0% | 1 | 0 | 0 | 0 |
| +0..+12h | 1.00 | 0 | 0% | 1 | 0 | 0 | 0 |
| +12..+24h | 1.00 | 0 | 0% | 0 | 0 | 0 | 0 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0xb349…8b6a | 182 | 3 | +79h before trough | 3 | 0 | $5,574 |
| 0x665c…37f4 | -0 | 3 | +112h before trough | 0 | 0 | $0 |
| 0x15dc…ebde | -11 | 3 | +102h before trough | 10 | 0 | $0 |
| 0x342a…f67e | -12 | 3 | +112h before trough | 1 | 0 | $2,522 |
| 0x802e…d651 | -113 | 3 | +112h before trough | 7 | 2 | $1 |
| 0x5f64…6ba9 | -114 | 3 | +112h before trough | 7 | 2 | $1 |
| 0x1cdd…f9d9 | -114 | 3 | +112h before trough | 13 | 2 | $7,130 |
| 0x8fee…29df | -116 | 3 | +112h before trough | 15 | 2 | $2,360 |

First-time buyers in the 72h before: 0; sharing a block with another first-timer: 0; same-size (rounded $) as 2+ others: 0.

## GIWA — 28.71x in 26h, trough 08-07 01:00 (token age 257h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 1.43 | 130 | 90% | 6 | 1 | 5 | 0 |
| -60..-48h | 1.30 | 521 | 3% | 5 | 3 | 3 | 0 |
| -48..-36h | 1.24 | 433 | 40% | 4 | 2 | 138 | 0 |
| -36..-24h | 1.15 | 638 | 23% | 8 | 3 | 59 | 0 |
| -24..-12h | 1.07 | 212 | 62% | 5 | 0 | 0 | 0 |
| -12..+0h | 1.03 | 291 | 5% | 1 | 0 | 0 | 0 |
| +0..+12h | 1.17 | 14,678 | 74% | 79 | 61 | 8,293 | 0 |
| +12..+24h | 10.77 | 146,517 | 56% | 305 | 195 | 55,075 | 10,521 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0x65f5…ef4d | 135 | 1 | +40h before trough | 3 | 1 | $556 |
| 0x218a…d77b | 34 | 1 | +26h before trough | 0 | 0 | $0 |
| 0xf3d7…97e0 | 27 | 1 | +230h before trough | 4 | 0 | $240 |
| 0x7fa5…13ea | 12 | 1 | +34h before trough | 0 | 0 | $0 |
| 0x5e77…342c | 5 | 1 | +66h before trough | 2 | 0 | $19 |
| 0xe335…45b7 | 5 | 3 | +246h before trough | 5 | 0 | $0 |
| 0x2490…952d | 4 | 1 | +142h before trough | 2 | 0 | $0 |
| 0xcbb8…ae00 | 3 | 2 | +208h before trough | 1 | 0 | $414 |

First-time buyers in the 72h before: 9; sharing a block with another first-timer: 0; same-size (rounded $) as 2+ others: 0.

## POOLS — 28.0x in 22h, trough 08-04 23:00 (token age 127h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 0.35 | 6,803 | 28% | 13 | 4 | 657 | 0 |
| -60..-48h | 0.37 | 18,203 | 61% | 65 | 45 | 8,016 | 0 |
| -48..-36h | 0.48 | 52,330 | 56% | 138 | 103 | 22,475 | 1,324 |
| -36..-24h | 0.61 | 91,640 | 51% | 153 | 81 | 29,236 | 18,578 |
| -24..-12h | 0.73 | 20,163 | 48% | 68 | 36 | 4,537 | 0 |
| -12..+0h | 1.05 | 977,836 | 50% | 2139 | 1774 | 390,882 | 149,720 |
| +0..+12h | 1.82 | 1,290,804 | 53% | 2196 | 1725 | 520,872 | 283,574 |
| +12..+24h | 12.14 | 15,061,678 | 50% | 19447 | 9439 | 3,011,418 | 3,627,531 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0x0ee2…e76e | 7,260 | 5 | +6h before trough | 6 | 0 | $0 |
| 0x00b1…a1e8 | 3,925 | 3 | +6h before trough | 1 | 0 | $7,615 |
| 0x5cd5…529f | 3,892 | 4 | +6h before trough | 1 | 2 | $18,000 |
| 0x6c81…18d5 | 3,744 | 7 | +2h before trough | 2 | 0 | $20,208 |
| 0x211c…0b4d | 3,359 | 9 | +5h before trough | 0 | 0 | $19,160 |
| 0xf885…70d5 | 2,993 | 1 | +6h before trough | 0 | 0 | $0 |
| 0x44ef…3263 | 2,899 | 3 | +6h before trough | 2 | 0 | $14,251 |
| 0x7a98…c158 | 2,558 | 5 | +6h before trough | 2 | 0 | $0 |

First-time buyers in the 72h before: 2042; sharing a block with another first-timer: 575; same-size (rounded $) as 2+ others: 1756.

## TAMPONS — 20.84x in 26h, trough 07-20 16:00 (token age 139h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 0.87 | 15,048 | 55% | 49 | 26 | 4,569 | 0 |
| -60..-48h | 1.07 | 4,288 | 21% | 11 | 4 | 399 | 0 |
| -48..-36h | 1.14 | 53,669 | 54% | 150 | 85 | 17,624 | 1,231 |
| -36..-24h | 1.52 | 25,200 | 47% | 68 | 36 | 5,790 | 2,431 |
| -24..-12h | 1.59 | 30,335 | 54% | 78 | 23 | 4,352 | 0 |
| -12..+0h | 1.28 | 15,099 | 44% | 35 | 8 | 665 | 0 |
| +0..+12h | 1.47 | 77,476 | 52% | 158 | 72 | 15,210 | 3,767 |
| +12..+24h | 4.18 | 223,359 | 51% | 371 | 213 | 67,379 | 32,326 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0x9cff…250e | 1,351 | 1 | +126h before trough | 3 | 2 | $8,559 |
| 0xe96e…9bb1 | 1,199 | 5 | +38h before trough | 2 | 2 | $15,094 |
| 0xfb2d…8e15 | 848 | 4 | +21h before trough | 2 | 1 | $1,380 |
| 0x7a9b…a514 | 695 | 4 | +38h before trough | 2 | 1 | $0 |
| 0x828e…e481 | 664 | 3 | +63h before trough | 8 | 1 | $3,852 |
| 0x098d…904e | 629 | 10 | +131h before trough | 6 | 1 | $4,293 |
| 0xc0eb…a5ef | 629 | 4 | +118h before trough | 3 | 1 | $4,197 |
| 0x249a…9ce8 | 598 | 2 | +38h before trough | 0 | 1 | $0 |

First-time buyers in the 72h before: 182; sharing a block with another first-timer: 25; same-size (rounded $) as 2+ others: 97.

## HOODRAT — 18.79x in 160h, trough 07-23 22:00 (token age 508h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 4.02 | 520,102 | 49% | 676 | 138 | 54,874 | 97,247 |
| -60..-48h | 3.32 | 578,567 | 49% | 714 | 132 | 40,578 | 112,181 |
| -48..-36h | 2.24 | 388,099 | 50% | 567 | 100 | 26,434 | 60,790 |
| -36..-24h | 2.14 | 311,515 | 47% | 435 | 93 | 21,898 | 51,422 |
| -24..-12h | 1.61 | 211,182 | 48% | 354 | 49 | 4,227 | 22,410 |
| -12..+0h | 1.22 | 234,151 | 47% | 422 | 61 | 10,027 | 28,716 |
| +0..+12h | 1.82 | 306,924 | 55% | 424 | 117 | 67,013 | 63,743 |
| +12..+24h | 1.93 | 171,631 | 49% | 313 | 82 | 24,262 | 35,231 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0xc5b3…269f | 38,632 | 23 | +326h before trough | 4 | 1 | $57,711 |
| 0x1cc4…a11e | 11,288 | 5 | +64h before trough | 4 | 0 | $26,212 |
| 0xa239…79eb | 8,888 | 25 | +162h before trough | 8 | 1 | $2,171 |
| 0xd7d5…d298 | 8,773 | 9 | +356h before trough | 4 | 3 | $54,519 |
| 0xd06f…b5d3 | 7,769 | 16 | +207h before trough | 2 | 1 | $56,498 |
| 0x35d4…dad6 | 7,569 | 6 | +384h before trough | 1 | 1 | $42,877 |
| 0xcc21…114d | 7,228 | 4 | +375h before trough | 2 | 2 | $301 |
| 0xd361…dded | 7,181 | 22 | +193h before trough | 5 | 1 | $12,466 |

First-time buyers in the 72h before: 573; sharing a block with another first-timer: 4; same-size (rounded $) as 2+ others: 347.

## WOOF — 17.91x in 137h, trough 08-02 02:00 (token age 123h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 1.18 | 133,866 | 52% | 266 | 93 | 18,362 | 8,178 |
| -60..-48h | 0.93 | 94,124 | 49% | 322 | 36 | 7,473 | 2,702 |
| -48..-36h | 0.86 | 163,920 | 49% | 825 | 24 | 4,648 | 1,092 |
| -36..-24h | 0.82 | 27,166 | 50% | 353 | 15 | 4,938 | 1,236 |
| -24..-12h | 1.07 | 170,978 | 55% | 889 | 113 | 36,049 | 20,373 |
| -12..+0h | 1.75 | 876,092 | 50% | 2063 | 359 | 110,395 | 74,084 |
| +0..+12h | 1.79 | 681,304 | 52% | 1423 | 564 | 145,092 | 91,730 |
| +12..+24h | 4.92 | 1,321,532 | 51% | 2217 | 692 | 224,304 | 263,835 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0xd647…bc6b | 9,455 | 6 | +15h before trough | 3 | 2 | $8,168 |
| 0x0146…6558 | 8,134 | 3 | 5h after trough | 6 | 0 | $3,104 |
| 0x05bc…0e91 | 6,378 | 11 | +7h before trough | 0 | 0 | $8,412 |
| 0x6c51…a2ee | 6,079 | 3 | 3h after trough | 0 | 0 | $14,954 |
| 0x93d8…742b | 5,900 | 11 | +6h before trough | 1 | 0 | $0 |
| 0x2daa…63bb | 4,728 | 5 | +6h before trough | 2 | 1 | $27,291 |
| 0x0132…ad82 | 4,616 | 2 | +1h before trough | 3 | 1 | $1,672 |
| 0xaaa5…b13c | 4,366 | 7 | +11h before trough | 10 | 0 | $26,611 |

First-time buyers in the 72h before: 639; sharing a block with another first-timer: 4; same-size (rounded $) as 2+ others: 429.

## KITSU — 17.53x in 151h, trough 06-25 12:00 (token age 261h)

| block | px vs trough | vol $ | buy % | buyers | new buyers | new-buyer $ | $1k+ buys |
|---|---|---|---|---|---|---|---|
| -72..-60h | 1.91 | 2,979 | 13% | 5 | 2 | 274 | 0 |
| -60..-48h | 1.80 | 6,673 | 40% | 11 | 6 | 1,275 | 0 |
| -48..-36h | 1.70 | 4,414 | 53% | 3 | 1 | 1,910 | 1,364 |
| -36..-24h | 1.46 | 1,331 | 0% | 0 | 0 | 0 | 0 |
| -24..-12h | 1.06 | 2,204 | 0% | 0 | 0 | 0 | 0 |
| -12..+0h | 1.01 | 70 | 100% | 2 | 1 | 46 | 0 |
| +0..+12h | 1.06 | 1,094 | 80% | 4 | 2 | 191 | 0 |
| +12..+24h | 1.10 | 0 | 0% | 0 | 0 | 0 | 0 |

Top net buyers, 72h before to 6h after the trough:

| wallet | net $ | trades | first seen in token | other tokens traded | earlier 2x legs caught early | sold into this leg's peak? |
|---|---|---|---|---|---|---|
| 0xe8f7…50bb | 1,910 | 2 | +46h before trough | 0 | 0 | $0 |
| 0x31ac…08af | 409 | 1 | +214h before trough | 2 | 0 | $4,842 |
| 0x7224…4ded | 273 | 1 | +157h before trough | 1 | 2 | $7,526 |
| 0x668d…5d8d | 135 | 4 | +65h before trough | 2 | 0 | $922 |
| 0x86f7…0454 | 109 | 2 | +130h before trough | 1 | 0 | $204 |
| 0xe123…f923 | 70 | 2 | +2h before trough | 0 | 0 | $762 |
| 0x71f2…969b | 55 | 2 | +173h before trough | 0 | 0 | $0 |
| 0x26aa…0cca | 16 | 2 | +56h before trough | 0 | 0 | $0 |

First-time buyers in the 72h before: 10; sharing a block with another first-timer: 0; same-size (rounded $) as 2+ others: 0.
