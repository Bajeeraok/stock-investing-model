"""Daily P/L from prior EOD + tracking gate filter."""

from __future__ import annotations

from unittest.mock import patch

from signals.paper_trade_logger import PaperTradeLogger
from signals.tracking_gate import enrich_tracking_row, passes_tracking_gate


def test_passes_tracking_gate_when_cleared():
    row = {"gate_cleared": True}
    cfg = {"paper_trading": {"require_gates_cleared": True}}
    assert passes_tracking_gate(row, cfg, "paper_trading") is True


def test_blocks_when_gates_locked():
    row = {"gate_cleared": False, "go_no_go": "no_go"}
    cfg = {"paper_trading": {"require_gates_cleared": True}}
    assert passes_tracking_gate(row, cfg, "paper_trading") is False


def test_mark_to_market_daily_delta_from_prior_eod(tmp_path):
    dates = ["2026-05-14", "2026-05-15", "2026-05-16"]
    snaps = {
        "2026-05-14": {"run_results": [{"ticker": "SPY", "close": 500.0}]},
        "2026-05-15": {"run_results": [{"ticker": "SPY", "close": 502.0}]},
        "2026-05-16": {"run_results": [{"ticker": "SPY", "close": 504.0}]},
    }

    def fake_load(date_str: str):
        return snaps.get(date_str)

    row = {
        "date": "2026-05-14",
        "ticker": "SPY",
        "signal": "BUY",
        "entry_price": 500.0,
        "horizon_trading_days": 20,
        "execution_mode": "close_to_close",
        "effective_entry_price": 500.0,
        "effective_entry_date": "2026-05-14",
        "mtm_date": "2026-05-15",
        "rolling_entry_price": 502.0,
    }

    with patch.object(PaperTradeLogger, "_list_eod_dates", return_value=dates), patch.object(
        PaperTradeLogger, "_load_snapshot", side_effect=fake_load
    ), patch.object(PaperTradeLogger, "_read_all", return_value=[row]), patch.object(
        PaperTradeLogger, "_write_all", lambda _self, _rows: None
    ):
        pt = PaperTradeLogger(data_root=tmp_path, execution_cfg={"mode": "close_to_close"})
        mtm = pt.mark_to_market()
        assert mtm.get("updated", 0) == 1
        assert row.get("rolling_pnl") is not None
        assert row.get("rolling_return_pct") is not None
        # 504 vs prior EOD 502 on 2026-05-15
        assert float(row["rolling_pnl"]) == 2.0


def test_enrich_tracking_row_sets_gate_fields():
    row = {
        "ticker": "SPY",
        "close": 500.0,
        "composite_buy": 75,
        "signal": "BUY",
        "rsi": 45,
        "regime": "UP",
        "st_band": {"high": 510, "low": 490},
        "lt_band": {"low": 480, "high": 520},
    }
    enrich_tracking_row(row)
    assert row.get("gate_cleared") is not None
    assert row.get("retail_status") is not None
