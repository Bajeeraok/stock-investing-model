"""
Actionable score — confidence-adjusted headline for retail cards.

Setup quality (raw composite / pattern) answers: "how attractive if systems are healthy?"
Actionable score answers: "how much should I trust acting on it *today*?"

    actionable ≈ setup × (gates_passed / gates_total) × min(1, fused/target) × ml_cal × freshness

Stale feeds suppress the headline (None + stale flag) rather than silently lying.
"""
from __future__ import annotations

from typing import Any


CONFIDENCE_GATE_TARGET_PCT = 55.0
# After close / weekends: allow longer; RTH quotes should be fresher.
STALE_PRICE_HOURS_DEFAULT = 36.0


def _sf(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None:
            return default
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def compute_actionable_score(
    setup_quality: float | None,
    *,
    gates_passed: int | None = None,
    gates_total: int = 4,
    fused_confidence_pct: float | None = None,
    confidence_target_pct: float = CONFIDENCE_GATE_TARGET_PCT,
    price_age_hours: float | None = None,
    stale_threshold_hours: float = STALE_PRICE_HOURS_DEFAULT,
    ml_calibration_factor: float | None = None,
) -> dict[str, Any]:
    """
    Returns a dict suitable for investor_summary["actionable_score"].

    Keys:
      setup_quality, actionable, stale, factors, note
    """
    setup = _sf(setup_quality)
    if setup is None:
        return {
            "setup_quality": None,
            "actionable": None,
            "stale": False,
            "suppressed": False,
            "factors": {},
            "note": "Setup quality unavailable",
        }

    setup = _clamp(float(setup))
    total = max(1, int(gates_total or 4))
    passed = int(gates_passed) if gates_passed is not None else total
    passed = max(0, min(passed, total))
    gate_mult = passed / total

    conf = _sf(fused_confidence_pct)
    target = max(1.0, float(confidence_target_pct or CONFIDENCE_GATE_TARGET_PCT))
    if conf is None:
        conf_mult = 1.0
        conf_note = "confidence n/a — no discount"
    else:
        conf_mult = min(1.0, max(0.05, float(conf) / target))
        conf_note = f"fused {conf:.0f}% / target {target:.0f}%"

    cal = _sf(ml_calibration_factor, 1.0)
    assert cal is not None
    cal = min(1.0, max(0.5, float(cal)))  # never inflate; floor so one bad fit can't zero the card

    stale = False
    suppressed = False
    freshness_mult = 1.0
    age = _sf(price_age_hours)
    if age is not None and age > stale_threshold_hours:
        stale = True
        suppressed = True
        freshness_mult = 0.0

    raw = setup * gate_mult * conf_mult * cal * freshness_mult
    actionable = None if suppressed else round(_clamp(raw), 1)

    note_parts = [
        f"setup {setup:.0f}",
        f"gates {passed}/{total} (×{gate_mult:.2f})",
        conf_note + f" (×{conf_mult:.2f})",
    ]
    if cal < 0.999:
        note_parts.append(f"ML cal ×{cal:.2f}")
    if stale:
        note_parts.append(f"STALE price (~{age:.0f}h) — score suppressed")

    return {
        "setup_quality": round(setup, 1),
        "actionable": actionable,
        "stale": stale,
        "suppressed": suppressed,
        "factors": {
            "gates_passed": passed,
            "gates_total": total,
            "gate_multiplier": round(gate_mult, 3),
            "fused_confidence_pct": round(conf, 1) if conf is not None else None,
            "confidence_target_pct": target,
            "confidence_multiplier": round(conf_mult, 3),
            "ml_calibration_factor": round(cal, 3),
            "price_age_hours": round(age, 2) if age is not None else None,
            "freshness_multiplier": freshness_mult,
        },
        "note": " · ".join(note_parts),
    }


def attach_actionable_score(
    investor_out: dict[str, Any],
    *,
    price_age_hours: float | None = None,
    ml_calibration_factor: float | None = None,
) -> dict[str, Any]:
    """Mutate investor_out with actionable_score from retail_action + confidence."""
    ra = investor_out.get("retail_action") if isinstance(investor_out.get("retail_action"), dict) else {}
    gates = ra.get("gates") if isinstance(ra.get("gates"), list) else []
    # Primary buy gates only (valuation / regime / momentum / ml) — confidence is a multiplier
    primary_ids = {"valuation", "regime", "momentum", "ml"}
    primary = [g for g in gates if isinstance(g, dict) and str(g.get("id") or "") in primary_ids]
    if primary:
        passed = sum(1 for g in primary if g.get("pass") or g.get("passed") or g.get("gateCleared"))
        total = len(primary)
    else:
        passed = ra.get("gates_passed")
        total = ra.get("gates_total") or 4
        if passed is None and ra.get("gate_cleared") is True:
            passed = total

    conf = investor_out.get("model_confidence_pct")
    if conf is None:
        tldr = ((investor_out.get("trade_roadmap") or {}).get("tldr") or {})
        conf = tldr.get("model_confidence_pct")

    block = compute_actionable_score(
        investor_out.get("pattern_score"),
        gates_passed=int(passed) if passed is not None else None,
        gates_total=int(total) if total is not None else 4,
        fused_confidence_pct=_sf(conf),
        price_age_hours=price_age_hours,
        ml_calibration_factor=ml_calibration_factor,
    )
    investor_out["actionable_score"] = block
    return investor_out
