from signals.ticker_consistency_audit import audit_ticker_detail


def _rules(lv):
    d = {"ticker": "T", "current_price": 100, "investor_summary": {"horizons": {"medium": {
        "stop_loss": 85, "target": 120,
        "entry_zone": {"low": 92, "high": 98, "levels": [{"id": "a", "label": "a", "price": 95, "role": "entry", **lv}]}}}}}
    return {f["rule"] for f in audit_ticker_detail(d)}


def test_valid_level_stats_pass():
    assert "level_stat_invalid" not in _rules({"similar_touch_pct": 60, "stop_first_pct": 30, "target_first_pct": 50})


def test_invalid_level_stats_flagged():
    assert "level_stat_invalid" in _rules({"after_touch_up_pct": 140})
    assert "level_stat_invalid" in _rules({"stop_first_pct": 70, "target_first_pct": 50})
