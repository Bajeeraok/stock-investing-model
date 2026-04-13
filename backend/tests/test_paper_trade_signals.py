"""Paper trading: buy-side signal filter for actionable summary."""
from __future__ import annotations

from signals.paper_trade_logger import _is_buy_side_signal


def test_buy_side_strong_buy_and_buy():
    assert _is_buy_side_signal("STRONG BUY") is True
    assert _is_buy_side_signal("BUY") is True
    assert _is_buy_side_signal("HOLD/ADD") is True


def test_buy_side_excludes_trim_hold_watch():
    assert _is_buy_side_signal("CONSIDER TRIM") is False
    assert _is_buy_side_signal("HOLD") is False
    assert _is_buy_side_signal("WATCH") is False
    assert _is_buy_side_signal("REDUCE") is False
