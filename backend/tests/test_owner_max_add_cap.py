from signals.horizon_entry_calculator import LT_PARTIAL_MOS_PCT, _enrich_horizon_entry_zone_extras


def _payload(long_lo, long_hi, fv, mos_pct):
    return {
        "short": {"entry_zone": {"low": 320.0, "high": 330.0}},
        "medium": {"entry_zone": {"low": 300.0, "high": 330.0}},
        "long": {
            "fair_value": fv,
            "entry_zone": {"low": long_lo, "high": long_hi},
            "entry_tiers": {"current_assessment": {"margin_of_safety_pct": mos_pct}},
        },
    }


def _run(p):
    _enrich_horizon_entry_zone_extras(p, current_price=330.0, vwap=328.0, support_level=322.0, ma50=334.0)
    return p["long"]["entry_zone"]


def test_band_above_max_add_moves_under_it():
    cap = round(260.0 * (1 - LT_PARTIAL_MOS_PCT / 100), 2)
    ez = _run(_payload(276.28, 311.9, 260.0, -14.0))
    assert ez["high"] == ez["max_add"] == cap
    assert ez["low"] < ez["high"]
    assert ez["chart_band"] == {"low": 276.28, "high": 311.9}
    assert ez["trigger_ceiling"] == cap
    assert all(lv["price"] <= cap + 0.02 and lv["price"] >= ez["low"] - 0.02 for lv in ez["levels"])


def test_band_straddling_max_add_keeps_low():
    cap = round(320.0 * (1 - LT_PARTIAL_MOS_PCT / 100), 2)
    lo = round(cap - 20, 2)
    ez = _run(_payload(lo, cap + 30, 320.0, 0.0))
    assert ez["low"] == lo and ez["high"] == cap


def test_band_below_max_add_unchanged():
    ez = _run(_payload(200.0, 220.0, 400.0, 40.0))
    assert ez["low"] == 200.0 and ez["high"] == 220.0 and "max_add" not in ez


def test_tiers_above_max_add_flagged_or_cut():
    p = _payload(276.28, 311.9, 260.0, -14.0)
    p["long"]["entry_tiers"].update({
        "active_tier_id": "T2",
        "spot_position": {"state": "in_tier", "active_tier_id": "T2", "next_add_tier_id": "T2"},
        "tiers": [
            {"id": "T1", "low": 280.0, "high": 320.0},
            {"id": "T2", "low": 200.0, "high": 300.0},
            {"id": "T3", "low": 150.0, "high": 190.0},
        ],
    })
    p["long"]["warnings"] = ["Inside Tier 2 band but above full-size ceiling $200.00 — partial position only"]
    ez = _run(p)
    cap = ez["max_add"]
    t1, t2, t3 = p["long"]["entry_tiers"]["tiers"]
    assert t1["above_max_add"] is True and "wait" in t1["status_label"]
    assert t2["high"] == cap and t2["low"] == 200.0 and "above_max_add" not in t2
    assert t3 == {"id": "T3", "low": 150.0, "high": 190.0}


def test_active_tier_above_max_add_clears_active_and_partial_warning():
    p = _payload(276.28, 311.9, 260.0, -14.0)
    p["long"]["warnings"] = ["Inside Tier 2 band but above full-size ceiling $200.00 — partial position only"]
    p["long"]["entry_tiers"].update({
        "active_tier_id": "T2",
        "spot_position": {"state": "in_tier", "active_tier_id": "T2", "next_add_tier_id": "T2"},
        "tiers": [{"id": "T2", "low": 270.0, "high": 300.0}],
    })
    _run(p)
    et = p["long"]["entry_tiers"]
    assert et["active_tier_id"] is None
    assert et["spot_position"] == {"state": "above_max_add", "active_tier_id": None, "next_add_tier_id": None}
    assert not any(w.startswith("Inside Tier 2 band") for w in p["long"]["warnings"])


def test_tier3_straddling_max_add_is_cut():
    p = _payload(276.28, 311.9, 260.0, -14.0)
    p["long"]["entry_tiers"]["tiers"] = [{"id": "T3", "low": 150.0, "high": 300.0}]
    ez = _run(p)
    assert p["long"]["entry_tiers"]["tiers"][0]["high"] == ez["max_add"]


def test_stop_moves_below_capped_band():
    """GS-like: band capped down to $782–823 but the tactical stop ($806) was set under the old T2."""
    p = {
        "short": {"entry_zone": {"low": 860.0, "high": 870.0}},
        "medium": {"entry_zone": {"low": 856.0, "high": 869.0}},
        "long": {
            "fair_value": 1097.5,
            "stop_loss": 805.92,
            "entry_zone": {"low": 848.95, "high": 945.05},
            "entry_tiers": {"current_assessment": {"margin_of_safety_pct": 20.8},
                            "structural_invalidation": {"price": 716.3}},
        },
    }
    _enrich_horizon_entry_zone_extras(p, current_price=869.0, vwap=868.0, support_level=850.0, ma50=900.0, atr=25.0)
    lh = p["long"]
    assert lh["entry_zone"]["high"] == 823.12
    assert lh["stop_loss"] < lh["entry_zone"]["low"]
    assert lh["stop_loss_pct"] < 0 and "Owner band" in lh["stop_loss_framing"]
