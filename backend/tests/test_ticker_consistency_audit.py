from signals.ticker_consistency_audit import audit_ticker_detail, summarize


def _detail(**over):
    d = {
        "ticker": "TEST",
        "current_price": 100.0,
        "low_52w": 80.0,
        "high_52w": 120.0,
        "gates_passed": 2,
        "model_confidence_pct": 50.0,
        "investor_summary": {
            "fair_value": 120.0,
            "model_confidence_pct": 50.0,
            "retail_action": {
                "entry_mode": "hard_lock",
                "go_no_go": "no_go",
                "max_sizing_pct": 0,
                "assessment_pct": 20.0,
                "gates": [{"id": "valuation", "pass": True}, {"id": "regime", "pass": True}, {"id": "ml", "pass": False}],
            },
            "horizons": {
                "short": {"entry_zone": {"low": 97.0, "high": 100.0}, "stop_loss": 94.0, "target": 105.0, "verdict": "HOLD"},
                "medium": {"entry_zone": {"low": 92.0, "high": 99.0}, "stop_loss": 88.0, "target": 112.0, "verdict": "HOLD"},
                "long": {"entry_zone": {"low": 85.0, "high": 95.0}, "stop_loss": 75.0, "target": 130.0, "verdict": "HOLD"},
            },
        },
    }
    d.update(over)
    return d


def _rules(findings):
    return {f["rule"] for f in findings}


def test_clean_detail_has_no_findings():
    assert audit_ticker_detail(_detail()) == []


def test_catches_list_vs_detail_and_gate_count():
    f = audit_ticker_detail(_detail(gates_passed=4), {"entry_mode": "full_go"})
    assert {"list_vs_detail_entry_mode", "gate_count_mismatch"} <= _rules(f)


def test_catches_band_and_target_problems():
    d = _detail()
    hz = d["investor_summary"]["horizons"]
    hz["medium"]["entry_zone"] = {"low": 80.0, "high": 104.0}
    hz["short"]["target"] = 95.0
    rules = _rules(audit_ticker_detail(d))
    assert {"band_above_price", "band_too_wide", "target_below_price"} <= rules


def test_buy_verdict_while_locked_and_nan():
    d = _detail(dividend_yield=float("nan"))
    d["investor_summary"]["horizons"]["long"]["verdict"] = "BUY"
    rules = _rules(audit_ticker_detail(d))
    assert {"buy_verdict_while_locked", "non_finite_values"} <= rules


def test_summary_counts():
    f = audit_ticker_detail(_detail(gates_passed=4))
    s = summarize(f, ["TEST"])
    assert s["counts"]["warn"] == 1 and s["by_rule"][0]["rule"] == "gate_count_mismatch"
