"""
Regression coverage for PaperTradeLogger.get_trades_for_ticker() and
build_ticker_trade_table() — the per-ticker daily signal/fill/outcome/PnL table requested
for the ticker-detail "Signal track record" card (what-we-said-vs-what-happened, but as
actual rows instead of only an aggregate win rate).
"""
from __future__ import annotations

from signals.paper_trade_logger import (
    PaperTradeLogger,
    _result_to_paper_record,
    build_ticker_trade_table,
)


def _rec(ticker, day, *, outcome=None, ret=None, entry=100.0, effective=None, target=110.0, stop=95.0):
    rec = _result_to_paper_record(
        {
            "ticker": ticker,
            "close": entry,
            "signal": "BUY",
            "st_band": {"low": stop, "high": target},
            "entry_mode": "full_go",
        },
        f"2027-01-{day:02d}",
    )
    assert rec is not None
    if effective is not None:
        rec["effective_entry_price"] = str(effective)
    if outcome:
        rec["outcome"] = outcome
        rec["hit_target"] = "1" if outcome == "HIT" else "0"
        rec["hit_stop"] = "1" if outcome == "STOP_HIT" else "0"
        rec["return_pct"] = str(ret)
        rec["actual_price"] = str(entry * (1 + (ret or 0) / 100.0))
        rec["next_date"] = f"2027-02-{day:02d}"
    else:
        rec["rolling_return_pct"] = str(ret) if ret is not None else ""
    return rec


def test_get_trades_for_ticker_filters_and_sorts_newest_first(tmp_path):
    logger = PaperTradeLogger(data_root=tmp_path)
    rows = [
        _rec("AAPL", 1, outcome="HIT", ret=3.0),
        _rec("MSFT", 2, outcome="HIT", ret=1.0),
        _rec("AAPL", 3, outcome="MISS", ret=-2.0),
    ]
    logger._write_all(rows)

    out = logger.get_trades_for_ticker("aapl")  # case-insensitive
    assert [r["date"] for r in out] == ["2027-01-03", "2027-01-01"]


def test_get_trades_for_ticker_respects_limit(tmp_path):
    logger = PaperTradeLogger(data_root=tmp_path)
    rows = [_rec("AAPL", d, outcome="HIT", ret=1.0) for d in range(1, 6)]
    logger._write_all(rows)
    out = logger.get_trades_for_ticker("AAPL", limit=2)
    assert len(out) == 2


def test_build_ticker_trade_table_resolved_row_shape():
    logger = PaperTradeLogger()
    row = _rec("AAPL", 1, outcome="HIT", ret=5.0, entry=100.0, effective=100.5, target=110.0, stop=95.0)
    row = dict(row)
    logger._coerce_numeric_fields(row)
    out = build_ticker_trade_table([row])
    assert len(out) == 1
    r = out[0]
    assert r["model_price"] == 100.0
    assert r["fill_price"] == 100.5
    assert r["target"] == 110.0
    assert r["stop"] == 95.0
    assert r["outcome"] == "HIT"
    assert r["win"] is True
    assert r["status"] == "resolved"
    assert r["return_pct"] == 5.0
    assert r["unrealized_return_pct"] is None


def test_build_ticker_trade_table_stop_hit_is_a_loss():
    logger = PaperTradeLogger()
    row = dict(_rec("AAPL", 1, outcome="STOP_HIT", ret=-4.5))
    logger._coerce_numeric_fields(row)
    out = build_ticker_trade_table([row])
    assert out[0]["win"] is False
    assert out[0]["outcome"] == "STOP_HIT"


def test_build_ticker_trade_table_pending_row_shows_unrealized_not_blank():
    """A trade with no outcome yet (still open) must surface the current paper mark
    (rolling_return_pct) rather than leaving the row with nothing useful at all."""
    logger = PaperTradeLogger()
    row = dict(_rec("AAPL", 1, ret=1.8))  # no outcome -> pending
    row["rolling_return_pct"] = "1.8"
    logger._coerce_numeric_fields(row)
    out = build_ticker_trade_table([row])
    r = out[0]
    assert r["status"] == "pending"
    assert r["outcome"] is None
    assert r["win"] is None
    assert r["return_pct"] is None
    assert r["unrealized_return_pct"] == 1.8


def test_build_ticker_trade_table_fill_price_falls_back_to_model_price_when_no_effective_price():
    logger = PaperTradeLogger()
    row = dict(_rec("AAPL", 1, outcome="HIT", ret=1.0, entry=100.0, effective=None))
    logger._coerce_numeric_fields(row)
    out = build_ticker_trade_table([row])
    assert out[0]["fill_price"] == 100.0
