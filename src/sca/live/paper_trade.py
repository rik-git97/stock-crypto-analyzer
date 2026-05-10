"""Weekly paper-trading runner.

Each run:
1. Pulls fresh prices for all 3 sleeves
2. Generates current picks (per-sleeve config: US/IN long-only, crypto L/S)
3. Saves picks to output/live/picks_<YYYY-MM-DD>.json
4. Compares LAST week's saved picks against THIS week's actual returns -> appends to live_track.parquet
5. Renders HTML brief and saves to output/live/brief_<date>.html
6. Optionally emails the brief if SMTP env vars present
7. India: also pulls today's NSE bulk+block deals and appends to archive
"""
from __future__ import annotations
import argparse, json, os, sys, traceback
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

LIMITATIONS = [
    "Universe is current-membership only — survivorship bias present.",
    "Cost model: flat-bps slippage + fees, no Almgren-Chriss impact.",
    "Walk-forward only — DSR / SPA / CPCV deferred.",
    "ATR stops use close-to-close.",
    "India alt-data: NSE bulk/block deals only (smart-money flow). News sentiment + earnings parsing deferred.",
    "X / FinTwit excluded.",
]

SLEEVE_BACKTEST_SHARPE = {
    "in": 0.45,
    "crypto": 0.66,
}


def _load_in(start: str, end: str) -> tuple[pd.DataFrame, pd.Series | None, str]:
    """Load Indian price data. Returns (prices, market_index, source).
    Tries Kite Connect SDK first; falls back to yfinance on auth/missing-creds."""
    from sca.universe.nifty500 import fetch_nifty500_tickers
    from sca.prices.yfinance_loader import load_prices as load_yf
    try:
        tickers = fetch_nifty500_tickers()
    except Exception:
        tickers = [t + ".NS" for t in [
            "RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","HINDUNILVR","SBIN","BHARTIARTL","ITC","LT",
            "KOTAKBANK","BAJFINANCE","HCLTECH","ASIANPAINT","MARUTI","AXISBANK","SUNPHARMA","TITAN","ULTRACEMCO","WIPRO",
            "NESTLEIND","ONGC","NTPC","POWERGRID","TATASTEEL","BAJAJFINSV","M&M","TECHM","HDFCLIFE","SBILIFE",
            "ADANIENT","ADANIPORTS","COALINDIA","GRASIM","JSWSTEEL","DRREDDY","INDUSINDBK","BRITANNIA","DIVISLAB","CIPLA",
            "HINDALCO","TATAMOTORS","BPCL","EICHERMOT","HEROMOTOCO","UPL","BAJAJ-AUTO","APOLLOHOSP","SHRIRAMFIN","LTIM",
        ]]

    source = "yfinance"
    df = pd.DataFrame()
    try:
        from sca.prices.kite_loader import load_prices_kite, KiteUnavailable
        try:
            df = load_prices_kite(tickers, start, end)
            if not df.empty:
                source = "kite"
        except KiteUnavailable as e:
            print(f"  [kite] unavailable, falling back to yfinance: {e}")
    except ImportError:
        pass

    if df.empty:
        df = load_yf(tickers, start, end)

    prices = df.pivot_table(index="date", columns="ticker", values="adj_close").sort_index()
    nsei = load_yf(["^NSEI"], start, end)
    market = nsei.pivot_table(index="date", columns="ticker", values="adj_close")["^NSEI"] if not nsei.empty else None
    print(f"  india data source: {source}")
    return prices, market, source


def _load_crypto(start: str, end: str):
    from sca.universe.crypto_top30 import fetch_crypto_top30
    from sca.prices.ccxt_loader import load_crypto_ohlcv
    syms = fetch_crypto_top30()
    df = load_crypto_ohlcv(syms, start, end)
    prices = df.pivot_table(index="date", columns="ticker", values="close").sort_index()
    market = prices["BTC/USDT:USDT"] if "BTC/USDT:USDT" in prices.columns else (prices.iloc[:, 0] if not prices.empty else None)
    return prices, market


