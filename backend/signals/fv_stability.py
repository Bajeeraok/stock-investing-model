"""Hold model fair value steady when it jumps without an earnings-input change.

Day-to-day FV swings of 20–50% (e.g. NVDA $233 -> $170 -> $233) came from flapping data inputs, not new
earnings, and flipped the valuation gate. A jump larger than JUMP_PCT is accepted only when TTM or forward EPS
moved by more than EPS_CHANGE_PCT, or when the new value repeats on a later day; otherwise the last accepted
value is kept."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date
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


def apply(ticker: str, raw: float | None, trailing_eps: float | None, forward_eps: float | None) -> tuple[float | None, str | None]:
    if raw is None or raw <= 0 or "PYTEST_CURRENT_TEST" in os.environ:
        return raw, None
    t = ticker.upper()
    try:
        with _lock:
            p = _path()
            data: dict[str, Any] = json.loads(p.read_text()) if p.exists() else {}
            fv, state, note = stabilize(data.get(t), float(raw), (trailing_eps, forward_eps), date.today().isoformat())
            if state != data.get(t):
                data[t] = state
                tmp = p.with_suffix(".tmp")
                tmp.write_text(json.dumps(data))
                tmp.replace(p)
        return round(fv, 2), note
    except Exception:
        logger.exception("[fv-stability] %s", t)
        return raw, None
