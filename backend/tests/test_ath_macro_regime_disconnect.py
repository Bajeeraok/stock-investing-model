"""ATH / near-highs vs strong non-bull regime — macro vs name communication note."""

from __future__ import annotations

from api.ticker_detail import _ath_vs_macro_regime_disconnect_payload


def test_fires_googl_style_extreme_non_bull():
    p = _ath_vs_macro_regime_disconnect_payload(
        current_price=100.0,
        high_52w=100.2,
        regime_bull_pct=1.0,
    )
    assert p is not None
    assert p["active"] is True
    assert "macro caution" in p["detail"]
    assert "company-specific weakness" in p["detail"]


def test_off_when_regime_bullish():
    assert (
        _ath_vs_macro_regime_disconnect_payload(
            current_price=100.0,
            high_52w=100.2,
            regime_bull_pct=55.0,
        )
        is None
    )


def test_off_when_not_near_high():
    assert (
        _ath_vs_macro_regime_disconnect_payload(
            current_price=90.0,
            high_52w=100.0,
            regime_bull_pct=5.0,
        )
        is None
    )


def test_fires_borderline_non_bull_42pct():
    p = _ath_vs_macro_regime_disconnect_payload(
        current_price=100.0,
        high_52w=100.1,
        regime_bull_pct=42.0,
    )
    assert p is not None
    assert p.get("non_bull_pct") == 58.0
