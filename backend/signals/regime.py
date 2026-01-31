"""
Regime (UP / NEUTRAL / DOWN) from composite score.
Uses configurable bands so alerts match what you trade on.
"""
from __future__ import annotations


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
