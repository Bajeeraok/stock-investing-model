"""
Hunter panel: tactical / readiness setups in your book (watchlist + portfolio).

Included in full dashboard cache — refreshed with dashboard signal universe on each Refresh.
Audit cohort band events surface in Alerts, not here.
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
            "Your book (watchlist + portfolio) after each Dashboard Refresh — "
            "tactical velocity or readiness go_ready / almost_ready / warming. "
            "Use Alerts below for band/gate events across the 100-name audit cohort too."
        ),
    }
