"""
Background analysis-bundle compute — paper-trading backfill can take several minutes;
never block GET /api/dashboard/analysis-bundle on that work.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger("api.analysis_bundle_job")

_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def get_analysis_job_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def is_analysis_running() -> bool:
    with _lock:
        return _state.get("status") == "running"


def try_begin_analysis() -> bool:
    with _lock:
        if _state.get("status") == "running":
            return False
        _state["status"] = "running"
        _state["started_at"] = time.time()
        _state["finished_at"] = None
        _state["error"] = None
        return True


def finish_analysis(*, success: bool = True, error: str | None = None) -> None:
    with _lock:
        _state["finished_at"] = time.time()
        if success:
            _state["status"] = "done"
            _state["error"] = None
        else:
            _state["status"] = "error"
            _state["error"] = error or "unknown error"


def trigger_background_analysis(compute_fn: Callable[[], dict | None]) -> bool:
    """Start analysis-bundle compute in a daemon thread. Returns False if already running."""
    if not try_begin_analysis():
        return False

    def _worker() -> None:
        try:
            logger.info("[analysis-bundle-job] background compute START")
            bundle = compute_fn()
            if bundle:
                try:
                    from signals.cache import get_cached_dashboard, set_analysis_bundle

                    dash = get_cached_dashboard()
                    refresh_ts = dash.get("refresh_ts") if isinstance(dash, dict) else None
                    ok = set_analysis_bundle(bundle, refresh_ts=refresh_ts)
                    logger.info("[analysis-bundle-job] cache write: %s", "ok" if ok else "FAILED")
                except Exception as cache_exc:
                    logger.warning("[analysis-bundle-job] cache write error: %s", cache_exc)
            finish_analysis(success=True)
            logger.info("[analysis-bundle-job] background compute DONE")
        except Exception as exc:
            logger.exception("[analysis-bundle-job] failed: %s", exc)
            finish_analysis(success=False, error=str(exc))

    threading.Thread(target=_worker, daemon=True, name="analysis-bundle-bg").start()
    return True
