"""Horizon zone reconciliation — ST enter-now vs LT tier below spot."""

from api.ticker_detail import _build_horizon_zone_reconciliation


def test_split_when_st_in_zone_above_lt_tier():
    long_h = {
        "entry_tiers": {
            "active_tier_id": "T1",
            "tiers": [
                {"id": "T1", "low": 375.0, "high": 398.0, "label": "Phase 1"},
                {"id": "T2", "low": 340.0, "high": 360.0, "label": "Phase 2"},
            ],
        },
        "entry_zone": {"low": 375.0, "high": 398.0},
    }
    hr = _build_horizon_zone_reconciliation(
        action_today="enter_now",
        in_short=True,
        in_medium=False,
        current_price=415.0,
        short_zone="$412.00-$421.00",
        long_h=long_h,
    )
    assert hr is not None
    assert hr["active"] is True
    assert "412" in hr["st_zone"]
    assert "375" in hr["lt_zone"]
    assert "398" in hr["lt_zone"]
    assert hr["lt_tier_id"] == "T1"
    assert "Short-term add OK" in hr["execution_label"]
    assert "swing" in hr["summary"].lower() or "core" in hr["summary"].lower()


def test_no_split_when_inside_lt_tier():
    long_h = {
        "entry_tiers": {
            "active_tier_id": "T1",
            "tiers": [{"id": "T1", "low": 375.0, "high": 398.0}],
        },
    }
    hr = _build_horizon_zone_reconciliation(
        action_today="enter_now",
        in_short=True,
        in_medium=False,
        current_price=390.0,
        short_zone="$380.00-$395.00",
        long_h=long_h,
    )
    assert hr is None


def test_no_split_when_not_enter_now():
    long_h = {"entry_tiers": {"tiers": [{"id": "T1", "low": 375.0, "high": 398.0}]}}
    hr = _build_horizon_zone_reconciliation(
        action_today="wait_for_pullback",
        in_short=False,
        in_medium=False,
        current_price=415.0,
        short_zone="$412.00-$421.00",
        long_h=long_h,
    )
    assert hr is None
