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


LOG_DROPS_PCT = (2.0, 5.0, 10.0)
LOG_WINDOWS = (20, 63)
_CAL_BUCKETS = ((0, 20), (20, 40), (40, 60), (60, 80), (80, 101))


def compact_level_odds(ohlcv, close: float | None) -> dict[str, Any] | None:
    """Daily log of predicted hit odds for fixed drops below the close, scored later in Track."""
    try:
        px = float(close or 0)
        cols = {str(c).lower(): c for c in ohlcv.columns}
        closes = np.asarray(ohlcv[cols["close"]], dtype=float)
        lows = np.asarray(ohlcv[cols["low"]], dtype=float)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if px <= 0:
        return None
    ok = np.isfinite(closes) & np.isfinite(lows) & (closes > 0)
    closes, lows = closes[ok], lows[ok]
    out = []
    for d in LOG_DROPS_PCT:
        row: dict[str, Any] = {"drop_pct": d, "price": round(px * (1 - d / 100.0), 2)}
        for w in LOG_WINDOWS:
            st = level_touch_stats(closes, lows, d, w)
            if st:
                row[f"w{w}"] = {"p": st[0], "days": st[1]}
        if len(row) > 2:
            out.append(row)
    return {"levels": out, "history_years": round(len(closes) / 252.0, 1)} if out else None


def _calibration(obs: list[tuple[float, bool]]) -> dict[str, Any] | None:
    if not obs:
        return None
    buckets = []
    for lo, hi in _CAL_BUCKETS:
        g = [(p, y) for p, y in obs if lo <= p < hi]
        if g:
            buckets.append({
                "range": f"{lo}–{min(hi, 100)}%",
                "n": len(g),
                "avg_predicted_pct": round(sum(p for p, _ in g) / len(g), 1),
                "actual_hit_pct": round(100.0 * sum(1 for _, y in g if y) / len(g), 1),
            })
    n = len(obs)
    return {
        "n": n,
        "avg_predicted_pct": round(sum(p for p, _ in obs) / n, 1),
        "actual_hit_pct": round(100.0 * sum(1 for _, y in obs if y) / n, 1),
        "brier": round(sum((p / 100.0 - (1.0 if y else 0.0)) ** 2 for p, y in obs) / n, 4),
        "buckets": buckets,
    }


def score_level_odds(dates: list[str], rows_by_date: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Resolve logged level odds against later snapshot lows: touched within the window, or not."""
    from signals.forward_tracking_metrics import bars_from_index

    pooled: dict[int, list[tuple[float, bool]]] = {}
    by_tk: dict[str, dict[int, list[tuple[float, bool]]]] = {}
    pending = 0
    for i, d in enumerate(dates):
        for tk, row in (rows_by_date.get(d) or {}).items():
            lo_block = row.get("level_odds") if isinstance(row, dict) else None
            if not isinstance(lo_block, dict):
                continue
            for lvl in lo_block.get("levels") or []:
                price = lvl.get("price")
                for w in LOG_WINDOWS:
                    pred = (lvl.get(f"w{w}") or {}).get("p")
                    if pred is None or not price:
                        continue
                    bars = bars_from_index(dates, i, w, tk, rows_by_date)
                    touched = any((b.get("low") or b.get("close") or 1e18) <= float(price) for b in bars)
                    if not touched and i + w >= len(dates):
                        pending += 1
                        continue
                    pooled.setdefault(w, []).append((float(pred), touched))
                    by_tk.setdefault(tk, {}).setdefault(w, []).append((float(pred), touched))
    return {
        "pooled": {str(w): _calibration(v) for w, v in pooled.items()},
        "by_ticker": {tk: {str(w): _calibration(v) for w, v in m.items()} for tk, m in by_tk.items()},
        "pending": pending,
    }
