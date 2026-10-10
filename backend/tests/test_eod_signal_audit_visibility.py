"""
Regression coverage for a silent-failure gap: both callers of run_eod_snapshot_only() (the
8pm cron in api/eod_scheduler.py and the safety-net thread in api/eod_job.py) only checked
the snapshot-save result's top-level "error"/"skipped" fields — never result["signal_audit"],
the nested sub-result from persist_daily_signal_logs(). A signal-audit logging failure or a
<90%-cohort-capture-ratio skip (log_signal_audit_from_results) was therefore invisible: the
scheduler logged "ok" either way, since the EOD snapshot itself saved fine. Confirmed live
that signal-audit's last captured day sat 2+ trading days behind the actual (correctly
current) EOD snapshot date with nothing surfacing why.

record_signal_audit_result() now stores the latest signal_audit outcome in eod_job's state,
exposed via eod_job_state() / GET /api/eod/status, and both call sites invoke it.
"""
from __future__ import annotations

from unittest.mock import patch

from api.eod_job import eod_job_state, record_signal_audit_result


def test_record_signal_audit_result_ok_case():
    record_signal_audit_result({"appended": 97, "skipped_duplicate": 0}, date_str="2026-10-09")
    state = eod_job_state()
    assert state["last_signal_audit"] == {
        "date": "2026-10-09",
        "ok": True,
        "error": None,
        "skipped": None,
        "reason": None,
        "appended": 97,
    }


def test_record_signal_audit_result_skipped_case():
    """The exact live failure mode: a low cohort-capture-ratio skip with no exception raised —
    must be visibly flagged as not-ok, not mistaken for success."""
    record_signal_audit_result(
        {"skipped": True, "reason": "cohort capture 84/100 (84%) below min 90%"},
        date_str="2026-10-08",
    )
    state = eod_job_state()
    assert state["last_signal_audit"]["ok"] is False
    assert state["last_signal_audit"]["skipped"] is True
    assert "84/100" in state["last_signal_audit"]["reason"]


def test_record_signal_audit_result_error_case():
    record_signal_audit_result({"error": "database is locked"}, date_str="2026-10-08")
    state = eod_job_state()
    assert state["last_signal_audit"]["ok"] is False
    assert state["last_signal_audit"]["error"] == "database is locked"


def test_record_signal_audit_result_ignores_non_dict():
    """A prior call's state must survive a later call that passes None/malformed input
    (e.g. result.get("signal_audit") was never set) rather than clobbering it with garbage."""
    record_signal_audit_result({"appended": 5}, date_str="2026-10-07")
    record_signal_audit_result(None, date_str="2026-10-08")
    state = eod_job_state()
    assert state["last_signal_audit"]["date"] == "2026-10-07"


@patch("api.eod_job.trigger_full_eod_background_if_missing")
@patch("scripts.run_daily.run_eod_snapshot_only")
def test_eod_scheduler_job_records_signal_audit_even_when_snapshot_ok(mock_run, _mock_trigger):
    """The actual bug scenario: snapshot save succeeds (no top-level error/skipped), but the
    nested signal_audit sub-result reports a skip — _run_eod_job must still record it, not
    silently drop it just because the overall result looked like success."""
    from api import eod_scheduler

    mock_run.return_value = {
        "snapshot_date": "2026-10-09",
        "snapshot_path": "/data/eod/2026-10-09.json",
        "tickers_count": 97,
        "signal_audit": {"skipped": True, "reason": "cohort capture 84/100 (84%) below min 90%"},
    }
    eod_scheduler._run_eod_job()
    state = eod_job_state()
    assert state["last_signal_audit"]["date"] == "2026-10-09"
    assert state["last_signal_audit"]["ok"] is False
