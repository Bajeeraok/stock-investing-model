"""
Regression coverage for GET /api/ticker/{ticker}/track-record's cache source.

Bug fixed: the route read only the dedicated per-key slice (get_analysis_slice(
"forward_tracking")), which has its own independent 6h TTL — confirmed live that this key
can be empty/expired while GET /api/dashboard/analysis-bundle still serves full
forward_tracking data (500 records) via its dedicated-bundle/dashboard-cache fallback tiers.
The route now reuses compute_analysis_bundle(allow_heavy=False), the same cache-only
fallback chain the Analysis tab already relies on, instead of only trying the first tier.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from api.routers.dashboard import get_ticker_track_record


def _run(ticker: str):
    return asyncio.run(get_ticker_track_record(ticker))


@patch("api.routers.dashboard.compute_analysis_bundle", return_value=None)
def test_unavailable_when_no_bundle_cached_anywhere(_mock):
    out = _run("AAPL")
    assert out == {"available": False, "ticker": "AAPL", "reason": "forward-tracking data not cached yet"}


@patch("api.routers.dashboard.compute_analysis_bundle")
def test_populates_from_bundle_even_when_dedicated_slice_is_stale(mock_bundle):
    """The exact bug scenario: the dedicated forward_tracking slice is gone, but
    compute_analysis_bundle's own fallback chain (dedicated bundle / dashboard-cache) still
    has the data — the route must use it, not report unavailable."""
    mock_bundle.return_value = {
        "forward_tracking": {
            "records": [
                {
                    "ticker": "AAPL",
                    "horizon_days": 20,
                    "model_version": "2026.09.4",
                    "actual_return_pct": 3.0,
                    "forward_status": "complete",
                },
                {
                    "ticker": "AAPL",
                    "horizon_days": 20,
                    "model_version": "2026.09.3",
                    "actual_return_pct": -1.0,
                    "forward_status": "complete",
                },
            ]
        }
    }
    with patch("signals.model_version.MODEL_VERSION", "2026.09.4"):
        out = _run("AAPL")
    assert out["available"] is True
    assert out["current"]["n_observations"] == 1
    assert out["legacy"]["n_observations"] == 1
    assert "by_horizon" in out
    assert out["by_horizon"][20]["current"]["n_observations"] == 1


@patch("api.routers.dashboard.compute_analysis_bundle", side_effect=RuntimeError("redis down"))
def test_degrades_cleanly_when_compute_raises(_mock):
    out = _run("AAPL")
    assert out == {"available": False, "ticker": "AAPL", "reason": "forward-tracking data not cached yet"}


@patch("api.routers.dashboard.compute_analysis_bundle", return_value={"forward_tracking": None})
def test_unavailable_when_forward_tracking_key_present_but_not_a_dict(_mock):
    out = _run("AAPL")
    assert out["available"] is False
