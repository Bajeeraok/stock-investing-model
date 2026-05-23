"""
Browser push for retail digests (story changes, trim list, regime flips).

Dedupes by content fingerprint so dashboard warm does not spam subscribers.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from config_loader import get_data_root

logger = logging.getLogger(__name__)


def _state_path() -> Path:
    return get_data_root() / "push_digest_state.json"


def _load_state() -> dict[str, Any]:
    p = _state_path()
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _fingerprint(story_changes: list[dict], trim_tickers: list[str]) -> str:
    parts: list[str] = []
    for r in story_changes or []:
        parts.append(f"{r.get('ticker')}:{r.get('story_change')}")
    parts.extend(sorted(trim_tickers or []))
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_push_title(story_changes: list[dict], trim_tickers: list[str]) -> str:
    n_story = len(story_changes or [])
    n_trim = len(trim_tickers or [])
    if n_story and n_trim:
        return f"Thrive Alpha: {n_story} story change(s), {n_trim} trim"
    if n_story:
        return f"Thrive Alpha: {n_story} story change(s)"
    if n_trim:
        return f"Thrive Alpha: {n_trim} trim candidate(s)"
    return "Thrive Alpha digest"


def build_push_body(
    story_changes: list[dict] | None = None,
    trim_tickers: list[str] | None = None,
    *,
    max_lines: int = 6,
) -> str:
    lines: list[str] = []
    for r in (story_changes or [])[:max_lines]:
        t = r.get("ticker", "?")
        msg = (r.get("story_change") or r.get("summary") or "")[:100]
        if msg:
            lines.append(f"{t}: {msg}")
    trim_t = trim_tickers or []
    if trim_t and len(lines) < max_lines:
        lines.append("Trim: " + ", ".join(trim_t[:12]))
    body = "\n".join(lines).strip()
    return body[:900] if body else "Dashboard update — open for details."


def maybe_broadcast_retail_push(
    config: dict,
    *,
    story_changes: list[dict] | None = None,
    trim_tickers: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Send web push when digest has content. Respects alerts.web_push_enabled (default true).
    Skips if fingerprint matches last send unless force=True.
    """
    alerts_cfg = (config.get("alerts") or {}) if config else {}
    if alerts_cfg.get("web_push_enabled") is False:
        return {"skipped": True, "reason": "web_push_disabled"}

    sc = story_changes or []
    trim_t = trim_tickers or []
    if not sc and not trim_t:
        return {"skipped": True, "reason": "empty_digest"}

    fp = _fingerprint(sc, trim_t)
    state = _load_state()
    if not force and state.get("last_fingerprint") == fp:
        return {"skipped": True, "reason": "duplicate_digest", "fingerprint": fp}

    title = build_push_title(sc, trim_t)
    body = build_push_body(sc, trim_t)
    try:
        from api.routers.push import broadcast_web_push

        result = broadcast_web_push(title, body, url="/")
    except Exception as e:
        logger.warning("web push digest failed: %s", e)
        return {"skipped": True, "reason": str(e)}

    if result.get("sent", 0) > 0 or result.get("total", 0) == 0:
        state["last_fingerprint"] = fp
        state["last_title"] = title
        _save_state(state)

    return {"ok": True, "fingerprint": fp, **result}


def _catalyst_fingerprint(line: str) -> str:
    return hashlib.sha256(f"catalyst:{line}".encode("utf-8")).hexdigest()[:16]


def maybe_broadcast_catalyst_push(
    config: dict,
    digest_line: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    P2: Push digest hook for macro catalyst countdown + gap-fade history.
    Example: "CPI in 30m; pre-market bull; gap-fade history 61%"
    """
    alerts_cfg = (config.get("alerts") or {}) if config else {}
    if alerts_cfg.get("web_push_enabled") is False:
        return {"skipped": True, "reason": "web_push_disabled"}
    if not digest_line or not str(digest_line).strip():
        return {"skipped": True, "reason": "empty_catalyst_line"}

    fp = _catalyst_fingerprint(digest_line.strip())
    state = _load_state()
    if not force and state.get("last_catalyst_fingerprint") == fp:
        return {"skipped": True, "reason": "duplicate_catalyst", "fingerprint": fp}

    title = "Thrive Alpha: market catalyst"
    body = digest_line.strip()[:900]
    try:
        from api.routers.push import broadcast_web_push

        result = broadcast_web_push(title, body, url="/")
    except Exception as e:
        logger.warning("catalyst web push failed: %s", e)
        return {"skipped": True, "reason": str(e)}

    if result.get("sent", 0) > 0 or result.get("total", 0) == 0:
        state["last_catalyst_fingerprint"] = fp
        state["last_catalyst_line"] = body
        _save_state(state)

    return {"ok": True, "fingerprint": fp, **result}
