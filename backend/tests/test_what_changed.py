"""Tests for behavior.what_changed — no spurious rows when nothing moved; summary shape."""
from behavior.what_changed import what_changed


def test_identical_snapshots_produce_empty():
    prev = {
        "ticker": "MSFT",
        "composite_buy": 84.0,
        "regime": "UP",
        "rsi": 50.0,
        "ma20": 100.0,
        "ma50": 95.0,
        "macd_hist": 0.1,
        "short_suggestion": "HOLD",
        "medium_suggestion": "HOLD",
        "long_suggestion": "HOLD",
    }
    curr = {**prev}
    changes, summary = what_changed(prev, curr)
    assert changes == []
    assert summary == ""


def test_score_and_regime_in_summary():
    prev = {
        "ticker": "MSFT",
        "composite_buy": 84.0,
        "regime": "UP",
        "rsi": 55.0,
        "ma20": 100.0,
        "ma50": 95.0,
        "macd_hist": 0.1,
        "short_suggestion": "HOLD",
        "medium_suggestion": "HOLD",
        "long_suggestion": "HOLD",
    }
    curr = {**prev, "composite_buy": 72.0, "regime": "NEUTRAL"}
    changes, summary = what_changed(prev, curr)
    assert changes
    assert "MSFT" in summary
    assert "84" in summary and "72" in summary
    assert "UP" in summary and "NEUTRAL" in summary
