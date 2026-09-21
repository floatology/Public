# The first result that survived everything thrown at it

**Measured 2026-09-21** on the V3 extraction: 4,247 pools, 3.43M trades,
3.94M depth observations, census-sampled with no survivorship bias. The panel
gives **9,036 decision points across 673 tokens**.

Read the caveats at the bottom before quoting anything here.

## What it says

Predicting whether a token returns 10x within a fortnight **from an arbitrary
decision block**, under the strictest split available — trained on the early
decision points of one set of tokens, tested on the **later** points of
**different** tokens:

| seed | AUC | control | AUC verdict | lift | lift floor | lift verdict |
|---|---|---|---|---|---|---|
| 1 | 0.775 | 0.639 | pass | 2.41x | 2.21x | pass |
| 2 | 0.771 | 0.560 | pass | 3.14x | 1.25x | pass |
| 3 | 0.739 | 0.572 | pass | 1.74x | 1.77x | **fail** |
| 4 | 0.788 | 0.588 | pass | 3.20x | 1.57x | pass |
| 5 | 0.693 | 0.521 | pass | 2.34x | 1.21x | pass |

**AUC beats the shuffled-label control in all five, by 0.10 to 0.17.** That is
the ranking claim, and it is the robust one.

**Lift does not.** In one of five it sits below the floor, and in another it
clears it by 0.2x. Ranking well over the whole set and having an edge in the
top decile you would actually buy are different claims, and only the first
survives. The harness now reports both verdicts separately so neither can be
quoted alone.

At the pre-registered thresholds under a token-only split, the picture is
consistent: 10x gives AUC 0.803/0.811 against a 0.564 control; 5x gives
0.800/0.755 against 0.559; 2x gives 0.687/0.753 against 0.527. All three
declared thresholds point the same way, which a fluke would not.

## Three leaks found on the way here, all caught by the same tripwire

The first run returned **a confirmation-half AUC of exactly 1.000 at all three
thresholds**. No honest model scores 1.000 on held-out data, so that number was
read as an alarm rather than a result. Three separate causes:

**1. The panel's forward columns were in the feature matrix.** `forward_max_multiple`,
`forward_end_multiple` and friends describe the window being predicted. L1 picked
two of them as its largest coefficients. Fixed with a prefix rule rather than a
list, so the next forward column cannot leak silently.

**2. The label itself was a feature.** Exclusion relied on `LEAKY` happening to
contain the default label, so any run with a custom `--label` predicted the
outcome from the outcome. This is now structural — the label is excluded
whatever it is called — and has a regression test.

**3. Each split had a hole the other covered.** A token-level split holds out
unseen tokens but both halves span the same calendar, so a market-wide regime
effect passes straight through; `decision_block` was L1's second-largest
coefficient, which is what that looks like. A time split fixes the calendar and
reintroduces the tokens: the same token appears in both periods, and out-of-time
the **shuffled control reached AUC 0.873 against the real model's 0.864** —
the control correctly announcing that memorisation alone gets you there.

Only the combination has neither hole. The control under it sits at **0.536**,
near the theoretical 0.5, which is how you know the leak paths are shut.

## What is actually driving it

L1 keeps 29 of 81 features. The largest coefficients:

| coefficient | feature | reading |
|---|---|---|
| **-1.02** | `sniper_buy_count` | snipers at launch are a negative |
| +0.92 | `decision_block` | calendar — the regime confound, see above |
| -0.61 | `buy_usd_share` | |
| +0.60 | `quiet_decile_share` | quiet periods within the base |
| -0.60 | `buy_count_share` | |
| +0.52 | `peak_hour_volume_share` | |
| -0.50 | `repeat_buyer_share` | |
| +0.33 | `bundle_volume_share` | |

Gradient boosting's top feature is `usd_minus_count_share` at 0.199 — the gap
between buys' share of dollars and their share of trade count, which is the
accumulation-versus-distribution tell the catalogue lists as 3.4.

Dropping `decision_block` entirely costs little: AUC 0.782/0.793 against a 0.569
control, lift 5.47x. So the calendar is not carrying the result.

## Caveats, in order of how much they should worry you

**57 positive tokens.** 581 positive rows, but 96% of tokens have a label that
never changes across their decision points, so the effective sample is the
number of tokens carrying a positive: 57. Every interval implied above is wider
than it looks.

**Lift is not established.** Say it again, because it is the number that decides
whether any of this is tradeable and it failed once in five.

**No execution costs.** The measured floor is brutal — a $500 trade through a
$20k pool cost 96%. A 10x on paper in a pool that thin is not a 10x. The V3
depth columns exist to price this and have not yet been applied to the result.

**One chain, twelve weeks, one market regime.** Nothing here has seen a
different environment.

## What this does not say

It does not say the accumulation thesis works. `docs/13` measured the opposite
on a separate dataset: being in a base scored *worse* than the impulse alone.
This result is a multivariate model over 81 features, most of which are flow and
wallet structure rather than chart shape, and `sniper_buy_count` — a launch
quality measure, not a pattern — carries the largest coefficient.
