"""Paper trading: buy-side signal filter for actionable summary."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from signals.paper_trade_logger import PaperTradeLogger, _is_buy_side_signal


def test_buy_side_strong_buy_and_buy():
    assert _is_buy_side_signal("STRONG BUY") is True
    assert _is_buy_side_signal("BUY") is True
    assert _is_buy_side_signal("HOLD/ADD") is True


def test_buy_side_excludes_trim_hold_watch():
    assert _is_buy_side_signal("CONSIDER TRIM") is False
    assert _is_buy_side_signal("HOLD") is False
    assert _is_buy_side_signal("WATCH") is False
    assert _is_buy_side_signal("REDUCE") is False


def test_completed_equity_curve_compounds():
    fake_rows = [
        {"outcome": "HIT", "return_pct": 10, "next_date": "2025-01-02", "ticker": "AAA", "signal": "BUY"},
        {"outcome": "MISS", "return_pct": -5, "next_date": "2025-01-03", "ticker": "BBB", "signal": "BUY"},
    ]
    with patch.object(PaperTradeLogger, "_read_all", return_value=fake_rows):
        pt = PaperTradeLogger(data_root=Path("."))
        curve = pt.get_completed_equity_curve()
    assert len(curve) == 2
    assert curve[0]["equity_index"] == pytest.approx(110.0, rel=1e-9)
    assert curve[1]["equity_index"] == pytest.approx(104.5, rel=1e-9)
    assert curve[1]["cumulative_return_pct"] == pytest.approx(4.5, rel=1e-9)
