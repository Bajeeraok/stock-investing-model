"""
Regime persistence: count consecutive EOD snapshots with the same regime label.

A regime that appeared today is less trustworthy than one stable for 2+ weeks.
Uses data/eod/*.json (or Redis) — same source as forward_tracking and paper_trade_logger.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EOD_DIR_NAME = "eod"
_MIN_CONFIRMED_DAYS = 5   # default: 5 trading days (~1 week) to call a regime "confirmed"


def _list_eod_dates(eod_dir: Path) -> list[str]:
    seen: set[str] = set()
    dates: list[str] = []
    try:
        from signals.cache import list_eod_dates_redis
        for d in list_eod_dates_redis():
            if d not in seen and len(d) == 10 and d[4] == "-":
                seen.add(d)
                dates.append(d)
    except Exception:
        pass
    if eod_dir and eod_dir.exists():
        for p in eod_dir.glob("*.json"):
            d = p.stem
            if d not in seen and len(d) == 10 and d[4] == "-":
                seen.add(d)
                dates.append(d)
    return sorted(seen)


def _load_snapshot(eod_dir: Path, date_str: str) -> dict | None:
    try:
        from signals.cache import get_eod_snapshot_redis
        data = get_eod_snapshot_redis(date_str)
        if data and isinstance(data, dict) and data.get("run_results") is not None:
            return data
    except Exception:
        pass
    p = eod_dir / f"{date_str}.json"
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _regime_from_snapshot(snap: dict) -> str | None:
    """Extract global market regime from an EOD snapshot dict."""
    # Top-level field (saved by run_daily when regime is stored at root)
    for key in ("global_market_regime", "market_regime"):
        r = snap.get(key)
        if r and isinstance(r, str) and r.strip():
            return r.upper().strip()
    # Fallback: first non-error ticker's _global_market_regime
    for row in snap.get("run_results") or []:
        if isinstance(row, dict) and not row.get("error"):
            reg = row.get("_global_market_regime")
            if reg and isinstance(reg, str) and reg.strip():
                return reg.upper().strip()
    return None


def compute_regime_persistence(
    current_regime: str,
    data_root: Path | None = None,
    min_confirmed_days: int = _MIN_CONFIRMED_DAYS,
    lookback: int = 60,
) -> dict[str, Any]:
    """
    Scan the last `lookback` EOD snapshots (newest→oldest) and count how many
    consecutive days share `current_regime`.

    Parameters
    ----------
    current_regime      : Regime label to track (e.g. "BULL", "NEUTRAL", "BEAR").
    data_root           : Root of the data directory; defaults to backend/data.
    min_confirmed_days  : Days required to mark `regime_confirmed` True (default 5).
    lookback            : Maximum snapshots to inspect (default 60 ≈ 3 months).

    Returns
    -------
    current_regime          : echo of input
    days_stable             : consecutive days in current_regime
    regime_confirmed        : True when days_stable >= min_confirmed_days
    streak_start_date       : earliest date in the current streak (YYYY-MM-DD)
    previous_regime         : regime label just before this streak
    previous_regime_duration: how many days the previous regime lasted in our window
    snapshots_checked       : how many snapshots were readable
    """
    if data_root is None:
        data_root = Path(__file__).resolve().parent.parent / "data"
    eod_dir = data_root / _EOD_DIR_NAME

    dates = _list_eod_dates(eod_dir)
    base: dict[str, Any] = {
        "current_regime": current_regime,
        "days_stable": 0,
        "regime_confirmed": False,
        "streak_start_date": None,
        "previous_regime": None,
        "previous_regime_duration": None,
        "snapshots_checked": 0,
    }

    if not dates:
        return base

    # Walk newest→oldest through the window
    window = list(reversed(dates[-lookback:]))
    target = current_regime.upper().strip()

    days_stable = 0
    streak_start: str | None = None
    prev_regime: str | None = None
    prev_duration = 0
    in_streak = True
    checked = 0

    for date_str in window:
        snap = _load_snapshot(eod_dir, date_str)
        if not snap:
            continue
        reg = _regime_from_snapshot(snap)
        if reg is None:
            continue
        checked += 1

        if in_streak:
            if reg == target:
                days_stable += 1
                streak_start = date_str
            else:
                in_streak = False
                prev_regime = reg
                prev_duration = 1
        else:
            if prev_regime is not None and reg == prev_regime:
                prev_duration += 1
            else:
                break  # prev regime also changed — stop here

    base["days_stable"] = days_stable
    base["regime_confirmed"] = days_stable >= min_confirmed_days
    base["streak_start_date"] = streak_start
    base["previous_regime"] = prev_regime
    base["previous_regime_duration"] = prev_duration if prev_regime else None
    base["snapshots_checked"] = checked
    return base
