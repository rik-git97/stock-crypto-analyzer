"""Walk-forward driver."""
from __future__ import annotations
import pandas as pd
from sca.backtest.engine import run_backtest


def walk_forward_run(
    prices: pd.DataFrame, asset_class: str,
    train_days: int = 252, test_days: int = 63, step_days: int = 63,
    **engine_kwargs,
) -> dict:
    folds = []
    oos_curves = []
    n = len(prices)
    start = train_days
    fold_id = 0
    while start + test_days <= n:
        window = prices.iloc[max(0, start - train_days): start + test_days]
        res = run_backtest(prices=window, asset_class=asset_class, **engine_kwargs)
        eq = res["equity"]
        if len(eq) == 0:
            start += step_days
            fold_id += 1
            continue
        oos = eq.iloc[-test_days:] if len(eq) >= test_days else eq
        if oos_curves:
            scale = oos_curves[-1].iloc[-1] / oos.iloc[0]
            oos = oos * scale
        oos_curves.append(oos)
        folds.append({
            "fold": fold_id,
            "start": str(prices.index[start].date()),
            "end": str(prices.index[min(start + test_days, n) - 1].date()),
        })
        start += step_days
        fold_id += 1
    if not oos_curves:
        return {"oos_equity": pd.Series(dtype=float), "folds": []}
    oos_equity = pd.concat(oos_curves)
    oos_equity = oos_equity[~oos_equity.index.duplicated(keep="last")]
    return {"oos_equity": oos_equity, "folds": folds}
