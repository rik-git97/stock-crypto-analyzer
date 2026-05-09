"""Bulk daily OHLCV loader via yfinance. Returns long-format DataFrame."""
from __future__ import annotations

import pandas as pd
import yfinance as yf


def load_prices(tickers: list[str], start: str, end: str, batch: int = 50) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for i in range(0, len(tickers), batch):
        chunk = tickers[i : i + batch]
        try:
            raw = yf.download(
                chunk, start=start, end=end,
                auto_adjust=False, progress=False, threads=True, group_by="ticker",
            )
        except Exception as e:
            print(f"[yfinance] batch {i} failed: {e}")
            continue
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            for t in chunk:
                if t not in raw.columns.get_level_values(0):
                    continue
                sub = raw[t].dropna(how="all").reset_index()
                if sub.empty:
                    continue
                sub["ticker"] = t
                frames.append(sub)
        else:
            sub = raw.dropna(how="all").reset_index()
            if sub.empty:
                continue
            sub["ticker"] = chunk[0]
            frames.append(sub)
    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"])
    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Adj Close": "adj_close", "Volume": "volume",
    })
    if "adj_close" not in out.columns and "close" in out.columns:
        out["adj_close"] = out["close"]
    out["date"] = pd.to_datetime(out["date"])
    keep = [c for c in ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"] if c in out.columns]
    return out[keep]
