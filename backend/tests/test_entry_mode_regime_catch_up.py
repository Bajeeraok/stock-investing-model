from signals.retail_action_payload import derive_entry_mode


def _gates(regime_pass: bool):
    return [
        {"id": "valuation", "pass": True},
        {"id": "regime", "pass": regime_pass},
        {"id": "momentum", "pass": True},
        {"id": "ml", "pass": True},
        {"id": "confidence", "pass": False},
    ]


def test_regime_only_fail_in_bull_market_stays_locked():
    out = derive_entry_mode(
        gates=_gates(False), assessment_pct=30.0, gate_cleared=False,
        overall_verdict="HOLD", market_regime_bull_pct=80.0, macro_regime_label="BULL",
    )
    assert out["entry_mode"] == "hard_lock"
    assert out["max_sizing_pct"] == 0
    assert out["full_go_via"] is None
    assert out["regime_catch_up_watch"] is True
    assert "Trend weather" in out["entry_mode_headline"]


def test_all_primary_gates_pass_is_full_go():
    out = derive_entry_mode(
        gates=_gates(True), assessment_pct=30.0, gate_cleared=True, overall_verdict="HOLD",
    )
    assert out["entry_mode"] == "full_go"
    assert out["full_go_via"] == "all_gates"
    assert out["regime_catch_up_watch"] is False
