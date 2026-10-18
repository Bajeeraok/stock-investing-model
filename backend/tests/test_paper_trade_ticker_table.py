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


def test_get_trades_for_ticker_not_truncated_by_other_tickers_volume(tmp_path, monkeypatch):
    """Regression for the confirmed live bug: get_trades_for_ticker used to call
    get_recent(limit=10_000), which caps to the 10,000 most recent rows ACROSS ALL TICKERS
    before filtering by ticker — with enough other-ticker volume, a thinly-traded ticker's
    older rows never made it past that cap. This ticker's rows must come back regardless of
    how get_recent() itself behaves — get_trades_for_ticker no longer routes through it at all."""
    logger = PaperTradeLogger(data_root=tmp_path)
    rows = [_rec("NVDA", 1, outcome="HIT", ret=2.0)]
    logger._write_all(rows)

    def _recent_returns_nothing(limit=50):
        return []  # simulates "this ticker's rows fell outside get_recent()'s cap"

    monkeypatch.setattr(logger, "get_recent", _recent_returns_nothing)
    out = logger.get_trades_for_ticker("NVDA")
    assert len(out) == 1
    assert out[0]["date"] == "2027-01-01"


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


def test_build_ticker_trade_table_hit_target_wins_even_when_outcome_says_stop_hit():
    """The exact confirmed-live bug: a volatile day can dip below the stop intraday (hit_stop=1,
    so fill_outcomes' outcome string becomes STOP_HIT — it checks hit_stop before hit_target)
    and still close well above the target (hit_target=1, return_pct strongly positive). The
    app's own aggregate win-rate (_stats_for_completed) decides win/loss from hit_target alone
    and never reads hit_stop or the outcome string — this table must agree with that, not
    silently use a different, stricter definition that can show "LOSS" next to +25%."""
    logger = PaperTradeLogger()
    row = dict(_rec("NVDA", 1, outcome="STOP_HIT", ret=25.0))
    row["hit_target"] = "1"  # closed above target that same day
    row["hit_stop"] = "1"    # intraday low also dipped below stop that same day
    logger._coerce_numeric_fields(row)
    out = build_ticker_trade_table([row])
    r = out[0]
    assert r["win"] is True
    assert r["return_pct"] == 25.0
    assert r["outcome"] == "STOP_HIT"  # kept, not hidden — it's real context
    assert r["volatile_note"] == "stop also touched intraday that day"


def test_build_ticker_trade_table_falls_back_to_outcome_string_when_hit_target_blank():
    """Older rows without a hit_target field at all (pre-dating that column, or a different
    track's schema) must still resolve a win/loss from the outcome string — the fallback
    _stats_for_completed() itself uses — rather than showing "pending" forever."""
    logger = PaperTradeLogger()
    row = dict(_rec("AAPL", 1, outcome="HIT", ret=3.0))
    row["hit_target"] = ""
    logger._coerce_numeric_fields(row)
    out = build_ticker_trade_table([row])
    assert out[0]["win"] is True


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


def test_build_ticker_trade_table_pending_row_uses_mark_vs_fill_and_mark_price():
    """Open rows show the latest marked close as outcome price, and P&L vs the fill
    (mtm_return_pct) — not the day-over-day rolling move, which is identical on every row."""
    logger = PaperTradeLogger()
    row = dict(_rec("AAPL", 1, ret=1.8))
    row["rolling_return_pct"] = "0.7"
    row["mtm_return_pct"] = "7.9"
    row["mtm_price"] = "1134.38"
    row["mtm_date"] = "2026-10-16"
    logger._coerce_numeric_fields(row)
    r = build_ticker_trade_table([row])[0]
    assert r["status"] == "pending"
    assert r["unrealized_return_pct"] == 7.9
    assert r["outcome_price"] == 1134.38
    assert r["mark_date"] == "2026-10-16"


def test_build_ticker_trade_table_fill_price_falls_back_to_model_price_when_no_effective_price():
    logger = PaperTradeLogger()
    row = dict(_rec("AAPL", 1, outcome="HIT", ret=1.0, entry=100.0, effective=None))
    logger._coerce_numeric_fields(row)
    out = build_ticker_trade_table([row])
    assert out[0]["fill_price"] == 100.0