def _try_pull_nse_deals():
    try:
        from sca.ingestion.nse_corp_actions import fetch_today_and_archive
        deals = fetch_today_and_archive("output/live/nse_deals.parquet")
        return len(deals), None
    except Exception as e:
        return 0, str(e)


def _build_in_overlay(prices: pd.DataFrame, deals_archive: Path) -> tuple[pd.DataFrame | None, str]:
    """Build smart-money overlay if archive has enough data; return (overlay, note)."""
    if not deals_archive.exists():
        return None, "No deals archive yet — overlay will activate after first archived day."
    from sca.signals.india_smart_money import load_deals_archive, smart_money_overlay_panel
    deals = load_deals_archive(deals_archive)
    if deals.empty or deals["date"].nunique() < 5:
        return None, f"Deals archive has {deals['date'].nunique() if not deals.empty else 0} unique days — need ≥ 5 for stable overlay."
    panel = smart_money_overlay_panel(deals, prices, window_days=30)
    return panel, f"Deals archive: {len(deals)} rows over {deals['date'].nunique()} days; overlay active."


def _next_monday_returns(saved_picks: dict, sleeve: str, prices: pd.DataFrame) -> dict | None:
    """Given a previously saved picks dict, compute the realized weekly return that the
    long-side picks would have earned from the saved as_of date to this run."""
    longs = saved_picks.get("longs", [])
    if not longs:
        return None
    as_of = pd.Timestamp(saved_picks["as_of"])
    fwd = prices.loc[prices.index > as_of]
    if fwd.empty:
        return None
    next_close = fwd.iloc[0]
    # equal-weight the longs (since we're tracking signal quality, not exact backtest replication)
    rets = []
    for p in longs:
        t = p["ticker"]
        if t in prices.columns:
            entry = prices.at[as_of, t] if as_of in prices.index else None
            if entry is None or pd.isna(entry):
                continue
            # take ~5 bar forward return
            target_idx = min(len(fwd) - 1, 5)
            exit_px = fwd.iloc[target_idx][t]
            if pd.isna(exit_px) or pd.isna(entry):
                continue
            rets.append(float(exit_px / entry - 1))
    if not rets:
        return None
    avg = float(np.mean(rets))
    return {"sleeve": sleeve, "as_of": str(as_of.date()), "n_longs": len(rets), "avg_5d_fwd_return": avg}


def _live_vs_backtest_summary(history_path: Path) -> list[dict]:
    if not history_path.exists():
        return []
    df = pd.read_parquet(history_path)
    if df.empty:
        return []
    out = []
    for sleeve in df["sleeve"].unique():
        sub = df[df["sleeve"] == sleeve]
        if len(sub) < 1:
            continue
        weekly = sub["avg_5d_fwd_return"].astype(float)
        live_total = float((1 + weekly).prod() - 1)
        live_sharpe = float(weekly.mean() / weekly.std(ddof=1) * np.sqrt(52)) if len(weekly) >= 2 and weekly.std(ddof=1) > 0 else float("nan")
        bt = SLEEVE_BACKTEST_SHARPE.get(sleeve, float("nan"))
        out.append({
            "sleeve": sleeve.upper(),
            "weeks": int(len(weekly)),
            "live_total": live_total,
            "live_sharpe": live_sharpe,
            "bt_sharpe": bt,
            "delta_sharpe": (live_sharpe - bt) if not np.isnan(live_sharpe) else float("nan"),
        })
    return out


