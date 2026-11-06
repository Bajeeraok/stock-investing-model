"""Per-level touch odds for entry-band levels from the ticker's own daily history
(up to 10 years; a 2018-2026 test on 20 tickers showed 10y calibrated better than 2y or 5y).

For a level d% below spot, measures how often this stock's low reached d% below a
given day's close within the horizon window, and the median sessions until it did.
"""
from __future__ import annotations

from typing import Any

import numpy as np

WINDOW_SESSIONS = {"short": 20, "medium": 63, "long": 252}
MIN_SAMPLES = 120
SIMILAR_MIN_N = 60
SIMILAR_STRETCH_PTS = 3.0
AFTER_TOUCH_DAYS = 20
MIN_EVENTS = 20


def _touch_matrix(closes: np.ndarray, lows: np.ndarray, drop_pct: float, window: int):
    from numpy.lib.stride_tricks import sliding_window_view

    n = len(closes) - window
    fwd_lows = sliding_window_view(lows[1:], window)[:n]
    entry = closes[:n] * (1.0 - drop_pct / 100.0)
    return n, entry, fwd_lows <= entry[:, None]


def level_touch_stats(
    closes: np.ndarray, lows: np.ndarray, drop_pct: float, window: int, mask: np.ndarray | None = None
) -> tuple[float, int | None, int] | None:
    n = len(closes) - window
    if n < MIN_SAMPLES or drop_pct < 0:
        return None
    n, _, hit = _touch_matrix(closes, lows, drop_pct, window)
    any_hit = hit.any(axis=1)
    days_all = hit.argmax(axis=1) + 1
    if mask is not None:
        sel = np.asarray(mask[:n], dtype=bool)
        if int(sel.sum()) < SIMILAR_MIN_N:
            return None
        any_hit, days_all, n = any_hit[sel], days_all[sel], int(sel.sum())
    pct = float(any_hit.mean() * 100.0)
    days = days_all[any_hit]
    median = int(np.median(days)) if days.size else None
    return round(pct), median, int(n)


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def similar_setup_mask(closes: np.ndarray) -> tuple[np.ndarray, dict[str, Any]] | None:
    """Past days like today: stretch vs MA50 within ±3 pts of today's, same side of MA200."""
    ma50, ma200 = _sma(closes, 50), _sma(closes, 200)
    if not (np.isfinite(ma50[-1]) and np.isfinite(ma200[-1])):
        return None
    stretch = (closes / ma50 - 1.0) * 100.0
    above = closes > ma200
    m = np.isfinite(stretch) & np.isfinite(ma200) & (np.abs(stretch - stretch[-1]) <= SIMILAR_STRETCH_PTS) & (above == above[-1])
    return m, {"stretch_vs_ma50_pct": round(float(stretch[-1]), 1), "above_ma200": bool(above[-1])}


def touch_outcomes(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    drop_pct: float,
    window: int,
    stop_pct: float | None = None,
    target_pct: float | None = None,
    after: int = AFTER_TOUCH_DAYS,
) -> dict[str, Any]:
    """Past touches of a level drop_pct below a close (one event per touch day), entered at that price:
    share closing above entry `after` sessions later, and whether the stop or the target came first
    within `window` sessions."""
    out: dict[str, Any] = {}
    if len(closes) - window < MIN_SAMPLES or drop_pct < 0:
        return out
    n, entry, hit = _touch_matrix(closes, lows, drop_pct, window)
    any_hit = hit.any(axis=1)
    idx = np.nonzero(any_hit)[0]
    if idx.size == 0:
        return out
    touch_day = idx + hit[idx].argmax(axis=1) + 1
    touch_day, first = np.unique(touch_day, return_index=True)
    e = entry[idx[first]]
    ok = touch_day + after < len(closes)
    if int(ok.sum()) >= MIN_EVENTS:
        ret = closes[touch_day[ok] + after] / e[ok] - 1.0
        out["after_touch_days"] = after
        out["after_touch_up_pct"] = round(float((ret > 0).mean() * 100.0))
        out["after_touch_median_ret_pct"] = round(float(np.median(ret) * 100.0), 1)
        out["after_touch_p25_ret_pct"] = round(float(np.percentile(ret, 25) * 100.0), 1)
        out["after_touch_n"] = int(ok.sum())
    if stop_pct and target_pct and stop_pct > 0 and target_pct > 0:
        stop_first = target_first = neither = 0
        for t, px in zip(touch_day, e):
            end = t + 1 + window
            if end > len(closes):
                continue
            s = np.nonzero(lows[t + 1:end] <= px * (1 - stop_pct / 100.0))[0]
            g = np.nonzero(highs[t + 1:end] >= px * (1 + target_pct / 100.0))[0]
            if not s.size and not g.size:
                neither += 1
            elif not g.size or (s.size and s[0] <= g[0]):
                stop_first += 1
            else:
                target_first += 1
        tot = stop_first + target_first + neither
        if tot >= MIN_EVENTS:
            out["stop_first_pct"] = round(100.0 * stop_first / tot)
            out["target_first_pct"] = round(100.0 * target_first / tot)
            out["outcome_window"] = window
            out["outcome_n"] = tot
    return out


