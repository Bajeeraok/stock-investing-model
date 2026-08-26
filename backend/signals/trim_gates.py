"""
Trim / exit gates — parallel stack to buy gates (extension + deterioration, not inverted entry).

Hybrid v1: four named gates, default min_pass=2 (not 4/4). Score trigger required for trim candidates.
"""
from __future__ import annotations

import json
from typing import Any

TRIM_GATE_IDS = ("extension", "tape", "ml_momentum", "plan")

DEFAULT_TRIM_CFG: dict[str, Any] = {
    "enabled": True,
    "min_pass": 2,
    "require_score_trigger": True,
    "extension_rsi_min": 65,
    "extension_above_ma20_pct": 3.0,
    "regime_bull_max": 45,
    "pattern_weak_max": 40,
    "ml_bear_max_pct": 35,
    "macd_hist_bear_max": 0.0,
}


def trim_gates_config(config: dict | None) -> dict[str, Any]:
    cfg = dict(DEFAULT_TRIM_CFG)
    raw = (config or {}).get("trim_gates") or {}
    if isinstance(raw, dict):
        cfg.update({k: raw[k] for k in raw if k in cfg or k == "enabled"})
    return cfg


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _ml_pct(short_ml_prob: float | None) -> float | None:
    if short_ml_prob is None:
        return None
    v = float(short_ml_prob)
    return v * 100.0 if v <= 1 else v


def score_trim_triggered(
    row: dict[str, Any],
    *,
    sell_max: float = 30.0,
) -> bool:
    score = _f(row.get("composite_buy") if row.get("composite_buy") is not None else row.get("score"))
    if score is not None and score <= sell_max:
        return True
    action = (row.get("plan_action") or row.get("action") or "").strip().upper()
    if action in ("REDUCE", "AVOID", "SELL"):
        return True
    for key in ("short_suggestion", "medium_suggestion", "long_suggestion", "suggestion", "signal"):
        s = (row.get(key) or "").upper()
        if "TRIM" in s or s in ("REDUCE", "AVOID", "SELL"):
            return True
    return False


