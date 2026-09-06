"""Tests for build_ticker_track_record — per-ticker signal accuracy filtered from an
already-computed forward-tracking records array (no I/O, no snapshot loading)."""

from __future__ import annotations

from signals.forward_tracking_metrics import build_ticker_track_record


def _rec(ticker, version, ret, horizon=20):
    return {
        "ticker": ticker,
        "horizon_days": horizon,
        "model_version": version,
        "actual_return_pct": ret,
        "forward_status": "complete",
        "data_quality": "ok",
    }


def test_unavailable_when_no_records_for_ticker():
    out = build_ticker_track_record([_rec("NVDA", "v1", 1.0)], "AMZN")
    assert out == {"available": False, "ticker": "AMZN", "horizon_days": 20}


def test_splits_current_vs_legacy_by_version():
    records = [
        _rec("AMZN", "2025.01.1", 3.0),
        _rec("AMZN", "2025.01.1", -2.0),
        _rec("AMZN", "2026.09.1", 5.0),
    ]
    out = build_ticker_track_record(records, "AMZN", current_model_version="2026.09.1")
    assert out["available"] is True
    assert out["current"]["n_observations"] == 1
    assert out["current"]["win_rate_pct"] == 100.0
    assert out["legacy"]["n_observations"] == 2
    assert out["legacy"]["win_rate_pct"] == 50.0


def test_ticker_match_is_case_insensitive():
    out = build_ticker_track_record([_rec("AMZN", "v1", 1.0)], "amzn", current_model_version="v1")
    assert out["available"] is True
    assert out["current"]["n_observations"] == 1


def test_filters_by_horizon_days():
    records = [_rec("AMZN", "v1", 1.0, horizon=5), _rec("AMZN", "v1", 2.0, horizon=20)]
    out = build_ticker_track_record(records, "AMZN", current_model_version="v1", horizon_days=20)
    assert out["current"]["n_observations"] == 1


def test_no_legacy_key_populated_when_all_records_are_current():
    records = [_rec("AMZN", "v1", 1.0)]
    out = build_ticker_track_record(records, "AMZN", current_model_version="v1")
    assert out["current"]["n_observations"] == 1
    assert out["legacy"] is None


def test_other_tickers_records_excluded_from_result():
    records = [_rec("AMZN", "v1", 1.0), _rec("NVDA", "v1", 9.0)]
    out = build_ticker_track_record(records, "AMZN", current_model_version="v1")
    assert out["current"]["n_observations"] == 1
