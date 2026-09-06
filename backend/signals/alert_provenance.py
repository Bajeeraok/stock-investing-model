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


def _safe_num(row: dict[str, Any] | None, key: str) -> float | None:
    if not row:
        return None
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _detect_ma50_transition(
    prev: dict[str, Any] | None,
    current_row: dict[str, Any] | None,
) -> tuple[str, str] | None:
    """Edge-cross on the same price-anchor fields _price_anchor_clause() explains
    (retail_action_payload.py) — was below/near-high yesterday, crossed the line today.
    Same prev-vs-curr edge-cross shape as scanner/engine.py's RSI_OVERSOLD/ML_PROB_CROSSED
    checks, applied to the daily EOD diff instead of the intraday scanner since only the
    daily row carries ma50/52w hi-lo.
    """
    prev_close, cur_close = _safe_num(prev, "close"), _safe_num(current_row, "close")
    prev_ma50, cur_ma50 = _safe_num(prev, "ma50"), _safe_num(current_row, "ma50")
    if prev_close is None or cur_close is None or prev_ma50 is None or cur_ma50 is None:
        return None
    if prev_ma50 <= 0 or cur_ma50 <= 0:
        return None

    if prev_close < prev_ma50 and cur_close >= cur_ma50:
        return (
            f"MA50 RECLAIM: closed at {cur_close:.2f}, back above its 50-day average "
            f"({cur_ma50:.2f})",
            "ma50_reclaim",
        )

    prev_high_52w = _safe_num(prev, "high_52w")
    if (
        prev_high_52w is not None
        and prev_high_52w > 0
        and prev_close >= prev_high_52w * 0.94
        and cur_close < cur_ma50
    ):
        return (
            f"PULLBACK FROM HIGHS: closed at {cur_close:.2f}, below its 50-day average "
            f"({cur_ma50:.2f}) after trading near its 52-week high",
            "momentum_extended_breakdown",
        )
    return None


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
    elif prev_score is not None and composite_buy is not None and (
        float(prev_score) - float(composite_buy) >= alert_delta
    ):
        delta = float(prev_score) - float(composite_buy)
        story_change = (
            f"SCORE DROP: {float(prev_score):.0f} -> {float(composite_buy):.0f} (-{delta:.0f})"
        )
        trigger = "score_drop"
    else:
        ma50_transition = _detect_ma50_transition(prev, current_row)
        if ma50_transition:
            story_change, trigger = ma50_transition

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
    trim_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Whether a portfolio holding is a trim candidate and why.
    Hybrid v1: score trigger required + trim_gates_passed >= min_pass when gates enabled.
    """
    from signals.trim_gates import DEFAULT_TRIM_CFG, trim_gates_config

    tg_cfg = trim_cfg if trim_cfg and "enabled" in trim_cfg else trim_gates_config(
        {"trim_gates": trim_cfg} if trim_cfg else None
    )
    if trim_cfg is None:
        try:
            from config_loader import load_config

            tg_cfg = trim_gates_config(load_config())
        except Exception:
            tg_cfg = dict(DEFAULT_TRIM_CFG)
    min_pass = int(tg_cfg.get("min_pass", 2))
    gates_enabled = bool(tg_cfg.get("enabled", True))
    require_score = bool(tg_cfg.get("require_score_trigger", True))

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

    score_trigger = bool(triggers)
    trim_passed = holding.get("trim_gates_passed")
    trim_total = holding.get("trim_gates_total") or 4
    trim_gate_cleared = holding.get("trim_gate_cleared")
    if trim_gate_cleared is None and trim_passed is not None:
        try:
            trim_gate_cleared = int(trim_passed) >= min_pass
        except (TypeError, ValueError):
            trim_gate_cleared = False

    gate_triggers: list[str] = []
    for g in holding.get("trim_gates") or []:
        if isinstance(g, dict) and g.get("pass") and g.get("id"):
            gate_triggers.append(str(g["id"]))

    is_candidate = score_trigger
    if gates_enabled and is_candidate:
        is_candidate = bool(trim_gate_cleared)
    elif gates_enabled and not require_score:
        is_candidate = bool(trim_gate_cleared)

    if not is_candidate:
        out: dict[str, Any] = {"is_trim_candidate": False}
        if score_trigger and gates_enabled and not trim_gate_cleared:
            out["trim_gates_pending"] = True
            out["trim_gates_passed"] = trim_passed
            out["trim_gates_total"] = trim_total
        return out

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

    all_triggers = triggers + [t for t in gate_triggers if t not in triggers]
    detail = " · ".join(label_parts) if label_parts else "Review sizing"
    if trim_passed is not None:
        detail = f"{detail} · trim gates {trim_passed}/{trim_total}"

    return {
        "is_trim_candidate": True,
        "trim_triggers": all_triggers,
        "trim_source": source,
        "trim_primary_driver": primary,
        "trim_horizon": "medium",
        "trim_detail": detail,
        "trim_gates_passed": trim_passed,
        "trim_gates_total": trim_total,
        "trim_gate_cleared": trim_gate_cleared,
        "trim_recommendation": holding.get("trim_recommendation"),
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
    signals_by_ticker: dict[str, dict[str, Any]] | None = None,
    trim_cfg: dict[str, Any] | None = None,
) -> None:
    """Mutates each holding with trim_* fields for UI (portfolio + Today's moves)."""
    from signals.trim_gates import trim_gates_config

    tg = trim_gates_config({"trim_gates": trim_cfg} if trim_cfg else None)
    for h in per_holding:
        if not isinstance(h, dict):
            continue
        tk = str(h.get("ticker") or "").upper()
        sig = (signals_by_ticker or {}).get(tk) if tk else None
        if isinstance(sig, dict):
            for fk in (
                "trim_gates",
                "trim_gates_passed",
                "trim_gates_total",
                "trim_gate_cleared",
                "trim_score_triggered",
                "trim_recommendation",
            ):
                if sig.get(fk) is not None:
                    h[fk] = sig[fk]
        meta = trim_alert_meta(h, sell_max=sell_max, trim_cfg=tg)
        for k in (
            "is_trim_candidate",
            "trim_source",
            "trim_primary_driver",
            "trim_triggers",
            "trim_horizon",
            "trim_detail",
            "trim_gates_passed",
            "trim_gates_total",
            "trim_gate_cleared",
            "trim_recommendation",
            "trim_gates_pending",
        ):
            if k in meta:
                h[k] = meta.get(k)


def build_trim_candidates_from_holdings(
    per_holding: list[dict[str, Any]],
    *,
    sell_max: float = 35.0,
    signals_by_ticker: dict[str, dict[str, Any]] | None = None,
    trim_cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Dashboard trim list with provenance (score trigger + trim gates when enabled)."""
    attach_trim_provenance_to_holdings(
        per_holding,
        sell_max=sell_max,
        signals_by_ticker=signals_by_ticker,
        trim_cfg=trim_cfg,
    )
    out: list[dict[str, Any]] = []
    for h in per_holding:
        if not isinstance(h, dict) or not h.get("ticker"):
            continue
        if h.get("is_trim_candidate"):
            out.append(dict(h))
    return sorted(out, key=lambda x: (x.get("score") is None, x.get("score") or 0))
