"""Tests for swing_engine EOD attachment."""
from __future__ import annotations

import pandas as pd

from signals.swing_engine import attach_swing_to_row, compute_swing_fields


def _mrvl_like_row() -> dict:
    return {
        "ticker": "MRVL",
        "close": 266.0,
        "rsi": 53.0,
        "volume_ratio": 0.5,
        "trend_score": 100.0,
        "composite_buy": 72.0,
        "confluence_score": 45.0,
        "ma20": 260.0,
        "ma50": 213.0,
        "ma200": 200.0,
        "atr_14": 8.0,
        "ml_short_prob": 0.30,
        "signal": "WAIT",
        "retail_status": {
            "go_no_go": "no_go",
            "stock_regime_bull_pct": 68.0,
        },
        "st_band": {"low": 264.0, "high": 268.0},
    }


def test_compute_swing_fields_dip_setup():
    fields = compute_swing_fields(_mrvl_like_row())
    assert fields["swing_setup_type"] == "dip_to_ma"
    assert fields.get("swing_score") is not None
    assert fields["swing_verdict"] in ("SWING_SIGNAL", "WATCH", "NO_SIGNAL")
    assert "swing_t1" in fields
    assert "swing_stop" in fields


def test_attach_swing_to_row_mutates():
    row = _mrvl_like_row()
    close = pd.Series([200.0] * 250 + [266.0])
    attach_swing_to_row(row, close=close, config={"swing_tactical": {"enabled": True}})
    assert row.get("swing_setup_type")
    assert "swing_triggered" in row


def test_swing_triggered_respects_min_score():
    row = _mrvl_like_row()
    fields = compute_swing_fields(
        row,
        config={"swing_tactical": {"min_swing_score": 99, "require_swing_signal_verdict": True}},
    )
    assert fields["swing_triggered"] is False
