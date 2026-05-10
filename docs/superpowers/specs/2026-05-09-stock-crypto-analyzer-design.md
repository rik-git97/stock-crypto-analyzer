# Stock + Crypto Analyzer — Institution-Grade Design

**Date:** 2026-05-09
**Author:** rikmitra20@gmail.com
**Status:** Draft v1 — pending user review
**Amendment 2026-05-10:** US sleeve removed by user request. Active sleeves: India (Nifty 500) + crypto (top 30 perps). Sections referencing US below are kept as historical record but are no longer in scope.

---

## 1. Goal

A personal-use, institution-grade swing/positional trading analyzer covering US equities, Indian equities, and crypto, with a transparent modular signal framework and rigorous backtesting. Distinguishing requirement: must have a real edge thesis, not be a generic indicator dashboard, and every claim of edge must survive honest out-of-sample statistical tests.

## 2. Non-goals (v1)

- Live order execution / broker integration (read-only signals first)
- Mobile app
- Multi-user / multi-tenant
- High-frequency / intraday strategies (timeframe is swing 3–20d for stocks, positional weeks–months for crypto)
- Paid market data
- Full options strategies (options flow used as a *signal input* only)

## 3. Phased plan

| Phase | Scope | Acceptance |
|---|---|---|
| **1** | Cross-sectional momentum signal end-to-end. Data pipeline + event-driven backtest engine + tearsheet. 3 sleeves: S&P 500, Nifty 500, crypto top 30 perps. Honest 1-year out-of-sample backtest. | Tearsheet shows real results with full statistical disclosure (DSR, SPA p-value, bootstrap CI). Loses or wins, numbers are reproducible from `run_id`. |
| **2** | Add alt-data signals one at a time, each with standalone backtest. Targets: insider clusters, PEAD, Fed tone, funding extremes, on-chain flows, 13F crowding, Reddit velocity. | Only signals with deflated Sharpe > 0.5 and SPA p < 0.05 enter the live portfolio. |
| **3** | Portfolio combiner with risk-aware weighting. Webapp UI. Live signal monitoring. | Bloomberg-style dashboard showing live signals, portfolio state, live tearsheet vs. backtest. |
| **4** | Live paper trading. | Performance vs. backtest within tolerance for ≥ 8 weeks before any real capital. |

## 4. Phase 1 strategy spec — Momentum

### 4.1 Universe

- **US sleeve:** historical S&P 500 constituents (point-in-time membership reconstructed from Wikipedia change log + SEC 8-K filings). Delisted names retained in universe up to delisting date.
- **India sleeve:** historical Nifty 500 constituents from NSE archives.
- **Crypto sleeve:** top 30 by 30-day average Binance perp volume, recomputed weekly. Stable-coin pairs only (USDT/USDC quote).

### 4.2 Signal

- Primary: 12-1 month total return (past 252 trading days excluding most recent 21), z-scored within sleeve and within sector (GICS for US/India, none for crypto).
- Secondary: residual momentum — 12-1 return after stripping market beta via 60-day rolling regression vs. SPX/Nifty/BTC.
- Combined rank: `0.6 * z_xs + 0.4 * z_residual`.

### 4.3 Entries / exits

- Weekly rebalance: Monday open (NYSE for US, NSE for India, 00:00 UTC for crypto).
- Long top 20% of combined rank per sleeve. Short bottom 20% per sleeve.
- Stop-loss: 1×ATR(14) below entry (long) / above entry (short), checked daily on close.
- After 1R favorable move: trail stop to breakeven, then ratchet at 1×ATR.
- Forced rebalance exit: name no longer in top/bottom 20% on next weekly rank → close at next bar open.

### 4.4 Position sizing

- Volatility-targeted: each position contributes ~1% portfolio annualized vol.
- Vol estimate: 30-day exponentially-weighted realized vol (λ = 0.94).
- Covariance: Ledoit-Wolf shrinkage on 60-day daily returns.
- Position size = `(target_vol_contribution / vol_i) * leverage_factor`, capped per risk limits below.

### 4.5 Risk limits (institutional layer)

| Limit | Value |
|---|---|
| Gross exposure | ≤ 200% per sleeve |
| Net exposure | ±20% per sleeve (kept market-neutral) |
| Single-name | ≤ 3% NAV |
| Sector | ≤ 25% gross per GICS sector |
| Liquidity | order ≤ 5% of 20-day ADV |
| Portfolio drawdown circuit breaker | flatten at 15%, re-enter on next signal |

