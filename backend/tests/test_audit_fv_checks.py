from signals import ticker_consistency_audit as a


def _detail(fv, ttm=7.91, fwd=9.29, val_pass=True):
    return {"ticker": "NVDA", "current_price": 161.0,
            "investor_summary": {"fair_value": fv, "fair_value_metadata": {"ttm_eps": ttm, "forward_eps": fwd},
                                 "retail_action": {"gates": [{"id": "valuation", "pass": val_pass}]}}}


def test_jump_without_eps_change_flagged():
    prev = {"NVDA": a.fair_value_inputs(_detail(233.7))}
    out = a.fair_value_jumps(prev, {"NVDA": a.fair_value_inputs(_detail(169.5))})
    assert [f["rule"] for f in out] == ["fair_value_jump"] and out[0]["severity"] == "error"


def test_jump_with_eps_change_or_small_move_not_flagged():
    prev = {"NVDA": a.fair_value_inputs(_detail(233.7))}
    assert a.fair_value_jumps(prev, {"NVDA": a.fair_value_inputs(_detail(300.0, ttm=9.5))}) == []
    assert a.fair_value_jumps(prev, {"NVDA": a.fair_value_inputs(_detail(240.0))}) == []
    assert a.fair_value_jumps({}, {"NVDA": a.fair_value_inputs(_detail(169.5))}) == []


def test_list_vs_detail_fair_value_and_gate():
    row = {"lt_fair_value_mid": 169.5, "retail_status": {"gates": [{"id": "valuation", "pass": False}]}}
    rules = {f["rule"] for f in a.audit_ticker_detail(_detail(233.7), row)}
    assert {"list_vs_detail_fair_value", "list_vs_detail_valuation_gate"} <= rules
    row_ok = {"lt_fair_value_mid": 233.0, "retail_status": {"gates": [{"id": "valuation", "pass": True}]}}
    rules = {f["rule"] for f in a.audit_ticker_detail(_detail(233.7), row_ok)}
    assert not rules & {"list_vs_detail_fair_value", "list_vs_detail_valuation_gate"}


def test_audit_missing_after_restart():
    assert a.audit_missing({"generated_at": "2026-11-12T01:42:15+00:00"}, "2026-11-12")  # Nov 11 ET report
    assert not a.audit_missing({"eod_date": "2026-11-12"}, "2026-11-12")
    assert a.audit_missing(None, "2026-11-12")
    assert not a.audit_missing(None, None)


def test_error_alert_names_tickers():
    rep = {"findings": [{"ticker": "NVDA", "rule": "fair_value_jump", "severity": "error"},
                        {"ticker": "AAPL", "rule": "go_no_go_mismatch", "severity": "error"},
                        {"ticker": "MSFT", "rule": "x", "severity": "warn"}]}
    title, msg = a.error_alert_text(rep)
    assert "2 errors on 2 tickers" in title and "AAPL, NVDA" in msg and "MSFT" not in msg
    assert a.error_alert_text({"findings": []}) is None
