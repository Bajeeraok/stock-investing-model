"""
Regression coverage for signals/fmp_client.py's fetch_revenue_concentration() — reduces
FMP's /stable/revenue-{product,geographic}-segmentation (an arbitrary {segment_name: revenue}
dict per fiscal year, no fixed schema across companies) to a single top-segment concentration
fact, since the raw breakdown would need per-company UI work to render sensibly.
"""
from unittest.mock import patch

from signals.fmp_client import fetch_revenue_concentration


def _row(fiscal_year, data):
    return {"symbol": "AAPL", "fiscalYear": fiscal_year, "period": "FY", "data": data}


@patch("signals.fmp_client._request")
def test_computes_top_segment_pct_of_total(mock_request):
    mock_request.return_value = (
        [_row(2025, {"iPhone": 209586000000, "Service": 109158000000, "Mac": 33708000000})],
        None,
    )
    out, err = fetch_revenue_concentration({"data": {"fmp_api_key": "x"}}, "AAPL", kind="product")
    assert err is None
    assert out["top_segment"] == "iPhone"
    total = 209586000000 + 109158000000 + 33708000000
    assert out["top_pct"] == round(209586000000 / total * 100.0, 1)
    assert out["fiscal_year"] == 2025
    assert out["segment_count"] == 3


@patch("signals.fmp_client._request", return_value=([], None))
def test_empty_list_yields_no_data_error(_mock_request):
    out, err = fetch_revenue_concentration({"data": {"fmp_api_key": "x"}}, "AAPL", kind="product")
    assert out is None
    assert "No segment data" in err


@patch("signals.fmp_client._request")
def test_row_with_empty_data_dict_yields_no_data_error(mock_request):
    mock_request.return_value = ([_row(2025, {})], None)
    out, err = fetch_revenue_concentration({"data": {"fmp_api_key": "x"}}, "AAPL", kind="geographic")
    assert out is None
    assert "No segment data" in err


def test_invalid_kind_raises():
    try:
        fetch_revenue_concentration({"data": {"fmp_api_key": "x"}}, "AAPL", kind="bogus")
        assert False, "expected ValueError"
    except ValueError:
        pass


@patch("signals.fmp_client._request")
def test_non_numeric_segment_values_are_ignored(mock_request):
    """FMP occasionally mixes in a non-numeric field; it must not crash the total/sum."""
    mock_request.return_value = (
        [_row(2025, {"iPhone": 200_000_000_000, "Note": "restated", "Mac": 50_000_000_000})],
        None,
    )
    out, err = fetch_revenue_concentration({"data": {"fmp_api_key": "x"}}, "AAPL", kind="product")
    assert err is None
    assert out["segment_count"] == 2
    assert out["top_segment"] == "iPhone"
