"""Live quote overlay on dashboard signal rows."""
from signals.live_quotes import apply_live_quotes_to_results, overlay_live_price_fields


def test_overlay_live_price_updates_close_and_change_pct():
    row = {"ticker": "NVDA", "close": 100.0}
    overlay_live_price_fields(row, 105.5, source="fmp_batch")
    assert row["close"] == 105.5
    assert row["ohlcv_close"] == 100.0
    assert row["live_price"] == 105.5
    assert row["change_pct"] == 5.5


def test_apply_live_quotes_skips_errors():
    rows = [{"ticker": "X", "error": "fail", "close": 1.0}, {"ticker": "AAPL", "close": 200.0}]
    apply_live_quotes_to_results(rows, {"AAPL": 201.0}, source="yfinance_latest")
    assert rows[0]["close"] == 1.0
    assert rows[1]["close"] == 201.0


def _detail_move(hist_dates, now, ticker="MSFT"):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from signals.live_quotes import _daily_move_vs_prior_session

    closes = [100.0, 110.0, 120.0][-len(hist_dates):]
    d = {"ticker": ticker, "price_history": [{"date": x, "close": c} for x, c in zip(hist_dates, closes)]}
    return _daily_move_vs_prior_session(d, 132.0, datetime(*now, tzinfo=ZoneInfo("America/New_York")))


def test_daily_move_uses_prior_session_close():
    # Build ends on the previous session (Wed Nov 4): move is vs that close.
    assert _detail_move(["2026-11-03", "2026-11-04"], (2026, 11, 5, 12, 0)) == 10.0
    # Build already has today's bar (close 120): move is vs the bar before it (110).
    assert _detail_move(["2026-11-04", "2026-11-05"], (2026, 11, 5, 17, 0)) == 20.0
    # Saturday: the live quote is Friday's session, measured from Thursday.
    assert _detail_move(["2026-11-05", "2026-11-06"], (2026, 11, 7, 10, 0)) == 20.0
    # Pre-market: still the previous session's move.
    assert _detail_move(["2026-11-03", "2026-11-04"], (2026, 11, 5, 8, 0)) == 20.0


def test_daily_move_none_when_build_is_stale():
    # Build ends Mon Nov 3 but today is Thu Nov 5: Wednesday's close is unknown.
    assert _detail_move(["2026-11-02", "2026-11-03"], (2026, 11, 5, 12, 0)) is None


def test_daily_move_crypto_uses_calendar_days():
    assert _detail_move(["2026-11-06", "2026-11-07"], (2026, 11, 8, 12, 0), "BTC-USD") == 10.0
