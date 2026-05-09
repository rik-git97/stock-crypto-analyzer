"""Risk caps for position weights."""
from __future__ import annotations
import pandas as pd


def apply_caps(weights: pd.Series, single_name_cap: float = 0.03, gross_cap: float = 2.0) -> pd.Series:
    w = weights.clip(lower=-single_name_cap, upper=single_name_cap)
    gross = w.abs().sum()
    if gross > gross_cap and gross > 0:
        w = w * (gross_cap / gross)
    return w
