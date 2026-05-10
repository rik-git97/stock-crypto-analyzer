"""Kite Connect (Zerodha) price loader.

This is the SDK path — needs KITE_API_KEY + KITE_ACCESS_TOKEN env vars. Access tokens
expire daily by SEBI mandate (no refresh token), so this loader is best-effort:
when env vars are missing or auth fails, it raises KiteUnavailable so the caller
can fall back to yfinance.

For interactive Kite use inside a Claude Code session, the kite MCP server is the
preferred path (no daily token ritual). Both produce the same end result; this
module exists for the automated/cron pipeline.
"""
from __future__ import annotations
import os
import time
from datetime import datetime, timedelta
import pandas as pd


class KiteUnavailable(RuntimeError):
    pass


def _client():
    api_key = os.environ.get("KITE_API_KEY")
    access_token = os.environ.get("KITE_ACCESS_TOKEN")
    if not api_key or not access_token:
        raise KiteUnavailable("KITE_API_KEY / KITE_ACCESS_TOKEN not set")
    try:
        from kiteconnect import KiteConnect
    except ImportError as e:
        raise KiteUnavailable(f"kiteconnect not installed: {e}")
    kc = KiteConnect(api_key=api_key)
    kc.set_access_token(access_token)
    try:
        kc.profile()
    except Exception as e:
        raise KiteUnavailable(f"Kite auth failed (token expired?): {e}")
    return kc


_INSTRUMENT_CACHE: dict[str, int] = {}


def _instrument_token(kc, exchange: str, tradingsymbol: str) -> int | None:
    key = f"{exchange}:{tradingsymbol}"
    if key in _INSTRUMENT_CACHE:
        return _INSTRUMENT_CACHE[key]
    try:
        instruments = kc.instruments(exchange)
    except Exception:
        return None
    for inst in instruments:
        sym = inst.get("tradingsymbol")
        if sym:
            _INSTRUMENT_CACHE[f"{exchange}:{sym}"] = inst["instrument_token"]
    return _INSTRUMENT_CACHE.get(key)


def _to_kite_symbol(yf_symbol: str) -> tuple[str, str]:
    """yfinance Indian tickers end in .NS (NSE) or .BO (BSE)."""
    if yf_symbol.endswith(".NS"):
        return ("NSE", yf_symbol[:-3])
    if yf_symbol.endswith(".BO"):
        return ("BSE", yf_symbol[:-3])
    return ("NSE", yf_symbol)


def load_prices_kite(tickers: list[str], start: str, end: str, sleep_ms: int = 200) -> pd.DataFrame:
    """Load daily OHLCV via Kite Connect. tickers in yfinance format (.NS/.BO suffix).
    Returns long-format DataFrame matching yfinance_loader.load_prices output."""
    kc = _client()
    from_dt = datetime.strptime(start, "%Y-%m-%d")
    to_dt = datetime.strptime(end, "%Y-%m-%d")
    frames: list[pd.DataFrame] = []
    for t in tickers:
        exch, ts = _to_kite_symbol(t)
        token = _instrument_token(kc, exch, ts)
        if token is None:
            continue
        try:
            bars = kc.historical_data(token, from_dt, to_dt, "day")
        except Exception as e:
            print(f"[kite] {t}: {e}")
            continue
        if not bars:
            continue
        df = pd.DataFrame(bars)
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df["ticker"] = t
        df["adj_close"] = df["close"]  # Kite EOD is already adjusted
        frames.append(df[["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]])
        if sleep_ms:
            time.sleep(sleep_ms / 1000)
    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"])
    return pd.concat(frames, ignore_index=True)