### 4.6 Regime filter

- US sleeve: gross exposure halved when SPX < 200-day SMA.
- India sleeve: same with Nifty 500.
- Crypto sleeve: BTC vs. 200-day SMA gates the sleeve.

### 4.7 Cost model

- **US equities:** 5 bps slippage + $0 commission. Borrow cost: 25 bps/yr general collateral; HTB approximation: 500 bps/yr for names with market cap < $1B.
- **India equities:** 10 bps slippage + STT (0.1% delivery, 0.025% intraday sell) + exchange charges + GST + SEBI fees, itemized.
- **Crypto perps:** 5 bps taker fee + actual historical 8h funding rates (paid/received).
- **Slippage model:** Almgren–Chriss simplified — `impact_bps = k * σ_daily * sqrt(order_size / ADV)` with k calibrated per asset class.

## 5. Validation methodology

- **Walk-forward analysis:** rolling 3-year train / 1-quarter test, no parameters refit on test.
- **Combinatorial Purged Cross-Validation** (López de Prado): 6 splits, embargo = 5 days.
- **Deflated Sharpe Ratio** (Bailey & López de Prado) — adjusts for the number of strategy variants tested.
- **White's Reality Check / Hansen SPA test** for data-snooping bias.
- **Bootstrapped confidence intervals** — 1000 stationary block-bootstrap (Politis–Romano) resamples on Sharpe, max DD, win rate.
- **Regime-stratified results:** by VIX quintile, by SPX trend regime, by BTC regime.
- **Factor attribution:** Fama–French 5-factor + momentum + quality regression on returns. Reports alpha, betas, t-stats.

## 6. Reporting (tearsheet)

- Sharpe, Sortino, Calmar, Omega, Ulcer Index, MAR
- Max DD with duration and recovery time
- VaR(95), CVaR(95), tail ratio
- Monthly returns heatmap, rolling 12m Sharpe
- Per-sleeve tearsheets + combined
- All metrics reported with bootstrap 95% CI
- Outputs: HTML dashboard + PDF + raw JSON for reproducibility

## 7. Alt-data ingestion (Phase 2 candidate signals)

### 7.1 Tier A — high-signal, free, automatable

| Source | Extract | API |
|---|---|---|
| SEC EDGAR | 10-K/Q/8-K, 13F, Form 4 | Free official |
| FRED | Fed funds, yield curve, CPI, PMI, NFP | Free official |
| GDELT 2.0 | News event graph, tone, themes | Free |
| Reddit | WSB / r/stocks / r/cryptocurrency mentions, velocity | Free Reddit + Pushshift |
| Google Trends | Search interest per ticker | pytrends |
| Glassnode free + Etherscan | Exchange flows, whale moves, stablecoin supply | Free tier |
| CCXT funding history | Crypto perp funding rates | Free |
| CBOE DataShop | Unusual options activity, P/C ratios | Free |
| NSE/BSE filings | Promoter buys, block deals, results | Free |
| Earnings transcripts | Tone, guidance | Seeking Alpha free + Whisper STT fallback |
| arXiv / SSRN / NBER | Factor research | Free RSS |

### 7.2 Tier B — partial

- **YouTube:** transcripts via youtube-transcript API. Curated allowlist only (FOMC channel, official IR). No random influencers.
- **X / Twitter:** free tier polling for live checks only. Not a backtest input.
- **Books:** index legally-owned PDFs (Kaufman, Chan, López de Prado etc.) for research RAG; no bulk copyrighted ingestion.

### 7.3 Tier C — explicitly rejected

- Stock-pick YouTubers, Telegram pump groups, Discord shills, gurus, paid signal services. Not allowed near the backtest.

### 7.4 Phase 2 signal candidates

Each is a separate module subclassing the `Signal` interface, each with its own walk-forward backtest. Adopted into live portfolio only if deflated Sharpe > 0.5 and SPA p < 0.05.

- `signal_insider_cluster_buy`
- `signal_pead`
- `signal_fed_dovish_shift` (NLP on FOMC statements)
- `signal_funding_extreme`
- `signal_13f_crowding`
- `signal_reddit_velocity`
- `signal_onchain_exchange_outflow`
- `signal_options_unusual_activity`
- `signal_yield_curve_regime`

