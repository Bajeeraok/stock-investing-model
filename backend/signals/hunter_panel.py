"""
Hunter panel (Phase B): candidates from dashboard signal rows after gates + readiness + velocity.

Included in full dashboard cache — refreshed with signal universe (~watchlist + portfolio + demo),
not the 100-ticker audit cohort (EOD-only).
"""
from __future__ import annotations

from typing import Any, Literal

HUNT_READINESS_TIERS = frozenset({"go_ready", "almost_ready", "warming"})

HunterReason = Literal["velocity", "go_ready", "almost_ready", "warming"]
PositionStatus = Literal["owned", "watching", "universe"]

_REASON_SORT = {"velocity": 0, "go_ready": 1, "almost_ready": 2, "warming": 3}


def _position_status(
    ticker: str,
    *,
    portfolio: set[str],
    watchlist: set[str],
) -> PositionStatus:
    u = ticker.upper()
    if u in portfolio:
        return "owned"
    if u in watchlist:
        return "watching"
    return "universe"


def _hunter_reason(row: dict[str, Any]) -> HunterReason | None:
    track = str(row.get("track") or "").lower()
    if track == "velocity" or row.get("velocity_triggered"):
        return "velocity"
    tier = str(row.get("readiness_tier") or "").lower()
    if tier == "go_ready":
        return "go_ready"
    if tier == "almost_ready":
        return "almost_ready"
    if tier == "warming":
        return "warming"
    return None


def is_hunter_candidate(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict) or row.get("error"):
        return False
    return _hunter_reason(row) is not None


def _row_to_hunter_item(
    row: dict[str, Any],
    *,
    portfolio: set[str],
    watchlist: set[str],
) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").upper()
    reason = _hunter_reason(row)
    assert reason is not None
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    return {
        "ticker": ticker,
        "position_status": _position_status(ticker, portfolio=portfolio, watchlist=watchlist),
        "hunter_reason": reason,
        "readiness_tier": row.get("readiness_tier"),
        "readiness_score": row.get("readiness_score"),
        "track": row.get("track") or ("velocity" if row.get("velocity_triggered") else "accumulate"),
        "velocity_triggered": bool(row.get("velocity_triggered")),
        "velocity_score": row.get("velocity_score"),
        "gates_passed": row.get("gates_passed"),
        "gates_total": row.get("gates_total") or 4,
        "gate_cleared": row.get("gate_cleared"),
        "go_no_go": rs.get("go_no_go") or row.get("go_no_go"),
        "composite_buy": row.get("composite_buy"),
        "confluence_score": row.get("confluence_score"),
        "close": row.get("close"),
        "signal": row.get("signal"),
        "plan_action": row.get("plan_action"),
        "regime": row.get("regime"),
        "rsi": row.get("rsi"),
        "tactical_t1": row.get("tactical_t1"),
        "tactical_stop": row.get("tactical_stop"),
    }


def build_hunter_panel(
    results: list[dict[str, Any]] | None,
    *,
    portfolio_tickers: list[str] | None = None,
    watchlist_tickers: list[str] | None = None,
    signal_universe: list[str] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """All hunter candidates from the latest signal run (no arbitrary cap)."""
    portfolio = {str(t).upper() for t in (portfolio_tickers or []) if t}
    watchlist = {str(t).upper() for t in (watchlist_tickers or []) if t}
    items: list[dict[str, Any]] = []
    for row in results or []:
        if not is_hunter_candidate(row):
            continue
        items.append(_row_to_hunter_item(row, portfolio=portfolio, watchlist=watchlist))

    items.sort(
        key=lambda x: (
            _REASON_SORT.get(x.get("hunter_reason") or "warming", 9),
            -(float(x.get("readiness_score") or 0)),
            -(float(x.get("velocity_score") or 0)),
            str(x.get("ticker") or ""),
        ),
    )

    velocity_n = sum(1 for x in items if x.get("hunter_reason") == "velocity")
    go_n = sum(1 for x in items if x.get("hunter_reason") == "go_ready")
    almost_n = sum(1 for x in items if x.get("hunter_reason") == "almost_ready")
    warm_n = sum(1 for x in items if x.get("hunter_reason") == "warming")
    not_owned = [x for x in items if x.get("position_status") != "owned"]

    return {
        "as_of": as_of,
        "universe_size": len(signal_universe or []),
        "candidate_count": len(items),
        "counts": {
            "velocity": velocity_n,
            "go_ready": go_n,
            "almost_ready": almost_n,
            "warming": warm_n,
            "not_in_portfolio": len(not_owned),
        },
        "candidates": items,
        "methodology": (
            "Filtered from dashboard signal universe after each cache warm "
            "(readiness go_ready / almost_ready / warming, or tactical velocity track). "
            "Audit cohort (100) updates at EOD only."
        ),
    }


def build_scanner_home_lite(data_root, *, limit: int = 12) -> dict[str, Any]:
    """Top recent scanner alerts from file store (no extra scan)."""
    from pathlib import Path

    from scanner.store import ScannerStore

    root = Path(data_root)
    store = ScannerStore(root)
    dismissed = store.load_dismissed()
    alerts = store.load_alerts(limit=limit * 3)
    rows: list[dict[str, Any]] = []
    for a in alerts:
        aid = str(a.get("id") or "")
        if aid and aid in dismissed:
            continue
        sym = str(a.get("ticker") or a.get("symbol") or "").upper()
        if not sym:
            continue
        rows.append({
            "id": aid or None,
            "ticker": sym,
            "alert_type": a.get("alert_type") or a.get("type"),
            "priority": a.get("priority"),
            "message": a.get("message") or a.get("headline"),
            "created_at": a.get("created_at") or a.get("ts"),
        })
        if len(rows) >= limit:
            break
    stats = store.read_stats()
    return {
        "alerts": rows,
        "alert_count": len(rows),
        "universe_size": stats.get("universe_size"),
        "as_of": stats.get("as_of"),
        "message": None if rows else "No scanner alerts yet — scanner runs on its own schedule.",
    }
