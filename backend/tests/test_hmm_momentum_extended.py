"""HMM momentum-extended tier (ATH + aligned MAs, low bull %)."""

from signals.hmm_regime import detect_momentum_extended, validate_regime
from signals.retail_action_payload import _regime_gate_detail, regime_weather_status


def test_mrvl_like_ath_low_bull_is_momentum_extended():
    """Parabolic name at highs: 0% bull HMM should read as extended, not bear."""
    ctx = detect_momentum_extended(
        last_close=100.0,
        ma20=96.0,
        ma50=92.0,
        ma200=78.0,
        high_52w=101.0,
        bull_prob=0.0,
        bear_prob=0.55,
        dominant_validated="BEAR",
        gap_ma200_pct=28.0,
        recent_63d_return_pct=35.0,
        rsi=68.0,
    )
    assert ctx["active"] is True
    assert ctx["display_regime"] == "MOMENTUM_EXTENDED"


def test_weak_structure_not_extended():
    ctx = detect_momentum_extended(
        last_close=100.0,
        ma20=98.0,
        ma50=95.0,
        ma200=102.0,
        high_52w=105.0,
        bull_prob=0.0,
        bear_prob=0.8,
        dominant_validated="BEAR",
        gap_ma200_pct=-2.0,
        recent_63d_return_pct=-5.0,
        rsi=42.0,
    )
    assert ctx["active"] is False


def test_validate_regime_bear_above_stack_is_momentum_extended():
    v = validate_regime(
        ticker="MRVL",
        hmm_dominant="BEAR",
        last_close=100.0,
        ma20=97.0,
        ma50=94.0,
        ma200=80.0,
    )
    assert v["resolved_regime"] == "MOMENTUM_EXTENDED"
    assert v["reason"] == "HMM_BEAR_BUT_ABOVE_STACK"


def test_regime_weather_extended_token():
    assert regime_weather_status(5.0, momentum_extended=True) == "extended"


def test_regime_gate_copy_not_stormy_when_extended():
    detail = _regime_gate_detail(
        ticker="MRVL",
        stock_bull_pct=0.0,
        regime_ok=False,
        momentum_extended=True,
    )
    assert "Extended tape" in detail
    assert "Stormy" not in detail
    assert "not structural bear" in detail
