"""
Market pulse: pre-open outlook + intraday "likely close" range for SPY, with a daily scorecard.

Calibration (SPY, see docstrings of each function):
  • Pre-open: 10y of SPY daily bars (2016–2026). Full-day return (prior close → close)
    grouped by opening gap. A gap mostly tells you which side of yesterday's close the day
    ends on; whether the market keeps falling/rising after the open is close to a coin flip.
    The 80% range is widened/narrowed by VIX (GAP_VIX_RESID) since daily swings scale with it.
  • Intraday: final ≈ move so far + N(0, k·σ_VIX·√(time left)), σ_VIX = prior VIX/√252.
    k=0.40 gave ~85–90% coverage of the nominal 80% band on the last 60 sessions (k=0.30
    ≈ 80%); we keep the slightly wider band and track real coverage in the scorecard.
Probabilities, not predictions. Never feeds stock buy/sell decisions.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# (gap_low, gap_high, n, p_red, q10, q50, q90) — SPY 2016–2026 full-day % return by open gap %
GAP_TABLE: list[tuple[float, float, int, float, float, float, float]] = [
    (-99.0, -1.5, 50, 0.88, -5.13, -2.69, 0.19),
    (-1.5, -0.75, 139, 0.86, -2.15, -0.81, 0.12),
    (-0.75, -0.25, 401, 0.71, -1.55, -0.36, 0.49),
    (-0.25, 0.25, 1109, 0.47, -0.67, 0.04, 0.71),
    (0.25, 0.75, 608, 0.22, -0.45, 0.49, 1.28),
    (0.75, 1.5, 165, 0.13, -0.41, 1.21, 2.21),
    (1.5, 99.0, 41, 0.05, 0.76, 2.22, 5.40),
]
# Per gap bucket (same rows): median of (close − gap) and 10th/90th pct of the remainder in units of
# (VIX/√252)^1.5. Walk-forward 2019–2026: 79–84% of closes inside the band in every VIX regime,
# vs 39% (VIX>30) to 88% (VIX<15) for the fixed GAP_TABLE range.
VIX_RANGE_POW = 1.5
GAP_VIX_RESID: list[tuple[float, float, float]] = [
    (-0.064, -0.996, 0.942),
    (0.112, -0.746, 0.715),
    (0.065, -0.820, 0.658),
    (0.019, -0.641, 0.625),
    (0.076, -0.776, 0.576),
    (0.293, -0.708, 0.415),
    (0.293, -0.749, 0.467),
]
# Fitted on 2023-12..2026-11 hourly SPY (10:30-15:30 snapshots): 80% band held 81% of closes
# at 10:30-14:30, leave-one-half-year-out 80%. Width grows as (VIX/20)^1.25.
INTRADAY_K = 0.49
INTRADAY_VIX_EXP = 1.25
Z80 = 1.2816
SLOTS = ("pre_open", "10:30", "12:30")
# Extra hourly snapshots: scored only for calibration, never in the headline scorecard.
CALIBRATION_SLOTS = ("11:30", "13:30", "14:30", "15:30")
INTRADAY_SLOT_TIMES = {"10:30": (10, 30), "11:30": (11, 30), "12:30": (12, 30),
                       "13:30": (13, 30), "14:30": (14, 30), "15:30": (15, 30)}
SLOT_LATE_MIN = 45
SESSION_MIN = 390


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bucket(gap_pct: float) -> tuple:
    for row in GAP_TABLE:
        if row[0] < gap_pct <= row[1]:
            return row
    return GAP_TABLE[3]


def pre_open_outlook(
    es_pct: float | None,
    vix_level: float | None = None,
    vix_pct: float | None = None,
    engine_bias: str | None = None,
    ref_label: str = "yesterday",
) -> dict[str, Any] | None:
    """Expected open gap ≈ S&P futures move since yesterday's close → full-day odds from GAP_TABLE."""
    if es_pct is None:
        return None
    row = _bucket(float(es_pct))
    lo, hi, n, p_red, q10, q50, q90 = row
    vix_scaled = vix_level is not None and vix_level > 0
    if vix_scaled:
        r50, z10, z90 = GAP_VIX_RESID[GAP_TABLE.index(row)]
        s = (vix_level / math.sqrt(252)) ** VIX_RANGE_POW
        mid = float(es_pct) + r50
        q10, q50, q90 = round(mid + z10 * s, 2), round(mid, 2), round(mid + z90 * s, 2)
    risk_reasons = []
    if abs(es_pct) >= 1.0:
        risk_reasons.append(f"S&P futures {es_pct:+.2f}% overnight")
    if vix_pct is not None and vix_pct >= 10:
        risk_reasons.append(f"VIX up {vix_pct:.0f}%")
    if vix_level is not None and vix_level >= 25:
        risk_reasons.append(f"VIX at {vix_level:.1f}")
    if p_red >= 0.6:
        lean = "BEARISH"
    elif p_red <= 0.4:
        lean = "BULLISH"
    else:
        lean = "MIXED"
    return {
        "expected_gap_pct": round(float(es_pct), 2),
        "lean": lean,
        "p_close_red": p_red,
        "p_close_green": round(1 - p_red, 2),
        "eod_range_pct": {"q10": q10, "q50": q50, "q90": q90},
        "similar_days": n,
        "gap_bucket": [lo, hi],
        "high_risk": bool(risk_reasons),
        "risk_reasons": risk_reasons,
        "engine_bias": engine_bias,
        "range_vix_scaled": vix_scaled,
        "note": (
            f"On {n} past days with a similar open, SPY closed red {p_red * 100:.0f}% of the time. "
            + (
                f"Sized for VIX {vix_level:.1f}, 80% of closes should land between {q10:+.2f}% and {q90:+.2f}% vs {ref_label}."
                if vix_scaled
                else f"80% closed between {q10:+.2f}% and {q90:+.2f}% vs {ref_label}."
            )
        ),
    }