def build_trim_gates(
    *,
    current_price: float | None,
    assessment_pct: float | None,
    regime_bull_pct: float | None,
    pattern_score: float | None,
    short_ml_prob: float | None,
    rsi: float | None,
    macd_hist: float | None = None,
    regime: str | None = None,
    plan_action: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Four trim gates: extension, tape deterioration, ML/momentum bear, plan alignment."""
    c = cfg or DEFAULT_TRIM_CFG
    rsi_val = _f(rsi) or 50.0
    assess = _f(assessment_pct) or 0.0
    rb = regime_bull_pct
    pat = _f(pattern_score)
    ml = _ml_pct(short_ml_prob)
    macd = _f(macd_hist)
    reg = (regime or "").upper()
    plan = (plan_action or "").upper()

    ext_rsi = float(c.get("extension_rsi_min", 65))
    rich = assess < 0
    extension_ok = rsi_val >= ext_rsi or rich

    regime_weak = rb is not None and rb < float(c.get("regime_bull_max", 45))
    pattern_weak = pat is not None and pat < float(c.get("pattern_weak_max", 40))
    tape_regime_down = reg == "DOWN"
    tape_ok = regime_weak or pattern_weak or tape_regime_down

    ml_bear = ml is not None and ml <= float(c.get("ml_bear_max_pct", 35))
    macd_bear = macd is not None and macd <= float(c.get("macd_hist_bear_max", 0))
    momentum_hot = rsi_val >= 55
    ml_momentum_ok = ml_bear or macd_bear or momentum_hot

    plan_ok = plan in ("REDUCE", "AVOID", "SELL") or "TRIM" in plan

    gates: list[dict[str, Any]] = [
        {
            "id": "extension",
            "label": "EXTENSION",
            "detail": (
                f"Overextended · RSI {rsi_val:.0f} (≥{ext_rsi:.0f})"
                if rsi_val >= ext_rsi
                else f"Rich vs LT band ({assess:.1f}%)" if rich
                else f"Not extended · RSI {rsi_val:.0f}"
            ),
            "pass": extension_ok,
            "gate_cleared": extension_ok,
            "visual_status": "hot" if extension_ok else "cleared",
            "icon": "📈" if extension_ok else "➖",
        },
        {
            "id": "tape",
            "label": "TAPE WEAK",
            "detail": (
                f"HMM bull {round(rb)}% (<{c.get('regime_bull_max', 45)})"
                if regime_weak and rb is not None
                else "Regime DOWN"
                if tape_regime_down
                else f"Pattern weak ({pat:.0f})"
                if pattern_weak and pat is not None
                else "Structure still firm"
            ),
            "pass": tape_ok,
            "gate_cleared": tape_ok,
            "visual_status": "stormy" if tape_ok else "bull",
            "icon": "🌧️" if tape_ok else "☀️",
        },
        {
            "id": "ml_momentum",
            "label": "ML / MOMENTUM",
            "detail": (
                f"ML bearish ({ml:.0f}%)" if ml_bear and ml is not None
                else f"MACD fading ({macd:.2f})" if macd_bear and macd is not None
                else f"Momentum hot · RSI {rsi_val:.0f}" if momentum_hot
                else "No bearish confirmation"
            ),
            "pass": ml_momentum_ok,
            "gate_cleared": ml_momentum_ok,
            "visual_status": "blocked" if ml_momentum_ok else "cleared",
            "icon": "🤖" if ml_momentum_ok else "➖",
        },
        {
            "id": "plan",
            "label": "PLAN ALIGN",
            "detail": (
                f"7-layer {plan} aligns with trim"
                if plan_ok and plan
                else "Plan still HOLD/BUY — score-only trim trigger"
            ),
            "pass": plan_ok,
            "gate_cleared": plan_ok,
            "visual_status": "cleared" if plan_ok else "blocked",
            "icon": "🎯" if plan_ok else "➖",
        },
    ]
    return gates


def evaluate_trim_recommendation(
    row: dict[str, Any],
    gates: list[dict[str, Any]],
    *,
    sell_max: float = 30.0,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize trim gate pass count and recommendation tier."""
    c = cfg or DEFAULT_TRIM_CFG
    min_pass = int(c.get("min_pass", 2))
    enabled = bool(c.get("enabled", True))
    require_score = bool(c.get("require_score_trigger", True))

    passed = sum(1 for g in gates if g.get("pass"))
    total = len(gates) or 4
    score_trig = score_trim_triggered(row, sell_max=sell_max)
    trim_gate_cleared = passed >= min_pass

    if not enabled:
        return {
            "trim_gates_enabled": False,
            "trim_gates_passed": passed,
            "trim_gates_total": total,
            "trim_gate_cleared": True,
            "trim_score_triggered": score_trig,
            "trim_recommendation": "consider_trim" if score_trig else "watch",
            "trim_gates": gates,
        }

    if score_trig and trim_gate_cleared:
        rec = "urgent_trim" if passed >= total - 1 else "consider_trim"
    elif score_trig:
        rec = "watch"
    else:
        rec = "watch"

    return {
        "trim_gates_enabled": True,
        "trim_gates_passed": passed,
        "trim_gates_total": total,
        "trim_gate_cleared": trim_gate_cleared,
        "trim_score_triggered": score_trig,
        "trim_recommendation": rec,
        "trim_gates": gates,
        "trim_min_pass": min_pass,
        "trim_eligible": score_trig or not require_score,
    }


def attach_trim_gates_to_row(
    row: dict[str, Any],
    *,
    regime_bull_pct: float | None = None,
    sell_max: float = 30.0,
    config: dict | None = None,
) -> dict[str, Any]:
    """Build trim gates from row fields; mutates row retail_status + top-level trim fields."""
    from signals.retail_action_payload import _assessment_from_lt_band, _global_regime_bull_pct

    cfg = trim_gates_config(config)
    if config is None:
        try:
            from config_loader import load_config

            full = load_config()
            cfg = trim_gates_config(full)
            sell_max = float((full.get("score") or {}).get("sell_max", sell_max))
        except Exception:
            pass
    cp = _f(row.get("close"))
    rb = regime_bull_pct
    if rb is None:
        rb = _f(row.get("regime_bull_pct"))
    if rb is None:
        rb = _global_regime_bull_pct(row.get("_global_market_regime"))

    ml_raw = row.get("ml_short_prob")
    assessment = _assessment_from_lt_band(cp, row.get("lt_band"), row.get("lt_fair_value_mid"))

    gates = build_trim_gates(
        current_price=cp,
        assessment_pct=assessment,
        regime_bull_pct=rb,
        pattern_score=_f(row.get("confluence_score") or row.get("composite_buy")),
        short_ml_prob=_f(ml_raw),
        rsi=_f(row.get("rsi")),
        macd_hist=_f(row.get("macd_hist")),
        regime=row.get("regime"),
        plan_action=row.get("plan_action") or row.get("signal"),
        cfg=cfg,
    )
    summary = evaluate_trim_recommendation(row, gates, sell_max=sell_max, cfg=cfg)

    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    if not rs:
        rs = {}
    rs.update(summary)
    row["retail_status"] = rs

    for k, v in summary.items():
        if k != "trim_gates":
            row[k] = v
    row["trim_gates"] = gates
    return row


def trim_gate_snapshot_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Compact trim gate fields for EOD / forward tracking."""
    if row.get("trim_gates_frozen"):
        try:
            passed = int(row.get("trim_gates_passed")) if row.get("trim_gates_passed") is not None else 0
        except (TypeError, ValueError):
            passed = 0
        total = int(row.get("trim_gates_total") or 4)
        cleared = row.get("trim_gate_cleared")
        if cleared is None:
            cleared = passed >= int(row.get("trim_min_pass") or 2)
        return {
            "trim_gate_cleared": bool(cleared),
            "trim_gates_passed": passed,
            "trim_gates_total": total,
            "trim_score_triggered": bool(row.get("trim_score_triggered")),
            "trim_recommendation": row.get("trim_recommendation"),
        }

    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    gates = row.get("trim_gates") or rs.get("trim_gates") or []
    total = len(gates) if gates else int(rs.get("trim_gates_total") or row.get("trim_gates_total") or 4)
    passed = rs.get("trim_gates_passed")
    if passed is None:
        passed = row.get("trim_gates_passed")
    if passed is None and gates:
        passed = sum(1 for g in gates if isinstance(g, dict) and g.get("pass"))
    try:
        passed = int(passed) if passed is not None else 0
    except (TypeError, ValueError):
        passed = 0

    cleared = rs.get("trim_gate_cleared")
    if cleared is None:
        cleared = row.get("trim_gate_cleared")
    if cleared is None:
        min_pass = int(rs.get("trim_min_pass") or row.get("trim_min_pass") or 2)
        cleared = passed >= min_pass

    return {
        "trim_gate_cleared": bool(cleared),
        "trim_gates_passed": passed,
        "trim_gates_total": total,
        "trim_score_triggered": bool(rs.get("trim_score_triggered") or row.get("trim_score_triggered")),
        "trim_recommendation": rs.get("trim_recommendation") or row.get("trim_recommendation"),
    }


def primary_trim_gates_detail(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Frozen trim gate detail for EOD JSON."""
    gates = row.get("trim_gates") or []
    if not gates:
        rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
        gates = rs.get("trim_gates") or []
    out = []
    for g in gates:
        if not isinstance(g, dict) or g.get("id") not in TRIM_GATE_IDS:
            continue
        out.append(
            {
                "id": g.get("id"),
                "label": g.get("label"),
                "pass": bool(g.get("pass")),
                "detail": (g.get("detail") or "")[:200],
            }
        )
    return out
