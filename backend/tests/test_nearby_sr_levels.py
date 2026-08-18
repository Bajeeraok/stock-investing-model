"""Next support / resistance picker for ticker-detail horizons."""
from __future__ import annotations

from signals.nearby_sr_levels import attach_nearby_sr, pick_nearby_sr


def test_next_support_is_nearest_below_spot():
    out = pick_nearby_sr(
        spot=100.0,
        horizon_key="short",
        ma20=98.0,
        ma50=94.0,
        swing_low=97.5,
        swing_high=103.0,
        high_52w=120.0,
    )
    assert out is not None
    assert out["next_support"]["price"] == 98.0
    assert out["next_support"]["label"] == "MA20"
    assert out["next_resistance"]["price"] == 103.0
    assert "swing high" in out["next_resistance"]["label"].lower()


def test_omits_when_nothing_nearby_for_scout():
    out = pick_nearby_sr(
        spot=100.0,
        horizon_key="short",
        ma200=70.0,  # 30% below — outside scout 8% window
        high_52w=140.0,  # 40% above
    )
    assert out is None


def test_owner_can_see_farther_ma200_and_52w():
    out = pick_nearby_sr(
        spot=400.0,
        horizon_key="long",
        ma200=385.0,
        t1_high=396.0,
        high_52w=430.0,
        low_52w=320.0,
    )
    assert out is not None
    assert out["next_support"]["price"] == 396.0
    assert out["next_resistance"]["label"] == "52w high"


def test_attach_writes_per_horizon():
    horizons = {
        "short": {"entry_zone": {"low": 97.0, "high": 99.5}},
        "medium": {"entry_zone": {"low": 94.0, "high": 101.0}},
        "long": {
            "entry_zone": {"low": 90.0, "high": 96.0},
            "entry_tiers": {"tiers": [{"id": "T1", "high": 96.0}, {"id": "T2", "high": 88.0}]},
        },
    }
    attach_nearby_sr(
        horizons,
        spot=100.0,
        ma50=94.0,
        ma200=88.0,
        swing_high=104.0,
        high_52w=130.0,
    )
    assert horizons["short"]["nearby_sr"]["next_support"]["price"] == 99.5
    assert horizons["medium"]["nearby_sr"]["next_resistance"]["price"] == 101.0
    assert horizons["long"]["nearby_sr"]["next_support"]["price"] == 96.0
