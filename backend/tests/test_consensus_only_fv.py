from signals.horizon_entry_calculator import LongTermInputs, compute_long_term_entry
from signals.retail_action_payload import derive_entry_mode
from tests.test_entry_mode import _gates


def _lt(**kw):
    base = dict(current_price=100.0, fair_value=200.0, ma200=110.0, week52_low=90.0,
                ml_prob=40.0, regime_bull_pct=55.0, fundamentals_score=60.0, ticker="XYZ")
    base.update(kw)
    return compute_long_term_entry(LongTermInputs(**base))


def _tier(sig, tid):
    for t in sig.entry_tiers["tiers"]:
        t = t if isinstance(t, dict) else t.__dict__
        if t["id"] == tid:
            return t


def test_consensus_only_fair_value_caps_at_partial():
    ca = _lt(fv_model_suppressed=True, fv_street_anchor_usd=200.0).entry_tiers["current_assessment"]
    assert ca["margin_of_safety_pct"] >= 25 and ca["verdict"] == "PARTIAL" and ca["fv_consensus_only"]


def test_model_fair_value_keeps_full_buy():
    ca = _lt().entry_tiers["current_assessment"]
    assert ca["verdict"] == "BUY" and not ca["fv_consensus_only"]


def test_tier3_stress_band_bounded_to_half_of_spot():
    """SNDK-like: 52w low $180 vs spot $800 put T3 at $189–207."""
    sig = _lt(current_price=800.0, fair_value=1000.0, ma200=700.0, week52_low=180.0)
    assert _tier(sig, "T3")["high"] >= 399.0


def test_full_go_on_consensus_only_fv_is_partial_size():
    gates = _gates(assessment_pct=30.0, regime_bull_pct=70.0, rsi=42.0)
    entry = derive_entry_mode(gates=gates, assessment_pct=30.0, gate_cleared=True, fv_consensus_only=True)
    assert entry["entry_mode"] == "full_go" and entry["max_sizing_pct"] == 50
    assert "consensus" in entry["entry_mode_headline"]
