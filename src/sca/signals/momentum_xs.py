"""Cross-sectional 12-1 momentum signal, z-scored within sleeve."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .base import Signal


def compute_momentum_zscore(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    if len(prices) < lookback + 1:
        return pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    raw = prices.shift(skip) / prices.shift(lookback) - 1.0
    mu = raw.mean(axis=1)
    sd = raw.std(axis=1, ddof=0)
    z = raw.sub(mu, axis=0).div(sd.replace(0, np.nan), axis=0)
    return z


class MomentumXS(Signal):
    name = "momentum_xs"

    def __init__(self, lookback: int = 252, skip: int = 21):
        self.lookback = lookback
        self.skip = skip

    def compute(self, prices: pd.DataFrame) -> pd.DataFrame:
        return compute_momentum_zscore(prices, self.lookback, self.skip)
