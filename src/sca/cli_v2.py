"""v2 runner: variant grid per sleeve to honestly evaluate which fixes help.

Variants (per sleeve):
- v1_baseline:        plain 12-1 z, long/short
- v2a_long_only:      plain 12-1 z, long-only
- v2b_residual:       0.6 plain + 0.4 residual, long-only
- v2c_sector_neutral: residual + sector-neutral z, long-only (US only — needs sector map)
- v2d_full:           v2c + per-name 200-day trend filter (long only above 200-DMA)

Reports all variants in one comparison table per sleeve.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, traceback
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

LIMITATIONS = [
    "Universe is current-membership only — survivorship bias present (PIT reconstruction deferred to Phase 1.5).",
    "Cost model: flat-bps slippage + fees, no Almgren-Chriss impact, flat 50 bps/yr borrow.",
    "Walk-forward only — DSR / SPA / CPCV deferred to Phase 1.5.",
    "X / FinTwit excluded.",
    "ATR stops use close-to-close.",
    "Sector map: GICS sectors from Wikipedia (US only). India/crypto: no sector neutralization in v2.",
]


def _run_id(config: dict) -> str:
    payload = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _wide(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(index="date", columns="ticker", values=value_col, aggfunc="last").sort_index()


def _build_variants(prices: pd.DataFrame, market: pd.Series | None, sectors: dict[str, str] | None):
    from sca.signals.momentum_xs import compute_momentum_zscore, compute_combined_signal

    variants = {}
    variants["v1_baseline"] = {
        "signal_df": compute_momentum_zscore(prices),
        "long_only": False, "trend_filter_window": None,
    }
    variants["v2a_long_only"] = {
        "signal_df": compute_momentum_zscore(prices),
        "long_only": True, "trend_filter_window": None,
    }
    if market is not None:
        variants["v2b_residual"] = {
            "signal_df": compute_combined_signal(prices, market=market, sectors=None,
                                                  w_xs=0.6, w_residual=0.4),
            "long_only": True, "trend_filter_window": None,
        }
        if sectors:
            variants["v2c_sector_neutral"] = {
                "signal_df": compute_combined_signal(prices, market=market, sectors=sectors,
                                                      w_xs=0.6, w_residual=0.4),
                "long_only": True, "trend_filter_window": None,
            }
            variants["v2d_full"] = {
                "signal_df": compute_combined_signal(prices, market=market, sectors=sectors,
                                                      w_xs=0.6, w_residual=0.4),
                "long_only": True, "trend_filter_window": 200,
            }
        else:
            variants["v2d_full"] = {
                "signal_df": compute_combined_signal(prices, market=market, sectors=None,
                                                      w_xs=0.6, w_residual=0.4),
                "long_only": True, "trend_filter_window": 200,
            }
    return variants


def _run_variants(sleeve: str, prices: pd.DataFrame, asset_class: str, market: pd.Series | None,
                  sectors: dict[str, str] | None, args):
    from sca.backtest.engine import run_backtest
    from sca.backtest.stats import tearsheet_metrics
    from sca.reporting.tearsheet import build_tearsheet, render_html

    if prices.empty or prices.shape[1] < 5 or prices.shape[0] < 260:
        print(f"  [skip] {sleeve}: insufficient data shape={prices.shape}")
        return {}

    print(f"  Universe: {prices.shape[1]} names, {prices.shape[0]} bars", flush=True)
    variants = _build_variants(prices, market, sectors)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {}

    for variant_name, vparams in variants.items():
        print(f"\n  --- {variant_name} ---", flush=True)
        cfg = {
            "sleeve": sleeve, "asset_class": asset_class, "variant": variant_name,
            "top_pct": 0.20, "bottom_pct": 0.20,
            "target_vol_per_pos": 0.01, "single_name_cap": 0.03, "gross_cap": 2.0,
            "atr_period": 14, "atr_mult": 1.0, "rebalance": "W-MON",
            "long_only": vparams["long_only"],
            "trend_filter_window": vparams["trend_filter_window"],
            "start": args.start, "end": args.end,
        }
        try:
            res = run_backtest(
                prices=prices, asset_class=asset_class,
                top_pct=cfg["top_pct"], bottom_pct=cfg["bottom_pct"],
                target_vol_per_pos=cfg["target_vol_per_pos"],
                single_name_cap=cfg["single_name_cap"], gross_cap=cfg["gross_cap"],
                atr_period=cfg["atr_period"], atr_mult=cfg["atr_mult"],
                rebalance=cfg["rebalance"],
                regime_filter_index=market,
                signal_df=vparams["signal_df"],
                long_only=vparams["long_only"],
                trend_filter_window=vparams["trend_filter_window"],
            )
            run_id = _run_id(cfg)
            ts = build_tearsheet(res["equity"], f"{sleeve.upper()}_{variant_name}", run_id, cfg, LIMITATIONS)
            (out_dir / f"v2_tearsheet_{sleeve}_{variant_name}_{run_id}.html").write_text(render_html(ts), encoding="utf-8")
            (out_dir / f"v2_tearsheet_{sleeve}_{variant_name}_{run_id}.json").write_text(json.dumps(ts, indent=2, default=str), encoding="utf-8")
            res["equity"].to_csv(out_dir / f"v2_equity_{sleeve}_{variant_name}_{run_id}.csv")
            summary[variant_name] = {"run_id": run_id, "metrics": ts["metrics"]}
            m = ts["metrics"]
            print(f"    total={m['total_return']*100:+.2f}%  CAGR={m['cagr']*100:+.2f}%  "
                  f"Sharpe={m['sharpe']:+.2f} CI[{m['sharpe_ci95'][0]:+.2f},{m['sharpe_ci95'][1]:+.2f}]  "
                  f"MaxDD={m['max_drawdown']*100:+.2f}%", flush=True)
        except Exception as e:
            print(f"    ERROR {variant_name}: {e}", flush=True)
            traceback.print_exc()
            summary[variant_name] = {"error": str(e)}
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["backtest"])
    p.add_argument("--start", default=(date.today() - timedelta(days=750)).isoformat())
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--output", default="output")
    p.add_argument("--sleeves", default="us,in,crypto")
    p.add_argument("--limit-universe", type=int, default=0)
    args = p.parse_args(argv)

    sleeves = [s.strip() for s in args.sleeves.split(",") if s.strip()]
    big_summary: dict = {}

    for sleeve in sleeves:
        try:
            print(f"\n=== {sleeve.upper()} sleeve ===", flush=True)
            market = None
            sectors = None
            if sleeve == "us":
                from sca.universe.sp500 import fetch_sp500_tickers, fetch_sp500_sectors
                from sca.prices.yfinance_loader import load_prices
                tickers = fetch_sp500_tickers()
                sectors = fetch_sp500_sectors()
                if args.limit_universe:
                    tickers = tickers[: args.limit_universe]
                print(f"  fetched {len(tickers)} S&P 500 tickers, {len(sectors)} sectors")
                df = load_prices(tickers, args.start, args.end)
                prices = _wide(df, "adj_close")
                spy_df = load_prices(["SPY"], "2023-01-01", args.end)
                market = (spy_df.pivot_table(index="date", columns="ticker", values="adj_close")["SPY"]
                          if not spy_df.empty else None)
                ac = "US"
            elif sleeve == "in":
                from sca.universe.nifty500 import fetch_nifty500_tickers
                from sca.prices.yfinance_loader import load_prices
                try:
                    tickers = fetch_nifty500_tickers()
                except Exception as e:
                    print(f"  [warn] NSE list fetch failed: {e}; using Nifty 50 fallback")
                    tickers = [t + ".NS" for t in [
                        "RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","HINDUNILVR","SBIN","BHARTIARTL","ITC","LT",
                        "KOTAKBANK","BAJFINANCE","HCLTECH","ASIANPAINT","MARUTI","AXISBANK","SUNPHARMA","TITAN","ULTRACEMCO","WIPRO",
                        "NESTLEIND","ONGC","NTPC","POWERGRID","TATASTEEL","BAJAJFINSV","M&M","TECHM","HDFCLIFE","SBILIFE",
                        "ADANIENT","ADANIPORTS","COALINDIA","GRASIM","JSWSTEEL","DRREDDY","INDUSINDBK","BRITANNIA","DIVISLAB","CIPLA",
                        "HINDALCO","TATAMOTORS","BPCL","EICHERMOT","HEROMOTOCO","UPL","BAJAJ-AUTO","APOLLOHOSP","SHRIRAMFIN","LTIM",
                    ]]
                if args.limit_universe:
                    tickers = tickers[: args.limit_universe]
                print(f"  fetched {len(tickers)} Indian tickers")
                df = load_prices(tickers, args.start, args.end)
                prices = _wide(df, "adj_close")
                # Nifty index proxy: NIFTYBEES.NS or ^NSEI
                idx_df = load_prices(["^NSEI"], "2023-01-01", args.end)
                market = (idx_df.pivot_table(index="date", columns="ticker", values="adj_close")["^NSEI"]
                          if not idx_df.empty else None)
                ac = "IN"
            elif sleeve == "crypto":
                from sca.universe.crypto_top30 import fetch_crypto_top30
                from sca.prices.ccxt_loader import load_crypto_ohlcv
                syms = fetch_crypto_top30()
                if args.limit_universe:
                    syms = syms[: args.limit_universe]
                print(f"  fetched {len(syms)} crypto perps")
                df = load_crypto_ohlcv(syms, args.start, args.end)
                prices = _wide(df, "close")
                # BTC as market proxy
                market = prices["BTC/USDT:USDT"] if "BTC/USDT:USDT" in prices.columns else prices.iloc[:, 0]
                ac = "CRYPTO"
            else:
                continue

            big_summary[sleeve] = _run_variants(sleeve, prices, ac, market, sectors, args)
        except Exception as e:
            print(f"ERROR sleeve {sleeve}: {e}", file=sys.stderr)
            traceback.print_exc()
            big_summary[sleeve] = {"error": str(e)}

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "v2_summary.json").write_text(json.dumps(big_summary, indent=2, default=str), encoding="utf-8")
    print("\n=== V2 SUMMARY ===")
    for sleeve, variants in big_summary.items():
        if isinstance(variants, dict) and "error" not in variants:
            print(f"\n{sleeve.upper()}:")
            print(f"  {'variant':<22} {'total':>9} {'CAGR':>8} {'Sharpe':>8} {'CI lo':>7} {'CI hi':>7} {'MaxDD':>8}")
            for v, info in variants.items():
                if "metrics" not in info:
                    print(f"  {v:<22} ERROR")
                    continue
                m = info["metrics"]
                print(f"  {v:<22} {m['total_return']*100:>+8.2f}% {m['cagr']*100:>+7.2f}% "
                      f"{m['sharpe']:>+8.2f} {m['sharpe_ci95'][0]:>+7.2f} {m['sharpe_ci95'][1]:>+7.2f} "
                      f"{m['max_drawdown']*100:>+7.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
