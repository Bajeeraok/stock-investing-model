"""
Scenario target helpers.

`compute_initial_scenario_target` seeds the roadmap before RC-1 alignment.
After `apply_roadmap_consistency` in ticker detail, the roadmap’s `scenario_target`
is canonical; `sync_medium_horizon_target` sets `horizons["medium"]["target"]` to that
value so horizon cards and trade roadmap stay aligned (one source of truth).
"""

from __future__ import annotations

from typing import Any

from signals.horizon_entry_calculator import refresh_horizon_rr_from_levels


def _sf(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
        return x if x == x and x > 0 else None  # not NaN
    except (TypeError, ValueError):
        return None


def compute_initial_scenario_target(
    medium: dict[str, Any] | None,
    long_h: dict[str, Any] | None,
    fair_value: float,
) -> float:
    """Same rule as legacy ticker_detail: MT target, else LT target, else fair value."""
    mt = _sf((medium or {}).get("target"))
    lt = _sf((long_h or {}).get("target"))
    fv = float(fair_value) if fair_value and fair_value > 0 else 0.0
    return float(mt or lt or fv or 0.0)


def sync_medium_horizon_target(
    horizons: dict[str, Any],
    scenario: float,
    *,
    spot: float | None = None,
) -> None:
    """
    Set `horizons["medium"]["target"]` to the canonical scenario target (post roadmap alignment).
    Mutates horizons in place and refreshes R:R from the painted stop/target/spot.
    """
    if scenario <= 0:
        return
    med = horizons.get("medium")
    if not isinstance(med, dict):
        return
    med["target"] = round(scenario, 2)
    refresh_horizon_rr_from_levels(med, spot)
