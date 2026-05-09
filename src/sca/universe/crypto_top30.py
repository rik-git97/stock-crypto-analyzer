"""Top 30 USDT-perp markets on Binance by 24h quote volume (proxy for 30d ADV)."""
from __future__ import annotations

import ccxt


def fetch_crypto_top30(n: int = 30) -> list[str]:
    ex = ccxt.binanceusdm()
    markets = ex.load_markets()
    perps = [
        s for s, m in markets.items()
        if m.get("swap") and m.get("quote") == "USDT" and m.get("active")
    ]
    tickers = ex.fetch_tickers(perps)
    rows = []
    for s in perps:
        t = tickers.get(s)
        if not t:
            continue
        qv = t.get("quoteVolume") or 0
        rows.append((s, qv))
    rows.sort(key=lambda r: r[1], reverse=True)
    return [s for s, _ in rows[:n]]
