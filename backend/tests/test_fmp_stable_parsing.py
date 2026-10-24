"""FMP /stable field names parse (they used to leave eps_fwd / cons_low / cons_high null)."""
from datetime import date, timedelta
from unittest.mock import patch

from signals import fmp_client as f


def test_price_target_consensus_normalized_and_etf_skipped():
    raw = {"symbol": "AVGO", "targetHigh": 650, "targetLow": 380, "targetMedian": 509.61, "targetConsensus": 512}
    with patch.object(f, "get_api_key", return_value="k"), patch.object(f, "_request", return_value=([raw], None)):
        out, err = f.fetch_price_target_consensus({}, "AVGO")
    assert err is None and out["low"] == 380 and out["high"] == 650 and out["median"] == 509.61
    out, err = f.fetch_price_target_consensus({}, "XLF")
    assert out is None and "ETF" in err


def test_analyst_estimates_stable_names_and_next_fiscal_year():
    nxt = (date.today() + timedelta(days=200)).isoformat()
    far = (date.today() + timedelta(days=900)).isoformat()
    rows = [
        {"date": far, "epsAvg": 30.0, "epsHigh": 34.0, "epsLow": 26.0, "numAnalystsEps": 20},
        {"date": nxt, "epsAvg": 12.0, "epsHigh": 13.0, "epsLow": 11.0, "numAnalystsEps": 30},
    ]
    with patch.object(f, "get_api_key", return_value="k"), patch.object(f, "_request", return_value=(rows, None)):
        out, err = f.fetch_analyst_estimates({}, "MSFT")
    assert err is None and out["eps_fwd"] == 12.0 and out["analyst_count"] == 30
    assert out["eps_dispersion"] == round(2.0 / 12.0, 4)
