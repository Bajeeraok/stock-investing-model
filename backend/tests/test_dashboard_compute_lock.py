"""Single-flight dashboard compute lock."""
from api.dashboard_job import finish_compute, is_refresh_running, try_begin_compute


def test_try_begin_compute_single_flight():
    assert try_begin_compute() is True
    assert is_refresh_running() is True
    assert try_begin_compute() is False
    finish_compute(success=True)
    assert is_refresh_running() is False
    assert try_begin_compute() is True
    finish_compute(success=False, error="boom")
    assert is_refresh_running() is False
