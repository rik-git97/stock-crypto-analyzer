"""India smart-money signal: net institutional flow from NSE block + bulk deals.

Logic:
- For each ticker, compute rolling 30-day net BUY notional minus net SELL notional from deals.
- Z-score within sleeve per day.
- Use as overlay on momentum (additive in z-space).

Honest caveats:
- This signal only has data going forward from when we start archiving. v1.5 backtest cannot use
  historical block/bulk data without a paid history feed. So this signal is forward-only initially.
- Many "Client Name" entries are not unique-stable (FII/MF intermediaries trade under various names).
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd


def load_deals_archive(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=["date", "symbol", "side", "qty", "price", "client", "kind", "notional"])
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "symbol"])
    return df


def smart_money_zscore(
    deals: pd.DataFrame,
    universe: list[str],
    as_of: pd.Timestamp,
    window_days: int = 30,
) -> pd.Series:
    """Return per-ticker z-score of net buy notional over [as_of - window, as_of].

    Tickers must be passed as plain NSE symbols (no .NS suffix) — deals archive uses raw symbols.
    """
    if deals.empty:
        return pd.Series(0.0, index=universe)
    start = as_of - pd.Timedelta(days=window_days)
    win = deals[(deals["date"] > start) & (deals["date"] <= as_of)].copy()
    if win.empty:
        return pd.Series(0.0, index=universe)
    win["signed_notional"] = win.apply(
        lambda r: r["notional"] if str(r.get("side", "")).startswith("B") else -r["notional"],
        axis=1,
    )
    net = win.groupby("symbol")["signed_notional"].sum()
    series = pd.Series(0.0, index=universe)
    common = net.index.intersection(universe)
    series.loc[common] = net.loc[common].values
    if series.std(ddof=0) == 0:
        return series * 0.0
    return (series - series.mean()) / series.std(ddof=0)


def smart_money_overlay_panel(
    deals: pd.DataFrame, prices: pd.DataFrame, window_days: int = 30,
) -> pd.DataFrame:
    """Build a date × ticker DataFrame of smart-money z-scores, aligned to prices index.
    `prices` columns are .NS-suffixed; deals archive uses bare symbols. We strip .NS for matching.
    """
    if prices.empty:
        return pd.DataFrame()
    bare_to_ns = {col[:-3] if col.endswith(".NS") else col: col for col in prices.columns}
    bare_universe = list(bare_to_ns.keys())
    out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    if deals.empty:
        return out
    # Compute weekly to keep it cheap (signal changes slowly enough)
    weekly_idx = prices.resample("W-MON").first().index.intersection(prices.index)
    for dt in weekly_idx:
        z_bare = smart_money_zscore(deals, bare_universe, pd.Timestamp(dt), window_days)
        for bare, ns_col in bare_to_ns.items():
            out.loc[dt, ns_col] = float(z_bare.get(bare, 0.0))
    out = out.replace(0.0, np.nan).ffill().fillna(0.0)
    return out
