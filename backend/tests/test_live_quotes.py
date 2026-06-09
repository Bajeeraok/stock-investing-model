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
