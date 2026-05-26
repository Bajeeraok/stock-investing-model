"""Crowd positioning — Fear & Greed, SPY put/call, config overrides."""
from __future__ import annotations

from unittest.mock import patch

from signals.sentiment_positioning import (
    _positioning_read,
    _put_call_from_config,
    _spy_put_call_positioning,
    get_crowd_positioning,
)


def test_positioning_read_moderate_hedge():
    read = _positioning_read(0.82)
    assert read["signal"] == "MODERATE_HEDGE"
    assert "0.82" in read["plain_english"]
    assert "moderate hedging" in read["plain_english"].lower()


def test_config_put_call_override():
    cfg = {"retail": {"sentiment": {"put_call_ratio": 0.82}}}
    out = _put_call_from_config(cfg)
    assert out is not None
    assert out["ratio"] == 0.82
    assert "config override" in out["source"]


def test_spy_pc_config_skips_yfinance():
    with patch("signals.sentiment_positioning._fetch_spy_put_call_yfinance") as mock_yf:
        out = _spy_put_call_positioning({"retail": {"sentiment": {"put_call_ratio": 1.05}}})
        mock_yf.assert_not_called()
    assert out is not None
    assert out["ratio"] == 1.05


@patch("signals.sentiment_positioning._fetch_cnn_fear_greed")
@patch("signals.sentiment_positioning._fetch_spy_put_call_yfinance")
def test_get_crowd_positioning_includes_spy_pc(mock_spy, mock_fng):
    mock_fng.return_value = {"score": 42.0, "rating": "Fear", "source": "CNN Fear & Greed"}
    mock_spy.return_value = {
        "ratio": 0.82,
        "pc_oi_ratio": 0.91,
        "signal": "MODERATE_HEDGE",
        "plain_english": "Put/Call 0.82 — moderate hedging, not extreme fear.",
        "source": "SPY options (yfinance, nearest expiry)",
    }
    with patch("signals.cache.get_cached", return_value=None), patch("signals.cache.set_cached"):
        out = get_crowd_positioning({})
    assert out["spy_put_call"]["ratio"] == 0.82
    assert "Put/Call 0.82" in out["plain_english"]
