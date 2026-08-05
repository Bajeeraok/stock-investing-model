"""Dashboard freshness meta survives when shell serves last_snapshot."""
from __future__ import annotations

from unittest.mock import patch


def test_freshness_meta_overlays_shell():
    from api.dashboard_shell import enrich_shell_snapshot_meta

    shell = {
        "data_freshness": {
            "signals_updated_at": "2026-08-02T17:52:00-04:00",
            "quotes_updated_at": "2026-08-02T17:52:00-04:00",
        },
        "refresh_ts": "old",
    }
    meta = {
        "signals_updated_at": "2026-08-02T23:38:20-04:00",
        "quotes_updated_at": "2026-08-02T23:38:20-04:00",
        "refresh_ts": "2026-08-02T23:38:20-04:00",
    }
    with patch("signals.cache.get_dashboard_freshness_meta", return_value=meta):
        out = enrich_shell_snapshot_meta(dict(shell))
    df = out["data_freshness"]
    assert df["signals_updated_at"] == "2026-08-02T23:38:20-04:00"
    assert df["quotes_updated_at"] == "2026-08-02T23:38:20-04:00"
    assert out["refresh_ts"] == "2026-08-02T23:38:20-04:00"


def test_persist_freshness_meta_on_cache_write():
    from signals.cache import _persist_dashboard_freshness_meta, get_dashboard_freshness_meta

    payload = {
        "refresh_ts": "2026-08-02T23:38:20-04:00",
        "data_freshness": {
            "signals_updated_at": "2026-08-02T23:38:20-04:00",
            "quotes_updated_at": "2026-08-02T23:38:20-04:00",
        },
    }
    with patch("signals.cache.set_cached", return_value=True) as mock_set:
        _persist_dashboard_freshness_meta(payload)
        assert mock_set.called
    with patch("signals.cache.get_cached", return_value=payload["data_freshness"]):
        meta = get_dashboard_freshness_meta()
    assert meta is not None