## 8. Architecture

### 8.1 Approach: monolith Python compute + Supabase serving

- **Compute (local laptop → later Hetzner CX32 VPS):** all Python — ingestion, signals, backtest engine, NLP, walk-forward.
- **Storage + serving (Supabase):** Postgres + pgvector for prices, signals, runs, tearsheets, embeddings; Supabase Storage for raw filings and tearsheet PDFs; Supabase Auth gates the dashboard; Supabase Realtime pushes live signal updates.
- **Web (Vercel):** Next.js 15 reads Supabase via RLS. Backtest triggers go through a Next.js API route → Supabase Edge Function → job queue polled by the local worker.
- **Orchestration:** Prefect Cloud free tier for daily/weekly DAGs.

### 8.2 Module layout

```
stock-crypto-analyzer/
├── ingestion/
│   ├── prices/{yfinance_us,yfinance_india,kite_india,ccxt_crypto,on_chain}.py
│   ├── universe/{sp500_pit,nifty500_pit,crypto_top30}.py
│   ├── fundamentals/{edgar,nse_filings}.py
│   ├── macro/fred.py
│   ├── news/{gdelt,rss_aggregator,reddit}.py
│   ├── transcripts/{youtube_curated,earnings_calls}.py
│   └── options/cboe_unusual.py
├── signals/
│   ├── base.py                 # Signal abstract class
│   ├── momentum_xs.py
│   ├── momentum_residual.py
│   └── …                        (Phase 2)
├── backtest/
│   ├── engine.py               # Event-driven simulator
│   ├── execution.py            # Almgren-Chriss slippage, borrow, funding
│   ├── walk_forward.py
│   ├── cpcv.py
│   ├── stats.py                # Sharpe, Sortino, DSR, SPA, bootstrap
│   └── tearsheet.py
├── portfolio/
│   ├── sizing.py               # Vol-target + Ledoit-Wolf
│   ├── risk_caps.py
│   └── combiner.py
├── api/
│   └── main.py                 # FastAPI for backtest triggers + heavy queries
├── web/                        # Next.js 15 + Tremor
└── infra/
    ├── docker-compose.yml      # Local dev: Postgres+Timescale, Qdrant optional
    └── prefect/                # Job DAGs
```

### 8.3 Reproducibility guarantees

- Every backtest writes a `run_id` row containing: data snapshot hash, signal version, full config JSON, seed, library versions.
- Same `run_id` → bit-for-bit identical numbers forever.
- Tearsheet PDFs are immutable artifacts in Supabase Storage.

## 9. Honest limitations (named, not hidden)

| Compromise | Impact | Mitigation |
|---|---|---|
| Free PIT data reconstructed from Wikipedia + filings | Some membership errors at quarter boundaries | Sensitivity analysis: results reported with conservative ±5% universe perturbation |
| Borrow rates approximated, not real prime broker | Short side P&L overstated for HTB names | Conservatively assume 500 bps/yr for sub-$1B caps; flag any signal that depends critically on shorts |
| No real-time intraday fills — daily close approximation | Slightly optimistic vs. real execution | 5 bps additional slippage budget added globally |
| X/Twitter excluded from backtest | Miss FinTwit signal | Documented gap; revisit if other signals demand it |
| Earnings transcripts via Whisper STT for some tickers | Transcription errors degrade NLP signals | Cross-check against Seeking Alpha when available; flag low-confidence transcripts |
| Single-machine compute | Can't run massive parameter sweeps | Walk-forward + CPCV constrain search space; deflated Sharpe penalizes over-search |

## 10. Acceptance criteria for Phase 1

- [ ] PIT universe builders produce dated CSVs that pass cross-checks against publicly known index changes
- [ ] Event-driven backtest engine produces identical numbers across two independent runs (`run_id` reproducibility)
- [ ] 1-year backtest report includes: tearsheet, walk-forward, DSR, SPA p-value, bootstrap CIs, regime stratification, factor attribution
- [ ] Real results published transparently — including if the strategy loses money in the period
- [ ] All approximations and gaps explicitly named in the report

## 11. Open questions

- None blocking Phase 1. Phase 3 webapp visual style (terminal-dark Bloomberg vs. modern light) deferred until Phase 1 numbers exist.

---

**Next step after user approval:** invoke `superpowers:writing-plans` to create the Phase 1 implementation plan.
