"""DIY backtest universe helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from signals.backtest_universe import (
    apply_universe_config,
    filter_tickers_by_membership_at_date,
    load_membership_ranges_csv,
    ticker_in_universe,
)


def test_membership_csv_in_out(tmp_path: Path):
    p = tmp_path / "m.csv"
    p.write_text(
        "ticker,start_date,end_date\n"
        "AAPL,2015-06-01,\n"
        "MSFT,2010-01-01,2019-12-31\n",
        encoding="utf-8",
    )
    df = load_membership_ranges_csv(p)
    assert ticker_in_universe("AAPL", pd.Timestamp("2020-01-01"), df)
    assert not ticker_in_universe("MSFT", pd.Timestamp("2020-01-01"), df)
    assert ticker_in_universe("MSFT", pd.Timestamp("2015-01-01"), df)
    assert filter_tickers_by_membership_at_date(["AAPL", "MSFT", "ZZZ"], pd.Timestamp("2016-01-01"), df) == [
        "AAPL",
        "MSFT",
    ]


def test_apply_full_history_drops_short_series():
    def fake_fetch(ticker: str, period: str):
        if ticker == "LONG":
            return pd.Series(range(600), index=pd.date_range("2015-01-01", periods=600, freq="B"))
        return pd.Series(range(50), index=pd.date_range("2024-01-01", periods=50, freq="B"))

    cfg = {
        "data": {"period": "5y"},
        "backtest": {"universe": {"mode": "full_history", "full_history_min_bars": 500}},
    }
    out, meta = apply_universe_config(cfg, ["LONG", "SHORT"], backend_root=Path("."), fetch_close=fake_fetch)
    assert out == ["LONG"]
    assert "SHORT" in meta["dropped"]


def test_apply_none_passes_through():
    cfg = {"backtest": {"universe": {"mode": "none"}}}
    out, meta = apply_universe_config(cfg, ["SPY", "QQQ"], backend_root=Path("."))
    assert out == ["SPY", "QQQ"]
    assert meta["mode"] == "none"
