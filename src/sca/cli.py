"""End-to-end CLI: pull universes, prices, run momentum backtest per sleeve, write tearsheets.

US sleeve was removed by user request — focus narrowed to India (Nifty 500) + crypto (top 30 perps)."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

LIMITATIONS_V1 = [
    "Universe is current-membership only — survivorship bias present (PIT reconstruction deferred to Phase 1.5).",
    "Plain 12-1 momentum, not residual + sector-neutral (deferred).",
    "Cost model: flat-bps slippage + fees, no Almgren-Chriss impact, flat 50 bps/yr borrow.",
    "Vol-targeted sizing without Ledoit-Wolf shrinkage (deferred).",
    "Walk-forward only — DSR / SPA / CPCV deferred to Phase 1.5.",
    "X / FinTwit excluded from this backtest.",
    "ATR stops use close-to-close, not intraday — slightly optimistic vs. real fills.",
]


def _run_id(config: dict) -> str:
    payload = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _wide_close(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return (
        df.pivot_table(index="date", columns="ticker", values=value_col, aggfunc="last")
          .sort_index()
    )


def _run_sleeve(sleeve: str, prices: pd.DataFrame, asset_class: str, args, regime_index: pd.Series | None = None):
    from sca.backtest.engine import run_backtest
    from sca.reporting.tearsheet import build_tearsheet, render_html

    if prices.empty or prices.shape[1] < 5 or prices.shape[0] < 260:
        print(f"  [skip] {sleeve}: insufficient data shape={prices.shape}")
        return None

    cfg = {
        "sleeve": sleeve, "asset_class": asset_class,
        "top_pct": 0.20, "bottom_pct": 0.20,
        "target_vol_per_pos": 0.01, "single_name_cap": 0.03, "gross_cap": 2.0,
        "atr_period": 14, "atr_mult": 1.0, "rebalance": "W-MON",
        "start": args.start, "end": args.end,
    }
    print(f"  Universe: {prices.shape[1]} names, {prices.shape[0]} bars", flush=True)

    res = run_backtest(
        prices=prices,
        asset_class=asset_class,
        top_pct=cfg["top_pct"], bottom_pct=cfg["bottom_pct"],
        target_vol_per_pos=cfg["target_vol_per_pos"],
        single_name_cap=cfg["single_name_cap"], gross_cap=cfg["gross_cap"],
        atr_period=cfg["atr_period"], atr_mult=cfg["atr_mult"],
        rebalance=cfg["rebalance"],
        regime_filter_index=regime_index,
    )
    run_id = _run_id(cfg)
    ts = build_tearsheet(res["equity"], sleeve.upper(), run_id, cfg, LIMITATIONS_V1)
    html = render_html(ts)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"tearsheet_{sleeve}_{run_id}.html").write_text(html, encoding="utf-8")
    (out / f"tearsheet_{sleeve}_{run_id}.json").write_text(json.dumps(ts, indent=2, default=str), encoding="utf-8")
    res["equity"].to_csv(out / f"equity_{sleeve}_{run_id}.csv")
    if not res["trades"].empty:
        res["trades"].to_csv(out / f"trades_{sleeve}_{run_id}.csv", index=False)
    print(json.dumps(ts["metrics"], indent=2), flush=True)
    return {"run_id": run_id, "metrics": ts["metrics"]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["backtest"])
    p.add_argument("--start", default=(date.today() - timedelta(days=400)).isoformat())
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--output", default="output")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sleeves", default="in,crypto")
    p.add_argument("--limit-universe", type=int, default=0)
    args = p.parse_args(argv)

    sleeves = [s.strip() for s in args.sleeves.split(",") if s.strip()]
    summary: dict = {}

    for sleeve in sleeves:
        try:
            print(f"\n=== {sleeve.upper()} sleeve ===", flush=True)
            regime = None

            if args.dry_run:
                import numpy as np
                rng = np.random.default_rng(0)
                idx = pd.bdate_range(args.start, args.end)
                if len(idx) < 260:
                    idx = pd.bdate_range(end=args.end, periods=300)
                cols = [f"X{i}" for i in range(20)]
                rets = rng.normal(0.0005, 0.02, (len(idx), 20))
                prices = pd.DataFrame(100 * np.exp(rets.cumsum(axis=0)), index=idx, columns=cols)
                ac = "IN"
                summary[sleeve] = _run_sleeve(sleeve, prices, ac, args, regime)
                continue

            if sleeve == "in":
                from sca.universe.nifty500 import fetch_nifty500_tickers
                from sca.prices.yfinance_loader import load_prices
                try:
                    tickers = fetch_nifty500_tickers()
                except Exception as e:
                    print(f"  [warn] NSE list fetch failed: {e}; falling back to Nifty 50 proxy")
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
                prices = _wide_close(df, "adj_close")
                ac = "IN"

            elif sleeve == "crypto":
                from sca.universe.crypto_top30 import fetch_crypto_top30
                from sca.prices.ccxt_loader import load_crypto_ohlcv
                syms = fetch_crypto_top30()
                if args.limit_universe:
                    syms = syms[: args.limit_universe]
                print(f"  fetched {len(syms)} crypto perps")
                df = load_crypto_ohlcv(syms, args.start, args.end)
                prices = _wide_close(df, "close")
                ac = "CRYPTO"
            else:
                print(f"  [skip] unknown sleeve {sleeve}")
                continue

            summary[sleeve] = _run_sleeve(sleeve, prices, ac, args, regime)

        except Exception as e:
            print(f"ERROR in sleeve {sleeve}: {e}", file=sys.stderr)
            traceback.print_exc()
            summary[sleeve] = {"error": str(e)}

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
