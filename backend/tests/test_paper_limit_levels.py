from signals.paper_trade_logger import build_ticker_trade_table


def test_trade_table_hides_levels_inverted_vs_fill():
    rows = [{"date": "2026-09-11", "ticker": "AAPL", "signal": "STARTER:BUY", "entry_price": "317.07",
             "target_1": "353.61", "hard_stop": "329.4"}]
    t = build_ticker_trade_table(rows)[0]
    assert t["stop"] is None and t["target"] == 353.61
    rows[0].update(target_1="300", hard_stop="310")
    t = build_ticker_trade_table(rows)[0]
    assert t["target"] is None and t["stop"] == 310.0
