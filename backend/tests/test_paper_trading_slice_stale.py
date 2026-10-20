"""Cached paper-trading slice is stale when its MTM date is older than the newest EOD snapshot."""
import signals.cache as cache_mod
from api.routers.dashboard import _paper_trading_slice_stale


def _pt(as_of):
    return {"recent": [{"date": as_of}], "summary": {"completed": 3}, "mtm": {"as_of": as_of}}


def test_older_mtm_than_latest_snapshot_is_stale(monkeypatch):
    monkeypatch.setattr(cache_mod, "build_eod_snapshot_index", lambda: [{"date": "2026-10-19"}])
    assert _paper_trading_slice_stale(_pt("2026-10-15")) is True


def test_current_mtm_is_fresh(monkeypatch):
    monkeypatch.setattr(cache_mod, "build_eod_snapshot_index", lambda: [{"date": "2026-10-19"}])
    assert _paper_trading_slice_stale(_pt("2026-10-19")) is False