def intraday_close_range(
    move_so_far_pct: float,
    minutes_since_open: float,
    vix_prev: float | None,
    ref_label: str = "yesterday",
) -> dict[str, Any] | None:
    if vix_prev is None or vix_prev <= 0:
        return None
    frac = min(max(minutes_since_open / SESSION_MIN, 0.0), 1.0)
    sd = INTRADAY_K * (vix_prev / math.sqrt(252)) * (vix_prev / 20.0) ** (INTRADAY_VIX_EXP - 1.0) * math.sqrt(max(1.0 - frac, 0.0))
    r = float(move_so_far_pct)
    if sd <= 1e-9:
        p_green = 1.0 if r > 0 else 0.0 if r < 0 else 0.5
        lo = hi = r
    else:
        p_green = 1.0 - _norm_cdf(-r / sd)
        lo, hi = r - Z80 * sd, r + Z80 * sd
    return {
        "move_so_far_pct": round(r, 2),
        "minutes_since_open": int(minutes_since_open),
        "likely_close_pct": round(r, 2),
        "range80_pct": [round(lo, 2), round(hi, 2)],
        "p_close_green": round(p_green, 2),
        "note": (
            f"With {max(0, SESSION_MIN - int(minutes_since_open))} min left, 80% of similar days "
            f"closed between {lo:+.2f}% and {hi:+.2f}% vs {ref_label}."
        ),
    }


# ── live inputs ─────────────────────────────────────────────────────────

def _last_bar_date(sym: str) -> date | None:
    from signals.fetcher import _download_with_crumb_retry

    df = _download_with_crumb_retry(sym, period="5d", interval="1d", threads=False)
    if df is None or df.empty:
        return None
    return df.index[-1].date()


def _daily_last_two(sym: str) -> tuple[float | None, float | None]:
    from signals.fetcher import _download_with_crumb_retry

    df = _download_with_crumb_retry(sym, period="5d", interval="1d", threads=False)
    if df is None or df.empty:
        return None, None
    if hasattr(df.columns, "levels"):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    c = df["Close"].dropna()
    if len(c) < 2:
        return None, None
    return float(c.iloc[-2]), float(c.iloc[-1])


