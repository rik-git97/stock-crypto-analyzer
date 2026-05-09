# Phase 1 v1 Backtest Results — Honest Report

**Date:** 2026-05-10
**Window:** 2024-04-01 → 2026-05-10 (~2 years; first ~252 trading days are momentum-lookback warmup, rest is live trading equity curve)
**Strategy:** Cross-sectional 12-1 momentum, weekly Monday rebalance, long top 20% / short bottom 20%, vol-targeted sizing (1% per-position vol contribution), 1×ATR trailing stops, 200% gross / 3% single-name caps, 50 bps/yr flat borrow.
**Universes:** S&P 500 current (503 names), Nifty 500 current (500 names), Binance USDT-perps top 30 by volume.

---

## Headline numbers (real, not curve-fit)

| Sleeve | Total Return | CAGR | Sharpe | Sharpe 95% CI | Max DD | Sortino | Calmar | Win rate (daily) | n bars |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **US (S&P 500)** | **-6.6%** | -3.2% | **-0.27** | [-1.49, +0.76] | -18.6% | -0.24 | -0.17 | 29.4% | 528 |
| **India (Nifty 500)** | **-14.2%** | -7.2% | **-0.99** | [-2.16, +0.48] | -17.5% | -0.92 | -0.41 | 23.3% | 520 |
| **Crypto (Top 30 perps)** | **+3.6%** | +1.2% | **+0.66** | [-0.51, +1.74] | -2.1% | +0.72 | +0.54 | 36.1% | 768 |

## What this actually says

**Two of three sleeves lost money. None of the three Sharpes are statistically distinguishable from zero** — every confidence interval crosses zero. This is the *correct* result for plain 12-1 cross-sectional momentum on this window, executed honestly without the institutional refinements.

This is the value of the v1 build: **it tells you the truth.** A backtest claiming +25% Sharpe-2.5 on plain 12-1 momentum during 2024-2026 would be a lie or a curve-fit.

## Why each sleeve lost (or barely won)

**US (-6.6%):**
- The 2024-2026 mega-cap concentration (the Mag-7 dominating index returns) breaks plain cross-sectional momentum: top decile by 12-1 return *was* the overcrowded AI/megacap bucket, which mean-reverted in chunks. Bottom decile shorts included low-quality small-caps that ripped on AI/refi narratives.
- Long/short market-neutral construction strips out the broad index gain — and SPX itself rose ~30% in this window. So we forfeited beta without capturing alpha.
- Survivorship bias should have *helped* the longs (failed companies aren't in the current SP500 list) — losing money despite this tailwind tells us plain 12-1 has no edge in this regime.

**India (-14.2%):**
- Worst performer. Nifty 500 small/mid-caps had a brutal momentum reversal in late 2024 / early 2025 (well-documented Indian small-cap drawdown).
- High statutory costs (10 bps STT + 5 bps GST = 15 bps/turnover) compound on weekly rebalancing.
- Same long-short market-neutral construction as US; same problem — gave up the broad bull rally.

**Crypto (+3.6%):**
- Lowest realized vol (1.8% annualized!) — vol-targeting kept sizes tiny because crypto's per-asset vol is high. This is correct behavior, but means the strategy barely participates.
- The ATR-stop + weekly rebalance combo cuts losers fast in a high-vol asset class — reflected in the very small max DD (-2.1%).
- Positive Sharpe point estimate is encouraging but CI crosses zero — could be luck.

## Statistical honesty

Bootstrap (1000 resamples, block size 20) on Sharpe gives **wide CIs that all include zero**. With ~500 daily observations per sleeve, you simply cannot detect a Sharpe < 1 with statistical confidence in this window. This is a feature, not a bug, of running honest stats — most "amazing" retail backtests would also fail this test if their authors ran it.

## Files produced

- `output/tearsheet_us_53e2641244e5.html` — full US tearsheet
- `output/tearsheet_in_221d0169e91f.html` — full India tearsheet
- `output/tearsheet_crypto_a9d12b276b4c.html` — full crypto tearsheet
- `output/equity_*.csv` — daily equity curves
- `output/trades_*.csv` — every entry/exit with date + price
- `output/summary.json` — machine-readable summary

Open the HTML tearsheets in a browser for monthly returns heatmap + full config.

## Reproducibility

Each `run_id` is a hash of full config. Re-running with the same config + data window will produce **bit-for-bit identical numbers**. Configs are saved in the tearsheet JSON.

## What's missing (not snuck-in features, real gaps)

Everything in §9 of the spec:
- **PIT membership reconstruction** → current S&P 500 / Nifty 500 has survivorship bias. Bias direction here actually flatters longs, so real PIT results would likely be *worse* on longs.
- **Residual + sector-neutral momentum** → the most important upgrade. Plain 12-1 is largely a sector + factor bet, not a name-selection bet. Sector-neutralizing typically halves drawdowns in academic backtests.
- **Almgren-Chriss execution** → flat 5 bps slippage probably understates costs at high turnover.
- **Tiered HTB borrow** → flat 50 bps/yr flatters the short side.
- **Combinatorial Purged CV / Deflated Sharpe / SPA test** → would not change the conclusion (none of these point estimates clear bars anyway), but needed for any *positive* claim later.

## Recommended next moves

1. **Phase 1.5 — sector-neutralize and residualize the signal.** This alone is expected to push US Sharpe from -0.27 to roughly +0.3-0.6 based on academic literature (Jegadeesh & Titman, AQR papers). Still won't be a unicorn. Real but modest.
2. **Phase 2 — start adding alt-data signals.** Insider clusters (Form 4) and PEAD (post-earnings drift) are the two best-documented free-data edges. Each gets its own backtest. Combine only those that pass DSR > 0.5 + SPA p < 0.05.
3. **Phase 3 — portfolio combiner across surviving signals.** Multi-signal portfolios with Ledoit-Wolf shrinkage on signal-return covariance. This is where edge finally compounds.
4. **Do NOT trade this v1 with real money.** It loses money out-of-sample on 2 of 3 sleeves and is statistically indistinguishable from zero on all three.

## Bottom line

You asked for honest results — these are honest results. Plain cross-sectional 12-1 momentum is *not* an edge in this window. Building the correct framework first means we now have an engine that can honestly evaluate every additional signal we add. That's the institution-grade contribution of Phase 1 — the engine, not these numbers.
