"""Forward-tracking-only refresh is single-flight; the bundle job never resets a live worker."""
import threading
import time

import api.analysis_bundle_job as job


def test_ft_refresh_single_flight_and_stores():
    gate = threading.Event()
    stored = []

    def compute():
        gate.wait(2)
        return {"meta": {"eod_date_last": "2026-10-19"}}

    assert job.trigger_forward_tracking_refresh(compute, stored.append) is True
    assert job.trigger_forward_tracking_refresh(compute, stored.append) is False  # already running
    gate.set()
    for _ in range(50):
        if not job.get_forward_tracking_job_status()["alive"]:
            break
        time.sleep(0.05)
    st = job.get_forward_tracking_job_status()
    assert st["status"] == "done" and stored and stored[0]["meta"]["eod_date_last"] == "2026-10-19"


def test_bundle_job_not_reset_while_worker_alive(monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(job, "_STALE_RUNNING_SEC", 0)
    assert job.trigger_background_analysis(lambda: (gate.wait(2), None)[1]) is True
    time.sleep(0.05)
    assert job.is_analysis_running() is True  # stale by timer, but thread is alive → still running
    gate.set()
