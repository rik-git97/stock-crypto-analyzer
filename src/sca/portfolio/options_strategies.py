"""Defined-risk vertical-spread suggester for small-capital options.

For ₹50K accounts, the only sane plays are vertical spreads (defined max-loss).
Picks the nearest expiry that is ≥ target_dte days out (default 90 days, so it
sits in the 3-6 month bucket) and the spread strikes around the underlying spot.
Returns concrete strike/premium/payoff for the user to actually trade.

Ideas generated:
- Bull call spread (bullish regime): long ATM call, short OTM call
- Bear put spread (bearish regime): long ATM put, short OTM put

Regime gate: caller passes the underlying's current price vs. its 200-DMA;
this module picks bull or bear, never both.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import date
import pandas as pd

LOT_SIZES = {"NIFTY": 75, "BANKNIFTY": 35, "FINNIFTY": 65}


@dataclass
class SpreadIdea:
    underlying: str
    direction: str               # "bullish" or "bearish"
    spread_type: str             # "bull_call" or "bear_put"
    expiry: str
    days_to_expiry: int
    long_strike: float
    short_strike: float
    long_premium: float
    short_premium: float
    net_debit_per_lot: float
    max_profit_per_lot: float
    max_loss_per_lot: float
    breakeven: float
    risk_reward: float
    lot_size: int
    capital_required: float
    spot: float
    notes: list[str]


def find_target_expiry(chain_df: pd.DataFrame, target_dte: int = 90, today: date | None = None) -> pd.Timestamp | None:
    if chain_df.empty:
        return None
    today = today or date.today()
    expiries = sorted(chain_df["expiry"].dropna().unique())
    candidates = [e for e in expiries if (pd.Timestamp(e).date() - today).days >= target_dte]
    if not candidates:
        # fallback: pick the longest-dated available
        return expiries[-1] if expiries else None
    return pd.Timestamp(candidates[0])


def _strike_near(chain_df: pd.DataFrame, expiry: pd.Timestamp, side: str, target: float) -> dict | None:
    sub = chain_df[(chain_df["expiry"] == expiry) & (chain_df["side"] == side)].copy()
    if sub.empty:
        return None
    sub["abs_diff"] = (sub["strike"] - target).abs()
    sub = sub.sort_values("abs_diff")
    row = sub.iloc[0]
    return row.to_dict()


def build_bull_call_spread(
    chain_df: pd.DataFrame, underlying: str, spot: float,
    target_dte: int = 90, otm_buffer_pct: float = 0.05,
) -> SpreadIdea | None:
    expiry = find_target_expiry(chain_df, target_dte)
    if expiry is None:
        return None
    long_target = spot                          # ATM
    short_target = spot * (1 + otm_buffer_pct)  # ~5% OTM
    long_leg = _strike_near(chain_df, expiry, "CE", long_target)
    short_leg = _strike_near(chain_df, expiry, "CE", short_target)
    if not long_leg or not short_leg:
        return None
    if long_leg["strike"] >= short_leg["strike"]:
        return None
    lot = LOT_SIZES.get(underlying, 1)
    debit_pp = float(long_leg["ltp"]) - float(short_leg["ltp"])
    net_debit_lot = debit_pp * lot
    if net_debit_lot <= 0:
        return None
    max_prof_lot = (float(short_leg["strike"]) - float(long_leg["strike"]) - debit_pp) * lot
    max_loss_lot = net_debit_lot
    breakeven = float(long_leg["strike"]) + debit_pp
    rr = max_prof_lot / max_loss_lot if max_loss_lot > 0 else float("inf")
    days_to_expiry = (pd.Timestamp(expiry).date() - date.today()).days
    notes = []
    if long_leg["iv"] == 0:
        notes.append("Long-leg IV = 0 (likely no recent trade — premium may be stale)")
    if int(long_leg.get("oi", 0)) < 1000:
        notes.append(f"Long-leg OI low ({int(long_leg['oi'])}) — liquidity risk")
    return SpreadIdea(
        underlying=underlying, direction="bullish", spread_type="bull_call",
        expiry=str(pd.Timestamp(expiry).date()), days_to_expiry=days_to_expiry,
        long_strike=float(long_leg["strike"]), short_strike=float(short_leg["strike"]),
        long_premium=float(long_leg["ltp"]), short_premium=float(short_leg["ltp"]),
        net_debit_per_lot=net_debit_lot,
        max_profit_per_lot=max_prof_lot, max_loss_per_lot=max_loss_lot,
        breakeven=breakeven, risk_reward=rr,
        lot_size=lot, capital_required=net_debit_lot, spot=spot, notes=notes,
    )


def build_bear_put_spread(
    chain_df: pd.DataFrame, underlying: str, spot: float,
    target_dte: int = 90, otm_buffer_pct: float = 0.05,
) -> SpreadIdea | None:
    expiry = find_target_expiry(chain_df, target_dte)
    if expiry is None:
        return None
    long_target = spot                          # ATM put
    short_target = spot * (1 - otm_buffer_pct)  # ~5% OTM put
    long_leg = _strike_near(chain_df, expiry, "PE", long_target)
    short_leg = _strike_near(chain_df, expiry, "PE", short_target)
    if not long_leg or not short_leg:
        return None
    if long_leg["strike"] <= short_leg["strike"]:
        return None
    lot = LOT_SIZES.get(underlying, 1)
    debit_pp = float(long_leg["ltp"]) - float(short_leg["ltp"])
    net_debit_lot = debit_pp * lot
    if net_debit_lot <= 0:
        return None
    max_prof_lot = (float(long_leg["strike"]) - float(short_leg["strike"]) - debit_pp) * lot
    max_loss_lot = net_debit_lot
    breakeven = float(long_leg["strike"]) - debit_pp
    rr = max_prof_lot / max_loss_lot if max_loss_lot > 0 else float("inf")
    days_to_expiry = (pd.Timestamp(expiry).date() - date.today()).days
    notes = []
    if int(long_leg.get("oi", 0)) < 1000:
        notes.append(f"Long-leg OI low ({int(long_leg['oi'])}) — liquidity risk")
    return SpreadIdea(
        underlying=underlying, direction="bearish", spread_type="bear_put",
        expiry=str(pd.Timestamp(expiry).date()), days_to_expiry=days_to_expiry,
        long_strike=float(long_leg["strike"]), short_strike=float(short_leg["strike"]),
        long_premium=float(long_leg["ltp"]), short_premium=float(short_leg["ltp"]),
        net_debit_per_lot=net_debit_lot,
        max_profit_per_lot=max_prof_lot, max_loss_per_lot=max_loss_lot,
        breakeven=breakeven, risk_reward=rr,
        lot_size=lot, capital_required=net_debit_lot, spot=spot, notes=notes,
    )


def regime_pick_spread(
    chain_df: pd.DataFrame, underlying: str, spot: float,
    sma200: float | None, target_dte: int = 90,
) -> SpreadIdea | None:
    """Pick bull or bear spread based on regime (spot vs 200-DMA)."""
    if sma200 is None or pd.isna(sma200):
        # No regime info — default to bull spread (long-bias) but flag uncertainty
        idea = build_bull_call_spread(chain_df, underlying, spot, target_dte)
        if idea:
            idea.notes.insert(0, "Regime data missing — defaulted to bull spread")
        return idea
    if spot >= sma200:
        return build_bull_call_spread(chain_df, underlying, spot, target_dte)
    return build_bear_put_spread(chain_df, underlying, spot, target_dte)
