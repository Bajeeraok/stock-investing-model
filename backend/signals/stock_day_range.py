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
Probabilities, not predictions. Display only — never feeds the buy/sell signal.
"""
from __future__ import annotations

import math
from datetime import datetime
from statistics import NormalDist
from typing import Any

SPAN = 20
Z80 = 1.2816
Z50 = 0.6745
CLOSE_K = 0.97
INTRA_K = 0.55
INTRA_K_LATE = 0.65
INTRA_REACH_K = 0.57
SESSION_MIN = 390
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


def reach_ladder(anchor: float, sig: float, left: float | None) -> list[dict[str, float]]:
    """Dip/pop prices with a given chance of trading before the close (left=None: next session)."""
    out = []
    for p in LADDER_P:
        if left is None:
            m = _pre_open_move(p)
        elif left > 0:
            m = INTRA_REACH_K * math.sqrt(left) * NormalDist().inv_cdf(1 - p / 2)
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


def build_day_range(
    closes: list[float],
    dates: list[str],
    *,
    session: dict[str, float] | None = None,
    levels: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """closes/dates: completed daily sessions (oldest first), excluding today's partial bar.
    session: {last, high, low, minutes_since_open} while the market is open, else None."""
    if len(closes) < 25 or len(closes) != len(dates):
        return None
    sig = ewma_sigmas(closes)[-1]
    ref = closes[-1]
    if not sig or ref <= 0:
        return None
    live = bool(session and session.get("last") and 0 <= session.get("minutes_since_open", -1) < SESSION_MIN)
    px = lambda lr, base: round(base * math.exp(lr), 2)
    out: dict[str, Any] = {
        "phase": "intraday" if live else "next_session",
        "ref_close": round(ref, 2),
        "ref_date": dates[-1],
        "sigma_pct": round(sig * 100, 2),
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
        )
        anchor = last
    else:
        sd = CLOSE_K * sig
        out.update(close_low=px(-Z80 * sd, ref), close_mid=round(ref, 2), close_high=px(Z80 * sd, ref),
                   close_low50=px(-Z50 * sd, ref), close_high50=px(Z50 * sd, ref),
                   p_close_green=None)
        anchor = ref
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
            prob = min(0.99, 2 * (1 - _phi(d / rem))) if left > 0 else 0.0
        else:
            prob = min(0.99, _pre_open_touch(abs(math.log(p / anchor)) / sig))
        z = math.log(p / anchor) / sd if sd > 0 else 0.0
        p_close = _phi(z) if below else 1 - _phi(z)
        lv_out.append({"label": lv.get("label"), "price": round(p, 2), "side": "below" if below else "above",
                       "p_reach": round(prob, 2), "p_close_beyond": round(p_close, 2), "touched": touched})
    out["levels"] = sorted(lv_out, key=lambda x: -x["price"])
    out["ladder"] = reach_ladder(anchor, sig, left if live else None)
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


def compute_stock_day_range(ticker: str, summary: dict | None = None, now: datetime | None = None) -> dict | None:
    """Live fetch (daily 6mo + today's 5-min bars) → build_day_range. None on any data gap."""
    import yfinance as yf
    from zoneinfo import ZoneInfo

    now = now or datetime.now(ZoneInfo("America/New_York"))
    t = yf.Ticker(ticker)
    d = t.history(period="6mo", interval="1d", auto_adjust=False)
    if d is None or d.empty:
        return None
    idx = d.index.tz_convert("America/New_York") if d.index.tz is not None else d.index
    today = now.date()
    in_session = now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) < (16, 0)
    rows = [(ts.date(), float(c)) for ts, c in zip(idx, d["Close"]) if c == c and (not in_session or ts.date() < today)]
    session = None
    if in_session:
        m = t.history(period="1d", interval="5m", auto_adjust=False)
        if m is not None and not m.empty:
            mi = m.index.tz_convert("America/New_York") if m.index.tz is not None else m.index
            m = m.set_axis(mi)
            m = m[m.index.date == today]
            if not m.empty:
                session = {"last": float(m["Close"].iloc[-1]), "high": float(m["High"].max()),
                           "low": float(m["Low"].min()),
                           "minutes_since_open": (now.hour * 60 + now.minute) - (9 * 60 + 30)}
    return build_day_range([c for _, c in rows], [x.isoformat() for x, _ in rows],
                           session=session, levels=levels_from_summary(summary))
