"""Cross-sectional momentum signals: plain 12-1, residual, sector-neutral, combined."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .base import Signal


def _z_within(s: pd.Series) -> pd.Series:
    if len(s) < 2:
        return s * 0.0
    sd = s.std(ddof=0)
    if sd == 0 or pd.isna(sd):
        return s * 0.0
    return (s - s.mean()) / sd


def compute_raw_momentum(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """Plain 12-1 return. Returns DataFrame of raw returns, no z-scoring."""
    if len(prices) < lookback + 1:
        return pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    return prices.shift(skip) / prices.shift(lookback) - 1.0


def compute_momentum_zscore(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """Plain 12-1 momentum, z-scored cross-sectionally per row."""
    raw = compute_raw_momentum(prices, lookback, skip)
    return raw.apply(_z_within, axis=1)


def compute_residual_momentum(
    prices: pd.DataFrame, market: pd.Series,
    lookback: int = 252, skip: int = 21, beta_window: int = 60,
) -> pd.DataFrame:
    """Per-name beta-residual 12-1 return.
    For each name: regress recent daily returns on market over beta_window;
    compute name 12-1 return minus beta * market 12-1 return."""
    if len(prices) < lookback + 1:
        return pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    rets = prices.pct_change()
    mkt_rets = market.pct_change().reindex(rets.index)
    var_m = mkt_rets.rolling(beta_window).var()
    cov = rets.rolling(beta_window).cov(mkt_rets)
    beta = cov.div(var_m, axis=0)
    raw_name = compute_raw_momentum(prices, lookback, skip)
    raw_mkt = market.shift(skip) / market.shift(lookback) - 1.0
    raw_mkt = raw_mkt.reindex(raw_name.index)
    return raw_name.sub(beta.mul(raw_mkt, axis=0))


def sector_neutral_zscore(raw: pd.DataFrame, sectors: dict[str, str]) -> pd.DataFrame:
    """Z-score within sector per row; tickers without sector mapping are z-scored across the whole row."""
    out = raw.copy() * np.nan
    by_sector: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for col in raw.columns:
        sec = sectors.get(col)
        if sec:
            by_sector.setdefault(sec, []).append(col)
        else:
            unmapped.append(col)
    for sec, cols in by_sector.items():
        if len(cols) < 3:
            unmapped.extend(cols)
            continue
        sub = raw[cols]
        out[cols] = sub.sub(sub.mean(axis=1), axis=0).div(sub.std(axis=1, ddof=0).replace(0, np.nan), axis=0)
    if unmapped:
        sub = raw[unmapped]
        out[unmapped] = sub.sub(sub.mean(axis=1), axis=0).div(sub.std(axis=1, ddof=0).replace(0, np.nan), axis=0)
    return out


def compute_combined_signal(
    prices: pd.DataFrame, market: pd.Series | None = None,
    sectors: dict[str, str] | None = None,
    lookback: int = 252, skip: int = 21, beta_window: int = 60,
    w_xs: float = 0.6, w_residual: float = 0.4,
) -> pd.DataFrame:
    """Combined signal: w_xs * sector-neutral 12-1 z + w_residual * sector-neutral residual z.
    If market is None, residual term is dropped (weights renormalized).
    If sectors is None, sector neutralization is skipped (plain cross-sectional z)."""
    raw_xs = compute_raw_momentum(prices, lookback, skip)
    if sectors:
        z_xs = sector_neutral_zscore(raw_xs, sectors)
    else:
        z_xs = raw_xs.apply(_z_within, axis=1)

    if market is None:
        return z_xs

    raw_res = compute_residual_momentum(prices, market, lookback, skip, beta_window)
    if sectors:
        z_res = sector_neutral_zscore(raw_res, sectors)
    else:
        z_res = raw_res.apply(_z_within, axis=1)

    total = w_xs + w_residual
    return (w_xs * z_xs + w_residual * z_res) / total


class MomentumXS(Signal):
    name = "momentum_xs"

    def __init__(self, lookback: int = 252, skip: int = 21):
        self.lookback = lookback
        self.skip = skip

    def compute(self, prices: pd.DataFrame) -> pd.DataFrame:
        return compute_momentum_zscore(prices, self.lookback, self.skip)
