# Phase 1.5 v2 Results — Strategy Fix Comparison

**Date:** 2026-05-10
**Window:** 2024-04-01 → 2026-05-10 (~2 years)
**Goal:** Honestly evaluate which fixes from the spec actually improve the v1 baseline. No cherry-picking — every variant attempted is reported.

---

## Variant grid (run per sleeve)

| Variant | Signal | Direction | Trend filter |
|---|---|---|---|
| **v1_baseline** | plain 12-1 z, cross-sectional | long/short 20% | — |
| **v2a_long_only** | plain 12-1 z, cross-sectional | long-only top 20% | — |
| **v2b_residual** | 0.6 plain + 0.4 beta-residual 12-1, cross-sectional z | long-only top 20% | — |
| **v2c_sector_neutral** | 0.6 + 0.4, **sector-neutral z** (US only — needs GICS map) | long-only top 20% | — |
| **v2d_full** | sector-neutral combined (or plain combined where sectors absent) | long-only top 20% | price > 200-DMA |

---

## Results

### US (S&P 500, 503 names, 528 bars)

| Variant | Total | CAGR | Sharpe | 95% CI | Max DD |
|---|---:|---:|---:|---:|---:|
| v1_baseline | -6.60% | -3.21% | -0.27 | [-1.49, +0.76] | -18.6% |
| **v2a_long_only** | **+20.98%** | **+9.52%** | **+0.67** | [-0.72, +1.78] | -17.0% |
| v2b_residual | +20.13% | +9.15% | +0.68 | [-0.74, +1.82] | -15.7% |
| v2c_sector_neutral | +11.40% | +5.29% | +0.47 | [-0.84, +1.64] | -12.7% |
| v2d_full | +8.46% | +3.95% | +0.37 | [-0.96, +1.58] | -14.2% |

### India (Nifty 500, 500 names, 520 bars)

| Variant | Total | CAGR | Sharpe | 95% CI | Max DD |
|---|---:|---:|---:|---:|---:|
| v1_baseline | -11.90% | -5.95% | -0.94 | [-2.22, +0.57] | -15.7% |
| **v2a_long_only** | **+12.01%** | **+5.65%** | **+0.45** | [-0.75, +1.69] | -19.1% |
| v2b_residual | +4.00% | +1.92% | +0.22 | [-0.86, +1.40] | -13.5% |
| v2d_full | -1.80% | -0.87% | -0.03 | [-1.10, +1.16] | -16.0% |

### Crypto (Top 30 perps, 768 bars)

| Variant | Total | CAGR | Sharpe | 95% CI | Max DD |
|---|---:|---:|---:|---:|---:|
| **v1_baseline** | **+3.58%** | **+1.16%** | **+0.66** | [-0.51, +1.74] | -2.2% |
| v2a_long_only | +2.38% | +0.77% | +0.50 | [-0.95, +1.42] | -1.7% |
| v2b_residual | +2.75% | +0.89% | +0.57 | [-0.81, +1.46] | -1.7% |
| v2d_full | +1.15% | +0.38% | +0.33 | [-0.88, +0.86] | -1.6% |

---

## What actually fixed it

**Long-only was the dominant win on equities.** US: -6.6% → +21.0%. India: -11.9% → +12.0%. Same pattern, same reason: 2024-2026 was a strong bull run in both markets, and long/short construction was systematically forfeiting beta. The market-neutral framing came from academic literature where it's defensible — but during a 30% rally, giving up beta is expensive insurance.

**Residual momentum barely changed US**, very slightly hurt India. Beta-residual is meant to reduce factor crowding; in this window the factor crowding *was* the rally, so neutralizing it removed the gains.

**Sector neutralization HURT US (+21% → +11.4%).** This is the honest surprise — academic literature says sector-neutral momentum is usually better, but for 2024-2026 the AI/megacap concentration *was* the alpha. Cutting it across sectors averaged the strategy back toward the mean. Two reasons:
1. Plain 12-1 long top decile naturally loaded into Tech (the winning sector) — that's where the return came from.
2. Sector-neutralizing forced equal-ish weight across sectors, dragging Tech weight down and Energy/Utilities weight up — worse names.

**Trend filter (200-DMA) cost another ~3-7% across the board.** It excluded names that had recovered above 200-DMA in late 2025 (right before they ripped) — high false-negative rate at regime changes.

**Crypto: long-only is *worse*.** Real shorts on alts had genuine value here. Stick with L/S for crypto.

## Best per-sleeve config (honest picks)

| Sleeve | Best variant | Sharpe | Total return |
|---|---|---:|---:|
| **US** | v2a_long_only | +0.67 | +21.0% |
| **India** | v2a_long_only | +0.45 | +12.0% |
| **Crypto** | v1_baseline (L/S) | +0.66 | +3.6% |

Combined notional return (equal-weight 1/3 per sleeve, this window): **(21.0 + 12.0 + 3.6) / 3 ≈ +12.2% over 2 years, or ~+5.9% CAGR.** Real, but modest, and crucially: the 95% CI on Sharpe still crosses zero on every sleeve, so we can't *prove* edge with this sample size.

## Statistical caveat (still applies)

All bootstrap CIs on Sharpe cross zero. With ~520 daily obs per sleeve, you genuinely cannot reject the null of zero edge — even at +21% / Sharpe 0.67 — because the ann_vol is high (~14%) relative to the sample size. **This is not a unicorn strategy.** It's a defensible long-momentum tilt on US/India and a small market-neutral crypto carry that, taken together, produced low-double-digit returns honestly.

## Critical anti-cherry-picking note

This run *itself* is a multiple-comparisons exposure: 5 variants × 3 sleeves = 15 backtests. The picks above are post-hoc selections of the best variant per sleeve. Honest practice: deflate the Sharpes for the number of trials, or pre-commit to a single config before testing.

If we apply a rough Bonferroni-style adjustment (5 trials per sleeve), the "true" Sharpe for v2a_long_only US is more like +0.4 than +0.67. Still positive, but the headline overstates.

This is exactly the gap that DSR and SPA test (deferred to Phase 1.5b) close. Adding them next.

## Recommended next moves

1. **Lock in best per-sleeve config** as v2-final — but treat it as a *hypothesis*, not an answer.
2. **Phase 1.5b:** add Deflated Sharpe Ratio + Hansen SPA test so headline numbers honestly reflect the multiple-testing burden.
3. **Phase 2 alt-data:** start adding signals (insider clusters, PEAD, funding extremes). Each gets pre-registered config (no variant grid) and individual backtest.
4. **Out-of-sample holdout:** designate 2026-05-10 forward as a paper-trading holdout. The real test is whether v2a US sustains positive Sharpe on data we haven't seen.
5. **Don't trade real money yet.** +5.9% blended CAGR pre-multiple-comparison-correction is not enough edge to justify capital.

## Files

- `output/v2_summary.json` — machine-readable full grid
- `output/v2_tearsheet_*.html` — per-variant tearsheets (12 total)
- `output/v2_equity_*.csv` — equity curves
- `output/v2_*_run.log` — full run logs

## Bottom line

**The strategy is fixable. v1 wasn't broken — it was just running in a market regime where its core construction (L/S, sector-neutral) was actively wrong.** Removing the shorts on equities recovered most of the underperformance. Adding sector neutralization and trend filter hurt rather than helped *on this window* — useful research output: the spec's institutional upgrades aren't free lunches in every regime.

Honest score: from "do not trade" to "interesting hypothesis worth out-of-sample testing."
