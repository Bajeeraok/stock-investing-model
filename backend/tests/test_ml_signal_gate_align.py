"""ML signal alignment with retail gates (audit win-rate hygiene)."""
from __future__ import annotations

from signals.retail_action_payload import align_ml_signal_with_retail_gates


def test_buy_downgraded_when_hard_lock():
    row = {"signal": "BUY", "entry_mode": "hard_lock", "retail_status": {"go_no_go": "no_go"}}
    align_ml_signal_with_retail_gates(row)
    assert row["signal"] == "WATCH"
    assert row.get("signal_gate_capped") == "hard_lock"


def test_strong_buy_downgraded_when_hard_lock():
    row = {"signal": "STRONG BUY", "entry_mode": "hard_lock"}
    align_ml_signal_with_retail_gates(row)
    assert row["signal"] == "HOLD"


def test_full_go_keeps_buy():
    row = {"signal": "BUY", "entry_mode": "full_go", "retail_status": {"go_no_go": "go"}}
    align_ml_signal_with_retail_gates(row)
    assert row["signal"] == "BUY"


def test_starter_only_caps_to_watch():
    row = {"signal": "BUY", "entry_mode": "starter_only", "retail_status": {"go_no_go": "no_go"}}
    align_ml_signal_with_retail_gates(row)
    assert row["signal"] == "WATCH"
    assert row.get("signal_gate_capped") == "starter_only"


def test_go_without_full_go_downgrades_buy():
    row = {
        "signal": "BUY",
        "entry_mode": "starter_only",
        "retail_status": {"go_no_go": "go"},
    }
    align_ml_signal_with_retail_gates(row)
    assert row["signal"] == "WATCH"


def test_go_hard_lock_downgrades_buy():
    row = {
        "signal": "BUY",
        "entry_mode": "hard_lock",
        "retail_status": {"go_no_go": "go"},
    }
    align_ml_signal_with_retail_gates(row)
    assert row["signal"] == "WATCH"