def _spy_today(now) -> tuple[float | None, float | None, float | None]:
    """(prior close, last price, today's open) from 5-min bars; None outside a session day."""
    from signals.fetcher import _download_with_crumb_retry

    df = _download_with_crumb_retry("SPY", period="5d", interval="5m", threads=False)
    if df is None or df.empty:
        return None, None, None
    if hasattr(df.columns, "levels"):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    idx = df.index.tz_convert("America/New_York") if df.index.tz is not None else df.index
    df = df.set_axis(idx)
    today = df[df.index.date == now.date()]
    prev = df[df.index.date < now.date()]
    if today.empty or prev.empty:
        return None, None, None
    return float(prev["Close"].iloc[-1]), float(today["Close"].iloc[-1]), float(today["Open"].iloc[0])


def _prev_session(d: date) -> date:
    from signals.market_calendar import is_nyse_holiday

    d -= timedelta(days=1)
    while d.weekday() >= 5 or is_nyse_holiday(d):
        d -= timedelta(days=1)
    return d


def _ref_close_date(now) -> date:
    """Session whose close the pulse is measured against (the latest close before the next open)."""
    from signals.market_calendar import is_nyse_holiday

    d = now.date()
    if d.weekday() < 5 and not is_nyse_holiday(d) and now.hour * 60 + now.minute >= 960:
        return d
    return _prev_session(d)


def _close_label(d: date) -> str:
    return f"{d:%b} {d.day} close"


def _pre_open_scorable(c: dict) -> bool:
    """Only calls saved before the 9:30 ET open count; earlier builds saved them after the open."""
    try:
        t = datetime.fromisoformat(str(c.get("as_of")))
    except (TypeError, ValueError):
        return False
    return t.tzinfo is not None and (t.hour, t.minute) < (9, 30)


def _phase(now) -> str:
    if now.weekday() >= 5:
        return "closed"
    m = now.hour * 60 + now.minute
    if 240 <= m < 570:
        return "pre_open"
    if 570 <= m < 960:
        return "intraday"
    return "closed"


# ── storage + scoring ───────────────────────────────────────────────────

def _calls_dir():
    from config_loader import get_data_root

    d = get_data_root() / "market_pulse"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_day(day: str) -> dict:
    p = _calls_dir() / f"{day}.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def log_call(day: str, slot: str, payload: dict, *, overwrite: bool = False) -> bool:
    data = _load_day(day)
    if slot in data and not overwrite:
        return False
    from signals.time_et import now_et

    data[slot] = {**payload, "logged_at": now_et().isoformat(timespec="seconds")}
    p = _calls_dir() / f"{day}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(p)
    return True


def _due_intraday_slot(now) -> str | None:
    """The snapshot slot whose time just passed (within SLOT_LATE_MIN), so a late job never logs under an earlier slot."""
    cur = now.hour * 60 + now.minute
    for slot, (h, m) in sorted(INTRADAY_SLOT_TIMES.items(), key=lambda kv: kv[1], reverse=True):
        if 0 <= cur - (h * 60 + m) <= SLOT_LATE_MIN:
            return slot
    return None


def _score_intraday(c: dict, full: float) -> tuple[str, bool, bool, float | None, float | None]:
    lo, hi = (c.get("range80_pct") or [None, None])[:2]
    pg = c.get("p_close_green")
    called = "GREEN" if (0.5 if pg is None else pg) >= 0.5 else "RED"
    hit = (full > 0) if called == "GREEN" else (full < 0)
    inr = lo is not None and hi is not None and lo <= full <= hi
    return called, hit, inr, lo, hi


def score_calibration(calls: dict[str, dict], realized: dict[str, dict]) -> dict[str, Any]:
    """Hourly snapshots incl. headline intraday slots: green-odds buckets and range coverage by slot."""
    by_slot: dict[str, dict[str, int]] = {}
    buckets = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
    bk = [{"lo": lo, "hi": min(hi, 1.0), "n": 0, "green": 0, "sum_p": 0.0} for lo, hi in buckets]
    for day, slots in calls.items():
        rz = realized.get(day)
        if not rz:
            continue
        full = rz["full_pct"]
        for slot in INTRADAY_SLOT_TIMES:
            c = slots.get(slot)
            if not c or c.get("p_close_green") is None:
                continue
            _, hit, inr, _, _ = _score_intraday(c, full)
            a = by_slot.setdefault(slot, {"n": 0, "dir_hit": 0, "in_range": 0})
            a["n"] += 1
            a["dir_hit"] += int(hit)
            a["in_range"] += int(inr)
            pg = float(c["p_close_green"])
            for b, (lo, hi) in zip(bk, buckets):
                if lo <= pg < hi:
                    b["n"] += 1
                    b["green"] += int(full > 0)
                    b["sum_p"] += pg
                    break
    return {
        "by_slot": {
            s: {"days": a["n"], "direction_hit_pct": round(100 * a["dir_hit"] / a["n"], 1),
                "range_coverage_pct": round(100 * a["in_range"] / a["n"], 1)}
            for s, a in sorted(by_slot.items()) if a["n"]
        },
        "green_odds": [
            {"range": [b["lo"], b["hi"]], "n": b["n"], "avg_said_pct": round(100 * b["sum_p"] / b["n"], 1),
             "closed_green_pct": round(100 * b["green"] / b["n"], 1)}
            for b in bk if b["n"]
        ],
    }


