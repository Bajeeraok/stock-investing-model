"""
Phase C4/C5 — catalyst + post-earnings modifiers and setup stress labels on signal rows.

Mutates retail_status subtitles and adds top-level row fields for Signals UI.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ST_BUY_TOKENS = frozenset({"BUY", "ADD", "STRONG BUY", "ACCUMULATE"})


def _st_is_buy(row: dict[str, Any]) -> bool:
    st = str(row.get("short_suggestion") or row.get("short_term") or "").upper()
    sig = str(row.get("signal") or "").upper()
    for tok in _ST_BUY_TOKENS:
        if tok in st or tok in sig:
            return True
    plan = str(row.get("plan_action") or "").upper()
    return "BUY" in plan and "WATCH" not in plan and "AVOID" not in plan


def compute_stress_label(row: dict[str, Any], *, vix: float | None = None) -> str | None:
    """C5: contextual note when ST setup is sensitive to vol regime."""
    if not _st_is_buy(row):
        return None
    v = vix
    if v is None:
        mro = row.get("market_overlay") if isinstance(row.get("market_overlay"), dict) else {}
        try:
            v = float(mro.get("vix")) if mro.get("vix") is not None else None
        except (TypeError, ValueError):
            v = None
    if v is None:
        return None
    if v >= 28:
        return f"High-vol tape (VIX ~{v:.0f}) — tighten size; ST adds work better after VIX < 25."
    if v >= 22:
        return f"VIX ~{v:.0f} — ST breakout adds work better when VIX < 22 and breadth confirms."
    if v < 14:
        return f"Low VIX (~{v:.0f}) — complacency risk; still use stops on tactical adds."
    return None


def _days_since_earnings(row: dict[str, Any]) -> int | None:
    d = row.get("earnings_days_until")
    if d is None:
        return None
    try:
        n = int(d)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return abs(n)
    if n == 0:
        return 0
    return None


def apply_post_earnings_modifier(row: dict[str, Any], config: dict | None) -> dict[str, Any] | None:
    """C4: annotate retail read within 5 sessions after earnings."""
    days_since = _days_since_earnings(row)
    if days_since is None or days_since > 5:
        return None
    try:
        from signals.post_earnings_transition import compute_post_earnings_signal

        ctx = {
            "days_since_earnings": days_since,
            "most_recent_earnings_date": None,
            "post_earnings_return_pct": row.get("daily_move_pct"),
            "post_earnings_volume_ratio": row.get("volume_ratio"),
        }
        pe = compute_post_earnings_signal(str(row.get("ticker") or ""), config or {}, earnings_context=ctx)
        if not pe.active:
            return None
        out = {
            "active": True,
            "beat_or_miss": pe.beat_or_miss,
            "signal_direction": pe.signal_direction,
            "transition_note": pe.transition_note,
            "eps_surprise_pct": pe.eps_surprise_pct,
            "price_reaction_pct": pe.price_reaction_pct,
            "days_since": pe.days_since,
        }
        return out
    except Exception as exc:
        logger.debug("post_earnings modifier %s: %s", row.get("ticker"), exc)
        return None


def apply_catalyst_modifier(row: dict[str, Any]) -> dict[str, Any] | None:
    """C4: surface catalyst as retail modifier when active."""
    cat = row.get("catalyst")
    if not isinstance(cat, dict) or not cat.get("active"):
        return None
    regime = str(row.get("regime") or "").upper()
    bull = regime == "UP" or (row.get("composite_buy") or 0) >= 60
    note = cat.get("override_note") or cat.get("headline_summary")
    if bull and cat.get("top_impact", 0) >= 2:
        headline = (
            "Momentum regime + catalyst — valuation secondary until event digested."
        )
    else:
        headline = note or f"Catalyst active ({cat.get('top_event_type', 'event')})."
    return {
        "active": True,
        "event_type": cat.get("top_event_type"),
        "headline": headline,
        "override_note": note,
        "hours_since": cat.get("hours_since_catalyst"),
    }


def _append_subtitle(rs: dict[str, Any], extra: str) -> None:
    if not extra:
        return
    prev = str(rs.get("dynamic_subtitle") or "").strip()
    if extra in prev:
        return
    rs["dynamic_subtitle"] = f"{prev} · {extra}" if prev else extra


def enrich_signal_event_modifiers(
    row: dict[str, Any],
    config: dict | None = None,
    *,
    vix: float | None = None,
) -> dict[str, Any]:
    """Apply C4/C5 fields and patch retail_status copy."""
    pe = apply_post_earnings_modifier(row, config)
    if pe:
        row["post_earnings_transition"] = pe
        rs = row.get("retail_status")
        if isinstance(rs, dict):
            direction = pe.get("signal_direction") or "neutral"
            tag = f"Post-ER {direction}"
            if pe.get("beat_or_miss"):
                tag = f"Post-ER {pe['beat_or_miss']} → {direction}"
            _append_subtitle(rs, tag)
            if pe.get("transition_note"):
                rs["event_note"] = pe["transition_note"]

    cat = apply_catalyst_modifier(row)
    if cat:
        row["catalyst_modifier"] = cat
        rs = row.get("retail_status")
        if isinstance(rs, dict):
            _append_subtitle(rs, str(cat.get("headline") or "Catalyst active"))

    stress = compute_stress_label(row, vix=vix)
    if stress:
        row["stress_label"] = stress

    return row


def enrich_results_event_modifiers(
    results: list[dict[str, Any]] | None,
    config: dict | None = None,
    *,
    vix: float | None = None,
) -> None:
    """Batch apply modifiers after catalyst + retail_status enrichment."""
    for row in results or []:
        if not isinstance(row, dict) or row.get("error"):
            continue
        try:
            enrich_signal_event_modifiers(row, config, vix=vix)
        except Exception as exc:
            logger.debug("event_modifiers %s: %s", row.get("ticker"), exc)
