"""
enrich_shell_snapshot_meta() must overlay a LIVE EOD index onto both
eod_snapshot_latest_date AND eod_snapshot_saved_at on every shell serve.

Regression: only eod_snapshot_latest_date had this live overlay. A served shell built
from a stale cached full-dashboard blob kept eod_snapshot_saved_at frozen at whatever an
old full compute baked in (reported live: stuck at 2026-08-02 while
eod_snapshot_latest_date, right next to it, correctly showed a recent date) — confusing,
since a stale-looking "saved at" badge implied the underlying signals were also stale when
they usually weren't (see GET /api/eod/status, which reads the same live index).
"""
from __future__ import annotations

from unittest.mock import patch

from api.dashboard_shell import enrich_shell_snapshot_meta


def _fake_index():
    return [
        {"date": "2026-09-25", "run_date": "2026-09-25T20:05:00-04:00", "size_bytes": 123, "source": "disk"},
        {"date": "2026-08-02", "run_date": "2026-08-02T06:28:27-04:00", "size_bytes": 456, "source": "disk"},
    ]


def test_saved_at_and_latest_date_both_overlaid_from_live_index():
    shell = {
        "as_of_date": "2026-09-28T11:10:31-04:00",
        "data_freshness": {
            # Simulates a stale blob baked in by an old full compute.
            "eod_snapshot_latest_date": "2026-08-02",
            "eod_snapshot_saved_at": "2026-08-02T06:28:27-04:00",
        },
    }
    with patch("signals.cache.build_eod_snapshot_index", return_value=_fake_index()):
        out = enrich_shell_snapshot_meta(shell)

    assert out["eod_snapshot_latest_date"] == "2026-09-25"
    assert out["eod_snapshot_saved_at"] == "2026-09-25T20:05:00-04:00"
    df = out["data_freshness"]
    assert df["eod_snapshot_latest_date"] == "2026-09-25"
    assert df["eod_snapshot_saved_at"] == "2026-09-25T20:05:00-04:00"


def test_no_crash_and_no_overlay_when_index_empty():
    shell = {"as_of_date": "2026-09-28", "data_freshness": {"eod_snapshot_saved_at": "2026-08-02T06:28:27-04:00"}}
    with patch("signals.cache.build_eod_snapshot_index", return_value=[]):
        out = enrich_shell_snapshot_meta(shell)
    # Nothing to overlay — prior (stale) value stays rather than being wiped to None.
    assert out["data_freshness"]["eod_snapshot_saved_at"] == "2026-08-02T06:28:27-04:00"


def test_no_crash_when_index_lookup_raises():
    shell = {"as_of_date": "2026-09-28", "data_freshness": {}}
    with patch("signals.cache.build_eod_snapshot_index", side_effect=RuntimeError("redis down")):
        out = enrich_shell_snapshot_meta(shell)
    assert isinstance(out, dict)  # degrades gracefully, does not raise
