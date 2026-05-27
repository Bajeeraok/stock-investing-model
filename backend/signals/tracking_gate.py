"""
Gate enrichment + filtering for paper trading and forward tracking.

Mirrors dashboard signal rows: enrich_dashboard_signal_row() before logging so
gate_cleared / go_no_go are frozen at signal time (stored in EOD when saved).
"""

from __future__ import annotations

from typing import Any

PRIMARY_GATE_IDS = frozenset({"valuation", "regime", "momentum", "ml"})


def _as_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


def gate_snapshot_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Compact gate fields for EOD / CSV persistence."""
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    gates = rs.get("gates") or []
    primary = [g for g in gates if isinstance(g, dict) and g.get("id") in PRIMARY_GATE_IDS]
    total = len(primary) if primary else 4
    passed = sum(1 for g in primary if g.get("pass"))
    if rs.get("gates_locked_count") is not None and primary:
        passed = max(0, total - int(rs.get("gates_locked_count") or 0))
    go = rs.get("go_no_go")
    if not go:
        if row.get("gate_cleared") is True:
            go = "go"
        elif row.get("gate_cleared") is False:
            go = "no_go"
    cleared = _as_bool(row.get("gate_cleared"))
    if cleared is None and go:
        cleared = go == "go"
    return {
        "gate_cleared": cleared,
        "go_no_go": str(go).lower() if go else None,
        "gates_passed": passed,
        "gates_total": total,
    }


def enrich_tracking_row(
    row: dict[str, Any],
    *,
    regime_bull_pct: float | None = None,
) -> dict[str, Any]:
    """Ensure gate fields exist on a run_results row (recompute from EOD fields if missing)."""
    if row.get("gate_cleared") is not None:
        snap = gate_snapshot_from_row(row)
        row.setdefault("go_no_go", snap.get("go_no_go"))
        row.setdefault("gates_passed", snap.get("gates_passed"))
        row.setdefault("gates_total", snap.get("gates_total"))
        return row
    try:
        from signals.retail_action_payload import enrich_dashboard_signal_row

        enrich_dashboard_signal_row(row, regime_bull_pct=regime_bull_pct)
    except Exception:
        pass
    snap = gate_snapshot_from_row(row)
    for k, v in snap.items():
        if v is not None:
            row[k] = v
    return row


def passes_tracking_gate(row: dict[str, Any], config: dict | None, section: str) -> bool:
    """
    When require_gates_cleared is true, only rows with gate_cleared=True are tracked.
    Legacy EOD rows without gate data are included so history is not dropped.
    """
    cfg = (config or {}).get(section) or {}
    if not cfg.get("require_gates_cleared", False):
        return True
    cleared = _as_bool(row.get("gate_cleared"))
    if cleared is True:
        return True
    if cleared is False:
        return False
    go = str(row.get("go_no_go") or "").lower()
    if go == "go":
        return True
    if go == "no_go":
        return False
    return True
