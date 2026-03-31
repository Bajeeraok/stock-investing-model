"""Unified scenario target helper."""

from __future__ import annotations

from signals.scenario_target import compute_initial_scenario_target, sync_medium_horizon_target


def test_compute_initial_scenario_target_priority():
    assert compute_initial_scenario_target({"target": 100.0}, {"target": 200.0}, 50.0) == 100.0
    assert compute_initial_scenario_target({}, {"target": 200.0}, 50.0) == 200.0
    assert compute_initial_scenario_target({}, {}, 50.0) == 50.0


def test_sync_medium_horizon_target_mutates():
    h = {"medium": {"target": 1.0}}
    sync_medium_horizon_target(h, 99.5)
    assert h["medium"]["target"] == 99.5
