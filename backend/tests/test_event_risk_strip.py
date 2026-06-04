"""Tests for event_risk_strip ranking."""
from __future__ import annotations

from signals.event_risk_strip import (
    _quick_event_score,
    build_event_risk_strip,
    _default_cfg,
)


def test_quick_score_boosts_imminent_earnings():
    cfg = _default_cfg({})
    base = {"close": 100.0, "atr_14": 4.0, "velocity_score": 30, "earnings_days_until": None}
    far = _quick_event_score(base, cfg)
    soon = _quick_event_score({**base, "earnings_days_until": 1}, cfg)
    assert soon > far


def test_build_strip_filters_to_watchlist():
    results = [
        {"ticker": "AVGO", "close": 200, "atr_14": 8, "velocity_score": 40, "earnings_days_until": 0},
        {"ticker": "ZZZZ", "close": 10, "atr_14": 1, "velocity_score": 90, "earnings_days_until": 0},
    ]
    out = build_event_risk_strip(
        results,
        {},
        watchlist_tickers=["AVGO"],
        portfolio_tickers=[],
        limit=5,
    )
    tickers = [r["ticker"] for r in out["rows"]]
    assert "AVGO" in tickers
    assert "ZZZZ" not in tickers


def test_row_payload_includes_bias_fields():
    row = {
        "ticker": "TEST",
        "close": 50.0,
        "atr_14": 2.5,
        "velocity_score": 45,
        "earnings_days_until": 3,
        "ml_short_prob": 0.62,
    }
    from signals.event_risk_strip import _row_payload

    payload = _row_payload(
        row,
        score=25.0,
        cfg=_default_cfg({}),
        earnings_target={
            "expected_move_pct": 8.5,
            "bias": "Bullish",
            "bias_prob_pct": 62.0,
            "upside_target": 54.25,
            "downside_target": 45.75,
            "directional_target": 52.35,
            "calibration_hit_rate": 0.67,
            "calibration_mae_pct": 2.1,
            "backtest_events": 6,
            "recent_events": [{"event_date": "2025-12-01", "realized_move_pct": 5.2}],
        },
    )
    assert payload["pre_earnings_bias"] == "Bullish"
    assert payload["post_earnings_directional"] == 52.35
    assert payload["calibration_hit_rate"] == 0.67
