"""Tests for paper vs forward-tracking baseline drift helper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from signals.paper_vs_backtest_drift import build_paper_vs_backtest_drift


def test_insufficient_paper():
    ft = {"summary_by_horizon": {20: {"avg_return_pct": 1.5, "n_observations": 100}}}
    with patch("signals.paper_vs_backtest_drift.PaperTradeLogger") as MockPtl:
        inst = MagicMock()
        inst.get_performance_summary.return_value = {"completed": 1}
        MockPtl.return_value = inst
        out = build_paper_vs_backtest_drift(ft, Path("/tmp"))
    assert out is not None
    assert out["status"] == "insufficient_paper"
    assert out["paper_completed_n"] == 1
    assert out["forward_20d_baseline_pct"] == 1.5


def test_drift_computed():
    ft = {"summary_by_horizon": {20: {"avg_return_pct": 2.0, "n_observations": 50}}}
    with patch("signals.paper_vs_backtest_drift.PaperTradeLogger") as MockPtl:
        inst = MagicMock()
        inst.get_performance_summary.return_value = {
            "status": "ok",
            "completed": 5,
            "avg_return_pct": 5.5,
            "win_rate_pct": 60.0,
            "avg_excess_vs_spy_pct": 1.0,
        }
        MockPtl.return_value = inst
        out = build_paper_vs_backtest_drift(ft, Path("/tmp"))
    assert out is not None
    assert out["drift_vs_forward_pct"] == pytest.approx(3.5)
    assert "note" in out


def test_none_forward_tracking():
    assert build_paper_vs_backtest_drift(None) is None
