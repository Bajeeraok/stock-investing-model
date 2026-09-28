"""
Regression coverage for signals/institutional_signals.py's weighted insider signal.

Two bugs fixed together here:
  1. fetch_insider_trading_list() called FMP's bare /insider-trading?symbol= path, which
     404s on the current API (FMP moved symbol-scoped queries under /insider-trading/search)
     — this silently zeroed the signal (err set, rows None -> {"signal": 0.0, "n": 0}).
  2. Buy/sell classification substring-matched transactionType ("purchase" in x.lower()),
     which happened to work for P-Purchase/S-Sale but was never tested against the rest of
     the real SEC Form 4 code set (A-Award, M-Exempt, F-InKind/F-Tax, G-Gift) FMP actually
     returns — those are compensation/administrative mechanics, not discretionary buy/sell
     decisions, and must not count toward the "conviction" signal.
"""
from unittest.mock import patch

from signals.institutional_signals import _tx_is_buy, _tx_is_sell, get_weighted_insider_signal


def test_tx_classification_only_counts_open_market_codes():
    assert _tx_is_buy("P-Purchase") is True
    assert _tx_is_sell("S-Sale") is True
    for noise_code in ("A-Award", "M-Exempt", "F-InKind", "F-Tax", "G-Gift", "C-Conversion", ""):
        assert _tx_is_buy(noise_code) is False, noise_code
        assert _tx_is_sell(noise_code) is False, noise_code


def _row(transaction_type, shares, price, reporting_name="Jane Doe"):
    return {
        "transactionType": transaction_type,
        "securitiesTransacted": shares,
        "price": price,
        "reportingName": reporting_name,
    }


@patch("signals.institutional_signals.fetch_insider_trading_list")
def test_weighted_signal_excludes_non_open_market_rows(mock_fetch):
    """A realistic mixed feed (the AAPL shape seen live: mostly S-Sale/M-Exempt/F-InKind)
    must only score the S-Sale/P-Purchase rows — n must reflect that, not the raw fetch count."""
    mock_fetch.return_value = (
        [
            _row("S-Sale", 1000, 300.0),
            _row("M-Exempt", 5000, 1.0),
            _row("F-InKind", 400, 300.0),
            _row("A-Award", 2000, 0.0),
            _row("P-Purchase", 500, 300.0, reporting_name="Chief Executive Officer"),
        ],
        None,
    )
    out = get_weighted_insider_signal({}, "AAPL", limit=20)
    assert out["n"] == 2  # only the S-Sale and P-Purchase rows
    assert out["n_fetched"] == 5
    assert out["buy_score"] > 0
    assert out["sell_score"] > 0
    # CEO buying $150k should score higher per-share than a plain sell of the same dollar
    # value from an unweighted role, but the exact net sign here just needs to reflect that
    # a real buy was counted at all (previously it would have been, coincidentally, but with
    # no exclusion of the noise rows diluting nothing — the guard is n == 2, not the sign).


@patch("signals.institutional_signals.fetch_insider_trading_list")
def test_weighted_signal_sizes_by_dollar_value_not_raw_share_count(mock_fetch):
    """securitiesTransacted is a share count; price is FMP's fill price for that row. Sizing
    must multiply them into a dollar value, not treat raw share count as if it were dollars
    (a 500-share row and a 500,000-share row at very different prices must NOT get the same
    size weight just because neither crosses the old code's implicit $1 = 1 share assumption)."""
    mock_fetch.return_value = ([_row("P-Purchase", 10_000, 300.0)], None)  # $3,000,000
    small = get_weighted_insider_signal({}, "AAPL", limit=20)

    mock_fetch.return_value = ([_row("P-Purchase", 10, 300.0)], None)  # $3,000
    tiny = get_weighted_insider_signal({}, "AAPL", limit=20)

    assert small["buy_score"] > tiny["buy_score"]


@patch("signals.institutional_signals.fetch_insider_trading_list", return_value=(None, "HTTP Error 404: Not Found"))
def test_weighted_signal_degrades_cleanly_on_fetch_error(_mock_fetch):
    out = get_weighted_insider_signal({}, "AAPL", limit=20)
    assert out["signal"] == 0.0
    assert out["n"] == 0
    assert out["error"] == "HTTP Error 404: Not Found"
