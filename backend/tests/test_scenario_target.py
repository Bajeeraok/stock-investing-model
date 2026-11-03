"""Unified scenario target helper."""

from __future__ import annotations

from signals.scenario_target import compute_initial_scenario_target, sync_medium_horizon_target


def test_compute_initial_scenario_target_priority():
    assert compute_initial_scenario_target({"target": 100.0}, {"target": 200.0}, 50.0) == 100.0
    assert compute_initial_scenario_target({}, {"target": 200.0}, 50.0) == 200.0
    assert compute_initial_scenario_target({}, {}, 50.0) == 50.0


def test_sync_medium_horizon_target_lowers_only():
    h = {"medium": {"target": 120.0}}
    sync_medium_horizon_target(h, 99.5)
    assert h["medium"]["target"] == 99.5
    h = {"medium": {"target": 1.0}}
    sync_medium_horizon_target(h, 99.5)
    assert h["medium"]["target"] == 1.0


def test_sync_medium_horizon_target_refreshes_rr_from_painted_levels():
    """Scenario target below the MT target lowers it; R:R must follow the new print."""
    h = {
        "medium": {
            "target": 660.00,
            "stop_loss": 479.78,
            "risk_reward": 1.7,
            "target_pct": 11.4,
        }
    }
    sync_medium_horizon_target(h, 625.88, spot=514.39)
    med = h["medium"]
    assert med["target"] == 625.88
    risk = 514.39 - 479.78
    reward = 625.88 - 514.39
    assert med["risk_reward"] == round(reward / risk, 2)
    assert med["risk_reward"] == 3.22
    assert med["target_pct"] == round(reward / 514.39 * 100, 1)


def test_swing_cap_is_tighter_than_owner_cap():
    from signals.horizon_entry_calculator import _MT_REALISTIC_SIGMA_MULT, _plausibility_cap
    swing = _plausibility_cap(280.0, 7.0, None, 63, sigma_mult=_MT_REALISTIC_SIGMA_MULT)
    assert swing is not None and swing < 280.0 * 1.25
