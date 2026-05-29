"""
Readiness score for alerts/UI — does NOT change primary GO/NO-GO gates.

Tiers:
  go_ready      — 4/4 gates (same as gate_cleared)
  almost_ready  — 3/4 gates + short-term verdict supports add
  warming       — 3/4 gates but ST not BUY yet
  watch         — fewer gates or no ST support
"""

from __future__ import annotations

from typing import Any, Literal

ReadinessTier = Literal["go_ready", "almost_ready", "warming", "watch"]

ST_BUY_VERDICTS = frozenset({"BUY", "STRONG BUY"})


def st_verdict_supports_add(row: dict[str, Any]) -> bool:
    """Proxy for horizon short verdict BUY when full horizons payload is unavailable."""
    verdict = str(row.get("st_verdict") or row.get("short_verdict") or "").upper().strip()
    if verdict in ST_BUY_VERDICTS:
        return True
    ss = str(row.get("short_suggestion") or "").upper()
    if "ADD" in ss:
        return True
    try:
        st = float(row.get("short_term")) if row.get("short_term") is not None else None
    except (TypeError, ValueError):
        st = None
    if st is not None and st >= 65:
        return True
    pa = str(row.get("plan_action") or row.get("signal") or "").upper()
    return pa in ST_BUY_VERDICTS


def compute_readiness(row: dict[str, Any]) -> dict[str, Any]:
    """
    Return readiness tier + score (0–100) from frozen gate fields on a signal row.
    Informational only — paper trading still uses gate_cleared for accumulate track.
    """
    try:
        gates_passed = int(row.get("gates_passed") if row.get("gates_passed") is not None else 0)
    except (TypeError, ValueError):
        gates_passed = 0
    try:
        gates_total = int(row.get("gates_total") if row.get("gates_total") is not None else 4)
    except (TypeError, ValueError):
        gates_total = 4
    gates_total = max(gates_total, 4)

    cleared = row.get("gate_cleared") is True
    if not cleared:
        go = str(row.get("go_no_go") or "").lower()
        cleared = go == "go"

    st_buy = st_verdict_supports_add(row)

    if cleared:
        tier: ReadinessTier = "go_ready"
        score = 100
    elif gates_passed >= gates_total - 1 and st_buy:
        tier = "almost_ready"
        score = min(95, 70 + gates_passed * 6)
    elif gates_passed >= gates_total - 1:
        tier = "warming"
        score = min(80, 55 + gates_passed * 6)
    else:
        tier = "watch"
        score = max(0, min(55, gates_passed * 12))

    return {
        "readiness_tier": tier,
        "readiness_score": score,
        "gates_passed": gates_passed,
        "gates_total": gates_total,
        "gate_cleared": cleared,
        "st_verdict_buy": st_buy,
        "almost_ready": tier == "almost_ready",
        "go_ready": tier == "go_ready",
    }
