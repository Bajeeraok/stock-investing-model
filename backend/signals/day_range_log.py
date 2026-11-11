"""
Live tracking of the per-stock day range: snapshot each ticker's range at fixed times
(9:20 pre-open, 10:30, 12:30, 15:30 ET), score every snapshot after the close against what
actually happened afterwards, and aggregate hit rates for tuning. Files: DATA_ROOT/day_range_log/.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

SLOTS: dict[str, tuple[int, int]] = {"0920": (9, 20), "1030": (10, 31), "1230": (12, 31), "1530": (15, 31)}
SLOT_START: dict[str, tuple[int, int]] = {"0920": (9, 30), "1030": (10, 30), "1230": (12, 30), "1530": (15, 30)}
SLOT_LABEL = {"0920": "Pre-open", "1030": "10:30", "1230": "12:30", "1530": "3:30"}


def _dir():
    from config_loader import get_data_root

    d = get_data_root() / "day_range_log"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(day: str) -> dict:
    p = _dir() / f"{day}.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def _save(day: str, data: dict) -> None:
    p = _dir() / f"{day}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=str))
    tmp.replace(p)


def compact(r: dict) -> dict:
    keep = ("phase", "ref_close", "ref_date", "sigma_pct", "last", "minutes_left", "close_low", "close_mid",
            "close_high", "close_low50", "close_high50", "p_close_green", "ladder")
    out = {k: r.get(k) for k in keep if r.get(k) is not None}
    out["levels"] = [{k: lv.get(k) for k in ("label", "price", "side", "p_reach", "p_close_beyond")}
                     for lv in r.get("levels") or []]
    return out


def _summary_for(ticker: str, period: str) -> dict | None:
    try:
        from signals.cache import cache_key, get_cached

        for k in (cache_key("ticker_detail", ticker, period), cache_key("ticker_detail_last", ticker, period)):
            d = get_cached(k)
            if isinstance(d, dict) and d.get("investor_summary"):
                return d["investor_summary"]
    except Exception:
        pass
    return None


def log_slot(slot: str, config: dict, *, tickers: list[str] | None = None, now: datetime | None = None) -> int:
    from config_loader import get_dashboard_signal_universe
    from signals.stock_day_range import compute_stock_day_range
    from signals.time_et import now_et

    now = now or now_et()
    day = now.date().isoformat()
    data = _load(day)
    snaps = data.setdefault("snapshots", {}).setdefault(slot, {})
    period = (config.get("data") or {}).get("period", "2y") or "2y"
    todo = [t for t in (tickers or get_dashboard_signal_universe(config)) if t not in snaps and not t.endswith("-USD")]

    def _one(t: str):
        try:
            r = compute_stock_day_range(t, _summary_for(t, period), now=now)
            return t, compact(r) if r else None
        except Exception as e:
            logger.debug("day_range_log %s failed: %s", t, e)
            return t, None

    with ThreadPoolExecutor(max_workers=4) as ex:
        for t, snap in ex.map(_one, todo):
            if snap:
                snaps[t] = {**snap, "logged_at": now.isoformat(timespec="seconds")}
    _save(day, data)
    return len(snaps)


def score_snapshot(snap: dict, *, low: float, high: float, close: float) -> dict:
    """Score one snapshot against the low/high traded after it and the official close."""
    lo80, hi80 = snap.get("close_low"), snap.get("close_high")
    lo50, hi50 = snap.get("close_low50"), snap.get("close_high50")
    mid = snap.get("close_mid")
    out: dict[str, Any] = {
        "close": round(close, 2), "low_after": round(low, 2), "high_after": round(high, 2),
        "in80": None if lo80 is None else lo80 <= close <= hi80,
        "in50": None if lo50 is None else lo50 <= close <= hi50,
        "close_err_pct": round((close / mid - 1) * 100, 2) if mid else None,
        "ladder": [{"p": r["p"], "dip_hit": low <= r["dip"], "pop_hit": high >= r["pop"]}
                   for r in snap.get("ladder") or []],
        "levels": [],
    }
    for lv in snap.get("levels") or []:
        p, below = lv.get("price"), lv.get("side") == "below"
        if not p:
            continue
        out["levels"].append({
            "label": lv.get("label"), "p_reach": lv.get("p_reach"), "p_close_beyond": lv.get("p_close_beyond"),
            "reached": low <= p if below else high >= p,
            "closed_beyond": close < p if below else close > p,
        })
    return out


def _session_bars(ticker: str, day: str):
    import yfinance as yf

    t = yf.Ticker(ticker)
    m = t.history(period="5d", interval="5m", auto_adjust=False)
    d = t.history(period="5d", interval="1d", auto_adjust=False)
    if m is None or m.empty or d is None or d.empty:
        return None, None
    mi = m.index.tz_convert("America/New_York") if m.index.tz is not None else m.index
    m = m.set_axis(mi)
    m = m[[x.date().isoformat() == day for x in m.index]]
    di = d.index.tz_convert("America/New_York") if d.index.tz is not None else d.index
    closes = {x.date().isoformat(): float(c) for x, c in zip(di, d["Close"])}
    return (m if not m.empty else None), closes.get(day)


def score_day(day: str, *, bars_fn=None) -> int:
    data = _load(day)
    snaps = data.get("snapshots") or {}
    scored = data.setdefault("scored", {})
    tickers = sorted({t for s in snaps.values() for t in s})
    fn = bars_fn or _session_bars

    def _one(t: str):
        try:
            return t, fn(t, day)
        except Exception:
            return t, (None, None)

    n = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for t, (m, close) in ex.map(_one, [t for t in tickers if any(t not in scored.get(s, {}) for s in snaps if t in snaps[s])]):
            if m is None or close is None:
                continue
            for slot, by_t in snaps.items():
                if t not in by_t or t in scored.get(slot, {}):
                    continue
                h, mi = SLOT_START.get(slot, (9, 30))
                after = m[[(x.hour, x.minute) >= (h, mi) for x in m.index]]
                if after.empty:
                    continue
                scored.setdefault(slot, {})[t] = score_snapshot(
                    by_t[t], low=float(after["Low"].min()), high=float(after["High"].max()), close=close)
                n += 1
    _save(day, data)
    return n


def score_pending(today: str, *, include_today: bool) -> int:
    n = 0
    for p in sorted(_dir().glob("*.json"))[-30:]:
        d = p.stem
        if d > today or (d == today and not include_today):
            continue
        data = _load(d)
        snaps, scored = data.get("snapshots") or {}, data.get("scored") or {}
        if any(t not in scored.get(s, {}) for s, by_t in snaps.items() for t in by_t):
            n += score_day(d)
    return n


def aggregate(days_data: list[dict], ticker: str | None = None) -> dict[str, Any]:
    """Hit rates per slot (optionally one ticker): close-range coverage and ladder calibration."""
    out: dict[str, Any] = {}
    for slot in SLOTS:
        rows = [r for d in days_data for t, r in ((d.get("scored") or {}).get(slot) or {}).items()
                if ticker is None or t == ticker]
        if not rows:
            continue
        pct = lambda xs: round(100 * sum(xs) / len(xs)) if xs else None  # noqa: E731
        ladder: dict[float, list[bool]] = {}
        for r in rows:
            for x in r.get("ladder") or []:
                ladder.setdefault(x["p"], []).extend([x["dip_hit"], x["pop_hit"]])
        out[slot] = {
            "label": SLOT_LABEL[slot],
            "n": len(rows),
            "in80_pct": pct([r["in80"] for r in rows if r.get("in80") is not None]),
            "in50_pct": pct([r["in50"] for r in rows if r.get("in50") is not None]),
            "avg_abs_close_err_pct": round(sum(abs(r["close_err_pct"]) for r in rows if r.get("close_err_pct") is not None)
                                           / max(1, sum(r.get("close_err_pct") is not None for r in rows)), 2),
            "ladder": [{"p": p, "hit_pct": pct(v), "n": len(v)} for p, v in sorted(ladder.items(), reverse=True)],
        }
    return out


_AGG_CACHE: dict[str, Any] = {"ts": 0.0, "days": None}


def _recent_days(limit: int = 60) -> list[dict]:
    import time as _t

    if _AGG_CACHE["days"] is not None and _t.time() - _AGG_CACHE["ts"] < 600:
        return _AGG_CACHE["days"]
    days = []
    for p in sorted(_dir().glob("*.json"))[-limit:]:
        d = _load(p.stem)
        if d.get("scored"):
            days.append({"date": p.stem, "scored": d["scored"]})
    _AGG_CACHE.update(ts=_t.time(), days=days)
    return days


def scorecard(ticker: str | None = None) -> dict[str, Any]:
    days = _recent_days()
    return {"days": len(days), "since": days[0]["date"] if days else None,
            "slots": aggregate(days, ticker.upper() if ticker else None)}
