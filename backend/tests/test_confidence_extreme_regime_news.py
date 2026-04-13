"""Extreme HMM certainty: news weight shifts toward regime."""

from __future__ import annotations

from signals.confidence_engine import _apply_extreme_regime_news_shrink


def test_shrink_moves_mass_to_regime_when_bear_certain():
    w0 = {
        "regime_hmm": 0.11,
        "pattern_technical": 0.15,
        "lgbm_probability": 0.18,
        "options_sentiment": 0.14,
        "insider_signal": 0.14,
        "fundamental_score": 0.14,
        "nlp_sentiment": 0.14,
    }
    hmm = {"bear_probability": 1.0, "bull_probability": 0.0}
    cfg = {"confidence": {"extreme_regime_news": {"enabled": True, "certainty_threshold": 0.9, "news_weight_fraction": 0.35}}}
    w1, audit = _apply_extreme_regime_news_shrink(w0, hmm, cfg)
    assert audit and audit.get("applied") and audit.get("mode") == "fraction"
    assert w1["nlp_sentiment"] == round(0.14 * 0.35, 10)
    assert abs(w1["regime_hmm"] - (0.11 + 0.14 * (1 - 0.35))) < 1e-9


def test_no_shrink_below_threshold():
    w0 = {"regime_hmm": 0.11, "nlp_sentiment": 0.14}
    hmm = {"bear_probability": 0.5, "bull_probability": 0.2}
    cfg = {"confidence": {"extreme_regime_news": {"enabled": True, "certainty_threshold": 0.9}}}
    w1, audit = _apply_extreme_regime_news_shrink(w0, hmm, cfg)
    assert audit is None
    assert w1 == w0


def test_disabled_noop():
    w0 = {"regime_hmm": 0.1, "nlp_sentiment": 0.2}
    hmm = {"bear_probability": 0.99}
    cfg = {"confidence": {"extreme_regime_news": {"enabled": False}}}
    w1, audit = _apply_extreme_regime_news_shrink(w0, hmm, cfg)
    assert audit is None
    assert w1 == w0
