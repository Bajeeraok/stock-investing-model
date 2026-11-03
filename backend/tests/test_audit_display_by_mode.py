from signals.ticker_consistency_audit import audit_ticker_detail


def _detail(alert, passed=1, max_add=None):
    long_ez = {"low": 80, "high": 90, **({"max_add": max_add} if max_add else {})}
    return {"ticker": "T", "current_price": 100, "investor_summary": {
        "horizons": {"long": {"entry_zone": long_ez}},
        "retail_action": {
            "gates_by_mode": {"owner": [{"id": "valuation", "pass": False}, {"id": "ml", "pass": True}]},
            "display_by_mode": {"owner": {"gates_passed": passed, "gates_total": 2, "alert_level": alert}}}}}


def _rules(d):
    return {f["rule"] for f in audit_ticker_detail(d)}


def test_clean_display_has_no_display_findings():
    assert not {r for r in _rules(_detail(85, max_add=90)) if r.startswith("display_")}


def test_display_errors():
    assert "display_alert_above_price" in _rules(_detail(120))
    assert "display_alert_above_max_add" in _rules(_detail(95, max_add=90))
    assert "display_gate_count_mismatch" in _rules(_detail(85, passed=2))
