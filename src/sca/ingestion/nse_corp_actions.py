"""NSE block + bulk deals daily archive — free official feed.

Block deals: single-day large negotiated trades (≥ 5 lakh shares OR ≥ 10 cr value).
Bulk deals: trades > 0.5% of listed shares of a company, reported same day.

Both are smart-money flow indicators — institutional/HNI activity that often precedes/confirms
sustained moves.

Endpoints (CSV):
- https://archives.nseindia.com/content/equities/bulk.csv  (current day)
- https://archives.nseindia.com/content/equities/block.csv (current day)
- Historical via date-stamped URLs but NSE rotates these and gates with cookies; for the v1
  signal we accumulate daily snapshots locally and build a rolling history that way.
"""
from __future__ import annotations
import io
from pathlib import Path
import pandas as pd
import requests

NSE_BULK_CURRENT = "https://archives.nseindia.com/content/equities/bulk.csv"
NSE_BLOCK_CURRENT = "https://archives.nseindia.com/content/equities/block.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/csv,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/",
}


def _safe_csv(url: str, timeout: int = 30) -> pd.DataFrame:
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get("https://www.nseindia.com/", timeout=timeout)
    except Exception:
        pass
    r = s.get(url, timeout=timeout)
    r.raise_for_status()
    text = r.text
    if not text.strip():
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(text))


def fetch_bulk_deals_current() -> pd.DataFrame:
    df = _safe_csv(NSE_BULK_CURRENT)
    if df.empty:
        return df
    df.columns = [c.strip() for c in df.columns]
    return df


def fetch_block_deals_current() -> pd.DataFrame:
    df = _safe_csv(NSE_BLOCK_CURRENT)
    if df.empty:
        return df
    df.columns = [c.strip() for c in df.columns]
    return df


def _normalize_row(row: pd.Series, kind: str) -> dict | None:
    """Map raw NSE columns to a stable schema. Column names vary slightly across endpoints."""
    cols = {c.lower(): c for c in row.index}
    def g(*names):
        for n in names:
            if n.lower() in cols:
                v = row[cols[n.lower()]]
                if pd.notna(v):
                    return v
        return None
    sym = g("Symbol", "SYMBOL")
    if sym is None:
        return None
    qty = g("Quantity Traded", "QtyTraded", "Quantity")
    px = g("Trade Price / Wght. Avg. Price", "Price", "Trade Price")
    side = g("Buy/Sell", "BuySell", "BuySellFlag")
    client = g("Client Name", "ClientName", "Client")
    deal_date = g("Date", "DealDate", "Trade Date", "TradeDate")
    try:
        qty = int(str(qty).replace(",", "")) if qty is not None else None
    except Exception:
        qty = None
    try:
        px = float(str(px).replace(",", "")) if px is not None else None
    except Exception:
        px = None
    return {
        "date": str(deal_date) if deal_date is not None else None,
        "symbol": str(sym).strip().upper(),
        "side": str(side).strip().upper() if side else None,
        "qty": qty,
        "price": px,
        "client": str(client).strip() if client else None,
        "kind": kind,
    }


def deals_normalized(bulk: pd.DataFrame, block: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for kind, df in [("bulk", bulk), ("block", block)]:
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            n = _normalize_row(r, kind)
            if n:
                rows.append(n)
    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "side", "qty", "price", "client", "kind"])
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out["date"], errors="coerce", dayfirst=True)
    out["notional"] = (out["qty"].fillna(0) * out["price"].fillna(0)).astype(float)
    return out


def append_to_archive(deals: pd.DataFrame, archive_path: Path) -> Path:
    """Append today's deals to a long Parquet archive, dedup by (date, symbol, client, side, qty)."""
    archive_path = Path(archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        prev = pd.read_parquet(archive_path)
        merged = pd.concat([prev, deals], ignore_index=True)
    else:
        merged = deals
    if merged.empty:
        return archive_path
    merged = merged.drop_duplicates(subset=["date", "symbol", "client", "side", "qty", "kind"]).reset_index(drop=True)
    merged.to_parquet(archive_path, index=False)
    return archive_path


def fetch_today_and_archive(archive_path: str | Path = "output/live/nse_deals.parquet") -> pd.DataFrame:
    bulk = fetch_bulk_deals_current()
    block = fetch_block_deals_current()
    deals = deals_normalized(bulk, block)
    if deals.empty:
        return deals
    append_to_archive(deals, Path(archive_path))
    return deals
