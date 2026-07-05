"""Tests for swing paper trade logging."""
from __future__ import annotations

from signals.paper_trade_logger import PaperTradeLogger, _result_to_swing_paper_record


def test_swing_paper_record_requires_trigger():
    row = {"ticker": "AAPL", "close": 100.0, "swing_triggered": False}
    assert _result_to_swing_paper_record(row, "2026-06-01") is None


def test_swing_paper_record_builds_track():
    row = {
        "ticker": "AAPL",
        "close": 100.0,
        "swing_triggered": True,
        "swing_setup_type": "dip_to_ma",
        "swing_setup_label": "DIP TO MA21",
        "swing_score": 75.0,
        "swing_t1": 105.0,
        "swing_stop": 95.0,
        "swing_horizon_trading_days": 12,
        "composite_buy": 70.0,
        "regime": "UP",
    }
    rec = _result_to_swing_paper_record(row, "2026-06-01", config={})
    assert rec is not None
    assert rec["track"] == "swing"
    assert rec["signal"].startswith("SWING:")
    assert rec["target_1"] == 105.0
    assert rec["hard_stop"] == 95.0


def test_log_swing_disabled_by_default(tmp_path):
    pt = PaperTradeLogger(data_root=tmp_path)
    out = pt.log_swing_trades_from_results(
        [{"ticker": "AAPL", "swing_triggered": True, "close": 100.0}],
        date_str="2026-06-01",
        config={"swing_tactical": {"enabled": True, "log_paper_trades": False}},
    )
    assert out.get("enabled") is False
    assert out.get("appended") == 0
