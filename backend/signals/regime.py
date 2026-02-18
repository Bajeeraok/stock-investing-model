"""
Regime (UP / NEUTRAL / DOWN) from composite score or MA-based (UP / UP-HV / DOWN / SIDE).
Uses configurable bands so alerts match what you trade on.
"""
from __future__ import annotations


def get_regime_ma(
    price: float,
    ma50: float | None,
    ma200: float | None,
    vol_20: float | None,
    vol_70_pct: float | None,
) -> str:
    """
    MA-based regime from price vs MA50 vs MA200 and 20d volatility.
    Spec: price > MA50 > MA200 + vol <= p70 -> UP; vol > p70 -> UP-HV;
    price < MA50 < MA200 -> DOWN; else SIDE.
    """
    if ma200 is None or ma200 <= 0 or ma50 is None or ma50 <= 0:
        return "SIDE"
    if price > ma50 > ma200:
        if vol_20 is not None and vol_70_pct is not None and vol_20 > vol_70_pct:
            return "UP-HV"  # high-vol uptrend
        return "UP"
    if price < ma50 < ma200:
        return "DOWN"
    return "SIDE"


def _ma_regime_to_display(ma_regime: str) -> str:
    """Map MA regime to display regime (UP/NEUTRAL/DOWN) for backward compatibility."""
    if ma_regime in ("UP", "UP-HV"):
        return "UP"
    if ma_regime == "DOWN":
        return "DOWN"
    return "NEUTRAL"


def get_regime(composite_buy: float, up_min: float = 60, down_max: float = 40) -> str:
    """
    UP: composite_buy >= up_min
    DOWN: composite_buy <= down_max
    else NEUTRAL
    """
    if composite_buy >= up_min:
        return "UP"
    if composite_buy <= down_max:
        return "DOWN"
    return "NEUTRAL"


def get_signal(composite_buy: float, buy_min: float = 70, sell_max: float = 30) -> str:
    """BUY / HOLD / SELL from composite and bands."""
    if composite_buy >= buy_min:
        return "BUY"
    if composite_buy <= sell_max:
        return "SELL"
    return "HOLD"
