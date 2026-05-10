"""Real-money concentrated-portfolio sizing for small-capital accounts.

Given a list of momentum picks (ticker + z-score + last_price), allocate a fixed
INR/USD capital across the top N names with whole-share rounding. Honest about
unaffordable names — drops any where 1 share > max_per_pick_pct of capital.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math


@dataclass
class PortfolioPosition:
    ticker: str
    z_score: float
    last_price: float
    shares: int
    allocated: float
    weight: float
    skipped_reason: str = ""


@dataclass
class CapitalPortfolio:
    capital: float
    currency: str
    target_n_positions: int
    positions: list[PortfolioPosition]
    skipped: list[PortfolioPosition]
    cash_residual: float
    deployed_pct: float


def build_capital_portfolio(
    picks: list[dict],
    capital: float = 50_000.0,
    currency: str = "INR",
    target_n_positions: int = 12,
    max_per_pick_pct: float = 0.12,   # cap any single name at 12% of capital
    min_per_pick_pct: float = 0.04,   # 4% floor — anything smaller, skip rather than fragment
) -> CapitalPortfolio:
    """Concentrate the top picks into target_n_positions equal-tilted by inverse-vol where available.

    Each pick must come in as a dict with keys: ticker, z_score, last_price, weight, realized_vol_30d.
    `weight` is the original momentum-portfolio weight (vol-targeted); we use it as a relative tilt.
    Output positions are integer-share, sorted by z_score desc.
    """
    target_per_pick = capital / target_n_positions

    candidates = sorted(
        [p for p in picks if p.get("last_price", 0) > 0],
        key=lambda p: -p.get("z_score", 0),
    )

    positions: list[PortfolioPosition] = []
    skipped: list[PortfolioPosition] = []
    used = 0.0

    for p in candidates:
        if len(positions) >= target_n_positions:
            break
        price = float(p["last_price"])
        if price <= 0:
            continue

        cap_for_this = min(target_per_pick, capital * max_per_pick_pct)
        shares = int(cap_for_this // price)
        cost = shares * price

        if shares == 0:
            skipped.append(PortfolioPosition(
                ticker=p["ticker"], z_score=float(p["z_score"]),
                last_price=price, shares=0, allocated=0.0, weight=0.0,
                skipped_reason=f"1 share = {price:.0f} > cap {cap_for_this:.0f}",
            ))
            continue

        if cost < capital * min_per_pick_pct:
            # Fragment too small — skip
            skipped.append(PortfolioPosition(
                ticker=p["ticker"], z_score=float(p["z_score"]),
                last_price=price, shares=shares, allocated=cost,
                weight=cost / capital,
                skipped_reason=f"position {cost:.0f} < min {capital*min_per_pick_pct:.0f}",
            ))
            continue

        if used + cost > capital:
            shares = int((capital - used) // price)
            cost = shares * price
            if shares == 0:
                continue

        positions.append(PortfolioPosition(
            ticker=p["ticker"], z_score=float(p["z_score"]),
            last_price=price, shares=shares, allocated=cost,
            weight=cost / capital,
        ))
        used += cost

    return CapitalPortfolio(
        capital=capital,
        currency=currency,
        target_n_positions=target_n_positions,
        positions=positions,
        skipped=skipped,
        cash_residual=max(0.0, capital - used),
        deployed_pct=used / capital if capital > 0 else 0.0,
    )


def portfolio_to_dict(p: CapitalPortfolio) -> dict:
    return {
        "capital": p.capital,
        "currency": p.currency,
        "target_n_positions": p.target_n_positions,
        "positions": [asdict(pos) for pos in p.positions],
        "skipped": [asdict(s) for s in p.skipped],
        "cash_residual": p.cash_residual,
        "deployed_pct": p.deployed_pct,
    }
