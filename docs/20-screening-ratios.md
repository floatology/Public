# Screening a $100k–$400k coin: what the ratios say

**Measured 2026-09-22** on 330–344 V3 census tokens whose market cap first
entered $100,000–$400,000, with every ratio computed from trades **up to that
moment only** and the outcome measured over the following 14 days. Right-censored
entries excluded.

---

## The one that matters

**Depth ÷ market cap ≥ 0.25.** Everything else in this document is secondary.

| depth / market cap | n | survived (≥0.5x after 14d) | 95% CI | median end |
|---|---:|---:|---|---:|
| 0.10 – 0.25 | 237 | **3.8%** | 2.0–7.1% | 0.04x |
| 0.25 – 0.50 | 59 | 64.4% | 51.7–75.4% | 0.95x |
| above 0.50 | 31 | **87.1%** | 71.1–94.9% | 1.57x |

Pooled: **3.8% against 72.2%**, intervals nowhere near touching. This is the
largest clean effect measured anywhere in the project.

### What the ratio actually is

Not a liquidity ratio in the usual sense. The algebra collapses:

```
depth ≈ quote reserve Q          (V3 active liquidity x 200)
cap   = price x supply = (Q/B) x S
depth/cap = Q / ((Q/B) x S) = B / S
```

**It is the fraction of total supply sitting in the pool.** A token at 0.18 has
82% of its supply held somewhere outside the pool — an overhang that can be sold
into it. A token at 0.5 has half its supply already in the liquidity and far less
available to dump.

That is the float-lockup mechanism, which is the hypothesis this whole project
started from, appearing in memecoins rather than in stock tokens.

### Three checks it survived

**Not direction of entry.** 327 of 330 tokens entered the band rising, so there
is no falling cohort to confound it. Within the rising group the split is 5.5%
against 73.0%.

**Not dormancy.** The obvious objection is that a token nobody trades holds its
price by default. The opposite is true — high-ratio tokens trade **seven times
more dollar volume** in the forward window:

| depth/cap | median forward trades | median forward volume | median peak |
|---|---:|---:|---:|
| below 0.25 | 654 | $30,870 | 1.51x |
| 0.25 and above | 515 | **$229,433** | **2.19x** |

**Not a threshold artefact.** The effect is monotone across three bins, not a
cliff at one cut point.

---

## The other two ratios, which are weaker

### Turnover = 24h volume ÷ market cap

Typical range in this band: **p25 0.18, median 0.25, p75 0.52.** So a normal
$100k–$400k coin turns over roughly a fifth to a half of its cap per day.

| turnover | n | ran 2x | survived |
|---|---:|---:|---:|
| below 0.1 | 19 | 73.7% | 42.1% |
| 0.1 – 0.3 | 186 | 29.0% | **9.1%** |
| 0.3 – 1 | 91 | 48.4% | 39.6% |
| 1 – 3 | 45 | 40.0% | 40.0% |

Non-monotone, and the best bin has 19 tokens. **Do not screen on this alone.**
What it does say: the crowded middle — turnover 0.1 to 0.3, which is where the
majority sit — has the worst survival of any bin. Being unremarkable is the bad
outcome.

### 24h volume ÷ depth

Typical range: **p25 0.92, median 1.14, p75 2.26.** A healthy pool in this band
trades roughly its own depth once a day.

Survival is flat at 21–25% across the middle bins, so this does not discriminate
on its own. **Its use is as a veto, not a ranking.** The wash screen found 32 of
the 60 busiest pools on the chain turning over many multiples of their depth
daily — one at 1,139x its $3,709 of reserves. Nothing in the $100k–$400k band
should be anywhere near that.

---

## Practical screen

**Require:**
- **Depth ÷ market cap ≥ 0.25.** The single strongest filter available. Below
  0.1–0.25 the survival rate is 3.8%.
- **Depth ≥ $25k in absolute terms.** In this band the ratio implies it anyway,
  and it is separately necessary: a $500 trade through a $20k pool cost 96%.

**Red flags:**
- **Depth ÷ market cap below 0.25**, and especially in 0.10–0.25, where 96% of
  tokens fail to hold half their value over a fortnight.
- **Volume ÷ depth above roughly 10.** Not because it predicts failure here, but
  because it is the wash signature and the number cannot be trusted.
- **Turnover 0.1–0.3 with nothing else notable.** The crowded middle, 9.1%
  survival.

**Ignore:**
- Turnover as a ranking signal. Non-monotone, and the best bin is nineteen tokens.

---

## What this does not claim

**It is a survival filter, not a return engine.** The ≥0.25 group has a median
peak of 2.19x and a median end of 0.95x — it roughly holds its value. That is a
vastly better base to trade from than a 96% failure rate, and it is not by itself
a profitable system. Everything measured in `docs/18` still applies: no exit rule
tested compounds above 1.0x across all entries, and the numbers here are gross of
execution cost.

**One chain, twelve weeks, V3 only.** V2 has no archived reserves so the ratio
cannot be computed there, and V4 is unmeasured entirely.

**Depth is V3 active liquidity x200**, a constant-product-equivalent reserve. It
is the right order of magnitude and is not the "liquidity" figure an aggregator
displays, so a screen run against DexScreener numbers should be recalibrated
rather than assumed to transfer.