def score_days(calls: dict[str, dict], realized: dict[str, dict]) -> dict[str, Any]:
    """calls: {date: {slot: payload}}; realized: {date: {gap_pct, full_pct}}."""
    rows = []
    agg: dict[str, dict[str, int]] = {s: {"n": 0, "dir_hit": 0, "dir_n": 0, "in_range": 0} for s in SLOTS}
    for day in sorted(calls, reverse=True):
        rz = realized.get(day)
        if not rz:
            continue
        full = rz["full_pct"]
        row: dict[str, Any] = {"date": day, "actual_gap_pct": rz.get("gap_pct"), "actual_close_pct": full}
        for slot in SLOTS:
            c = calls[day].get(slot)
            if not c:
                continue
            a = agg[slot]
            a["n"] += 1
            if slot == "pre_open" and not _pre_open_scorable(c):
                a["n"] -= 1
                row["pre_open"] = {"lean": c.get("lean"), "hit": None, "in_range": None, "late": True}
                continue
            if slot == "pre_open":
                p_red = c.get("p_close_red")
                rng = c.get("eod_range_pct") or {}
                lo, hi = rng.get("q10"), rng.get("q90")
                called = c.get("lean")
                hit = None
                if called in ("BEARISH", "BULLISH"):
                    hit = (full < 0) if called == "BEARISH" else (full > 0)
                inr = lo is not None and hi is not None and lo <= full <= hi
                row["pre_open"] = {"lean": called, "p_close_red": p_red, "range": [lo, hi], "hit": hit, "in_range": inr}
            else:
                called, hit, inr, lo, hi = _score_intraday(c, full)
                row[slot] = {"call": called, "likely_close_pct": c.get("likely_close_pct"), "range": [lo, hi], "hit": hit, "in_range": inr}
            if hit is not None:
                a["dir_n"] += 1
                a["dir_hit"] += int(bool(hit))
            a["in_range"] += int(bool(inr))
        rows.append(row)
    summary = {
        s: {
            "days": a["n"],
            "direction_hit_pct": round(100 * a["dir_hit"] / a["dir_n"], 1) if a["dir_n"] else None,
            "direction_calls": a["dir_n"],
            "range_coverage_pct": round(100 * a["in_range"] / a["n"], 1) if a["n"] else None,
        }
        for s, a in agg.items()
    }
    return {"summary": summary, "days": rows[:30]}


def _realized_spy(days: list[str]) -> dict[str, dict]:
    if not days:
        return {}
    from signals.fetcher import _download_with_crumb_retry

    start = (datetime.fromisoformat(min(days)) - timedelta(days=7)).date().isoformat()
    df = _download_with_crumb_retry("SPY", start=start, interval="1d", threads=False)
    if df is None or df.empty:
        return {}
    if hasattr(df.columns, "levels"):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    out = {}
    prev_close = None
    for ts, r in df.iterrows():
        d = ts.date().isoformat()
        if prev_close is not None and d in days:
            out[d] = {
                "gap_pct": round((float(r["Open"]) / prev_close - 1) * 100, 2),
                "full_pct": round((float(r["Close"]) / prev_close - 1) * 100, 2),
            }
        prev_close = float(r["Close"])
    return out


