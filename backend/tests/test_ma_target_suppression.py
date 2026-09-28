"""
Regression coverage for M&A-target fair-value suppression — wiring the previously-dead
fv_router.route_fair_value(is_acquisition_target=...) path (never populated by any caller
before this) to a real signal: FMP's /stable/mergers-acquisitions-latest.

Design boundary (deliberate, discussed before implementing): this feed only ever sets
is_acquisition_target, which fv_router.py already handles as a full suppression (fair value
falls back to street consensus) — it must NOT feed fair_value_estimator.py's point-estimate
math directly. A named M&A target's price trades to a deal spread, not to a PE/EPS-implied
value, which is exactly the class of problem fv_router already solves for banks/REITs/biotech.
"""
from unittest.mock import patch

from signals.cache import cached_ma_targets
from signals.fv_router import FvRoute


def _ma_row(target, acquirer, acquirer_name, date):
    return {
        "symbol": acquirer,
        "companyName": acquirer_name,
        "targetedSymbol": target,
        "transactionDate": date,
    }


def test_cached_ma_targets_builds_lookup_keyed_by_target():
    rows = [
        _ma_row("CSR", "IRT", "INDEPENDENCE REALTY TRUST, INC.", "2026-09-23"),
        _ma_row("LCII", "PATK", "PATRICK INDUSTRIES INC", "2026-09-23"),
    ]
    out = cached_ma_targets(lambda: rows)
    assert out["CSR"]["acquirer"] == "IRT"
    assert out["CSR"]["acquirer_name"] == "INDEPENDENCE REALTY TRUST, INC."
    assert "LCII" in out
    assert "IRT" not in out  # acquirer, not target — must not be keyed


def test_cached_ma_targets_keeps_most_recent_when_target_appears_twice():
    """A target can appear in more than one filing row (amendments); the most recent
    transactionDate must win, not whichever row happened to iterate last."""
    rows = [
        _ma_row("CHMI", "MITT", "AG Mortgage Investment Trust, Inc.", "2026-01-01"),
        _ma_row("CHMI", "MITT", "AG Mortgage Investment Trust, Inc.", "2026-09-15"),
    ]
    out = cached_ma_targets(lambda: rows)
    assert out["CHMI"]["transaction_date"] == "2026-09-15"


def test_cached_ma_targets_skips_rows_without_a_target_symbol():
    rows = [{"symbol": "IRT", "companyName": "x", "targetedSymbol": "", "transactionDate": "2026-09-23"}]
    out = cached_ma_targets(lambda: rows)
    assert out == {}


def test_cached_ma_targets_empty_on_non_list_input():
    assert cached_ma_targets(lambda: None) == {}


@patch("signals.fetcher.build_fundamentals_info")
@patch("signals.fv_eps_history.fetch_quarterly_income")
@patch("signals.cache.cached_ma_targets")
def test_compute_fair_value_suppresses_named_ma_target(mock_ma_targets, mock_qi, mock_fund):
    """A ticker present in the M&A target lookup must route through fv_router with
    is_acquisition_target=True — fair value suppressed, street-anchored, deal noted."""
    from signals.fair_value_pipeline import compute_fair_value

    mock_ma_targets.return_value = {
        "CSR": {"acquirer": "IRT", "acquirer_name": "Independence Realty Trust", "transaction_date": "2026-09-23"},
    }
    mock_qi.return_value = None
    mock_fund.return_value = (
        {"trailingEps": 1.0, "forwardEps": 1.1, "sector": "Real Estate", "targetMeanPrice": 20.0},
        {"peRatioTTM": 20.0},
    )

    result = compute_fair_value({}, "CSR", 20.0, consensus_median=20.0)

    assert result.fair_value == 20.0
    assert result.fv_result is not None
    assert result.fv_result.fv_suppressed is True
    assert "ACQUISITION TARGET" in result.fv_result.fv_suppressed_reason
    assert any("Independence Realty Trust" in n for n in (result.fv_result.notes or []))


@patch("signals.fetcher.build_fundamentals_info")
@patch("signals.fv_eps_history.fetch_quarterly_income")
@patch("signals.cache.cached_ma_targets")
def test_compute_fair_value_unaffected_when_not_an_ma_target(mock_ma_targets, mock_qi, mock_fund):
    """A ticker absent from the lookup must route normally — is_acquisition_target=False,
    confirming this wiring can't accidentally suppress FV for unrelated tickers."""
    from signals.fair_value_pipeline import compute_fair_value
    from signals.fv_router import FvRoute as _FvRoute

    mock_ma_targets.return_value = {
        "CSR": {"acquirer": "IRT", "acquirer_name": "Independence Realty Trust", "transaction_date": "2026-09-23"},
    }
    mock_qi.return_value = None
    mock_fund.return_value = (
        {
            "trailingEps": 3.27, "forwardEps": 3.60, "forwardPE": 30.0,
            "revenueGrowth": 0.14, "earningsGrowth": 0.16, "profitMargins": 0.22,
            "debtToEquity": 0.5, "targetMeanPrice": 200.0, "sector": "Technology",
            "freeCashflow": None, "sharesOutstanding": None,
        },
        {"peRatioTTM": 30.0},
    )

    with patch("signals.fv_router.route_fair_value", return_value=_FvRoute()) as mock_route:
        result = compute_fair_value({}, "ACME", 100.0, consensus_median=200.0)

    assert mock_route.call_args.kwargs["is_acquisition_target"] is False
    assert result.fv_result is not None
    assert result.fv_result.fv_suppressed is False
