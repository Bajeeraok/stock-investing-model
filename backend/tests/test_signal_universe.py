"""Signal universe = watchlist ∪ portfolio holdings."""
from __future__ import annotations

from config_loader import get_signal_universe, portfolio_tickers_from_config


def test_portfolio_tickers_from_multi_account():
    config = {
        "portfolios": {
            "Taxable": [{"ticker": "nvda", "quantity": 10}],
            "IRA": [{"ticker": "AAPL", "quantity": 5}],
        }
    }
    assert portfolio_tickers_from_config(config) == ["NVDA", "AAPL"]


def test_signal_universe_appends_portfolio_only():
    config = {
        "watchlist": ["SPY", "QQQ", "AAPL"],
        "portfolios": {
            "Default": [
                {"ticker": "AAPL", "quantity": 1},
                {"ticker": "SNDK", "quantity": 2},
            ],
        },
    }
    assert get_signal_universe(config) == ["SPY", "QQQ", "AAPL", "SNDK"]


def test_signal_universe_watchlist_order_preserved():
    config = {
        "watchlist": ["GLD", "SPY"],
        "portfolio": [{"ticker": "MSFT", "quantity": 1}],
    }
    assert get_signal_universe(config) == ["GLD", "SPY", "MSFT"]