def scorecard(today: str | None = None) -> dict[str, Any]:
    calls = {}
    for p in sorted(_calls_dir().glob("*.json")):
        d = p.stem
        if today and d >= today:
            continue
        data = _load_day(d)
        if data:
            calls[d] = data
    try:
        realized = _realized_spy(list(calls))
    except Exception as e:
        logger.debug("market_pulse realized fetch failed: %s", e)
        realized = {}
    out = score_days(calls, realized)
    out["calibration"] = score_calibration(calls, realized)
    return out


# ── main entry ──────────────────────────────────────────────────────────

def _engine_bias_today(day: str) -> str | None:
    try:
        from config_loader import get_data_root

        p = get_data_root() / "pre_market_latest.json"
        d = json.loads(p.read_text())
        return d.get("bias") if str(d.get("timestamp", ""))[:10] == day else None
    except Exception:
        return None


def build_market_pulse(*, log: bool = False, now=None) -> dict[str, Any]:
    from signals.time_et import now_et

    now = now or now_et()
    day = now.date().isoformat()
    phase = _phase(now)
    out: dict[str, Any] = {"as_of": now.isoformat(timespec="seconds"), "date": day, "phase": phase}

    vix_prev = vix_last = None
    try:
        vix_prev, vix_last = _daily_last_two("^VIX")
    except Exception as e:
        logger.debug("market_pulse VIX failed: %s", e)
    vix_pct = round((vix_last / vix_prev - 1) * 100, 1) if vix_prev and vix_last else None

    ref_day = _ref_close_date(now)
    ref_label = _close_label(ref_day)
    out["ref_close_date"] = ref_day.isoformat()
    stamp = {"as_of": out["as_of"], "ref_close_date": ref_day.isoformat()}

    stored = _load_day(day)
    pre = stored.get("pre_open")
    if phase == "pre_open" or pre is None:
        es_pct = None
        try:
            es_prev, es_last = _daily_last_two("ES=F")
            if es_prev and es_last:
                es_pct = (es_last / es_prev - 1) * 100
        except Exception as e:
            logger.debug("market_pulse ES failed: %s", e)
        live_pre = pre_open_outlook(es_pct, vix_last, vix_pct, _engine_bias_today(day), ref_label)
        if live_pre:
            live_pre.update(stamp)
        if phase == "pre_open" and live_pre:
            pre = live_pre
            if log and now.weekday() < 5:
                log_call(day, "pre_open", live_pre, overwrite=True)
        elif pre is None and live_pre:
            # Evenings/weekends: show the next-session preview only once futures have traded
            # past the last SPY session (else ES "change" is just the last day's move).
            try:
                es_d, spy_d = _last_bar_date("ES=F"), _last_bar_date("SPY")
                if es_d and spy_d and es_d > spy_d:
                    pre = {**live_pre, "preview": True}
            except Exception:
                pass
    if pre and not pre.get("ref_close_date"):
        pre = {**pre, "ref_close_date": _prev_session(now.date()).isoformat()}
    out["pre_open"] = pre

    intraday = None
    if phase in ("intraday", "closed") and now.weekday() < 5:
        try:
            prev_close, last, open_px = _spy_today(now)
            if prev_close and last:
                mins = (now.hour * 60 + now.minute) - 570
                # prior-session VIX close sets the day's volatility scale
                vix_ref = vix_prev if phase == "intraday" else vix_prev
                sess_ref = _prev_session(now.date())
                intraday = intraday_close_range(
                    (last / prev_close - 1) * 100, min(mins, SESSION_MIN), vix_ref, _close_label(sess_ref)
                )
                if intraday:
                    intraday.update(as_of=out["as_of"], ref_close_date=sess_ref.isoformat())
                if intraday and open_px:
                    intraday["actual_gap_pct"] = round((open_px / prev_close - 1) * 100, 2)
                if intraday and log and phase == "intraday":
                    slot = _due_intraday_slot(now)
                    if slot and slot not in stored:
                        log_call(day, slot, intraday)
        except Exception as e:
            logger.debug("market_pulse intraday failed: %s", e)
    out["intraday"] = intraday
    out["vix"] = {"prev_close": vix_prev, "last": vix_last, "pct": vix_pct}
    out["logged_today"] = sorted(_load_day(day).keys())
    out["disclaimer"] = "Odds from past SPY days, not a forecast of the exact close. Does not change stock signals."
    return out
