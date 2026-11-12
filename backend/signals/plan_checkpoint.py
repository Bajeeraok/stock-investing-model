"""
Entry bands and stops refresh at set times during the session, not on every price tick.

A band rebuilt from the live price slides with it (a falling stock drags its swing band down and is
never "reached"). So while the market is open, today's partial daily bar is pinned to the price at
the latest checkpoint: the previous close until 10:30 ET (10:00 on gap days), then 10:30, 12:30, 14:30 and 15:30. Live
price, alerts and day-range odds stay live; only the plan levels hold still between checkpoints.

Volatile days: between checkpoints the plan also rebuilds early (from 10:00) when price breaks that plan's
stop or moves more than one normal day's move from the price the plan was built at, at most once per 30 min.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any, Callable

import numpy as np
import pandas as pd

CHECKPOINTS_ET: tuple[tuple[int, int], ...] = ((10, 30), (12, 30), (14, 30), (15, 30))
# Gap days only: an open or 10:00 price over one normal day's move from the prior close makes prev-close levels stale.
GAP_CHECKPOINT_ET: tuple[int, int] = (10, 0)
GAP_SIGMAS = 1.0

EVENT_SIGMAS = 1.0
EVENT_COOLDOWN_MIN = 30

_BAR_CACHE: dict[tuple[str, str], dict[str, float] | None] = {}
_SESSION_CACHE: dict[str, tuple[float, pd.DataFrame | None]] = {}
# Stop of the plan built at each base: (ticker, base key) -> highest Scout/Swing stop.
_PLAN_STOPS: dict[tuple[str, str], float] = {}


def _base_key(now: datetime, meta: dict[str, Any] | None) -> str:
    return (meta or {}).get("checkpoint") or f"{now.date()}:prev"


def remember_plan_stop(ticker: str, meta: dict[str, Any] | None, horizons: dict | None, now: datetime | None = None) -> None:
    """Called after a build so a later stop break can trigger an early rebuild."""
    now = now or _now_et()
    if not in_regular_session(now):
        return
    stops = [float(h["stop_loss"]) for k in ("short", "medium")
             if isinstance(h := (horizons or {}).get(k), dict) and h.get("stop_loss")]
    if stops:
        _PLAN_STOPS[(ticker.upper(), _base_key(now, meta))] = max(stops)
        if len(_PLAN_STOPS) > 5000:
            _PLAN_STOPS.clear()


def _session_bars(ticker: str, now: datetime) -> pd.DataFrame | None:
    """Today's 5-min bars (ET index), cached for a minute."""
    import time as _t

    hit = _SESSION_CACHE.get(ticker.upper())
    if hit and _t.time() - hit[0] < 60:
        return hit[1]
    m = None
    try:
        import yfinance as yf

        m = yf.Ticker(ticker).history(period="1d", interval="5m", auto_adjust=False)
        if m is not None and not m.empty:
            idx = m.index.tz_convert("America/New_York") if m.index.tz is not None else m.index
            m = m.set_axis(idx)
            m = m[m.index.date == now.date()]
    except Exception:
        m = None
    _SESSION_CACHE[ticker.upper()] = (_t.time(), m)
    return m


def find_plan_event(
    bars: pd.DataFrame | None,
    *,
    now: datetime,
    base_time: datetime,
    base_px: float,
    sigma: float,
    stop_for: Callable[[str], float | None],
    base_key: str,
) -> dict[str, Any] | None:
    """Latest early rebuild after base_time: a bar breaking the stop or closing over one normal move away."""
    if bars is None or bars.empty or not base_px or sigma <= 0:
        return None
    start = max(base_time, now.replace(hour=GAP_CHECKPOINT_ET[0], minute=GAP_CHECKPOINT_ET[1], second=0, microsecond=0))
    ev = None
    last_ev = None
    for t, row in bars.iterrows():
        end = t + pd.Timedelta(minutes=5)
        if end <= start or end > now:
            continue
        if last_ev is not None and end < last_ev + pd.Timedelta(minutes=EVENT_COOLDOWN_MIN):
            continue
        stop = stop_for(base_key)
        px = float(row["Close"])
        reason = None
        if stop and float(row["Low"]) <= stop:
            reason = "stop break"
        elif abs(px / base_px - 1) > EVENT_SIGMAS * sigma:
            reason = "big move"
        if reason:
            upto = bars[bars.index + pd.Timedelta(minutes=5) <= end]
            ev = {"time": end.to_pydatetime(), "reason": reason, "open": float(upto["Open"].iloc[0]),
                  "close": px, "high": float(upto["High"].max()), "low": float(upto["Low"].min())}
            last_ev, base_px = end, px
            base_key = end.to_pydatetime().isoformat(timespec="minutes")
    return ev


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
                out = {"open": float(m["Open"].iloc[0]), "close": float(m["Close"].iloc[-1]),
                       "high": float(m["High"].max()), "low": float(m["Low"].min())}
    except Exception:
        out = None
    if out is not None:
        _BAR_CACHE[key] = out
    return out


