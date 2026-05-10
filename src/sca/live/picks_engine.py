"""Generate current momentum picks per sleeve from latest available data.

Returns a dataclass with: as_of date, top picks (with z-scores + sized weights), bottom picks (avoid),
and the universe size with computable signal."""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timedelta
from typing import Optional
import pandas as pd

from sca.signals.momentum_xs import compute_momentum_zscore, compute_combined_signal
from sca.portfolio.sizing import vol_target_weights
from sca.portfolio.risk_caps import apply_caps


@dataclass
class Pick:
    ticker: str
    z_score: float
    weight: float
    last_price: float = 0.0
    ret_1w: float = 0.0     # 5 trading-day return
    ret_1m: float = 0.0     # 21 trading-day
    ret_3m: float = 0.0     # 63 trading-day
    ret_6m: float = 0.0     # 126 trading-day
    ret_12m: float = 0.0    # 252 trading-day
    realized_vol_30d: float = 0.0   # annualized 30d vol
    days_listed: int = 0


def _compute_pick_metrics(ticker: str, prices: pd.DataFrame) -> dict:
    """Return real historical metrics from the price series. No synthesis."""
    if ticker not in prices.columns:
        return {}
    s = prices[ticker].dropna()
    if len(s) < 2:
        return {}
    last = float(s.iloc[-1])
    out = {
        "last_price": last,
        "days_listed": int(s.notna().sum()),
    }
    for label, n in (("ret_1w", 5), ("ret_1m", 21), ("ret_3m", 63), ("ret_6m", 126), ("ret_12m", 252)):
        if len(s) > n:
            past = float(s.iloc[-1 - n])
            if past > 0:
                out[label] = last / past - 1.0
    if len(s) >= 30:
        import numpy as np
        rets = s.pct_change().tail(30).dropna()
        if len(rets) >= 5 and rets.std(ddof=0) > 0:
            out["realized_vol_30d"] = float(rets.std(ddof=0) * np.sqrt(252))
    return out


@dataclass
class SleevePicks:
    sleeve: str
    asset_class: str
    as_of: str
    universe_size: int
    longs: list[Pick] = field(default_factory=list)
    shorts: list[Pick] = field(default_factory=list)
    flagged: list[str] = field(default_factory=list)  # data-quality red flags (e.g., outlier z)
    config_variant: str = "v2a_long_only"


def _flag_outliers(z_row: pd.Series, prices: pd.DataFrame, listing_min_days: int = 252) -> list[str]:
    """Flag tickers that look like data-quality issues:
    - z-score above 4.0 (likely IPO/spinoff with short price history inflating 12-1 return)
    - fewer than listing_min_days non-NaN bars in the price history
    """
    flagged = []
    for t in z_row.index:
        if abs(z_row.get(t, 0)) > 4.0:
            flagged.append(t)
            continue
        non_null = prices[t].notna().sum() if t in prices.columns else 0
        if non_null < listing_min_days:
            flagged.append(t)
    return flagged


def generate_sleeve_picks(
    sleeve: str, asset_class: str, prices: pd.DataFrame,
    market: pd.Series | None = None, sectors: dict[str, str] | None = None,
    top_pct: float = 0.20, bottom_pct: float = 0.20,
    target_vol_per_pos: float = 0.01, single_name_cap: float = 0.03, gross_cap: float = 2.0,
    long_only: bool = True,
    use_combined_signal: bool = False,
    overlay_signal: pd.DataFrame | None = None,
    overlay_weight: float = 0.0,
) -> SleevePicks:
    """Compute today's picks. By default uses plain 12-1 z-score (matches v2a config from the v2 grid).

    If use_combined_signal=True, uses 0.6 cross-sectional + 0.4 residual (sector-neutral if sectors given).
    If overlay_signal is provided, blends: combined_signal*(1-overlay_weight) + overlay*overlay_weight.
    """
    closes = prices.sort_index().dropna(how="all")
    if len(closes) < 260:
        return SleevePicks(sleeve, asset_class, str(closes.index[-1].date()) if len(closes) else "n/a", 0)

    if use_combined_signal:
        z = compute_combined_signal(closes, market=market, sectors=sectors, w_xs=0.6, w_residual=0.4)
    else:
        z = compute_momentum_zscore(closes)

    if overlay_signal is not None and overlay_weight > 0:
        ov = overlay_signal.reindex(z.index).reindex(z.columns, axis=1)
        z = z.fillna(0) * (1 - overlay_weight) + ov.fillna(0) * overlay_weight

    z_clean = z.dropna(how="all")
    if z_clean.empty:
        return SleevePicks(sleeve, asset_class, str(closes.index[-1].date()), 0)

    last_date = z_clean.index[-1]
    last = z_clean.iloc[-1].dropna().sort_values(ascending=False)
    flagged = _flag_outliers(last, closes)
    last_filtered = last.drop(flagged, errors="ignore")
    n = len(last_filtered)
    if n < 5:
        return SleevePicks(sleeve, asset_class, str(last_date.date()), n, flagged=flagged)

    n_top = max(1, int(n * top_pct))
    n_bot = max(1, int(n * bottom_pct))
    longs_idx = list(last_filtered.head(n_top).index)
    shorts_idx = list(last_filtered.tail(n_bot).index)

    rets = closes.pct_change().tail(60)
    w_long = vol_target_weights(rets[longs_idx], target_vol_per_pos) if longs_idx else pd.Series(dtype=float)
    if long_only:
        target = pd.Series(0.0, index=closes.columns)
        if len(w_long):
            target.loc[w_long.index] = w_long.values
    else:
        w_short = -vol_target_weights(rets[shorts_idx], target_vol_per_pos) if shorts_idx else pd.Series(dtype=float)
        target = pd.Series(0.0, index=closes.columns)
        if len(w_long): target.loc[w_long.index] = w_long.values
        if len(w_short): target.loc[w_short.index] = w_short.values
    target = apply_caps(target, single_name_cap, gross_cap)

    def _mk_pick(t: str) -> Pick:
        m = _compute_pick_metrics(t, closes)
        return Pick(
            ticker=t,
            z_score=float(last.get(t, 0.0)),
            weight=float(target.get(t, 0.0)),
            last_price=float(m.get("last_price", 0.0)),
            ret_1w=float(m.get("ret_1w", 0.0)),
            ret_1m=float(m.get("ret_1m", 0.0)),
            ret_3m=float(m.get("ret_3m", 0.0)),
            ret_6m=float(m.get("ret_6m", 0.0)),
            ret_12m=float(m.get("ret_12m", 0.0)),
            realized_vol_30d=float(m.get("realized_vol_30d", 0.0)),
            days_listed=int(m.get("days_listed", 0)),
        )

    longs_out = [_mk_pick(t) for t in longs_idx if target.get(t, 0.0) > 0]
    shorts_out = [_mk_pick(t) for t in shorts_idx if target.get(t, 0.0) < 0]

    return SleevePicks(
        sleeve=sleeve, asset_class=asset_class,
        as_of=str(last_date.date()),
        universe_size=n,
        longs=longs_out, shorts=shorts_out,
        flagged=flagged,
        config_variant="v2a_long_only" if long_only else "v1_long_short",
    )


def picks_to_dict(p: SleevePicks) -> dict:
    return {
        "sleeve": p.sleeve, "asset_class": p.asset_class, "as_of": p.as_of,
        "universe_size": p.universe_size, "config_variant": p.config_variant,
        "longs": [asdict(x) for x in p.longs],
        "shorts": [asdict(x) for x in p.shorts],
        "flagged": p.flagged,
    }
