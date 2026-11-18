"""
Per-stock "today's range": likely close range, green-close odds and the chance price trades at
key levels (entry band, stop) before the close. Same idea as Market Pulse for SPY/QQQ, but sized
by each stock's own 20-day EWMA daily volatility (no futures / implied vol needed).

Calibration (125 tracked tickers):
  • Close band: prev close ± 1.2816 × 0.97 × σ20 covered 80–81% of closes over 2016–2026 daily bars,
    79.7–83.8% in every calendar year (2020 and 2022 included).
  • Intraday: last ± 1.2816 × 0.55 × σ20 × √(session left) covered 79–81% at 10:30–13:30 on 2y of
    hourly bars (0.65 in the last 90 min, where 0.55 under-covered at 74%).
  • Touch odds before the open use the empirical 10y touch rate of a level m·σ20 from the prior
    close (fat tails: a 2σ level traded 6.2% of days vs 2% for a normal); intraday uses the
    reflection rule 2·(1−Φ(d / (0.57·σ√left))).
  • Pre-open with a pre-market price (4:00–9:30 ET): centre on it, not the prior close, with
    0.80 × σ20 for the close band and 0.85 × the touch moves (fitted vs prev-close k on 60 days
    of 5-min bars, 125 tickers: the ratio held at 0.79–0.84 in both halves). Out of sample: close
    error 2.7% → 2.1%, error of the 50% low 1.4% → 0.9%; on gap days (>1σ) 80% band coverage
    45% → 63% and low error 3.8% → 1.2%.
  • Predicted open = last pre-market trade (mean error 0.41% vs 1.44% from the prior close, same
    60 days); open band ±0.19σ (80%) / ±0.17σ (50%), or ±0.61σ / ±0.56σ around the prior close
    when there is no pre-market print. Both halves agreed within 0.01.
Probabilities, not predictions. Display only — never feeds the buy/sell signal.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from statistics import NormalDist
from typing import Any

SPAN = 20
Z80 = 1.2816
Z50 = 0.6745
CLOSE_K = 0.97
INTRA_K = 0.55
INTRA_K_LATE = 0.65
INTRA_REACH_K = 0.57
PRE_K = 0.80
PRE_MOVE_K = 0.85
# Earnings reaction day (docs/research/findings/2026-11-18-earnings-day-range.md): the normal bands held only
# 32% (before the report) / 46% (after it, from the open) of 3,223 reaction closes. Before the report use the
# earnings 80% move; after it, σ20 × 2.20 (fit pre-2021, 79.5% on 2,105 reports 2021+).
EVENT_POST_K = 2.20
OPEN_K = {True: (0.19, 0.17), False: (0.61, 0.56)}  # (80%, 50%) × σ20; key: has pre-market
SESSION_MIN = 390
# Intraday reach odds -> observed retouch rate of the day's low/high from 10:30/12:30/2:30/3:30
# (24 large caps + SPY/QQQ, 59 sessions of 5-min bars, 11,328 cases; both ticker halves agree).
REACH_CALIBRATION = ((0.0, 0.0), (0.01, 0.02), (0.12, 0.12), (0.29, 0.26), (0.5, 0.42),
                     (0.7, 0.64), (0.87, 0.84), (0.97, 0.95), (1.0, 0.97))
REACH_CALIBRATION_N = {"sessions": 59, "tickers": 24, "cases": 11328}
SCORE_DAYS = 60
PRE_OPEN_TOUCH = [(0.0, 1.0), (0.25, 0.689), (0.5, 0.529), (0.75, 0.384), (1.0, 0.271),
                  (1.5, 0.129), (2.0, 0.062), (2.5, 0.031), (3.5, 0.01)]


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def ewma_sigmas(closes: list[float], span: int = SPAN) -> list[float | None]:
    """sig[i] = EWMA std of log returns through bar i (so sig[i-1] is known before bar i)."""
    a = 2 / (span + 1)
    out: list[float | None] = [None]
    mean = var = None
    n = 0
    for i in range(1, len(closes)):
        if closes[i - 1] <= 0 or closes[i] <= 0:
            out.append(out[-1])
            continue
        r = math.log(closes[i] / closes[i - 1])
        n += 1
        if mean is None:
            mean, var = r, 0.0
        else:
            d = r - mean
            mean += a * d
            var = (1 - a) * (var + a * d * d)
        out.append(math.sqrt(var) if n >= 10 and var > 0 else None)
    return out


LADDER_P = (0.75, 0.5, 0.25, 0.1)


def _pre_open_move(p: float) -> float:
    """Inverse of _pre_open_touch: move (in sigmas) touched with probability p."""
    for (x0, y0), (x1, y1) in zip(PRE_OPEN_TOUCH, PRE_OPEN_TOUCH[1:]):
        if y1 <= p <= y0:
            return x0 + (y0 - p) / (y0 - y1) * (x1 - x0)
    return PRE_OPEN_TOUCH[-1][0]


def calibrate_reach(p: float) -> float:
    pts = REACH_CALIBRATION
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if p <= x1:
            return y0 + (y1 - y0) * (p - x0) / (x1 - x0)
    return pts[-1][1]


def _uncalibrate_reach(q: float) -> float:
    pts = REACH_CALIBRATION
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if q <= y1:
            return x0 + (x1 - x0) * (q - y0) / (y1 - y0)
    return pts[-1][0]


def reach_ladder(anchor: float, sig: float, left: float | None, pre_k: float = 1.0) -> list[dict[str, float]]:
    """Dip/pop prices with a given chance of trading before the close (left=None: next session)."""
    out = []
    for p in LADDER_P:
        if left is None:
            m = pre_k * _pre_open_move(p)
        elif left > 0:
            m = INTRA_REACH_K * math.sqrt(left) * NormalDist().inv_cdf(1 - _uncalibrate_reach(p) / 2)
        else:
            continue
        out.append({"p": p, "dip": round(anchor * math.exp(-m * sig), 2), "pop": round(anchor * math.exp(m * sig), 2)})
    return out


def _pre_open_touch(m: float) -> float:
    for (x0, y0), (x1, y1) in zip(PRE_OPEN_TOUCH, PRE_OPEN_TOUCH[1:]):
        if m <= x1:
            return y0 + (y1 - y0) * (m - x0) / (x1 - x0)
    return PRE_OPEN_TOUCH[-1][1]


def scorecard(closes: list[float], dates: list[str], days: int = SCORE_DAYS) -> dict[str, Any] | None:
    sig = ewma_sigmas(closes)
    rows = []
    for i in range(max(1, len(closes) - days), len(closes)):
        s = sig[i - 1]
        if s is None or closes[i - 1] <= 0:
            continue
        rows.append(abs(math.log(closes[i] / closes[i - 1])) <= Z80 * CLOSE_K * s)
    if len(rows) < 20:
        return None
    hit = sum(rows)
    return {"sessions": len(rows), "inside": hit, "coverage_pct": round(100 * hit / len(rows)),
            "since": dates[len(closes) - len(rows)] if len(dates) == len(closes) else None}


def _next_session(ref: str) -> str | None:
    """First NYSE trading day after the reference close (the session being forecast)."""
    try:
        from datetime import date, timedelta

        from signals.market_calendar import is_nyse_holiday

        d = date.fromisoformat(str(ref)[:10]) + timedelta(days=1)
        while d.weekday() >= 5 or is_nyse_holiday(d):
            d += timedelta(days=1)
        return d.isoformat()
    except Exception:
        return None


def build_day_range(
    closes: list[float],
    dates: list[str],
    *,
    session: dict[str, float] | None = None,
    levels: list[dict[str, Any]] | None = None,
    premarket: float | None = None,
    event: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """closes/dates: completed daily sessions (oldest first), excluding today's partial bar.
    session: {last, high, low, minutes_since_open} while the market is open, else None.
    premarket: last pre-market trade before the open (centres the next-session forecast)."""
    if len(closes) < 25 or len(closes) != len(dates):
        return None
    sig = ewma_sigmas(closes)[-1]
    ref = closes[-1]
    if not sig or ref <= 0:
        return None
    live = bool(session and session.get("last") and 0 <= session.get("minutes_since_open", -1) < SESSION_MIN)
    raw_sig = sig
    if event and event.get("move80"):
        has_pre = bool(not live and premarket and 0.6 < premarket / ref < 1.6)
        if event.get("reported") and (live or has_pre):
            scale = EVENT_POST_K
        else:
            scale = max(1.0, math.log(1 + event["move80"]) / Z80 / ((PRE_K if has_pre else CLOSE_K) * sig))
        sig *= scale
        event = {**event, "scale": round(scale, 2)}
    px = lambda lr, base: round(base * math.exp(lr), 2)
    out: dict[str, Any] = {
        "phase": "intraday" if live else "next_session",
        "ref_close": round(ref, 2),
        "ref_date": dates[-1],
        "session_date": _next_session(dates[-1]),
        "sigma_pct": round(raw_sig * 100, 2),
        "event": event if event and event.get("scale") else None,
    }
    if live:
        last = float(session["last"])
        left = max(0.0, 1 - float(session["minutes_since_open"]) / SESSION_MIN)
        k = INTRA_K if left >= 0.25 else INTRA_K_LATE
        sd = k * sig * math.sqrt(left)
        out.update(
            last=round(last, 2),
            minutes_left=int(left * SESSION_MIN),
            close_low=px(-Z80 * sd, last), close_mid=round(last, 2), close_high=px(Z80 * sd, last),
            close_low50=px(-Z50 * sd, last), close_high50=px(Z50 * sd, last),
            p_close_green=round(_phi(math.log(last / ref) / sd), 2) if sd > 0 else (1.0 if last > ref else 0.0),
            day_low=session.get("low"), day_high=session.get("high"),
            day_open=round(float(session["open"]), 2) if session.get("open") else None,
        )
        anchor = last
    else:
        pre = float(premarket) if premarket and 0.6 < premarket / ref < 1.6 else None
        anchor = pre or ref
        sd = (PRE_K if pre else CLOSE_K) * sig
        out.update(close_low=px(-Z80 * sd, anchor), close_mid=round(anchor, 2), close_high=px(Z80 * sd, anchor),
                   close_low50=px(-Z50 * sd, anchor), close_high50=px(Z50 * sd, anchor),
                   p_close_green=None, premarket=round(pre, 2) if pre else None)
        k80, k50 = OPEN_K[bool(pre)]
        out.update(open_mid=round(anchor, 2), open_low=px(-Z80 * k80 * sig, anchor), open_high=px(Z80 * k80 * sig, anchor),
                   open_low50=px(-Z50 * k50 * sig, anchor), open_high50=px(Z50 * k50 * sig, anchor))
    move_k = PRE_MOVE_K if not live and out.get("premarket") else 1.0
    lv_out = []
    seen = set()
    for lv in levels or []:
        p = lv.get("price")
        if not p or p <= 0 or round(p, 2) in seen:
            continue
        seen.add(round(p, 2))
        below = p < anchor
        touched = False
        if live:
            lo, hi = session.get("low"), session.get("high")
            touched = bool((below and lo is not None and lo <= p) or (not below and hi is not None and hi >= p))
            d = abs(math.log(p / anchor)) / sig
            rem = INTRA_REACH_K * math.sqrt(max(left, 1e-9))
            # Forward odds from the current price; an earlier touch is reported separately.
            prob = calibrate_reach(min(0.99, 2 * (1 - _phi(d / rem)))) if left > 0 else 0.0
        else:
            prob = min(0.99, _pre_open_touch(abs(math.log(p / anchor)) / sig / move_k))
        z = math.log(p / anchor) / sd if sd > 0 else 0.0
        p_close = _phi(z) if below else 1 - _phi(z)
        lv_out.append({"label": lv.get("label"), "price": round(p, 2), "side": "below" if below else "above",
                       "p_reach": round(prob, 2), "p_close_beyond": round(p_close, 2), "touched": touched})
    out["levels"] = sorted(lv_out, key=lambda x: -x["price"])
    out["ladder"] = reach_ladder(anchor, sig, left if live else None, move_k)
    if sd > 0:
        # Same close distribution as the bands: a touch is always at least as likely as closing beyond.
        for r in out["ladder"]:
            r["close_below"] = round(_phi(math.log(r["dip"] / anchor) / sd), 2)
            r["close_above"] = round(1 - _phi(math.log(r["pop"] / anchor) / sd), 2)
    if live:
        out["reach_calibration"] = REACH_CALIBRATION_N
        # The day's low/high can only extend past what already printed: odds of a new low/high by the close.
        rem = INTRA_REACH_K * math.sqrt(max(left, 1e-9))
        for key, lvl in (("new_low", session.get("low")), ("new_high", session.get("high"))):
            if lvl and lvl > 0 and left > 0:
                d = abs(math.log(lvl / anchor)) / sig
                out[f"p_{key}"] = round(calibrate_reach(min(0.99, 2 * (1 - _phi(d / rem)))), 2)
                z = math.log(lvl / anchor) / sd if sd > 0 else 0.0
                out[f"p_close_{'below' if key == 'new_low' else 'above'}_day"] = round(_phi(z) if key == "new_low" else 1 - _phi(z), 2)
    out["scorecard"] = scorecard(closes, dates)
    return out


def levels_from_summary(summary: dict | None) -> list[dict[str, Any]]:
    hz = (summary or {}).get("horizons") or {}
    out = []
    med, lng = hz.get("medium") or {}, hz.get("long") or {}
    mz, lz = med.get("entry_zone") or {}, lng.get("entry_zone") or {}
    out += [{"label": "Swing band top", "price": mz.get("high")}, {"label": "Swing band low", "price": mz.get("low")},
            {"label": "Owner band top", "price": lz.get("high")}, {"label": "Swing stop", "price": med.get("stop_loss")}]
    return [x for x in out if isinstance(x["price"], (int, float))]


_DAILY: dict[str, tuple[float, Any]] = {}
DAILY_TTL_S = 900


def _daily(t, ticker: str):
    """1y daily bars, reused for 15 min (only today's intraday bars change minute to minute)."""
    import time

    hit = _DAILY.get(ticker)
    if hit and time.time() - hit[0] < DAILY_TTL_S:
        return hit[1]
    d = t.history(period="1y", interval="1d", auto_adjust=False)
    if d is not None and not d.empty:
        _DAILY[ticker] = (time.time(), d)
    return d


_EARN: dict[str, tuple[float, Any]] = {}
EARN_TTL_S = 6 * 3600


def _earnings_event(t, ticker: str, d, rows, session_day: str | None, now: datetime) -> dict | None:
    """Earnings report whose first reaction close is the forecast session, with its 80% move (else None)."""
    import time

    import pandas as pd

    from signals.earnings_log import pre_close_date
    from signals.earnings_move import _naive, forecast, report_timing

    if not rows or not session_day or ticker.endswith("-USD"):
        return None
    try:
        hit = _EARN.get(ticker)
        if hit and time.time() - hit[0] < EARN_TTL_S:
            ed = hit[1]
        else:
            ed = t.get_earnings_dates(limit=8)
            _EARN[ticker] = (time.time(), ed)
        if ed is None or ed.empty:
            return None
        last = rows[-1][0]
        for ts in ed.index:
            pre = pre_close_date(ts)
            if pre != last or _next_session(pre.isoformat()) != session_day:
                continue
            idx = d.index.tz_convert("America/New_York") if d.index.tz is not None else d.index
            close = pd.Series(d["Close"].values, index=idx)
            close = close[[x.date() <= last for x in idx]]
            f = forecast(close, ed[ed.index < ts], float(rows[-1][1]))
            if not f:
                return None
            return {"type": "earnings", "report": _naive(ts).isoformat(), "timing": report_timing(ts),
                    "move80": f["move80_pct"] / 100, "reported": _naive(now) >= _naive(ts)}
    except Exception:
        return None
    return None


def compute_stock_day_range(ticker: str, summary: dict | None = None, now: datetime | None = None) -> dict | None:
    """Live fetch (daily 1y + today's 1-min bars) → build_day_range. None on any data gap."""
    import yfinance as yf
    from zoneinfo import ZoneInfo

    now = now or datetime.now(ZoneInfo("America/New_York"))
    t = yf.Ticker(ticker)
    d = _daily(t, ticker)
    if d is None or d.empty:
        return None
    idx = d.index.tz_convert("America/New_York") if d.index.tz is not None else d.index
    today = now.date()
    in_session = now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) < (16, 0)
    pre_open = now.weekday() < 5 and (4, 0) <= (now.hour, now.minute) < (9, 30)
    rows = [(ts.date(), float(c)) for ts, c in zip(idx, d["Close"])
            if c == c and (not (in_session or pre_open) or ts.date() < today)]
    session = premarket = None
    if pre_open:
        try:
            m = t.history(period="1d", interval="5m", prepost=True, auto_adjust=False)
            if m is not None and not m.empty:
                mi = m.index.tz_convert("America/New_York") if m.index.tz is not None else m.index
                m = m.set_axis(mi)
                m = m[(m.index.date == today) & (m.index.hour * 60 + m.index.minute < 570)]["Close"].dropna()
                premarket = float(m.iloc[-1]) if not m.empty else None
        except Exception:
            premarket = None
    if in_session:
        m = t.history(period="1d", interval="1m", auto_adjust=False)
        if m is None or m.empty:
            m = t.history(period="1d", interval="5m", auto_adjust=False)
        if m is not None and not m.empty:
            mi = m.index.tz_convert("America/New_York") if m.index.tz is not None else m.index
            m = m.set_axis(mi)
            m = m[m.index.date == today]
            if not m.empty:
                session = {"last": float(m["Close"].iloc[-1]), "high": float(m["High"].max()),
                           "open": float(m["Open"].iloc[0]),
                           "low": float(m["Low"].min()),
                           "minutes_since_open": (now.hour * 60 + now.minute) - (9 * 60 + 30)}
    closes = [c for _, c in rows]
    from signals import options_levels as ol

    opt = None
    nxt = _next_session(rows[-1][0].isoformat()) if rows else None
    if closes and (in_session or nxt):
        anchor = (session or {}).get("last") or premarket or closes[-1]
        sday = today if in_session else date.fromisoformat(nxt)
        opt = ol.fetch(t, ticker, float(anchor), sday, now_day=today)
    event = _earnings_event(t, ticker, d, rows, nxt, now)
    out = build_day_range(closes, [x.isoformat() for x, _ in rows], session=session,
                          levels=levels_from_summary(summary) + ol.wall_levels(opt),
                          premarket=premarket, event=event)
    if out is not None:
        live_left = out["minutes_left"] / SESSION_MIN if out.get("phase") == "intraday" else None
        if out.get("session_date"):
            out.update(ol.day_range_fields(opt, out.get("last") or out["close_mid"],
                                           session_day=date.fromisoformat(out["session_date"]), live_left=live_left))
        from signals.bounce_zone import bounce_zone

        out["bounce_zone"] = bounce_zone(closes)
    return out