def gap_size(prior: pd.Series, open_px: float | None) -> tuple[float, float] | None:
    """(|gap| as a fraction, normal daily move from a 20-day EWMA of prior closes)."""
    if open_px is None or prior is None or len(prior) < 22:
        return None
    r = np.log(prior.astype(float)).diff().dropna()
    sigma = float(np.sqrt((r**2).ewm(span=20, adjust=False).mean().iloc[-1]))
    prev = float(prior.iloc[-1])
    if prev <= 0 or sigma <= 0:
        return None
    return abs(open_px / prev - 1), sigma


def is_gap_day(prior: pd.Series, *prices: float | None) -> bool:
    """True if any of the prices (the open, the 10:00 price) sits over one normal day's move from the prior close."""
    for px in prices:
        g = gap_size(prior, px)
        if g and g[0] > GAP_SIGMAS * g[1]:
            return True
    return False


def pin_session_bar(
    ticker: str,
    close: pd.Series | None,
    volume: pd.Series | None,
    df: pd.DataFrame | None,
    *,
    now: datetime | None = None,
    bars_fn: Callable[[str, datetime, tuple[int, int]], dict[str, float] | None] | None = None,
    session_fn: Callable[[str, datetime], pd.DataFrame | None] | None = None,
) -> tuple[pd.Series | None, pd.Series | None, pd.DataFrame | None, dict[str, Any] | None]:
    """Return (close, volume, df, levels_as_of). Outside the session, data is returned unchanged."""
    now = now or _now_et()
    if close is None or close.empty or not in_regular_session(now):
        return close, volume, df, None
    last_d = pd.Timestamp(close.index[-1]).date()
    if last_d != now.date():
        return close, volume, df, None
    fn = bars_fn or _bars_until
    cp = latest_checkpoint(now)
    bar = fn(ticker, now, cp) if cp else None
    gap = False
    event_reason = None
    if cp is None and (now.hour, now.minute) >= GAP_CHECKPOINT_ET:
        early = fn(ticker, now, GAP_CHECKPOINT_ET)
        if early and is_gap_day(close.iloc[:-1], early.get("open"), early.get("close")):
            cp, bar, gap = GAP_CHECKPOINT_ET, early, True
    if session_fn is not None or bars_fn is None:
        try:
            g = gap_size(close.iloc[:-1], float(close.iloc[-2]) if len(close) >= 2 else None)
            if cp is not None and bar is not None:
                base_t, base_px = now.replace(hour=cp[0], minute=cp[1], second=0, microsecond=0), bar["close"]
                key = now.replace(hour=cp[0], minute=cp[1], second=0, microsecond=0).isoformat(timespec="minutes")
            else:
                base_t, base_px, key = now.replace(hour=9, minute=30, second=0, microsecond=0), float(close.iloc[-2]), f"{now.date()}:prev"
            ev = find_plan_event((session_fn or _session_bars)(ticker, now), now=now, base_time=base_t, base_px=base_px,
                                 sigma=g[1] if g else 0.0, stop_for=lambda k: _PLAN_STOPS.get((ticker.upper(), k)),
                                 base_key=key)
        except Exception:
            ev = None
        if ev:
            et = ev["time"]
            cp, bar, gap = (et.hour, et.minute), ev, False
            event_reason = ev["reason"]
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
        "label": _fmt(cp) + (" (gap open)" if gap else f" ({event_reason})" if event_reason else ""),
        "event": event_reason,
        "checkpoint": now.replace(hour=cp[0], minute=cp[1], second=0, microsecond=0).isoformat(timespec="minutes"),
        "price": round(bar["close"], 2),
        "next": _fmt(later[0]) if later else "after the close",
        "gap": gap,
    }
