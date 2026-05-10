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
    "us": 0.67,
    "in": 0.45,
    "crypto": 0.66,
}


def _load_us(start: str, end: str):
    from sca.universe.sp500 import fetch_sp500_tickers, fetch_sp500_sectors
    from sca.prices.yfinance_loader import load_prices
    tickers = fetch_sp500_tickers()
    sectors = fetch_sp500_sectors()
    df = load_prices(tickers, start, end)
    prices = df.pivot_table(index="date", columns="ticker", values="adj_close").sort_index()
    spy = load_prices(["SPY"], start, end)
    market = spy.pivot_table(index="date", columns="ticker", values="adj_close")["SPY"] if not spy.empty else None
    return prices, market, sectors


def _load_in(start: str, end: str):
    from sca.universe.nifty500 import fetch_nifty500_tickers
    from sca.prices.yfinance_loader import load_prices
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
    df = load_prices(tickers, start, end)
    prices = df.pivot_table(index="date", columns="ticker", values="adj_close").sort_index()
    nsei = load_prices(["^NSEI"], start, end)
    market = nsei.pivot_table(index="date", columns="ticker", values="adj_close")["^NSEI"] if not nsei.empty else None
    return prices, market


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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["run"], default="run", nargs="?")
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--lookback-days", type=int, default=550, help="Days of price history to pull")
    p.add_argument("--out", default="output/live")
    p.add_argument("--no-email", action="store_true")
    p.add_argument("--sleeves", default="us,in,crypto")
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
            if sleeve == "us":
                prices, market, sectors = _load_us(start, end)
                picks = generate_sleeve_picks(
                    sleeve="us", asset_class="US", prices=prices, market=market, sectors=sectors,
                    long_only=True, use_combined_signal=False,
                )
            elif sleeve == "in":
                prices, market = _load_in(start, end)
                overlay, note = _build_in_overlay(prices, out_dir / "nse_deals.parquet")
                if note:
                    notes.append(f"India overlay: {note}")
                picks = generate_sleeve_picks(
                    sleeve="in", asset_class="IN", prices=prices, market=market, sectors=None,
                    long_only=True, use_combined_signal=False,
                    overlay_signal=overlay, overlay_weight=0.3 if overlay is not None else 0.0,
                )
            elif sleeve == "crypto":
                prices, market = _load_crypto(start, end)
                picks = generate_sleeve_picks(
                    sleeve="crypto", asset_class="CRYPTO", prices=prices, market=market, sectors=None,
                    long_only=False, use_combined_signal=False,
                )
            else:
                continue
            print(f"  {sleeve}: {picks.universe_size} signal-eligible, {len(picks.longs)} longs, {len(picks.shorts)} shorts, {len(picks.flagged)} flagged")
            sleeve_picks_list.append(picks)

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

    # 5) brief
    from sca.live.notify import render_brief, send_email
    context = {
        "run_date": end,
        "sleeves": [picks_to_dict(p) for p in sleeve_picks_list],
        "live_vs_backtest": _live_vs_backtest_summary(track_path),
        "notes": notes or ["Run completed normally."],
        "limitations": LIMITATIONS,
    }
    html = render_brief(context)
    brief_path = out_dir / f"brief_{end}.html"
    brief_path.write_text(html, encoding="utf-8")
    (out_dir / "brief_latest.html").write_text(html, encoding="utf-8")
    (out_dir / f"brief_{end}.json").write_text(json.dumps(context, indent=2, default=str), encoding="utf-8")
    print(f"\nbrief saved: {brief_path}")

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
