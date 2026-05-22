"""
Trim cooldown + one-line trade journal (behavioral guardrails).

Persisted under DATA_ROOT/trade_discipline.json.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config_loader import get_data_root

logger = logging.getLogger(__name__)


def _path() -> Path:
    return get_data_root() / "trade_discipline.json"


def _load() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return {"cooldowns": {}, "journal": []}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"cooldowns": {}, "journal": []}
        data.setdefault("cooldowns", {})
        data.setdefault("journal", [])
        return data
    except Exception as e:
        logger.warning("trade_discipline read failed: %s", e)
        return {"cooldowns": {}, "journal": []}


def _save(data: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _cooldown_days(config: dict) -> int:
    beh = config.get("behavior") or {}
    try:
        return max(1, min(90, int(beh.get("cooldown_days_after_trim", 14))))
    except (TypeError, ValueError):
        return 14


def _journal_max(config: dict) -> int:
    beh = config.get("behavior") or {}
    try:
        return max(20, min(500, int(beh.get("journal_max_entries", 200))))
    except (TypeError, ValueError):
        return 200


def check_add_allowed(ticker: str, config: dict, *, thesis_override: bool = False) -> dict[str, Any]:
    """
    Returns { allowed, reason, until, days_left }.
    thesis_override=True skips cooldown (user logged a thesis update).
    """
    t = (ticker or "").strip().upper()
    if not t or thesis_override:
        return {"allowed": True, "ticker": t, "reason": None, "until": None, "days_left": 0}

    data = _load()
    entry = data.get("cooldowns", {}).get(t)
    if not isinstance(entry, dict):
        return {"allowed": True, "ticker": t, "reason": None, "until": None, "days_left": 0}

    until_s = entry.get("until")
    if not until_s:
        return {"allowed": True, "ticker": t, "reason": None, "until": None, "days_left": 0}

    try:
        until_d = date.fromisoformat(str(until_s)[:10])
    except ValueError:
        return {"allowed": True, "ticker": t, "reason": None, "until": None, "days_left": 0}

    today = date.today()
    if today >= until_d:
        return {"allowed": True, "ticker": t, "reason": None, "until": until_s, "days_left": 0}

    days_left = (until_d - today).days
    reason = entry.get("reason") or "trim"
    return {
        "allowed": False,
        "ticker": t,
        "reason": reason,
        "until": until_s,
        "days_left": days_left,
        "note": entry.get("note"),
    }


def record_trim_cooldown(ticker: str, config: dict, *, note: str | None = None) -> dict[str, Any]:
    """Start cooldown after user logs a trim."""
    t = (ticker or "").strip().upper()
    if not t:
        return {"ok": False, "error": "ticker required"}

    days = _cooldown_days(config)
    until = date.today() + timedelta(days=days)
    data = _load()
    data.setdefault("cooldowns", {})[t] = {
        "until": until.isoformat(),
        "reason": "trim",
        "note": (note or "").strip()[:500] or None,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(data)
    append_journal(t, "trim", note or f"Trim logged — {days}d re-add cooldown", config)
    return {"ok": True, "ticker": t, "until": until.isoformat(), "cooldown_days": days}


def append_journal(ticker: str, action: str, note: str, config: dict) -> dict[str, Any]:
    """Append one-line journal entry (add | trim)."""
    t = (ticker or "").strip().upper()
    text = (note or "").strip()
    if not t or not text:
        return {"ok": False, "error": "ticker and note required"}

    data = _load()
    entries = data.setdefault("journal", [])
    entries.insert(
        0,
        {
            "ticker": t,
            "action": (action or "add").lower()[:16],
            "note": text[:500],
            "at": datetime.now(timezone.utc).isoformat(),
        },
    )
    max_n = _journal_max(config)
    data["journal"] = entries[:max_n]
    _save(data)
    return {"ok": True, "ticker": t, "action": action}


def list_journal(limit: int = 30) -> list[dict]:
    data = _load()
    entries = data.get("journal") or []
    if not isinstance(entries, list):
        return []
    return entries[: max(1, min(100, limit))]
