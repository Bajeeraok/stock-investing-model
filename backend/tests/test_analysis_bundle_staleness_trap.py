"""
Regression coverage for the "self-perpetuating stale-cache trap" in compute_analysis_bundle
(api/routers/dashboard.py).

Root cause (confirmed live on prod): forward_tracking sat 8 weeks stale (EOD through
2026-08-02 while the live EOD snapshot index already had 2026-09-25) because every one of
compute_analysis_bundle's three cache-hit tiers checked only *presence*, never *freshness* —
whichever tier hit first returned immediately, including when the caller was
_ensure_analysis_background_compute() itself trying to force a fresh recompute. Once any tier
had cached a value even once, the real heavy compute (which correctly re-lists EOD dates) could
never run again short of the whole cache going fully cold.

Two-part fix tested here:
  1. _forward_tracking_staleness_days() compares a bundle's forward_tracking.meta.eod_date_last
     against the live EOD snapshot index and flags anything beyond _FORWARD_TRACKING_STALE_DAYS.
  2. compute_analysis_bundle(force=True) — used only by _ensure_analysis_background_compute() —
     skips all three cache-hit tiers outright, so a deliberate "give me a fresh one" call can't
     be swallowed by its own stale cache the way it always used to be.
"""
from __future__ import annotations

from unittest.mock import patch

from api.routers.dashboard import (
    _FORWARD_TRACKING_STALE_DAYS,
    _forward_tracking_staleness_days,
    compute_analysis_bundle,
)


def _bundle(eod_date_last: str) -> dict:
    return {"forward_tracking": {"meta": {"eod_date_last": eod_date_last}}}


@patch("signals.cache.build_eod_snapshot_index", return_value=[{"date": "2026-09-25"}])
def test_staleness_days_computed_against_live_index(_mock_index):
    days = _forward_tracking_staleness_days(_bundle("2026-08-02"))
    assert days == 54  # 2026-08-02 -> 2026-09-25


@patch("signals.cache.build_eod_snapshot_index", return_value=[{"date": "2026-09-25"}])
def test_staleness_days_zero_when_current(_mock_index):
    assert _forward_tracking_staleness_days(_bundle("2026-09-25")) == 0


def test_staleness_none_when_no_meta_date():
    assert _forward_tracking_staleness_days({"forward_tracking": {}}) is None


def test_staleness_none_when_bundle_not_a_dict():
    assert _forward_tracking_staleness_days(None) is None


@patch("signals.cache.build_eod_snapshot_index", side_effect=RuntimeError("redis down"))
def test_staleness_degrades_to_none_on_index_failure(_mock_index):
    assert _forward_tracking_staleness_days(_bundle("2026-08-02")) is None


@patch("api.routers.dashboard._forward_tracking_staleness_days", return_value=0)
@patch("signals.cache.assemble_analysis_slices")
def test_fresh_assembled_cache_hit_does_not_trigger_background_compute(mock_assembled, _mock_stale):
    mock_assembled.return_value = _bundle("2026-09-25")
    with patch("api.routers.dashboard._ensure_analysis_background_compute") as mock_trigger:
        out = compute_analysis_bundle(allow_heavy=False)
    assert out == _bundle("2026-09-25")
    mock_trigger.assert_not_called()


@patch("api.routers.dashboard._forward_tracking_staleness_days", return_value=_FORWARD_TRACKING_STALE_DAYS + 1)
@patch("signals.cache.assemble_analysis_slices")
def test_stale_assembled_cache_hit_still_returns_data_but_triggers_background_compute(mock_assembled, _mock_stale):
    """The whole point: never leave the UI with nothing, but don't let a stale hit go unnoticed
    forever either — this is what breaks the trap without a user-visible regression."""
    mock_assembled.return_value = _bundle("2026-08-02")
    with patch("api.routers.dashboard._ensure_analysis_background_compute") as mock_trigger:
        out = compute_analysis_bundle(allow_heavy=False)
    assert out == _bundle("2026-08-02")
    mock_trigger.assert_called_once()


@patch("signals.cache.assemble_analysis_slices", return_value={"forward_tracking": {"meta": {}}})
def test_force_true_skips_all_cache_tiers_entirely(mock_assembled):
    """force=True (used only by _ensure_analysis_background_compute) must never even call the
    fast-path tiers — that's the actual fix for the trap, since a tier succeeding is precisely
    what always swallowed every previous "force a refresh" attempt."""
    with patch("signals.cache.get_cached_dashboard", return_value=None), \
         patch("signals.cache.get_last_dashboard_snapshot", return_value=None):
        out = compute_analysis_bundle(allow_heavy=True, force=True)
    mock_assembled.assert_not_called()
    assert out is None  # no dashboard cache to build the heavy path from in this test


def test_ensure_background_compute_calls_with_force_true():
    from api.routers.dashboard import _ensure_analysis_background_compute

    with patch("api.analysis_bundle_job.is_analysis_running", return_value=False), \
         patch("api.analysis_bundle_job.trigger_background_analysis") as mock_trigger:
        _ensure_analysis_background_compute()
    assert mock_trigger.called
    # The lambda passed to trigger_background_analysis must call compute_analysis_bundle with
    # force=True — invoke it (with everything mocked out) to prove that, not just inspect it.
    compute_fn = mock_trigger.call_args[0][0]
    with patch("api.routers.dashboard.compute_analysis_bundle") as mock_compute:
        compute_fn()
    mock_compute.assert_called_once_with(allow_heavy=True, force=True)
