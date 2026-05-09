"""Daily OHLCV via CCXT (Binance USDM perps)."""
from __future__ import annotations

import time
import pandas as pd
import ccxt


def load_crypto_ohlcv(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    ex = ccxt.binanceusdm()
    ex.load_markets()
    since_ms = int(pd.Timestamp(start).timestamp() * 1000)
    end_ms = int(pd.Timestamp(end).timestamp() * 1000)
    frames: list[pd.DataFrame] = []
    for sym in symbols:
        all_rows: list[list] = []
        cursor = since_ms
        while cursor < end_ms:
            try:
                rows = ex.fetch_ohlcv(sym, timeframe="1d", since=cursor, limit=1000)
            except Exception as e:
                print(f"[ccxt] {sym} failed at {cursor}: {e}")
                break
            if not rows:
                break
            all_rows.extend(rows)
            new_cursor = rows[-1][0] + 24 * 3600 * 1000
            if new_cursor <= cursor:
                break
            cursor = new_cursor
            time.sleep(max(ex.rateLimit, 50) / 1000)
        if not all_rows:
            continue
        df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.normalize()
        df["ticker"] = sym
        df = df[(df["date"] >= start) & (df["date"] < end)]
        df = df.drop_duplicates(subset=["date", "ticker"])
        frames.append(df[["date", "ticker", "open", "high", "low", "close", "volume"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "ticker", "open", "high", "low", "close", "volume"]
    )
