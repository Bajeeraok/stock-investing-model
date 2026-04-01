"""
Earnings-window exclusion for backtests (short-horizon signal-to-noise).

Skips bars whose next earnings-related date (from FMP) falls within N calendar days ahead,
including the earnings day (0). Not point-in-time perfect (uses realized historical dates).
"""
from __future__ import annotations

import bisect
from typing import Any

import pandas as pd


def prepare_earnings_timestamps(date_strings: list[str]) -> list[pd.Timestamp]:
    """Sorted unique normalized timestamps from YYYY-MM-DD strings."""
    return sorted({pd.Timestamp(s).normalize() for s in date_strings if s})


def next_earnings_on_or_after(sorted_ts: list[pd.Timestamp], bar_ts: pd.Timestamp) -> pd.Timestamp | None:
    """Smallest earnings date >= bar calendar day (for event window around report day)."""
    if not sorted_ts:
        return None
    d = pd.Timestamp(bar_ts).normalize()
    i = bisect.bisect_left(sorted_ts, d)
    return sorted_ts[i] if i < len(sorted_ts) else None


def should_exclude_bar_for_earnings(
    bar_ts: pd.Timestamp,
    sorted_earnings_ts: list[pd.Timestamp],
    days_before: int,
) -> bool:
    """
    True if the next earnings date (on or after the bar) is within ``days_before`` calendar days.

    ``days_before`` = 5 means exclude if that next report falls within 0..5 days of the bar date.
    """
    if days_before <= 0 or not sorted_earnings_ts:
        return False
    nxt = next_earnings_on_or_after(sorted_earnings_ts, bar_ts)
    if nxt is None:
        return False
    d = pd.Timestamp(bar_ts).normalize()
    cal_days = int((nxt.normalize() - d).days)
    return 0 <= cal_days <= days_before


def load_earnings_exclusion_state(
    config: dict,
    ticker: str,
    close_index: pd.DatetimeIndex,
) -> tuple[list[pd.Timestamp] | None, dict[str, Any]]:
    """
    Load sorted earnings timestamps when exclusion is enabled and FMP returns dates.

    Returns (sorted_ts or None if exclusion inactive, meta dict for JSON).
    """
    bt = config.get("backtest") or {}
    ecfg = bt.get("earnings_exclusion") or {}
    meta: dict[str, Any] = {
        "enabled": bool(ecfg.get("enabled", False)),
        "days_before": int(ecfg.get("days_before") or 0),
        "dates_loaded": 0,
        "bars_skipped": 0,
        "source": None,
        "error": None,
        "note": None,
    }
    if not meta["enabled"] or meta["days_before"] <= 0:
        meta["note"] = "Earnings exclusion off (backtest.earnings_exclusion)."
        return None, meta

    sym = (ticker or "").upper().replace(".", "-").split("-")[0]
    if sym in _SKIP_EARNINGS_FETCH:
        meta["note"] = f"Ticker {sym} skipped (index/ETF — no earnings calendar)."
        return None, meta

    try:
        from signals.fmp_client import fetch_historical_earning_dates
    except Exception as e:
        meta["error"] = str(e)
        return None, meta

    start = str(close_index[0].date()) if len(close_index) else None
    end = str(close_index[-1].date()) if len(close_index) else None
    raw, err = fetch_historical_earning_dates(config, ticker, start_date=start, end_date=end)
    meta["error"] = err
    if not raw:
        meta["note"] = "No earnings dates from FMP — bars not filtered (add key or use equities)."
        return None, meta

    ts = prepare_earnings_timestamps(raw)
    meta["dates_loaded"] = len(ts)
    meta["source"] = "fmp"
    meta["note"] = (
        f"Excluding bars with next earnings in 0–{meta['days_before']} calendar days "
        f"({len(ts)} historical dates loaded; not full point-in-time calendar)."
    )
    return ts, meta


# Broad index / commodity ETFs — no earnings; avoid useless FMP calls
_SKIP_EARNINGS_FETCH = frozenset(
    {
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "VTI",
        "VOO",
        "GLD",
        "SLV",
        "USO",
        "TLT",
        "HYG",
        "LQD",
        "EEM",
        "XLF",
        "XLE",
        "SMH",
    }
)
