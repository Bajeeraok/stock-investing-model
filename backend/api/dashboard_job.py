"""
Background dashboard refresh job + status for stale-while-revalidate.
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


def trigger_background_refresh(compute_fn: Callable[[], dict]) -> bool:
    """Start full dashboard compute in a daemon thread. Returns False if already running."""
    with _lock:
        if _state.get("status") == "running":
            return False
        _state["status"] = "running"
        _state["started_at"] = time.time()
        _state["finished_at"] = None
        _state["error"] = None

    def _worker() -> None:
        try:
            logger.info("[dashboard-job] background refresh START")
            compute_fn()
            with _lock:
                _state["status"] = "done"
                _state["finished_at"] = time.time()
                _state["last_success_at"] = _state["finished_at"]
            logger.info("[dashboard-job] background refresh DONE")
        except Exception as exc:
            logger.exception("[dashboard-job] background refresh failed: %s", exc)
            with _lock:
                _state["status"] = "error"
                _state["finished_at"] = time.time()
                _state["error"] = str(exc)

    threading.Thread(target=_worker, daemon=True, name="dashboard-bg-refresh").start()
    return True