def _paper_trade_history(history_path: Path, history_dir: Path) -> dict:
    """Build a complete paper-trade tab: every weekly run + per-pick realized 5d returns
    + cumulative equity curve (per sleeve and combined equal-weight)."""
    if not history_path.exists():
        return {"weekly_rows": [], "equity_curves": {}, "n_total_picks_tracked": 0}
    df = pd.read_parquet(history_path)
    if df.empty:
        return {"weekly_rows": [], "equity_curves": {}, "n_total_picks_tracked": 0}
    df = df.sort_values(["sleeve", "as_of"]).reset_index(drop=True)
    weekly_rows = []
    for _, r in df.iterrows():
        weekly_rows.append({
            "as_of": str(r["as_of"]),
            "sleeve": str(r["sleeve"]).upper(),
            "n_picks": int(r.get("n_longs", 0)),
            "avg_5d_fwd_return": float(r.get("avg_5d_fwd_return", 0.0)),
            "recorded_at": str(r.get("recorded_at", "")),
        })
    equity_curves: dict[str, list[dict]] = {}
    for sleeve in df["sleeve"].unique():
        sub = df[df["sleeve"] == sleeve].sort_values("as_of")
        eq = 1.0
        points = [{"as_of": "start", "equity": 1.0}]
        for _, r in sub.iterrows():
            eq *= (1.0 + float(r["avg_5d_fwd_return"]))
            points.append({"as_of": str(r["as_of"]), "equity": float(eq)})
        equity_curves[str(sleeve).upper()] = points
    return {
        "weekly_rows": weekly_rows,
        "equity_curves": equity_curves,
        "n_total_picks_tracked": int(df["n_longs"].fillna(0).sum()) if "n_longs" in df else 0,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["run"], default="run", nargs="?")
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--lookback-days", type=int, default=550, help="Days of price history to pull")
    p.add_argument("--out", default="output/live")
    p.add_argument("--no-email", action="store_true")
    p.add_argument("--sleeves", default="in,crypto")
    p.add_argument("--capital-inr", type=float, default=50_000.0,
                   help="Capital to allocate to the concentrated India portfolio")
    p.add_argument("--portfolio-positions", type=int, default=12,
                   help="Target number of positions in the concentrated portfolio")
    p.add_argument("--no-news", action="store_true", help="Skip news aggregation")
    p.add_argument("--no-options", action="store_true", help="Skip options ideas")
    args = p.parse_args(argv)

    end = args.end
    start = (pd.Timestamp(end) - pd.Timedelta(days=args.lookback_days)).date().isoformat()
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    history_dir = out_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    track_path = history_dir / "live_track.parquet"
    notes: list[str] = []

    sleeves = [s.strip() for s in args.sleeves.split(",") if s.strip()]
    sleeve_picks_list = []
    sleeve_prices_map: dict[str, pd.DataFrame] = {}
    market = None  # for options regime check

    # 1) NSE deals daily snapshot (only when running today, only on weekdays in IST window)
    if "in" in sleeves:
        n_deals, err = _try_pull_nse_deals()
        if err:
            notes.append(f"NSE deals fetch failed: {err} (overlay falls back to momentum-only).")
        elif n_deals == 0:
            notes.append("NSE deals: 0 rows today (weekend/holiday or no deals reported).")
        else:
            notes.append(f"NSE deals archived: +{n_deals} rows.")

    # 2) Per-sleeve picks
    from sca.live.picks_engine import generate_sleeve_picks, picks_to_dict

    for sleeve in sleeves:
        try:
            print(f"\n=== {sleeve.upper()} ===", flush=True)
            if sleeve == "in":
                prices, market_in, in_source = _load_in(start, end)
                market = market_in
                notes.append(f"India data source: {in_source}")
                overlay, note = _build_in_overlay(prices, out_dir / "nse_deals.parquet")
                if note:
                    notes.append(f"India overlay: {note}")
                picks = generate_sleeve_picks(
                    sleeve="in", asset_class="IN", prices=prices, market=market_in, sectors=None,
                    long_only=True, use_combined_signal=False,
                    overlay_signal=overlay, overlay_weight=0.3 if overlay is not None else 0.0,
                )
            elif sleeve == "crypto":
                prices, market_crypto = _load_crypto(start, end)
                picks = generate_sleeve_picks(
                    sleeve="crypto", asset_class="CRYPTO", prices=prices, market=market_crypto, sectors=None,
                    long_only=False, use_combined_signal=False,
                )
            else:
                continue
            print(f"  {sleeve}: {picks.universe_size} signal-eligible, {len(picks.longs)} longs, {len(picks.shorts)} shorts, {len(picks.flagged)} flagged")
            sleeve_picks_list.append(picks)
            sleeve_prices_map[sleeve] = prices

            # 3) compare LAST week's picks vs realized
            last_picks_files = sorted([f for f in history_dir.glob(f"picks_{sleeve}_*.json")])
            if last_picks_files:
                with open(last_picks_files[-1]) as f:
                    saved = json.load(f)
                realized = _next_monday_returns(saved, sleeve, prices)
                if realized:
                    realized_df = pd.DataFrame([realized])
                    realized_df["recorded_at"] = pd.Timestamp.utcnow()
                    if track_path.exists():
                        prev = pd.read_parquet(track_path)
                        merged = pd.concat([prev, realized_df], ignore_index=True)
                    else:
                        merged = realized_df
                    merged = merged.drop_duplicates(subset=["sleeve", "as_of"]).reset_index(drop=True)
                    merged.to_parquet(track_path, index=False)
                    print(f"  tracked realized 5d-fwd avg = {realized['avg_5d_fwd_return']*100:+.2f}%")

            # 4) save THIS week's picks for next-week comparison
            picks_dict = picks_to_dict(picks)
            picks_path = history_dir / f"picks_{sleeve}_{picks.as_of}.json"
            with open(picks_path, "w") as f:
                json.dump(picks_dict, f, indent=2, default=str)
        except Exception as e:
            print(f"ERROR {sleeve}: {e}")
            traceback.print_exc()
            notes.append(f"{sleeve}: pipeline error {e}")

    # 5) build concentrated ₹50K portfolio from India picks
    capital_portfolio = None
    in_picks = next((p for p in sleeve_picks_list if p.sleeve == "in"), None)
    if in_picks and in_picks.longs:
        from sca.portfolio.sizing_for_capital import build_capital_portfolio, portfolio_to_dict
        in_pick_dicts = [
            {"ticker": pk.ticker, "z_score": pk.z_score, "weight": pk.weight,
             "last_price": pk.last_price, "realized_vol_30d": pk.realized_vol_30d}
            for pk in in_picks.longs
        ]
        cp = build_capital_portfolio(
            picks=in_pick_dicts,
            capital=args.capital_inr,
            currency="INR",
            target_n_positions=args.portfolio_positions,
        )
        capital_portfolio = portfolio_to_dict(cp)
        notes.append(
            f"₹{args.capital_inr:,.0f} portfolio: {len(cp.positions)} positions, "
            f"₹{args.capital_inr - cp.cash_residual:,.0f} deployed "
            f"({cp.deployed_pct*100:.1f}%), ₹{cp.cash_residual:,.0f} cash"
        )

    # 6) options ideas (NIFTY + BANKNIFTY, 3-month vertical spreads)
    options_ideas = []
    if not args.no_options and "in" in sleeves:
        try:
            from sca.ingestion.nse_options_chain import fetch_option_chain, chain_to_dataframe
            from sca.portfolio.options_strategies import regime_pick_spread
            from dataclasses import asdict as _asdict
            for underlying in ("NIFTY", "BANKNIFTY"):
                try:
                    raw = fetch_option_chain(underlying)
                    chain_df = chain_to_dataframe(raw)
                    if chain_df.empty:
                        continue
                    spot = float(chain_df["underlying"].dropna().iloc[0]) if "underlying" in chain_df else 0
                    # use Nifty 200-DMA as regime gate (already pulled above)
                    regime_idx = market if "in" in sleeves else None
                    sma200 = None
                    if regime_idx is not None and len(regime_idx) >= 200:
                        sma200 = float(regime_idx.tail(200).mean())
                    idea = regime_pick_spread(chain_df, underlying, spot, sma200, target_dte=90)
                    if idea:
                        options_ideas.append(_asdict(idea))
                except Exception as e:
                    notes.append(f"options {underlying}: {e}")
        except Exception as e:
            notes.append(f"options module error: {e}")

    # 7) news (per-pick headlines + risk flags)
    news_per_ticker: dict = {}
    if not args.no_news and "in" in sleeves:
        try:
            from sca.ingestion.news_rss import fetch_all_news, apply_flags, tag_per_ticker, newsitems_to_dict
            from sca.ingestion.nse_company_aliases import fetch_aliases
            aliases = fetch_aliases()
            items = fetch_all_news()
            items = apply_flags(items)
            in_tickers = [pk.ticker for pk in (in_picks.longs if in_picks else [])]
            in_aliases = {t: aliases.get(t, []) for t in in_tickers}
            tagged = tag_per_ticker(items, in_aliases, max_per_ticker=3)
            news_per_ticker = {t: newsitems_to_dict(v) for t, v in tagged.items() if v}
            n_with_news = sum(1 for v in news_per_ticker.values() if v)
            notes.append(f"News: {len(items)} headlines aggregated; {n_with_news} of {len(in_tickers)} picks tagged.")
        except Exception as e:
            notes.append(f"news pipeline: {e}")

    # 8) signal health (IC = Spearman corr of z-score vs realized 5d-fwd return)
    health_summary_rows: list[dict] = []
    try:
        from sca.live.health_metrics import compute_ic_for_picks, append_health, health_summary
        health_path = history_dir / "health.parquet"
        for sleeve in sleeves:
            sp = sleeve_prices_map.get(sleeve)
            if sp is None:
                continue
            old_picks_files = sorted([f for f in history_dir.glob(f"picks_{sleeve}_*.json")])
            if len(old_picks_files) < 2:
                continue
            with open(old_picks_files[-2]) as f:
                saved = json.load(f)
            row = compute_ic_for_picks(saved, sp, fwd_days=5)
            if not pd.isna(row.ic_5d):
                append_health(row, health_path)
                print(f"  IC[{sleeve}] {row.as_of}: {row.ic_5d:+.3f} (n={row.n_with_return})")
        health_summary_rows = health_summary(health_path)
    except Exception as e:
        notes.append(f"health metrics: {e}")

    # 5) brief
    from sca.live.notify import render_brief, send_email
    paper_trade_tab = _paper_trade_history(track_path, history_dir)
    context = {
        "run_date": end,
        "sleeves": [picks_to_dict(p) for p in sleeve_picks_list],
        "live_vs_backtest": _live_vs_backtest_summary(track_path),
        "capital_portfolio": capital_portfolio,
        "options_ideas": options_ideas,
        "news_per_ticker": news_per_ticker,
        "health_summary": health_summary_rows,
        "paper_trade": paper_trade_tab,
        "notes": notes or ["Run completed normally."],
        "limitations": LIMITATIONS,
    }
    html = render_brief(context)
    brief_path = out_dir / f"brief_{end}.html"
    brief_path.write_text(html, encoding="utf-8")
    (out_dir / "brief_latest.html").write_text(html, encoding="utf-8")
    (out_dir / f"brief_{end}.json").write_text(json.dumps(context, indent=2, default=str), encoding="utf-8")
    print(f"\nbrief saved: {brief_path}")

    # Also write to docs/ for GitHub Pages deployment
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "brief_latest.html").write_text(html, encoding="utf-8")
    (docs_dir / f"brief_{end}.html").write_text(html, encoding="utf-8")
    (docs_dir / "brief_latest.json").write_text(json.dumps(context, indent=2, default=str), encoding="utf-8")
    # index.html redirects to brief_latest.html
    index_html = (
        "<!doctype html><meta charset=utf-8><title>SCA Brief</title>"
        "<meta http-equiv=refresh content=\"0; url=brief_latest.html\">"
        "<style>body{font-family:ui-monospace,monospace;background:#0b0d10;color:#e6e6e6;padding:24px}</style>"
        "<p>Redirecting to <a href=\"brief_latest.html\" style=\"color:#ffaa00\">brief_latest.html</a>…</p>"
    )
    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")
    print(f"docs/ published: {docs_dir / 'brief_latest.html'}")

    # 6) email (best-effort)
    if not args.no_email:
        try:
            sent = send_email(html, subject=f"SCA weekly brief — {end}")
            if sent:
                print("email: sent")
            else:
                print("email: skipped (SMTP env vars not all set; see notify.py docstring)")
        except Exception as e:
            print(f"email: failed {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
