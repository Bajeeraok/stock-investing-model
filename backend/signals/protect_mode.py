"""
Optional "protect" sizing for a stock the user already owns or wants to own.

10y same-stock backtest (548 S&P 500 stocks, 2017–2026, scripts/timing_rules_backtest.py):
half position below the stock's own 200-day average cut the median worst drawdown from
-52% to -41% (smaller drawdown for 93% of stocks) at a cost of ~2%/yr return; half position
when SPY is risk-off cut it to -47% for ~0.8%/yr. Neither raised return, so this is a
user choice (insurance), not a sell signal. Default guidance stays HOLD.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from signals.alpha.core_satellite import regime_series

EVIDENCE = {
    "source": "scripts/timing_rules_backtest.py (548 S&P 500 stocks, 2017-2026, median stock)",
    "buy_and_hold": {"cagr_pct": 8.0, "max_dd_pct": -52.3},
    "half_below_own_200d": {"cagr_pct": 5.9, "max_dd_pct": -40.8},
    "half_when_spy_risk_off": {"cagr_pct": 7.2, "max_dd_pct": -46.9},
}


def _state(close: pd.Series | None, ma_days: int, band_pct: float) -> tuple[bool | None, float | None]:
    if close is None or len(close.dropna()) < ma_days:
        return None, None
    c = close.dropna().astype(float)
    s = regime_series(c, ma_days=ma_days, band_pct=band_pct).dropna()
    if s.empty:
        return None, None
    sma = float(c.rolling(ma_days).mean().iloc[-1])
    gap = (float(c.iloc[-1]) / sma - 1.0) * 100.0 if sma > 0 else None
    return bool(s.iloc[-1] < 0.5), (round(gap, 2) if gap is not None else None)


def compute_protect_mode(
    close: pd.Series | None,
    spy_close: pd.Series | None = None,
    *,
    ma_days: int = 200,
    band_pct: float = 1.0,
    reduced_pct: int = 50,
) -> dict[str, Any]:
    stock_below, stock_gap = _state(close, ma_days, band_pct)
    spy_off, spy_gap = _state(spy_close, ma_days, band_pct)
    reasons: list[str] = []
    if stock_below:
        reasons.append(f"Stock is below its {ma_days}-day average ({stock_gap:+.1f}%).")
    if spy_off:
        reasons.append(f"Market risk-off: SPY below its {ma_days}-day average ({spy_gap:+.1f}%).")
    active = bool(stock_below or spy_off)
    if stock_below is None and spy_off is None:
        headline = "Protect mode unavailable (not enough price history)."
    elif active:
        headline = f"Protect mode would hold ~{reduced_pct}% of a full position. Default: hold."
    else:
        headline = "Protect mode: full position (trend and market OK)."
    return {
        "available": stock_below is not None or spy_off is not None,
        "active": active,
        "suggested_position_pct": reduced_pct if active else 100,
        "default_action": "HOLD",
        "stock_below_ma200": stock_below,
        "stock_gap_vs_ma200_pct": stock_gap,
        "spy_risk_off": spy_off,
        "spy_gap_vs_ma200_pct": spy_gap,
        "reasons": reasons,
        "headline": headline,
        "note": (
            "Optional insurance, not a sell signal. Over 2017–2026 on S&P 500 stocks, halving the position "
            "below the 200-day average cut the typical worst drop from about -52% to -41% but lowered "
            "return by about 2% a year; buy-and-hold earned more."
        ),
        "evidence": EVIDENCE,
    }
