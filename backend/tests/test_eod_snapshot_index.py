"""
signals/cache.py — EOD snapshot Redis write + live index build.

Regression for the "stuck on 2026-08-02" symptom (documented in this module's own
comments): EOD snapshots are multi-MB JSON, and a client-side timeout on the big blob
write previously skipped the date-index update (r.sadd) entirely, even on writes that may
have landed server-side anyway. set_eod_snapshot_redis now attempts the index update
independently of the blob-write outcome. Separately, build_eod_snapshot_index() used to
hardcode run_date=None for every disk-sourced entry, so anything reading that field (the
eod_snapshot_saved_at freshness badge) had nothing current to fall back on.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest


class _FakeRedis:
    def __init__(self, *, fail_set=False, fail_sadd=False):
        self.fail_set = fail_set
        self.fail_sadd = fail_sadd
        self.set_calls: list[tuple] = []
        self.sadd_calls: list[tuple] = []

    def set(self, key, value):
        self.set_calls.append((key, value))
        if self.fail_set:
            raise TimeoutError("Timeout reading from socket")
        return True

    def sadd(self, key, value):
        self.sadd_calls.append((key, value))
        if self.fail_sadd:
            raise TimeoutError("Timeout reading from socket")
        return 1


class TestSetEodSnapshotRedis:
    def test_sadd_still_attempted_when_blob_set_times_out(self, monkeypatch):
        from signals import cache as cache_mod

        fake = _FakeRedis(fail_set=True)
        monkeypatch.setattr(cache_mod, "_redis_client", lambda: fake)
        ok = cache_mod.set_eod_snapshot_redis("2026-09-28", {"tickers": []})
        assert ok is False  # blob write genuinely failed
        assert len(fake.sadd_calls) == 1  # but the index update was still attempted
        assert fake.sadd_calls[0] == (cache_mod.EOD_DATES_SET, "2026-09-28")

    def test_returns_true_and_updates_index_on_full_success(self, monkeypatch):
        from signals import cache as cache_mod

        fake = _FakeRedis()
        monkeypatch.setattr(cache_mod, "_redis_client", lambda: fake)
        ok = cache_mod.set_eod_snapshot_redis("2026-09-28", {"tickers": []})
        assert ok is True
        assert len(fake.set_calls) == 1
        assert len(fake.sadd_calls) == 1

    def test_returns_false_without_redis_configured(self, monkeypatch):
        from signals import cache as cache_mod

        monkeypatch.setattr(cache_mod, "_redis_client", lambda: None)
        assert cache_mod.set_eod_snapshot_redis("2026-09-28", {}) is False

    def test_sadd_failure_does_not_raise(self, monkeypatch):
        from signals import cache as cache_mod

        fake = _FakeRedis(fail_sadd=True)
        monkeypatch.setattr(cache_mod, "_redis_client", lambda: fake)
        ok = cache_mod.set_eod_snapshot_redis("2026-09-28", {"tickers": []})
        assert ok is True  # blob write succeeded even though the index update failed


class TestBuildEodSnapshotIndexRunDate:
    def test_disk_entry_run_date_reflects_file_mtime(self, tmp_path, monkeypatch):
        from signals import cache as cache_mod

        eod_dir = tmp_path / "eod"
        eod_dir.mkdir()
        f = eod_dir / "2026-09-25.json"
        f.write_text(json.dumps({"tickers": []}))

        monkeypatch.setattr(cache_mod, "list_eod_dates_redis", lambda: [])
        monkeypatch.setattr("config_loader.get_data_root", lambda: tmp_path)

        index = cache_mod.build_eod_snapshot_index()
        assert len(index) == 1
        entry = index[0]
        assert entry["date"] == "2026-09-25"
        assert entry["run_date"] is not None
        # Should be a real, parseable, recent (just-written) timestamp, not a stale/frozen one.
        parsed = datetime.fromisoformat(entry["run_date"])
        assert abs((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()) < 300

    def test_redis_only_entry_keeps_run_date_none_without_disk_file(self, monkeypatch):
        from signals import cache as cache_mod

        monkeypatch.setattr(cache_mod, "list_eod_dates_redis", lambda: ["2026-09-25"])
        monkeypatch.setattr("config_loader.get_data_root", lambda: __import__("pathlib").Path("/nonexistent_dir_xyz"))

        index = cache_mod.build_eod_snapshot_index()
        assert len(index) == 1
        assert index[0]["date"] == "2026-09-25"
        assert index[0]["run_date"] is None
        assert index[0]["source"] == "redis"
