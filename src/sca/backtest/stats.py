"""Performance statistics with bootstrap CIs."""
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def sharpe(returns: pd.Series, rf: float = 0.0) -> float:
    r = returns.dropna()
    if len(r) < 2 or r.std(ddof=1) == 0:
        return float("nan")
    return float((r.mean() - rf / TRADING_DAYS) / r.std(ddof=1) * np.sqrt(TRADING_DAYS))


def sortino(returns: pd.Series, rf: float = 0.0) -> float:
    r = returns.dropna() - rf / TRADING_DAYS
    downside = r[r < 0]
    if len(downside) < 2 or downside.std(ddof=1) == 0:
        return float("nan")
    return float(r.mean() / downside.std(ddof=1) * np.sqrt(TRADING_DAYS))


def max_drawdown(equity: pd.Series) -> float:
    if len(equity) == 0:
        return float("nan")
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def calmar(equity: pd.Series) -> float:
    rets = equity.pct_change().dropna()
    if len(rets) == 0 or equity.iloc[0] <= 0:
        return float("nan")
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (TRADING_DAYS / max(len(rets), 1)) - 1
    mdd = abs(max_drawdown(equity))
    return float(cagr / mdd) if mdd > 0 else float("nan")


def bootstrap_sharpe_ci(
    returns: pd.Series, n: int = 1000, block: int = 20, alpha: float = 0.05, seed: int = 0,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    r = returns.dropna().to_numpy()
    if len(r) < block * 2:
        return float("nan"), float("nan")
    n_blocks = max(1, len(r) // block)
    samples = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, len(r) - block, size=n_blocks)
        sample = np.concatenate([r[j : j + block] for j in idx])
        sd = sample.std(ddof=1)
        samples[i] = (sample.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    return float(np.quantile(samples, alpha / 2)), float(np.quantile(samples, 1 - alpha / 2))


def tearsheet_metrics(equity: pd.Series) -> dict:
    rets = equity.pct_change().dropna()
    if len(rets) == 0 or len(equity) < 2:
        return {
            "n_days": 0, "total_return": float("nan"), "cagr": float("nan"),
            "ann_vol": float("nan"), "sharpe": float("nan"), "sharpe_ci95": [float("nan"), float("nan")],
            "sortino": float("nan"), "max_drawdown": float("nan"), "calmar": float("nan"),
            "win_rate_daily": float("nan"),
        }
    lo, hi = bootstrap_sharpe_ci(rets)
    return {
        "n_days": int(len(rets)),
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "cagr": float((equity.iloc[-1] / equity.iloc[0]) ** (TRADING_DAYS / len(rets)) - 1),
        "ann_vol": float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        "sharpe": sharpe(rets),
        "sharpe_ci95": [lo, hi],
        "sortino": sortino(rets),
        "max_drawdown": max_drawdown(equity),
        "calmar": calmar(equity),
        "win_rate_daily": float((rets > 0).mean()),
    }
