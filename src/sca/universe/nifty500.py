"""Current Nifty 500 constituents from NSE's published CSV."""
from __future__ import annotations

import io
import requests
import pandas as pd

NIFTY500_CSV = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"


def fetch_nifty500_tickers(timeout: int = 30) -> list[str]:
    headers = {
        "User-Agent": "Mozilla/5.0 sca/0.1",
        "Accept": "text/csv,application/csv,*/*",
    }
    resp = requests.get(NIFTY500_CSV, headers=headers, timeout=timeout)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    symbols = df["Symbol"].astype(str).str.strip().tolist()
    return [f"{s}.NS" for s in symbols if s]
