from signals.retail_action_payload import attach_display_alerts, display_alert_level

VAL_FAIL = [{"id": "valuation", "pass": False, "detail": "14.4% below fair value — need 15.3%"}]


def test_band_top_when_above_band_and_gates_pass():
    h = {"entry_zone": {"low": 90, "high": 95}}
    assert display_alert_level(h, [{"id": "valuation", "pass": True}], 100, 30)["alert_level"] == 95


def test_band_low_when_inside_band_and_stop_without_band():
    assert display_alert_level({"entry_zone": {"low": 90, "high": 105}}, [], 100, 0)["alert_level"] == 90
    assert display_alert_level({"stop_loss": 88}, [], 100, 0)["alert_level"] == 88


def test_valuation_clear_price_wins_and_is_capped_at_band_top():
    # FV = 115; clears at 115 * (1 - .153) = 97.41 < price, above band top 90 -> capped at 90
    r = display_alert_level({"entry_zone": {"low": 85, "high": 90}}, VAL_FAIL, 100, 15)
    assert r == {"alert_level": 90, "alert_at_valuation": True}
    # inside band: alert at the clear price
    r = display_alert_level({"entry_zone": {"low": 80, "high": 105}}, VAL_FAIL, 100, 10)
    assert r["alert_level"] == round(110 * (1 - 0.153), 2) and r["alert_at_valuation"]


def test_no_price_and_attach_per_mode():
    assert display_alert_level({}, [], None, 0)["alert_level"] is None
    d = {"current_price": 100, "investor_summary": {
        "horizons": {"medium": {"entry_zone": {"low": 90, "high": 95}}},
        "retail_action": {"assessment_pct": 30, "gates_by_mode": {"swing": [{"id": "ml", "pass": True}]}}}}
    attach_display_alerts(d)
    row = d["investor_summary"]["retail_action"]["display_by_mode"]["swing"]
    assert row["alert_level"] == 95 and row["gates_passed"] == 1


def test_below_band_alerts_at_stop_not_band_edge_above_price():
    h = {"entry_zone": {"low": 904.43, "high": 918.2}, "stop_loss": 820}
    assert display_alert_level(h, [], 832.78, 0)["alert_level"] == 820
    h["stop_loss"] = 840
    assert display_alert_level(h, [], 832.78, 0)["alert_level"] is None
