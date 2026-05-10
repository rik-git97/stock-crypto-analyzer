"""Show current top/bottom momentum picks per sleeve."""
from __future__ import annotations
import pandas as pd
from sca.universe.sp500 import fetch_sp500_tickers
from sca.prices.yfinance_loader import load_prices
from sca.signals.momentum_xs import compute_momentum_zscore


def main():
    print('Pulling current S&P 500...')
    tickers = fetch_sp500_tickers()
    df = load_prices(tickers, '2025-04-01', '2026-05-10')
    prices = df.pivot_table(index='date', columns='ticker', values='adj_close').sort_index()
    z = compute_momentum_zscore(prices)
    z_clean = z.dropna(how='all')
    if z_clean.empty:
        print('No signal computable on this window')
        return
    last_date = z_clean.index[-1]
    last = z_clean.iloc[-1].dropna().sort_values(ascending=False)
    n = len(last)
    print(f"\n=== Top 20 momentum picks (S&P 500) as of {last_date.date()} ===")
    print(f"Universe size with non-NaN signal: {n}")
    print()
    for t, s in last.head(20).items():
        print(f"  {t:10s}  z = {s:+.2f}")
    print(f"\n=== Bottom 10 (avoid / shorts in L/S) ===")
    for t, s in last.tail(10).items():
        print(f"  {t:10s}  z = {s:+.2f}")


if __name__ == '__main__':
    main()
