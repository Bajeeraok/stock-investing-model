"""Momentum vs fair-value tension flag (bull regime + near highs + rising ML vs stretched FV)."""

from __future__ import annotations

from api.ticker_detail import _momentum_valuation_tension_payload


def test_tension_fires_intel_like_snapshot():
    p = _momentum_valuation_tension_payload(
        current_price=127.0,
        fair_value=81.0,
        high_52w=130.57,
        regime_bull_pct=100.0,
        short_ml=38.0,
        medium_ml=44.0,
        long_ml=50.0,
    )
    assert p is not None
    assert p["active"] is True
    assert "Valuation stretched" in p["headline"]
    assert "52-week high" in p["detail"]
    assert p.get("premium_vs_fair_value_pct", 0) >= 18


def test_tension_off_when_regime_not_hot():
    assert (
        _momentum_valuation_tension_payload(
            current_price=127.0,
            fair_value=81.0,
            high_52w=130.57,
            regime_bull_pct=70.0,
            short_ml=38.0,
            medium_ml=44.0,
            long_ml=50.0,
        )
        is None
    )


def test_tension_off_when_not_near_high():
    assert (
        _momentum_valuation_tension_payload(
            current_price=90.0,
            fair_value=81.0,
            high_52w=130.57,
            regime_bull_pct=100.0,
            short_ml=38.0,
            medium_ml=44.0,
            long_ml=50.0,
        )
        is None
    )


def test_tension_off_when_ml_flat():
    assert (
        _momentum_valuation_tension_payload(
            current_price=127.0,
            fair_value=81.0,
            high_52w=130.57,
            regime_bull_pct=100.0,
            short_ml=40.0,
            medium_ml=40.0,
            long_ml=40.0,
        )
        is None
    )


def test_tension_off_without_fair_value():
    assert (
        _momentum_valuation_tension_payload(
            current_price=127.0,
            fair_value=None,
            high_52w=130.57,
            regime_bull_pct=100.0,
            short_ml=38.0,
            medium_ml=44.0,
            long_ml=50.0,
        )
        is None
    )
