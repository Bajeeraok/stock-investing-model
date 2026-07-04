"""In-process EOD scheduler resolution."""

from api import eod_scheduler


def test_resolve_eod_schedule_from_config_defaults(monkeypatch):
    monkeypatch.delenv("EOD_SCHEDULER_CRON", raising=False)
    monkeypatch.delenv("EOD_SCHEDULER_OFF", raising=False)
    resolved = eod_scheduler.resolve_eod_schedule()
    assert resolved is not None
    cron, tz = resolved
    assert cron == "0 20 * * 1-5"
    assert tz == "America/New_York"


def test_resolve_eod_schedule_env_overrides_config(monkeypatch):
    monkeypatch.setenv("EOD_SCHEDULER_CRON", "15 21 * * 1-5")
    monkeypatch.setenv("EOD_SCHEDULER_TZ", "America/Chicago")
    monkeypatch.delenv("EOD_SCHEDULER_OFF", raising=False)
    cron, tz = eod_scheduler.resolve_eod_schedule()
    assert cron == "15 21 * * 1-5"
    assert tz == "America/Chicago"


def test_resolve_eod_schedule_off_flag(monkeypatch):
    monkeypatch.setenv("EOD_SCHEDULER_OFF", "1")
    assert eod_scheduler.resolve_eod_schedule() is None
