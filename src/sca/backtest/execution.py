"""v1 honest cost model — flat-bps slippage + asset-class statutory charges."""
from __future__ import annotations

SLIPPAGE_US = 5.0
SLIPPAGE_IN = 5.0
STT_IN_DELIVERY_BPS = 10.0
EXCHANGE_GST_IN_BPS = 5.0
BORROW_BPS_PER_DAY = 50.0 / 365
CRYPTO_TAKER_BPS = 5.0


def trade_cost_bps(notional: float, asset_class: str, side: str) -> float:
    if asset_class == "US":
        return SLIPPAGE_US
    if asset_class == "IN":
        return SLIPPAGE_IN + STT_IN_DELIVERY_BPS + EXCHANGE_GST_IN_BPS
    if asset_class == "CRYPTO":
        return CRYPTO_TAKER_BPS
    raise ValueError(f"unknown asset_class {asset_class}")


def borrow_carry_bps_per_day(side: str) -> float:
    return BORROW_BPS_PER_DAY if side == "short" else 0.0
