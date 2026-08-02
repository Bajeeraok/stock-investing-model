"""EOD background job retry after failed attempt (489bd45 regression)."""
from __future__ import annotations

import api.eod_job as eod_job


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


def test_cooldown_blocks_then_force_retry(monkeypatch):
    _reset_state(
        last_attempt_ts=eod_job.time.time(),
        last_attempt_date="2026-07-07",
        last_result="error:boom",
    )

    class FakeNow:
        hour = 21

        def strftime(self, fmt):
            return "2026-07-07"

    class FakeDateTime:
        @staticmethod
        def now(tz=None):
            return FakeNow()

    import datetime as datetime_mod

    monkeypatch.setattr(datetime_mod, "datetime", FakeDateTime)
    monkeypatch.setattr("config_loader.load_config", lambda: {})

    import scripts.run_daily as rd

    monkeypatch.setattr(rd, "is_us_equity_session_day", lambda _d=None: True)
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
