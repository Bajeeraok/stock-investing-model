"""
session_vwap.py — Real single-session VWAP from free intraday bars (yfinance).

Distinct from two other VWAP-shaped things already in this codebase, on purpose:
  - thrive_phase2/intraday.py::IntradayFeed._compute_vwap() is a rolling 5-day cumulative
    VWAP for Phase 2's own short-term classifier — not the resets-at-open, single-session
    VWAP every trading platform (Fidelity included) means by "VWAP".
  - api/ticker_detail.py's `vwap` local variable is a stand-in (`= current_price`) that
    feeds horizon_entry_calculator.py's ST-band math under that name. This module's output
    must never be confused with or substituted into that variable — it's a separate,
    display-only reference figure.

Standard VWAP definition: cumulative(typical_price * volume) / cumulative(volume), reset at
the start of each trading session. Uses 5-minute bars for the most recent session only.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def compute_session_vwap(ticker: str) -> dict | None:
    """
    Fetch today's session bars and compute the running VWAP as of the latest bar.

    Returns None (not an error dict — this is a purely optional reference figure, not a
    scored signal layer) when there's no fresh intraday data: outside market hours with no
    completed session yet, delisted/halted tickers, or yfinance unavailable.

    Returns dict with:
      vwap                — float, volume-weighted average price for the session so far
      close_vs_vwap_pct    — float, % the latest price is above (+) or below (-) VWAP
      bars_used            — int, number of 5-minute bars the VWAP was computed over
    """
    try:
        import yfinance as yf
    except ImportError:
        return None

    import logging as _logging
    _yf_logger = _logging.getLogger("yfinance")
    _prev_level = _yf_logger.level
    _yf_logger.setLevel(_logging.CRITICAL)

    try:
        df = yf.Ticker(ticker).history(period="1d", interval="5m")
    except Exception as exc:
        logger.debug("session_vwap fetch failed for %s: %s", ticker, exc)
        return None
    finally:
        _yf_logger.setLevel(_prev_level)

    if df is None or df.empty or len(df) < 3:
        return None
    if not {"High", "Low", "Close", "Volume"}.issubset(df.columns):
        return None

    total_volume = float(df["Volume"].sum())
    if total_volume <= 0:
        return None

    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    cum_vwap = (typical * df["Volume"]).cumsum() / df["Volume"].cumsum()
    vwap = float(cum_vwap.iloc[-1])
    if vwap <= 0:
        return None

    close = float(df["Close"].iloc[-1])
    return {
        "vwap": round(vwap, 2),
        "close_vs_vwap_pct": round((close - vwap) / vwap * 100.0, 2),
        "bars_used": int(len(df)),
    }
