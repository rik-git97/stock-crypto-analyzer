"""Vol-targeted sizing."""
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def vol_target_weights(returns: pd.DataFrame, target_vol_per_pos: float = 0.01, lookback: int = 30) -> pd.Series:
    vol = returns.tail(lookback).std(ddof=0) * np.sqrt(TRADING_DAYS)
    vol = vol.replace(0, np.nan)
    return (target_vol_per_pos / vol).fillna(0.0)
