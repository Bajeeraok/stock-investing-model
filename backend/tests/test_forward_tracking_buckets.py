"""Forward tracking signal bucket respects full_go entry gate."""
from __future__ import annotations

from signals.forward_tracking import signal_bucket_from_row


def test_score_high_without_full_go_is_hold_not_add():
    row = {"composite_buy": 78, "entry_mode": "starter_only", "go_no_go": "go"}
    assert signal_bucket_from_row(row, buy_min=70, sell_max=30) == "HOLD"


def test_score_high_with_full_go_is_hold_add():
    row = {"composite_buy": 78, "entry_mode": "full_go", "go_no_go": "go"}
    assert signal_bucket_from_row(row, buy_min=70, sell_max=30) == "HOLD/ADD"
