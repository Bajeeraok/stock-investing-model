"""Tests for forward-tracking lens summaries and journal search."""
from __future__ import annotations

from behavior.trade_discipline import append_journal, list_journal
from signals.forward_tracking_lens import build_summary_by_lens


def test_build_summary_by_lens_from_horizons():
    ft = {
        "summary_by_horizon": {
            5: {"win_rate_pct": 55.0, "avg_return_pct": 1.2, "n_observations": 10},
            20: {"win_rate_pct": 58.0, "avg_return_pct": 2.1, "n_observations": 12},
            60: {"win_rate_pct": 52.0, "avg_return_pct": 4.0, "n_observations": 8},
        },
        "summary_by_signal": {
            "HOLD/ADD": {"hit_rate_pct": 57.0, "n_observations": 15, "avg_return_pct": 2.0},
        },
    }
    out = build_summary_by_lens(ft)
    assert "scout" in out
    assert out["scout"]["primary_horizon_days"] == 5
    assert out["scout"]["label"] is not None


def test_list_journal_search(monkeypatch, tmp_path):
    import behavior.trade_discipline as td

    monkeypatch.setattr(td, "_path", lambda: tmp_path / "trade_discipline.json")
    cfg = {"behavior": {"journal_max_entries": 50}}
    append_journal("NVDA", "add", "Pullback to MA50", cfg)
    append_journal("AAPL", "trim", "Score weak", cfg)

    rows = list_journal(20, ticker="NVDA")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "NVDA"

    rows_q = list_journal(20, q="ma50")
    assert len(rows_q) == 1
