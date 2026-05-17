"""Paper trade effective entry: provisional marks vs next-session upgrade."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from signals.paper_trade_logger import PaperTradeLogger, _provisional_entry_anchor_date


def test_provisional_anchor_never_after_latest_snapshot():
    dates = ["2026-05-14", "2026-05-15", "2026-05-16"]
    # Signal Saturday; latest EOD is Friday — anchor must not be a future Monday.
    assert _provisional_entry_anchor_date(dates, "2026-05-16") == "2026-05-16"


def test_next_session_provisional_allows_mtm_before_fill(tmp_path: Path):
    """Weekend signal + Friday EOD: effective entry must not be a future Monday (MTM was blocked)."""
    dates = ["2026-05-15", "2026-05-16"]
    snap = {
        "run_results": [
            {"ticker": "SPY", "close": 500.0, "high": 501.0, "low": 499.0},
        ]
    }

    def fake_load(date_str: str):
        return snap if date_str in dates else None

    row = {
        "date": "2026-05-16",
        "ticker": "SPY",
        "signal": "BUY",
        "entry_price": 499.0,
        "entry_price_source": "live_quote",
        "horizon_trading_days": 20,
        "execution_mode": "next_session",
    }

    with patch.object(PaperTradeLogger, "_list_eod_dates", return_value=dates), patch.object(
        PaperTradeLogger, "_load_snapshot", side_effect=fake_load
    ), patch.object(PaperTradeLogger, "_read_all", return_value=[row]), patch.object(
        PaperTradeLogger, "_write_all", lambda _self, _rows: None
    ):
        pt = PaperTradeLogger(data_root=tmp_path, execution_cfg={"mode": "next_session"})
        eff, eff_date = pt._ensure_effective_entry(row, dates)
        assert eff is not None
        assert eff_date == "2026-05-16"
        assert row["effective_entry_source"] == "signal_entry_provisional"

        mtm = pt.mark_to_market(max_rows=10)
        assert mtm.get("updated", 0) >= 1
        assert row.get("mtm_return_pct") is not None


def test_next_session_upgrades_when_monday_snapshot_exists(tmp_path: Path):
    dates = ["2026-05-16", "2026-05-19"]
    snaps = {
        "2026-05-16": {"run_results": [{"ticker": "SPY", "close": 500.0}]},
        "2026-05-19": {"run_results": [{"ticker": "SPY", "close": 510.0}]},
    }

    def fake_load(date_str: str):
        return snaps.get(date_str)

    row = {
        "date": "2026-05-16",
        "ticker": "SPY",
        "signal": "BUY",
        "entry_price": 499.0,
        "effective_entry_price": 499.15,
        "effective_entry_date": "2026-05-16",
        "effective_entry_source": "signal_entry_provisional",
        "execution_mode": "next_session",
    }

    with patch.object(PaperTradeLogger, "_list_eod_dates", return_value=dates), patch.object(
        PaperTradeLogger, "_load_snapshot", side_effect=fake_load
    ):
        pt = PaperTradeLogger(data_root=tmp_path, execution_cfg={"mode": "next_session"})
        eff, eff_date = pt._ensure_effective_entry(row, dates)
        assert eff_date == "2026-05-19"
        assert row["effective_entry_source"] == "next_session_close"
        assert eff == pytest.approx(510.0, rel=1e-4)
