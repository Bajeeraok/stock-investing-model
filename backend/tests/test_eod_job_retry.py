"""EOD background job retry after failed attempt (489bd45 regression)."""
from __future__ import annotations

from datetime import datetime

from zoneinfo import ZoneInfo

import api.eod_job as eod_job

EST = ZoneInfo("America/New_York")


def _reset_state(**kwargs):
    base = {
        "running": False,
        "last_success_date": None,
        "last_attempt_ts": 0.0,
        "last_attempt_date": None,
        "last_result": None,
    }
    base.update(kwargs)
    eod_job._state.update(base)


def test_last_completed_session_before_8pm_is_prior_day():
    now = datetime(2026, 8, 19, 13, 0, tzinfo=EST)
    assert eod_job.last_completed_session_date(now) == "2026-08-18"


def test_last_completed_session_after_8pm_is_today():
    now = datetime(2026, 8, 19, 21, 0, tzinfo=EST)
    assert eod_job.last_completed_session_date(now) == "2026-08-19"


def test_last_completed_session_monday_morning_is_friday():
    now = datetime(2026, 8, 17, 10, 0, tzinfo=EST)
    assert eod_job.last_completed_session_date(now) == "2026-08-14"


def test_cooldown_blocks_then_force_retry(monkeypatch):
    _reset_state(
        last_attempt_ts=eod_job.time.time(),
        last_attempt_date="2026-07-07",
        last_result="error:boom",
    )
    monkeypatch.setattr(eod_job, "last_completed_session_date", lambda *a, **k: "2026-07-07")
    monkeypatch.setattr("config_loader.load_config", lambda: {})

    import scripts.run_daily as rd

    monkeypatch.setattr(rd, "full_eod_snapshot_exists", lambda *_a, **_k: False)

    started: list[int] = []

    def fake_thread(*_a, **_k):
        class T:
            def start(self):
                started.append(1)

        return T()

    monkeypatch.setattr(eod_job.threading, "Thread", fake_thread)

    assert eod_job.trigger_full_eod_background_if_missing(min_hour_et=20) is False
    assert started == []
    assert eod_job.trigger_full_eod_background_if_missing(min_hour_et=20, force_retry=True) is True
    assert started == [1]
    _reset_state()


def test_catchup_queues_prior_session_before_8pm(monkeypatch):
    _reset_state()
    monkeypatch.setattr(eod_job, "last_completed_session_date", lambda *a, **k: "2026-08-18")
    monkeypatch.setattr("config_loader.load_config", lambda: {})

    import scripts.run_daily as rd

    monkeypatch.setattr(rd, "full_eod_snapshot_exists", lambda *_a, **_k: False)

    started: list[int] = []

    def fake_thread(*_a, **_k):
        class T:
            def start(self):
                started.append(1)

        return T()

    monkeypatch.setattr(eod_job.threading, "Thread", fake_thread)
    assert eod_job.trigger_full_eod_background_if_missing(min_hour_et=20) is True
    assert started == [1]
    assert eod_job._state["last_attempt_date"] == "2026-08-18"
    _reset_state()
