"""
Background dashboard refresh job + status for stale-while-revalidate.

Single-flight: only one full dashboard compute at a time (sync Refresh or background job).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger("api.dashboard_job")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "started_at": None,
    "finished_at": None,
    "error": None,
    "last_success_at": None,
}


def get_refresh_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def is_refresh_running() -> bool:
    with _lock:
        return _state.get("status") == "running"


def try_begin_compute() -> bool:
    """Mark compute as running. Returns False if a refresh is already in progress."""
    with _lock:
        if _state.get("status") == "running":
            return False
        _state["status"] = "running"
        _state["started_at"] = time.time()
        _state["finished_at"] = None
        _state["error"] = None
        return True


def finish_compute(*, success: bool = True, error: str | None = None) -> None:
    with _lock:
        _state["finished_at"] = time.time()
        if success:
            _state["status"] = "done"
            _state["last_success_at"] = _state["finished_at"]
            _state["error"] = None
        else:
            _state["status"] = "error"
            _state["error"] = error or "unknown error"


def trigger_background_refresh(compute_fn: Callable[[], dict]) -> bool:
    """Start full dashboard compute in a daemon thread. Returns False if already running."""
    if not try_begin_compute():
        return False

    def _worker() -> None:
        try:
            logger.info("[dashboard-job] background refresh START")
            compute_fn()
            finish_compute(success=True)
            logger.info("[dashboard-job] background refresh DONE")
        except Exception as exc:
            logger.exception("[dashboard-job] background refresh failed: %s", exc)
            finish_compute(success=False, error=str(exc))

    threading.Thread(target=_worker, daemon=True, name="dashboard-bg-refresh").start()
    return True
