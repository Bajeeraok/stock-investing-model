"""Tests for build_ticker_track_record — per-ticker signal accuracy filtered from an
already-computed forward-tracking records array (no I/O, no snapshot loading)."""

from __future__ import annotations

from signals.forward_tracking_metrics import (
    build_ticker_track_record,
    build_ticker_track_record_all_horizons,
)


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


def test_all_horizons_surfaces_early_read_when_20d_has_no_current_observations():
    """The actual motivating case: a just-launched model_version has zero resolved 20d
    outcomes (20 trading days haven't elapsed yet) but DOES already have resolved 1d ones —
    those must show up under by_horizon so the UI can offer an early read instead of nothing."""
    records = [
        _rec("AMZN", "2026.09.4", 1.5, horizon=1),
        _rec("AMZN", "2026.09.4", -0.5, horizon=1),
        _rec("AMZN", "2026.09.3", 3.0, horizon=20),  # legacy-side 20d history exists
    ]
    out = build_ticker_track_record_all_horizons(records, "AMZN", current_model_version="2026.09.4")
    assert out["available"] is True
    assert out["by_horizon"][1]["current"]["n_observations"] == 2
    assert out["by_horizon"][20]["current"] is None
    assert out["by_horizon"][20]["legacy"]["n_observations"] == 1


def test_all_horizons_unavailable_when_ticker_has_no_records_at_all():
    out = build_ticker_track_record_all_horizons([], "AMZN", current_model_version="2026.09.4")
    assert out["available"] is False
    assert all(v["current"] is None and v["legacy"] is None for v in out["by_horizon"].values())


def test_all_horizons_respects_custom_horizon_list():
    records = [_rec("AMZN", "v1", 1.0, horizon=5)]
    out = build_ticker_track_record_all_horizons(
        records, "AMZN", current_model_version="v1", horizons=(5,)
    )
    assert list(out["by_horizon"].keys()) == [5]
    assert out["by_horizon"][5]["current"]["n_observations"] == 1
