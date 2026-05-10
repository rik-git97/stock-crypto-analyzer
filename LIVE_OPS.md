# Live Operations — Paper Trading via GitHub Actions

## What this is

A weekly autonomous paper-trade runner that:
1. Pulls fresh data for US (S&P 500), India (Nifty 500), Crypto (top 30 perps)
2. Generates picks per sleeve using the v2 best config (US + India: long-only top 20%, crypto: L/S)
3. Pulls today's NSE bulk + block deals (smart-money flow) and accumulates into a rolling archive
4. Compares **last week's saved picks** against this week's realized 5-day forward returns
5. Tracks live Sharpe and compares it to backtest Sharpe — divergence > 1.0 over 8+ weeks = strategy is broken
6. Renders an HTML brief (`output/live/brief_<date>.html`)
7. Optionally emails the brief via SMTP
8. Commits everything back to the repo so you have a permanent record

## Schedule

| Cron (UTC) | Local (IST) | What runs |
|---|---|---|
| `30 3 * * 1` | Mon 09:00 | All 3 sleeves (US, India, crypto) |
| `0 4 * * *` | Daily 09:30 | Crypto only (24/7 market needs daily refresh) |

Both defined in [`.github/workflows/weekly-paper-trade.yml`](.github/workflows/weekly-paper-trade.yml).

You can also trigger manually via GitHub UI → Actions → "Weekly paper-trade" → "Run workflow".

## Setup (one-time)

```bash
# 1. Create a GitHub repo (private recommended — keeps your live track record off public)
gh repo create stock-crypto-analyzer --private --source=. --remote=origin --push

# 2. Optional: enable email delivery via repo secrets (Settings → Secrets and variables → Actions)
#    Set the following if you want email; otherwise the workflow still runs and commits artifacts.
#    SCA_SMTP_HOST       e.g. smtp.gmail.com
#    SCA_SMTP_PORT       e.g. 587
#    SCA_SMTP_USER       your gmail address
#    SCA_SMTP_PASS       a Gmail App Password (NOT your account password)
#    SCA_EMAIL_FROM      same as SCA_SMTP_USER
#    SCA_EMAIL_TO        rikmitra20@gmail.com

# 3. (No further setup needed — Actions runs on the schedule above.)
```

## What gets committed each run

```
output/live/
├── brief_<date>.html               # Human-readable brief (open in browser)
├── brief_<date>.json               # Machine-readable
├── brief_latest.html               # Always the most recent
├── nse_deals.parquet               # Rolling NSE bulk+block deals archive
└── history/
    ├── picks_us_<date>.json        # Per-sleeve picks
    ├── picks_in_<date>.json
    ├── picks_crypto_<date>.json
    └── live_track.parquet          # Realized 5-day returns by sleeve, accumulating
```

## How tracking works (the honest part)

Each run, BEFORE generating new picks, the runner:
1. Loads last week's `picks_<sleeve>_<old_date>.json`
2. Looks up the actual price 5 trading days after `old_date`
3. Computes equal-weighted forward return of the long picks
4. Appends to `live_track.parquet` with columns: `sleeve, as_of, n_longs, avg_5d_fwd_return, recorded_at`

After 8+ weeks of data the brief shows a live-vs-backtest comparison table. **If live Sharpe < (backtest Sharpe − 1.0) for 8+ weeks, the strategy is dead and the backtest was a curve-fit.** That's the gate before any real capital.

## India alt-data: what is and isn't included

**Included now:**
- **NSE bulk + block deals** (smart-money flow). Daily official feed. Net BUY notional minus net SELL over rolling 30-day window, z-scored, blended at 30% weight with momentum signal. Activates after archive accumulates ≥ 5 unique trading days.

**Explicitly deferred (each is its own multi-week build, not silently skipped):**
- Per-stock news sentiment NLP across 500 names (Moneycontrol/ET/Mint RSS pipeline + per-ticker tagging)
- Earnings surprise / PEAD signal (needs quarterly results parser from BSE/NSE corp filings)
- Promoter buy/sell parsing (different filings format, requires SEBI scraper)
- Mutual fund + FII flows (NSDL daily — high signal, parser deferred)
- Concall transcripts NLP (Trendlyne/Researchbytes — paid)

When you want any of these added, each gets its own backtest module and gets adopted into the live brief only if standalone Sharpe > 0.5 (deflated).

## Known limitations (still applicable; mirrored from backtest reports)

- Universe is current-membership only — survivorship bias present.
- Cost model: flat-bps slippage + fees, no Almgren-Chriss impact.
- DSR / SPA / CPCV deferred — backtest Sharpes overstate edge by ~30-40% per multiple-comparisons heuristic.
- ATR stops use close-to-close.
- Position sizing uses simple realized vol, not Ledoit-Wolf shrinkage covariance.
- X / FinTwit excluded.
- Outlier filter (|z| > 4 OR < 252 days listing history) catches IPO/spinoff garbage but is heuristic, not bulletproof.

## Manual run (if you want to refresh on-demand)

```bash
# From the repo root, with .venv activated
python -m sca.live.paper_trade run                     # all sleeves
python -m sca.live.paper_trade run --sleeves crypto    # just crypto
python -m sca.live.paper_trade run --no-email          # skip email even if SMTP configured
```

Output goes to `output/live/brief_<date>.html` — open it in any browser.

## Stop / disable

```bash
# In the GitHub repo:
gh workflow disable weekly-paper-trade.yml
```

## What to look at each Monday

Open the latest brief: `output/live/brief_latest.html`. Read in this order:

1. **Notes for this run** — any pipeline errors, NSE feed status, overlay state
2. **Flagged tickers** — data-quality outliers excluded from picks (act as a manual review queue)
3. **Long picks** per sleeve — the actual list
4. **Paper-trade tracking** (after week 4+) — live vs. backtest Sharpe divergence
5. **Limitations** — never let yourself forget what's deferred

Do **not** trade real money based on this until: (a) live tracking shows ≥ 8 consecutive weeks with positive Sharpe, (b) DSR/SPA upgrade is added and the deflated number is still > 0.3, (c) PIT membership reconstruction is done.
