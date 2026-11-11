"""
Entry bands and stops refresh at set times during the session, not on every price tick.

A band rebuilt from the live price slides with it (a falling stock drags its swing band down and is
never "reached"). So while the market is open, today's partial daily bar is pinned to the price at
the latest checkpoint: the previous close until 10:30 ET, then 10:30, 12:30, 14:30 and 15:30. Live
price, alerts and day-range odds stay live; only the plan levels hold still between checkpoints.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any, Callable

import pandas as pd

CHECKPOINTS_ET: tuple[tuple[int, int], ...] = ((10, 30), (12, 30), (14, 30), (15, 30))

_BAR_CACHE: dict[tuple[str, str], dict[str, float] | None] = {}


def _now_et() -> datetime:
    from signals.time_et import now_et

    return now_et()


def in_regular_session(now: datetime) -> bool:
    from signals.market_calendar import is_nyse_holiday

    return now.weekday() < 5 and not is_nyse_holiday(now.date()) and time(9, 30) <= now.time() < time(16, 0)


def latest_checkpoint(now: datetime) -> tuple[int, int] | None:
    done = [c for c in CHECKPOINTS_ET if (now.hour, now.minute) >= c]
    return done[-1] if done else None


def _fmt(c: tuple[int, int]) -> str:
    h, m = c
    return f"{(h - 1) % 12 + 1}:{m:02d} {'AM' if h < 12 else 'PM'} ET"


def _bars_until(ticker: str, now: datetime, cp: tuple[int, int]) -> dict[str, float] | None:
    """Today's session close/high/low from 5-min bars that finished before the checkpoint."""
    key = (ticker.upper(), f"{now.date()}T{cp[0]:02d}{cp[1]:02d}")
    if key in _BAR_CACHE:
        return _BAR_CACHE[key]
    out = None
    try:
        import yfinance as yf

        m = yf.Ticker(ticker).history(period="1d", interval="5m", auto_adjust=False)
        if m is not None and not m.empty:
            idx = m.index.tz_convert("America/New_York") if m.index.tz is not None else m.index
            m = m.set_axis(idx)
            cut = now.replace(hour=cp[0], minute=cp[1], second=0, microsecond=0)
            # A 5-min bar stamped t covers [t, t+5m); keep bars that closed by the checkpoint.
            m = m[(m.index.date == now.date()) & (m.index + pd.Timedelta(minutes=5) <= cut)]
            if not m.empty:
                out = {"close": float(m["Close"].iloc[-1]), "high": float(m["High"].max()),
                       "low": float(m["Low"].min())}
    except Exception:
        out = None
    if out is not None:
        _BAR_CACHE[key] = out
    return out


def pin_session_bar(
    ticker: str,
    close: pd.Series | None,
    volume: pd.Series | None,
    df: pd.DataFrame | None,
    *,
    now: datetime | None = None,
    bars_fn: Callable[[str, datetime, tuple[int, int]], dict[str, float] | None] | None = None,
) -> tuple[pd.Series | None, pd.Series | None, pd.DataFrame | None, dict[str, Any] | None]:
    """Return (close, volume, df, levels_as_of). Outside the session, data is returned unchanged."""
    now = now or _now_et()
    if close is None or close.empty or not in_regular_session(now):
        return close, volume, df, None
    last_d = pd.Timestamp(close.index[-1]).date()
    if last_d != now.date():
        return close, volume, df, None
    cp = latest_checkpoint(now)
    bar = (bars_fn or _bars_until)(ticker, now, cp) if cp else None
    if bar is None:
        # Before 10:30 (or no intraday bars): plan levels come from the previous close.
        prev = close.index[-2] if len(close) >= 2 else None
        close = close.iloc[:-1]
        if volume is not None and len(volume) and pd.Timestamp(volume.index[-1]).date() == now.date():
            volume = volume.iloc[:-1]
        if df is not None and len(df) and pd.Timestamp(df.index[-1]).date() == now.date():
            df = df.iloc[:-1]
        label = pd.Timestamp(prev).strftime("%b %-d close") if prev is not None else "previous close"
        return close, volume, df, {"label": label, "checkpoint": None, "next": _fmt(CHECKPOINTS_ET[0])}
    close = close.copy()
    close.iloc[-1] = bar["close"]
    if df is not None and len(df) and pd.Timestamp(df.index[-1]).date() == now.date():
        df = df.copy()
        j = df.index[-1]
        df.loc[j, "close"] = bar["close"]
        if "high" in df.columns:
            df.loc[j, "high"] = bar["high"]
        if "low" in df.columns:
            df.loc[j, "low"] = bar["low"]
    later = [c for c in CHECKPOINTS_ET if c > cp]
    return close, volume, df, {
        "label": _fmt(cp),
        "checkpoint": now.replace(hour=cp[0], minute=cp[1], second=0, microsecond=0).isoformat(timespec="minutes"),
        "price": round(bar["close"], 2),
        "next": _fmt(later[0]) if later else "after the close",
    }