def attach_level_touch_odds(payload: dict[str, Any], ohlcv, current_price: float) -> None:
    """Add touch_pct / median_days / window_sessions to each entry-zone level in place."""
    if ohlcv is None or not (current_price and current_price > 0):
        return
    try:
        cols = {str(c).lower(): c for c in ohlcv.columns}
        closes = np.asarray(ohlcv[cols["close"]], dtype=float)
        lows = np.asarray(ohlcv[cols["low"]], dtype=float)
        highs = np.asarray(ohlcv[cols["high"]], dtype=float) if "high" in cols else closes.copy()
    except (KeyError, TypeError, ValueError, AttributeError):
        return
    ok = np.isfinite(closes) & np.isfinite(lows) & np.isfinite(highs) & (closes > 0)
    closes, lows, highs = closes[ok], lows[ok], highs[ok]
    years = round(len(closes) / 252.0, 1)
    sim = similar_setup_mask(closes)
    for key, window in WINDOW_SESSIONS.items():
        h = payload.get(key)
        ez = (h or {}).get("entry_zone") if isinstance(h, dict) else None
        if not isinstance(ez, dict):
            continue
        if sim:
            ez["similar_setup"] = {**sim[1], "n": int(sim[0][: max(len(closes) - window, 0)].sum())}
        try:
            stop = float(h.get("stop_loss") or 0)
            target = float(h.get("target") or 0)
        except (TypeError, ValueError):
            stop = target = 0.0
        for lvl in ez.get("levels") or []:
            try:
                px = float(lvl.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if px <= 0:
                continue
            lvl["window_sessions"] = window
            lvl["touch_history_years"] = years
            drop = max(0.0, (current_price - px) / current_price * 100.0)
            sp = (px - stop) / px * 100.0 if 0 < stop < px else None
            tp = (target - px) / px * 100.0 if target > px else None
            lvl.update(touch_outcomes(closes, highs, lows, drop, window, sp, tp))
            if sim and px < current_price:
                ss = level_touch_stats(closes, lows, drop, window, mask=sim[0])
                if ss is not None:
                    lvl["similar_touch_pct"], lvl["similar_n"] = ss[0], ss[2]
            if px >= current_price:
                lvl["touch_pct"] = 100
                lvl["median_days"] = 0
                continue
            st = level_touch_stats(closes, lows, (current_price - px) / current_price * 100.0, window)
            if st is None:
                continue
            lvl["touch_pct"], lvl["median_days"], lvl["touch_sample_n"] = st


def forward_gain_odds(
    closes: np.ndarray, gain_pct: float, days: int, mask: np.ndarray | None = None
) -> tuple[int, int] | None:
    """How often this stock's close `days` sessions later was >= +gain_pct% — the model's own question."""
    n = len(closes) - days
    if n < MIN_SAMPLES:
        return None
    hit = closes[days:days + n] / closes[:n] - 1.0 >= gain_pct / 100.0
    if mask is not None:
        sel = np.asarray(mask[:n], dtype=bool)
        if int(sel.sum()) < SIMILAR_MIN_N:
            return None
        hit = hit[sel]
    return round(float(hit.mean() * 100.0)), int(hit.size)


def attach_history_odds(payload: dict[str, Any], ohlcv) -> None:
    """Per horizon: past odds of the model's +N% within its horizon (all days and similar setups)."""
    if ohlcv is None:
        return
    try:
        cols = {str(c).lower(): c for c in ohlcv.columns}
        closes = np.asarray(ohlcv[cols["close"]], dtype=float)
    except (KeyError, TypeError, ValueError, AttributeError):
        return
    closes = closes[np.isfinite(closes) & (closes > 0)]
    sim = similar_setup_mask(closes)
    for h in payload.values():
        if not isinstance(h, dict):
            continue
        gain, days = h.get("ml_target_gain_pct"), h.get("ml_horizon_days")
        if gain is None or not days:
            continue
        allh = forward_gain_odds(closes, float(gain), int(days))
        if allh is None:
            continue
        h["hist_prob"], h["hist_n"] = allh
        h["hist_years"] = round(len(closes) / 252.0, 1)
        ss = forward_gain_odds(closes, float(gain), int(days), mask=sim[0]) if sim else None
        if ss is not None:
            h["hist_prob_similar"], h["hist_similar_n"] = ss


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
                    # Score only once the whole window has passed: resolving early touches while
                    # misses wait would count only hits (a "100% happened" survivorship bias).
                    if i + w >= len(dates):
                        pending += 1
                        continue
                    bars = bars_from_index(dates, i, w, tk, rows_by_date)
                    touched = any((b.get("low") or b.get("close") or 1e18) <= float(price) for b in bars)
                    pooled.setdefault(w, []).append((float(pred), touched))
                    by_tk.setdefault(tk, {}).setdefault(w, []).append((float(pred), touched))
    return {
        "pooled": {str(w): _calibration(v) for w, v in pooled.items()},
        "by_ticker": {tk: {str(w): _calibration(v) for w, v in m.items()} for tk, m in by_tk.items()},
        "pending": pending,
    }
