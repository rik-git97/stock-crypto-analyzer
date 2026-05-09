"""Build tearsheet dict + HTML render."""
from __future__ import annotations
import pandas as pd
from sca.backtest.stats import tearsheet_metrics


def build_tearsheet(equity: pd.Series, sleeve: str, run_id: str,
                    config: dict, limitations: list[str]) -> dict:
    m = tearsheet_metrics(equity)
    monthly = equity.resample("ME").last().pct_change().dropna() if len(equity) > 0 else pd.Series(dtype=float)
    return {
        "run_id": run_id,
        "sleeve": sleeve,
        "config": config,
        "metrics": m,
        "equity_curve": [{"date": d.strftime("%Y-%m-%d"), "equity": float(v)} for d, v in equity.items()],
        "monthly_returns": [{"month": d.strftime("%Y-%m"), "return": float(v)} for d, v in monthly.items()],
        "limitations": limitations,
    }


def render_html(tearsheet: dict) -> str:
    from sca.reporting.html_renderer import render
    return render(tearsheet)
