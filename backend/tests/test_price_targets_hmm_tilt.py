"""Universal scenario probabilities tilt from HMM (scenario_regime_aware.compute_regime_factor)."""

from signals.price_targets import _tilt_universal_scenarios_for_hmm


def test_hmm_tilt_adds_fields_and_moves_bull_down_in_transition_regime():
    scenarios = [
        {
            "scenario_type": "bull",
            "probability": 0.40,
            "return_pct": 10.0,
            "name": "Bull Case",
        },
        {
            "scenario_type": "base",
            "probability": 0.35,
            "return_pct": 2.0,
            "name": "Base Case",
        },
        {
            "scenario_type": "bear",
            "probability": 0.25,
            "return_pct": -8.0,
            "name": "Bear Case",
        },
    ]
    _tilt_universal_scenarios_for_hmm(
        scenarios,
        {"bull": 0.01, "bear": 0.0, "transition": 0.99},
    )
    assert "regime_hmm_factor" in scenarios[0]
    assert scenarios[0]["probability"] < 0.40
    assert scenarios[2]["probability"] >= 0.25
