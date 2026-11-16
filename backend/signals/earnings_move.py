"""
Post-earnings 1-day move: size range (50% / 80%) and the options-implied move. Direction is not
predicted — no tested signal beat a coin flip (docs/research/findings/2026-11-16-earnings-move.md).

Typical move = ½ × (median of the last 8 reactions / 3.12%) + ½ × (σ20 / 1.54%), × 3.04%
(the medians of 1,040 pre-2021 reports, 102 stocks). Bands: 50% = ±0.97×, 80% = ±1.97× the typical
move; on 1,982 reports 2021+ they held 48% / 79% (80% band: 80/77/81% for calm/mid/jumpy stocks).
Reaction = close before the report → close of the first session after it. Display only.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

TRAIN_MED_MOVE = 0.0304
TRAIN_MED_PAST8 = 0.0312
TRAIN_MED_SIG = 0.0154
K50, K80 = 0.97, 1.97
MIN_PAST = 4


def _naive(ts) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    return ts.tz_convert("America/New_York").tz_localize(None) if ts.tzinfo is not None else ts


def report_timing(ts) -> str | None:
    """'amc' (after close), 'bmo' (before open) or None (time unknown)."""
    h = _naive(ts).hour
    return "amc" if h >= 12 else "bmo" if 4 <= h < 10 else None


def reaction_index(dates: pd.DatetimeIndex, ts) -> tuple[int, int] | None:
    """(pre, react) positions in a daily index for a report at ts."""
    t = _naive(ts)
    day, when = t.normalize(), report_timing(t)
    if when == "amc":
        pre = int(dates.searchsorted(day, side="right")) - 1
        if pre < 0 or dates[pre] != day:
            return None
        react = pre + 1
    elif when == "bmo":
        react = int(dates.searchsorted(day, side="left"))
        if react >= len(dates) or dates[react] != day:
            return None
        pre = react - 1
    else:
        return None
    return (pre, react) if pre >= 0 and react < len(dates) else None


def _sigmas(c: np.ndarray) -> np.ndarray:
    return pd.Series(np.log(c)).diff().ewm(span=20).std().values


def typical_move(past_abs: list[float], sig: float | None) -> float | None:
    parts = []
    if len(past_abs) >= MIN_PAST:
        parts.append(float(np.median(past_abs[-8:])) / TRAIN_MED_PAST8)
    if sig and sig > 0:
        parts.append(float(sig) / TRAIN_MED_SIG)
    if not parts:
        return None
    return TRAIN_MED_MOVE * (sum(parts) / len(parts) if len(parts) == 1 else 0.5 * parts[0] + 0.5 * parts[1])


def past_reactions(close: pd.Series, earnings_dates: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Reported events only, oldest first, each with the typical move predicted before it."""
    if earnings_dates is None or earnings_dates.empty or close is None or len(close) < 40:
        return []
    s = close.dropna()
    dates = pd.DatetimeIndex([_naive(x).normalize() for x in s.index])
    c = s.values.astype(float)
    sig = _sigmas(c)
    rows: list[dict[str, Any]] = []
    rep = earnings_dates
    if "Reported EPS" in rep.columns:
        rep = rep[rep["Reported EPS"].notna()]
    for ts in sorted(rep.index, key=_naive):
        ix = reaction_index(dates, ts)
        if not ix:
            continue
        pre, react = ix
        if c[pre] <= 0:
            continue
        m = float(c[react] / c[pre] - 1)
        if abs(m) > 0.6:
            continue
        rows.append({"event_date": _naive(ts).date().isoformat(), "timing": report_timing(ts),
                     "pre_close": round(float(c[pre]), 2), "post_close": round(float(c[react]), 2),
                     "realized_move_pct": round(m * 100, 2), "abs_move_pct": round(abs(m) * 100, 2),
                     "_sig": float(sig[pre]) if sig[pre] == sig[pre] else None})
    for i, r in enumerate(rows):
        tm = typical_move([x["abs_move_pct"] / 100 for x in rows[max(0, i - 8):i]], r["_sig"])
        r["pred_move80_pct"] = round(K80 * tm * 100, 2) if tm and i >= MIN_PAST else None
    return rows


def options_implied_move(ticker: str, report_ts, price: float) -> dict[str, Any] | None:
    """ATM straddle (mid) for the first expiry on/after the reaction day, as % of price."""
    try:
        import yfinance as yf

        t = _naive(report_ts)
        react = t.normalize() + (timedelta(days=1) if report_timing(t) != "bmo" else timedelta(0))
        tk = yf.Ticker(ticker)
        exp = next((e for e in tk.options if pd.Timestamp(e) >= react), None)
        if not exp or (pd.Timestamp(exp) - react).days > 10:
            return None
        ch = tk.option_chain(exp)
        k = float(ch.calls.iloc[(ch.calls.strike - price).abs().argsort()[:1]].strike.values[0])

        def mid(df):
            r = df[df.strike == k]
            if r.empty:
                return None
            b, a, last = float(r.bid.iloc[0]), float(r.ask.iloc[0]), float(r.lastPrice.iloc[0])
            return (b + a) / 2 if b > 0 and a > 0 else last if last > 0 else None

        cm, pm = mid(ch.calls), mid(ch.puts)
        if not cm or not pm or price <= 0:
            return None
        return {"move_pct": round((cm + pm) / price * 100, 1), "expiry": exp, "strike": k}
    except Exception:
        return None


def next_report(earnings_dates: pd.DataFrame | None, now: datetime | None = None):
    if earnings_dates is None or earnings_dates.empty:
        return None
    now_n = _naive(now or pd.Timestamp.now(tz="America/New_York"))
    fut = [ts for ts in earnings_dates.index if _naive(ts) >= now_n - timedelta(hours=12)]
    return min(fut, key=_naive) if fut else None


def forecast(close: pd.Series, earnings_dates: pd.DataFrame | None, price: float) -> dict[str, Any] | None:
    """Size bands for the next report from the price before it (close-to-close %)."""
    s = close.dropna() if close is not None else None
    if s is None or len(s) < 40 or price <= 0:
        return None
    hist = past_reactions(s, earnings_dates)
    sig = float(_sigmas(s.values.astype(float))[-1])
    tm = typical_move([r["abs_move_pct"] / 100 for r in hist], sig)
    if not tm:
        return None
    m50, m80 = K50 * tm, K80 * tm
    scored = [r for r in hist if r.get("pred_move80_pct")]
    inside = sum(1 for r in scored if r["abs_move_pct"] <= r["pred_move80_pct"])
    return {
        "typical_move_pct": round(tm * 100, 1), "move50_pct": round(m50 * 100, 1), "move80_pct": round(m80 * 100, 1),
        "range50_low": round(price * (1 - m50), 2), "range50_high": round(price * (1 + m50), 2),
        "range80_low": round(price * (1 - m80), 2), "range80_high": round(price * (1 + m80), 2),
        "sigma_pct": round(sig * 100, 2), "past_events": len(hist),
        "own_check": {"events": len(scored), "inside80": inside} if scored else None,
        "history": [{k: v for k, v in r.items() if not k.startswith("_")} for r in hist],
    }
