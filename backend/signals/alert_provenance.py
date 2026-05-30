"""
Provenance for overview alerts (Today's 3 moves, story changes, trim flags).

Separates *what fired the alert* from horizon playbook cards in ticker detail.
"""
from __future__ import annotations

from typing import Any


def _suggestion_bucket(s: str | None) -> str | None:
    if not s or not str(s).strip():
        return None
    u = str(s).upper()
    if "STRONG BUY" in u or u == "BUY" or "ADD" in u:
        return "add"
    if "TRIM" in u or "SELL" in u or "REDUCE" in u or "AVOID" in u:
        return "trim"
    if "WATCH" in u:
        return "watch"
    if "WAIT" in u or "HOLD" in u:
        return "hold"
    return "other"


def detect_horizon_suggestion_flips(
    prev: dict | None,
    current: dict[str, Any],
) -> list[str]:
    """Horizons whose suggestion bucket changed vs prior run (ST/MT/LT columns)."""
    if not prev:
        return []
    flips: list[str] = []
    for prev_key, cur_key, label in (
        ("short_suggestion", "short_suggestion", "short"),
        ("medium_suggestion", "medium_suggestion", "medium"),
        ("long_suggestion", "long_suggestion", "long"),
    ):
        pb = _suggestion_bucket(prev.get(prev_key))
        cb = _suggestion_bucket(current.get(cur_key))
        if pb is None or cb is None or pb == cb:
            continue
        flips.append(label)
    return flips


def detect_story_change(
    prev: dict | None,
    *,
    regime: str | None,
    composite_buy: float | None,
    current_row: dict[str, Any] | None = None,
    alert_delta: float = 15.0,
) -> dict[str, Any] | None:
    """
    Story-change vs last run. Returns None or fields to merge onto a signal row.

    Priority: regime flip > score drop (same as run_daily). Horizon flips are
    attached separately when present (do not replace composite headline).
    """
    if not prev:
        return None

    horizon_flips = detect_horizon_suggestion_flips(prev, current_row or {})
    prev_regime = prev.get("regime")
    prev_score = prev.get("composite_buy")

    story_change: str | None = None
    source = "composite"
    trigger: str | None = None
    horizon = "medium"

    if prev_regime and regime and prev_regime != regime:
        story_change = f"REGIME: {prev_regime} -> {regime}"
        trigger = "regime_flip"
    elif prev_score is not None and composite_buy is not None:
        delta = float(prev_score) - float(composite_buy)
        if delta >= alert_delta:
            story_change = (
                f"SCORE DROP: {float(prev_score):.0f} -> {float(composite_buy):.0f} (-{delta:.0f})"
            )
            trigger = "score_drop"

    if story_change is None and not horizon_flips:
        return None

    out: dict[str, Any] = {
        "story_change": story_change,
        "story_change_source": source,
        "story_change_trigger": trigger,
        "story_change_horizon": horizon,
    }
    if horizon_flips:
        out["story_change_horizon_flips"] = horizon_flips
        if story_change is None:
            labels = ", ".join(h.upper() for h in horizon_flips)
            out["story_change"] = f"HORIZON SHIFT: {labels} playbook changed"
            out["story_change_source"] = "horizon"
            out["story_change_trigger"] = "suggestion_flip"
            out["story_change_horizon"] = horizon_flips[0]
    return out


def trim_alert_meta(
    holding: dict[str, Any],
    *,
    sell_max: float = 35.0,
) -> dict[str, Any]:
    """
    Whether a portfolio holding is a trim candidate and why.
    Aligns with Dashboard.tsx filter (score, plan action, suggestion).
    """
    score = holding.get("score")
    action = (holding.get("action") or "").strip().upper()
    suggestion = (holding.get("suggestion") or "").strip().upper()

    triggers: list[str] = []
    if score is not None and float(score) < sell_max:
        triggers.append("score_below_threshold")
    if action in ("REDUCE", "AVOID"):
        triggers.append("plan_action")
    if "TRIM" in suggestion:
        triggers.append("suggestion_trim")

    is_candidate = bool(triggers)
    if not is_candidate:
        return {"is_trim_candidate": False}

    drivers: list[str] = []
    if "score_below_threshold" in triggers:
        drivers.append("composite_score")
    if "plan_action" in triggers:
        drivers.append("plan_7layer")
    if "suggestion_trim" in triggers and "composite_score" not in drivers:
        drivers.append("portfolio_suggestion")

    if len(drivers) == 1:
        primary = drivers[0]
        source = "composite" if primary == "composite_score" else "plan"
    else:
        primary = "composite+plan" if "composite_score" in drivers and "plan_7layer" in drivers else drivers[0]
        source = "composite+plan" if primary == "composite+plan" else (
            "composite" if "composite" in primary else "plan"
        )

    label_parts: list[str] = []
    if action:
        label_parts.append(action)
    elif suggestion and suggestion != "N/A":
        label_parts.append(suggestion.replace("CONSIDER ", ""))
    if score is not None and float(score) < sell_max:
        label_parts.append(f"score {float(score):.0f}")

    return {
        "is_trim_candidate": True,
        "trim_triggers": triggers,
        "trim_source": source,
        "trim_primary_driver": primary,
        "trim_horizon": "medium",
        "trim_detail": " · ".join(label_parts) if label_parts else "Review sizing",
    }


def enrich_signal_story_fields(
    row: dict[str, Any],
    prev: dict | None,
    *,
    alert_delta: float = 15.0,
) -> None:
    """Mutates row with story_change* fields from alert_provenance."""
    patch = detect_story_change(
        prev,
        regime=row.get("regime"),
        composite_buy=row.get("composite_buy"),
        current_row=row,
        alert_delta=alert_delta,
    )
    if not patch:
        row.setdefault("story_change", None)
        row.setdefault("story_change_source", None)
        row.setdefault("story_change_trigger", None)
        row.setdefault("story_change_horizon", None)
        row.setdefault("story_change_horizon_flips", None)
        return
    row.update(patch)


def attach_trim_provenance_to_holdings(
    per_holding: list[dict[str, Any]],
    *,
    sell_max: float = 35.0,
) -> None:
    """Mutates each holding with trim_* fields for UI (portfolio + Today's moves)."""
    for h in per_holding:
        if not isinstance(h, dict):
            continue
        meta = trim_alert_meta(h, sell_max=sell_max)
        for k in (
            "is_trim_candidate",
            "trim_source",
            "trim_primary_driver",
            "trim_triggers",
            "trim_horizon",
            "trim_detail",
        ):
            h[k] = meta.get(k)


def build_trim_candidates_from_holdings(
    per_holding: list[dict[str, Any]],
    *,
    sell_max: float = 35.0,
) -> list[dict[str, Any]]:
    """Dashboard trim list with provenance (score and/or plan)."""
    out: list[dict[str, Any]] = []
    for h in per_holding:
        if not isinstance(h, dict) or not h.get("ticker"):
            continue
        meta = trim_alert_meta(h, sell_max=sell_max)
        if meta.get("is_trim_candidate"):
            out.append({**h, **meta})
    return sorted(out, key=lambda x: (x.get("score") is None, x.get("score") or 0))
