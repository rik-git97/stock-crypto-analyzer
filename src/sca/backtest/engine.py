"""Weekly-rebalance backtest engine.

v2 features (additive, all backwards-compatible):
- accept precomputed signal DataFrame (signal_df) for sector-neutral / residual variants
- long_only: skip shorts entirely
- trend_filter_window: per-name SMA filter — long requires price > SMA, short requires price < SMA
- regime_filter_index: gate gross exposure when index < 200-DMA
"""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd

from sca.signals.momentum_xs import compute_momentum_zscore
from sca.portfolio.sizing import vol_target_weights
from sca.portfolio.risk_caps import apply_caps
from sca.backtest.execution import trade_cost_bps, borrow_carry_bps_per_day


def run_backtest(
    prices: pd.DataFrame,
    asset_class: str,
    top_pct: float = 0.20,
    bottom_pct: float = 0.20,
    target_vol_per_pos: float = 0.01,
    single_name_cap: float = 0.03,
    gross_cap: float = 2.0,
    atr_period: int = 14,
    atr_mult: float = 1.0,
    rebalance: str = "W-MON",
    initial_equity: float = 100_000.0,
    regime_filter_index: pd.Series | None = None,
    regime_sma: int = 200,
    signal_df: pd.DataFrame | None = None,
    long_only: bool = False,
    trend_filter_window: int | None = None,
) -> dict[str, Any]:
    closes = prices.copy().sort_index().astype(float)
    closes = closes.dropna(how="all")
    rets = closes.pct_change().fillna(0.0)
    z = signal_df.reindex(closes.index).reindex(closes.columns, axis=1) if signal_df is not None else compute_momentum_zscore(closes)

    if trend_filter_window:
        sma = closes.rolling(trend_filter_window).mean()
    else:
        sma = None

    rebal_dates = closes.resample(rebalance).first().index.intersection(closes.index)

    held = pd.Series(0.0, index=closes.columns)
    trail_stops: dict[str, float] = {}
    trail_dirs: dict[str, int] = {}
    entry_prices: dict[str, float] = {}
    entry_atr: dict[str, float] = {}

    atr_proxy = (rets.rolling(atr_period).std().fillna(0.0)) * closes
    if regime_filter_index is not None:
        regime_sma_series = regime_filter_index.rolling(regime_sma).mean()
    else:
        regime_sma_series = None

    equity = pd.Series(index=closes.index, dtype=float)
    equity.iloc[0] = initial_equity
    weights_history: list[pd.Series] = []
    trades: list[dict] = []

    for i, dt in enumerate(closes.index):
        if i > 0:
            day_ret = float((held * rets.loc[dt]).sum())
            short_gross = float(sum(abs(w) for w in held if w < 0))
            borrow = borrow_carry_bps_per_day("short") / 1e4 * short_gross
            equity.iloc[i] = equity.iloc[i - 1] * (1 + day_ret - borrow)

        breached: list[str] = []
        for t, w in held.items():
            if w == 0:
                continue
            px = closes.at[dt, t]
            if pd.isna(px):
                continue
            stop = trail_stops.get(t)
            if stop is None:
                continue
            direction = trail_dirs[t]
            if (direction == 1 and px <= stop) or (direction == -1 and px >= stop):
                breached.append(t)
                continue
            ep = entry_prices[t]; ea = entry_atr[t]
            if ea > 0:
                if direction == 1 and px >= ep + ea:
                    trail_stops[t] = max(stop, px - ea * atr_mult)
                elif direction == -1 and px <= ep - ea:
                    trail_stops[t] = min(stop, px + ea * atr_mult)
        for t in breached:
            w = held[t]
            cost_bps = trade_cost_bps(abs(w) * float(equity.iloc[i]), asset_class,
                                      "long" if trail_dirs[t] == 1 else "short") / 1e4
            equity.iloc[i] = float(equity.iloc[i]) * (1 - cost_bps * abs(w))
            trades.append({"date": dt, "ticker": t, "side": "exit_stop",
                           "weight": float(w), "price": float(closes.at[dt, t])})
            held[t] = 0.0
            trail_stops.pop(t, None); trail_dirs.pop(t, None)
            entry_prices.pop(t, None); entry_atr.pop(t, None)

        if dt in rebal_dates:
            zrow = z.loc[dt].dropna()
            if len(zrow) >= 10:
                gross_eff = gross_cap
                if regime_sma_series is not None and dt in regime_sma_series.index:
                    sma_val = regime_sma_series.loc[dt]
                    spot = regime_filter_index.loc[dt] if dt in regime_filter_index.index else None
                    if spot is not None and not pd.isna(sma_val) and spot < sma_val:
                        gross_eff = gross_cap * 0.5

                n = len(zrow)
                n_top = max(1, int(n * top_pct))
                longs = zrow.nlargest(n_top).index

                if sma is not None:
                    px_today = closes.loc[dt]
                    sma_today = sma.loc[dt]
                    longs = [t for t in longs if not pd.isna(sma_today.get(t)) and px_today.get(t, np.nan) > sma_today.get(t)]

                lookback_window = rets.loc[:dt].tail(60)
                if len(longs) > 0:
                    w_long_raw = vol_target_weights(lookback_window[list(longs)], target_vol_per_pos)
                else:
                    w_long_raw = pd.Series(dtype=float)

                if long_only:
                    target = pd.Series(0.0, index=closes.columns)
                    if len(w_long_raw):
                        target.loc[w_long_raw.index] = w_long_raw.values
                else:
                    n_bot = max(1, int(n * bottom_pct))
                    shorts = zrow.nsmallest(n_bot).index
                    if sma is not None:
                        px_today = closes.loc[dt]
                        sma_today = sma.loc[dt]
                        shorts = [t for t in shorts if not pd.isna(sma_today.get(t)) and px_today.get(t, np.nan) < sma_today.get(t)]
                    w_short_raw = -vol_target_weights(lookback_window[list(shorts)], target_vol_per_pos) if len(shorts) else pd.Series(dtype=float)
                    target = pd.Series(0.0, index=closes.columns)
                    if len(w_long_raw):
                        target.loc[w_long_raw.index] = w_long_raw.values
                    if len(w_short_raw):
                        target.loc[w_short_raw.index] = w_short_raw.values

                target = apply_caps(target, single_name_cap, gross_eff)

                turnover = float((target - held).abs().sum())
                cost_bps = trade_cost_bps(turnover * float(equity.iloc[i]), asset_class, "long") / 1e4
                equity.iloc[i] = float(equity.iloc[i]) * (1 - cost_bps * turnover)

                for t in target.index:
                    new_w = float(target[t]); old_w = float(held.get(t, 0.0))
                    if new_w == 0 and old_w == 0:
                        continue
                    sign_changed = (new_w != 0) and (np.sign(new_w) != np.sign(old_w) or old_w == 0)
                    if sign_changed:
                        px = float(closes.at[dt, t])
                        a = float(atr_proxy.at[dt, t]) if t in atr_proxy.columns else px * 0.02
                        if pd.isna(a) or a <= 0:
                            a = px * 0.02
                        direction = int(np.sign(new_w))
                        entry_prices[t] = px; entry_atr[t] = a
                        trail_dirs[t] = direction
                        trail_stops[t] = px - a * atr_mult if direction == 1 else px + a * atr_mult
                        trades.append({"date": dt, "ticker": t, "side": "entry",
                                       "weight": new_w, "price": px})
                    elif new_w == 0 and old_w != 0:
                        trades.append({"date": dt, "ticker": t, "side": "exit_signal",
                                       "weight": old_w, "price": float(closes.at[dt, t])})
                        trail_stops.pop(t, None); trail_dirs.pop(t, None)
                        entry_prices.pop(t, None); entry_atr.pop(t, None)
                held = target

        weights_history.append(held.rename(dt).copy())

    weights_df = pd.DataFrame(weights_history).fillna(0.0)
    return {
        "equity": equity.dropna(),
        "weights": weights_df,
        "trades": pd.DataFrame(trades),
    }
