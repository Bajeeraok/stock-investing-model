"""Limit-touch paper entries: log only when price hits reference entry."""

from __future__ import annotations

from unittest.mock import patch

from signals.paper_trade_logger import PaperTradeLogger, _bar_touches_limit, _reference_entry_from_row


def test_bar_touches_limit_with_low():
    assert _bar_touches_limit({"low": 98.0, "close": 101.0}, 99.0) is True
    assert _bar_touches_limit({"low": 100.5, "close": 101.0}, 99.0) is False


def test_reference_entry_st_band_with_fallback():
    row = {
        "close": 100.0,
        "st_band": {"low": 95.0, "high": 105.0},
        "suggested_buy_price": 98.0,
    }
    assert _reference_entry_from_row(row, "st_band_low") == 95.0


def test_reference_entry_falls_back_to_suggested_buy():
    row = {"close": 100.0, "st_band": None, "suggested_buy_price": 96.0}
    assert _reference_entry_from_row(row, "st_band_low") == 96.0


def test_reference_entry_rejects_above_spot():
    row = {"close": 90.0, "st_band": {"low": 95.0, "high": 100.0}}
    assert _reference_entry_from_row(row, "st_band_low") is None


def test_reference_entry_suggested_buy_only():
    row = {"suggested_buy_price": 150.0, "close": 160.0}
    assert _reference_entry_from_row(row, "suggested_buy_price") == 150.0


def test_scan_limit_entry_on_later_eod_touch(tmp_path):
    dates = ["2026-05-01", "2026-05-02", "2026-05-05"]
    base_row = {
        "ticker": "SPY",
        "signal": "BUY",
        "gate_cleared": True,
        "go_no_go": "go",
        "gates_passed": 4,
        "gates_total": 4,
        "suggested_buy_price": 500.0,
        "close": 510.0,
        "high": 512.0,
        "low": 508.0,
        "st_band": {"high": 520.0, "low": 490.0},
        "composite_buy": 75,
        "rsi": 45,
        "regime": "UP",
    }
    snaps = {
        "2026-05-01": {"run_results": [dict(base_row)]},
        "2026-05-02": {
            "run_results": [{"ticker": "SPY", "close": 505.0, "high": 506.0, "low": 504.0}]
        },
        "2026-05-05": {
            "run_results": [{"ticker": "SPY", "close": 492.0, "high": 495.0, "low": 489.0}]
        },
    }

    def fake_load(date_str: str):
        return snaps.get(date_str)

    cfg = {
        "paper_trading": {
            "entry_mode": "limit_touch",
            "reference_entry": "st_band_low",
            "limit_max_wait_days": 5,
            "require_gates_cleared": True,
            "require_actionable_signal": True,
        }
    }

    with patch.object(PaperTradeLogger, "_list_eod_dates", return_value=dates), patch.object(
        PaperTradeLogger, "_load_snapshot", side_effect=fake_load
    ):
        pt = PaperTradeLogger(data_root=tmp_path)
        out = pt.scan_limit_entries_from_eod(
            allowed_tickers={"SPY"},
            max_signal_days=30,
            config=cfg,
        )
        assert out["appended"] == 1
        rows = pt._read_all()
        assert len(rows) == 1
        assert rows[0]["limit_fill_date"] == "2026-05-05"
        assert float(rows[0]["entry_price"]) == 490.0
        assert float(rows[0]["reference_entry_price"]) == 490.0
        assert rows[0]["entry_price_source"] == "limit_touch"
        assert rows[0]["date"] == "2026-05-01"
