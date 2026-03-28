"""
Macro calendar + analyst dispersion helpers for widening ST/MT/LT bands when:
  - High-impact US data (CPI, FOMC, etc.) is imminent (FMP economic calendar)
  - Street estimates disagree (EPS dispersion, price-target range vs median)
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

logger = logging.getLogger(__name__)

_HIGH_IMPACT = (
    "cpi", "ppi", "pce", "inflation", "fomc", "fed chair", "powell", "interest rate",
    "non-farm", "nfp", "payroll", "employment situation", "gdp advance", "gdp preliminary",
    "retail sales", "consumer confidence", "ism manufacturing", "treasury auction",
)


def _parse_event_date(ev: dict) -> _dt.date | None:
    ds = ev.get("date") or ev.get("time") or ""
    if not ds or not isinstance(ds, str):
        return None
    try:
        return _dt.date.fromisoformat(ds[:10])
    except ValueError:
        return None


def macro_event_band_context(calendar_events: list[dict] | None) -> dict[str, Any]:
    """
    Next high-impact US macro event in the next 7 calendar days → widen ST/MT bands.

    Returns:
        multiplier: float in [1.0, 1.22] applied symmetrically to band half-width
        note: optional short UI string
        next_event: optional event label
    """
    today = _dt.date.today()
    horizon = today + _dt.timedelta(days=7)
    best: tuple[_dt.date, str] | None = None  # (event_date, name)

    for ev in calendar_events or []:
        if not isinstance(ev, dict):
            continue
        name = (ev.get("name") or ev.get("event") or ev.get("title") or "").strip()
        if not name:
            continue
        country = (ev.get("country") or "").upper()
        if country and country not in ("US", "USA", "UNITED STATES", ""):
            continue
        nl = name.lower()
        if not any(k in nl for k in _HIGH_IMPACT):
            continue
        d = _parse_event_date(ev)
        if d is None or d < today or d > horizon:
            continue
        if best is None or d < best[0]:
            best = (d, name[:80])

    if best is None:
        return {"multiplier": 1.0, "note": None, "next_event": None}

    event_d, title = best
    days_until = (event_d - today).days
    mult = 1.0
    if days_until <= 0:
        mult = 1.20
    elif days_until == 1:
        mult = 1.16
    elif days_until == 2:
        mult = 1.12
    elif days_until <= 4:
        mult = 1.08
    else:
        mult = 1.05

    mult = min(1.22, mult)
    note = f"ST/MT bands +{(mult - 1) * 100:.0f}% — major macro ({event_d.isoformat()}): {title[:48]}…"

    return {
        "multiplier": round(mult, 4),
        "note": note,
        "next_event": title,
        "days_until": days_until,
    }


def symmetric_widen(low: float, high: float, mult: float) -> tuple[float, float]:
    """Expand [low, high] around midpoint by mult (>= 1)."""
    if mult <= 1.001 or high <= low:
        return low, high
    mid = (low + high) / 2.0
    half = (high - low) / 2.0 * mult
    return mid - half, mid + half


def lt_dispersion_multiplier(row: dict[str, Any]) -> tuple[float, str | None]:
    """
    Widen LT band when analyst price targets or EPS estimates are dispersed.
    Returns (multiplier >= 1.0, optional note).
    """
    m = 1.0
    notes: list[str] = []

    cl = row.get("cons_low")
    ch = row.get("cons_high")
    med = row.get("consensus_median") or row.get("cons_median")

    if cl is not None and ch is not None and med is not None:
        try:
            cl, ch, med = float(cl), float(ch), float(med)
            if med > 0 and ch >= cl:
                spread = (ch - cl) / med
                if spread > 0.20:
                    bump = min(0.28, (spread - 0.20) * 0.9)
                    m = max(m, 1.0 + bump)
                    notes.append(f"street target range wide ({spread:.0%} of median)")
        except (TypeError, ValueError):
            pass

    ed = row.get("eps_dispersion")
    if ed is not None:
        try:
            ed = float(ed)
            if ed > 0.14:
                bump = min(0.22, (ed - 0.14) * 1.1)
                m = max(m, 1.0 + bump)
                notes.append(f"EPS consensus dispersion {ed:.0%}")
        except (TypeError, ValueError):
            pass

    m = min(m, 1.45)
    note = "LT band widened — " + "; ".join(notes) if notes else None
    return m, note if m > 1.02 else None
