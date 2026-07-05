"""Paper velocity track filters and stale outcome guards."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from signals.paper_trade_logger import (
    PaperTradeLogger,
    _pair_has_new_price_bar,
    _velocity_eligible_for_paper,
)


def test_velocity_skips_reduce_signal():
    row = {"signal": "REDUCE", "velocity_triggered": True, "gates_passed": 2}
    assert _velocity_eligible_for_paper(row, {"velocity_tactical": {"require_buy_side_for_paper": True}}) is False


def test_velocity_allows_hold_when_not_bearish():
    row = {"signal": "HOLD", "velocity_triggered": True, "gates_passed": 1}
    assert _velocity_eligible_for_paper(row, {"velocity_tactical": {"require_buy_side_for_paper": True}}) is True


def test_velocity_min_gates_for_paper():
    row = {"signal": "BUY", "velocity_triggered": True, "gates_passed": 1}
    cfg = {"velocity_tactical": {"require_buy_side_for_paper": True, "min_gates_for_paper": 2}}
    assert _velocity_eligible_for_paper(row, cfg) is False


def test_pair_has_new_price_bar_by_close_change():
    assert _pair_has_new_price_bar(None, None, prior_close=100.0, actual_close=101.0) is True


def test_pair_has_new_price_bar_stale_holiday():
    start = {"close": 100.0, "ohlcv_last_date": "2026-07-02"}
    end = {"close": 100.0, "ohlcv_last_date": "2026-07-02"}
    assert _pair_has_new_price_bar(start, end, prior_close=100.0, actual_close=100.0) is False


def test_pair_has_new_price_bar_advancing_ohlcv_date():
    start = {"close": 100.0, "ohlcv_last_date": "2026-07-02"}
    end = {"close": 100.0, "ohlcv_last_date": "2026-07-03"}
    assert _pair_has_new_price_bar(start, end, prior_close=100.0, actual_close=100.0) is True


def test_headline_no_accumulate_when_velocity_only(tmp_path: Path):
    rows = [
        {
            "date": "2026-06-01",
            "ticker": "NVDA",
            "signal": "HOLD",
            "track": "velocity",
            "outcome": "MISS",
            "return_pct": -5.0,
            "hit_target": 0,
            "next_date": "2026-06-06",
        }
    ] * 5
    with patch.object(PaperTradeLogger, "_read_all", return_value=rows):
        pt = PaperTradeLogger(data_root=tmp_path)
        summ = pt.get_performance_summary(min_completed=3, min_actionable=3)
    assert summ.get("headline_track") == "no_accumulate"
    assert summ.get("win_rate_pct") is None
    assert summ.get("tactical_summary") is not None
    assert summ["tactical_summary"]["completed_n"] == 5
