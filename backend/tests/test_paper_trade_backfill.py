"""Paper trade EOD backfill and outcome fill for open rows."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
from pandas.tseries.offsets import BDay

from signals.paper_trade_logger import PaperTradeLogger


def _make_snap(date_str: str, ticker: str, close: float) -> dict:
    return {
        "run_results": [
            {
                "ticker": ticker,
                "close": close,
                "high": close + 1,
                "low": close - 1,
                "signal": "HOLD",
                "st_band": {"high": close + 5, "low": close - 5},
            }
        ]
    }


def test_backfill_from_eod_appends_missing_rows(tmp_path):
    dates = ["2026-03-01", "2026-03-02", "2026-03-03"]
    snaps = {d: _make_snap(d, "SPY", 500.0 + i) for i, d in enumerate(dates)}

    def fake_load(date_str: str):
        return snaps.get(date_str)

    with patch.object(PaperTradeLogger, "_list_eod_dates", return_value=dates), patch.object(
        PaperTradeLogger, "_load_snapshot", side_effect=fake_load
    ):
        pt = PaperTradeLogger(data_root=tmp_path)
        out = pt.backfill_from_eod_snapshots(
            allowed_tickers={"SPY"},
            max_days=30,
            horizon_trading_days=20,
            config={"paper_trading": {"require_gates_cleared": False, "entry_mode": "market"}},
        )
        assert out["appended"] == 3
        rows = pt._read_all()
        assert len(rows) == 3
        assert {r["date"] for r in rows} == set(dates)


def test_fill_outcomes_completes_old_open_trade(tmp_path):
    signal_date = "2026-03-01"
    horizon = 20
    target_ts = pd.Timestamp(signal_date).normalize() + BDay(horizon)
    dates = []
    d = pd.Timestamp(signal_date)
    while len(dates) < 30:
        if d.weekday() < 5:
            dates.append(d.strftime("%Y-%m-%d"))
        d += pd.Timedelta(days=1)

    snaps = {ds: _make_snap(ds, "SPY", 500.0) for ds in dates}

    def fake_load(date_str: str):
        return snaps.get(date_str)

    row = {
        "date": signal_date,
        "ticker": "SPY",
        "signal": "HOLD",
        "entry_price": 500.0,
        "horizon_trading_days": horizon,
        "execution_mode": "close_to_close",
    }

    with patch.object(PaperTradeLogger, "_list_eod_dates", return_value=dates), patch.object(
        PaperTradeLogger, "_load_snapshot", side_effect=fake_load
    ), patch.object(PaperTradeLogger, "_read_all", return_value=[row]), patch.object(
        PaperTradeLogger, "_write_all", lambda _self, _rows: None
    ):
        pt = PaperTradeLogger(data_root=tmp_path, execution_cfg={"mode": "close_to_close"})
        fill = pt.fill_outcomes()
        assert fill["updated"] == 1
        assert row.get("outcome") in ("HIT", "MISS", "STOP_HIT")
        assert row.get("next_date") is not None
        assert pd.Timestamp(str(row["next_date"])).normalize() >= target_ts.normalize()
