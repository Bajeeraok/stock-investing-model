"""Per-level touch odds for entry-band levels from the ticker's own daily history
(up to 10 years; a 2018-2026 test on 20 tickers showed 10y calibrated better than 2y or 5y).

For a level d% below spot, measures how often this stock's low reached d% below a
given day's close within the horizon window, and the median sessions until it did.
"""
from __future__ import annotations

from typing import Any

import numpy as np

WINDOW_SESSIONS = {"short": 20, "medium": 63, "long": 126}
MIN_SAMPLES = 120


def level_touch_stats(closes: np.ndarray, lows: np.ndarray, drop_pct: float, window: int) -> tuple[float, int | None, int] | None:
    n = len(closes) - window
    if n < MIN_SAMPLES or drop_pct < 0:
        return None
    from numpy.lib.stride_tricks import sliding_window_view

    fwd_lows = sliding_window_view(lows[1:], window)[:n]
    thresh = closes[:n] * (1.0 - drop_pct / 100.0)
    hit = fwd_lows <= thresh[:, None]
    any_hit = hit.any(axis=1)
    pct = float(any_hit.mean() * 100.0)
    days = (hit.argmax(axis=1) + 1)[any_hit]
    median = int(np.median(days)) if days.size else None
    return round(pct), median, int(n)


def attach_level_touch_odds(payload: dict[str, Any], ohlcv, current_price: float) -> None:
    """Add touch_pct / median_days / window_sessions to each entry-zone level in place."""
    if ohlcv is None or not (current_price and current_price > 0):
        return
    try:
        cols = {str(c).lower(): c for c in ohlcv.columns}
        closes = np.asarray(ohlcv[cols["close"]], dtype=float)
        lows = np.asarray(ohlcv[cols["low"]], dtype=float)
    except (KeyError, TypeError, ValueError, AttributeError):
        return
    ok = np.isfinite(closes) & np.isfinite(lows) & (closes > 0)
    closes, lows = closes[ok], lows[ok]
    years = round(len(closes) / 252.0, 1)
    for key, window in WINDOW_SESSIONS.items():
        h = payload.get(key)
        ez = (h or {}).get("entry_zone") if isinstance(h, dict) else None
        if not isinstance(ez, dict):
            continue
        for lvl in ez.get("levels") or []:
            try:
                px = float(lvl.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if px <= 0:
                continue
            lvl["window_sessions"] = window
            lvl["touch_history_years"] = years
            if px >= current_price:
                lvl["touch_pct"] = 100
                lvl["median_days"] = 0
                continue
            st = level_touch_stats(closes, lows, (current_price - px) / current_price * 100.0, window)
            if st is None:
                continue
            lvl["touch_pct"], lvl["median_days"], lvl["touch_sample_n"] = st
