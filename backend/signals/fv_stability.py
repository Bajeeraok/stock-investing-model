"""Hold model fair value steady when it jumps without an earnings-input change.

Day-to-day FV swings of 20–50% (e.g. NVDA $233 -> $170 -> $233) came from flapping data inputs, not new
earnings, and flipped the valuation gate. A jump larger than JUMP_PCT is accepted only when TTM or forward EPS
moved by more than EPS_CHANGE_PCT, or when the new value repeats in a later market session; otherwise the last
accepted value is kept. State lives in Redis (disk fallback); with no state, the median of the last EOD snapshots
is the reference."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date
from statistics import median
from typing import Any

logger = logging.getLogger(__name__)

JUMP_PCT = 15.0
EPS_CHANGE_PCT = 3.0
CONFIRM_PCT = 5.0
_lock = threading.Lock()


def _moved(a: float | None, b: float | None, pct: float) -> bool:
    if a is None or b is None:
        return a != b
    if b == 0:
        return a != 0
    return abs(a / b - 1.0) * 100.0 > pct


def stabilize(prev: dict | None, raw: float, eps: tuple[float | None, float | None], today: str) -> tuple[float, dict, str | None]:
    """Return (fair value to use, new state, note when held)."""
    new = {"fv": raw, "eps": list(eps), "date": today}
    if not prev or not prev.get("fv"):
        return raw, new, None
    held = float(prev["fv"])
    if not _moved(raw, held, JUMP_PCT):
        return raw, new, None
    p_eps = prev.get("eps") or [None, None]
    if any(_moved(e, pe, EPS_CHANGE_PCT) for e, pe in zip(eps, p_eps) if e is not None and pe is not None):
        return raw, new, None
    pend = prev.get("pending") or {}
    if pend.get("fv") and pend.get("date") != today and not _moved(raw, float(pend["fv"]), CONFIRM_PCT):
        return raw, new, None
    state = dict(prev)
    if not pend.get("fv") or _moved(raw, float(pend["fv"]), CONFIRM_PCT):
        state["pending"] = {"fv": raw, "date": today}
    note = (f"Fair value held at ${held:,.2f}: today's estimate ${raw:,.2f} moved {abs(raw / held - 1) * 100:.0f}% "
            "with no change in earnings inputs. It updates if the new value repeats on another day.")
    return held, state, note


def _path():
    from config_loader import get_data_root

    return get_data_root() / "fv_stability.json"


_REDIS_KEY = "fv_stability:v1"
SEED_SESSIONS = 5
SEED_MIN_VALUES = 3
_seed_cache: dict[str, dict[str, dict]] = {}


def _session_today() -> str:
    """Last completed NYSE session, so a weekend or same-session rerun never counts as a later day."""
    try:
        from api.eod_job import last_completed_session_date

        return last_completed_session_date()
    except Exception:
        return date.today().isoformat()


def _load() -> dict[str, Any]:
    # Redis first: the disk file is lost on deploy restarts when DATA_ROOT is not a volume,
    # and an empty state accepted the first (possibly bad) value unchecked.
    try:
        from signals.cache import get_cached

        data = get_cached(_REDIS_KEY)
        if isinstance(data, dict) and data:
            return data
    except Exception:
        pass
    p = _path()
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def _save(data: dict[str, Any]) -> None:
    try:
        from signals.cache import _set_persistent

        _set_persistent(_REDIS_KEY, data)
    except Exception:
        pass
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(p)


def _seed_reference(ticker: str, today: str) -> dict | None:
    """Median fair value over the last SEED_SESSIONS EOD snapshots, when no state exists."""
    if today not in _seed_cache:
        by_ticker: dict[str, list[tuple[str, float]]] = {}
        try:
            from signals.cache import build_eod_snapshot_index
            from scripts.run_daily import load_eod_snapshot

            dates = sorted({s["date"] for s in build_eod_snapshot_index() if s.get("date")}, reverse=True)
            for d in [d for d in dates if d <= today][:SEED_SESSIONS]:
                for t, r in (load_eod_snapshot(d) or {}).items():
                    v = r.get("lt_fair_value_mid") if isinstance(r, dict) else None
                    if isinstance(v, (int, float)) and v > 0:
                        by_ticker.setdefault(str(t).upper(), []).append((d, float(v)))
        except Exception:
            logger.exception("[fv-stability] seed")
        _seed_cache.clear()
        _seed_cache[today] = {
            t: {"fv": round(median(v for _, v in vals), 2), "eps": [None, None], "date": max(d for d, _ in vals)}
            for t, vals in by_ticker.items()
            if len(vals) >= SEED_MIN_VALUES
        }
    return _seed_cache[today].get(ticker)


def apply(ticker: str, raw: float | None, trailing_eps: float | None, forward_eps: float | None) -> tuple[float | None, str | None]:
    if raw is None or raw <= 0 or "PYTEST_CURRENT_TEST" in os.environ:
        return raw, None
    t = ticker.upper()
    try:
        today = _session_today()
        with _lock:
            data = _load()
            prev = data.get(t) or _seed_reference(t, today)
            fv, state, note = stabilize(prev, float(raw), (trailing_eps, forward_eps), today)
            if state != data.get(t):
                data[t] = state
                _save(data)
        return round(fv, 2), note
    except Exception:
        logger.exception("[fv-stability] %s", t)
        return raw, None


MAX_FALLBACK_AGE_DAYS = 10


def last_accepted(ticker: str, today: date | None = None) -> float | None:
    """Last accepted model fair value (<= MAX_FALLBACK_AGE_DAYS old), for days the pipeline returns nothing."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return None
    try:
        st = _load().get(ticker.upper()) or {}
        fv, d = st.get("fv"), st.get("date")
        if not fv or not d:
            return None
        age = ((today or date.today()) - date.fromisoformat(d)).days
        return round(float(fv), 2) if 0 <= age <= MAX_FALLBACK_AGE_DAYS else None
    except Exception:
        logger.exception("[fv-stability] last_accepted %s", ticker)
        return None
