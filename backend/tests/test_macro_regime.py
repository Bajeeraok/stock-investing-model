"""No-network tests for macro regime scoring and fusion."""
from signals.macro_regime import classify_macro_regime, combine_macro_hmm, macro_hmm_coaching_note


def test_classify_macro_regime_neutral_baseline():
    out = classify_macro_regime({})
    assert out["macro_regime"] == "NEUTRAL"
    assert 40 <= out["macro_score"] <= 60


def test_classify_macro_regime_bullish_curve_and_calm_credit():
    out = classify_macro_regime({
        "yield_curve_2s10s": 0.6,
        "hy_oas_bp": 280.0,
        "vix": 14.0,
        "unemployment_mom_pct": -0.015,
    })
    assert out["macro_regime"] == "BULL"
    assert out["macro_score"] >= 65


def test_combine_macro_hmm_weights():
    c = combine_macro_hmm(80.0, 60.0, hmm_weight=0.4, macro_weight=0.6)
    # hmm_score = 20 → 20*0.4 + 60*0.6 = 8 + 36 = 44
    assert c["combined_score"] == 44.0
    assert c["combined_regime"] == "NEUTRAL"


def test_combine_macro_hmm_without_hmm():
    c = combine_macro_hmm(None, 55.0)
    assert c["combined_score"] == 55.0
    assert c["hmm_score"] is None


def test_macro_hmm_coaching_note_bearish_hmm_constructive_macro():
    note = macro_hmm_coaching_note({
        "macro_regime": "NEUTRAL",
        "macro_score": 50,
        "hmm_bear_pct_used": 70.0,
    })
    assert note is not None
    assert "Price model" in note


def test_macro_hmm_coaching_note_bear_macro_stressed_calm_hmm():
    note = macro_hmm_coaching_note({
        "macro_regime": "BEAR",
        "macro_score": 35,
        "hmm_bear_pct_used": 25.0,
    })
    assert note is not None
    assert "Macro" in note


def test_macro_hmm_coaching_note_aligned_none():
    assert macro_hmm_coaching_note({
        "macro_regime": "NEUTRAL",
        "hmm_bear_pct_used": 50.0,
    }) is None

