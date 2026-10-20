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

_STALE_RUNNING_SEC = 600  # reset stuck "running" after 10 min

_lock = threading.Lock()
_worker_thread: threading.Thread | None = None
_state: dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _reset_if_stale_running() -> None:
    with _lock:
        if _state.get("status") != "running":
            return
        # A slow-but-alive compute is not stuck: resetting it let a second full compute start
        # on top of the first (observed live — two heavy runs overlapping, doubling RAM).
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        started = _state.get("started_at")
        if started is not None and (time.time() - float(started)) > _STALE_RUNNING_SEC:
            logger.warning("[analysis-bundle-job] resetting stale running job (>%ds)", _STALE_RUNNING_SEC)
            _state["status"] = "idle"
            _state["started_at"] = None


def get_analysis_job_status() -> dict[str, Any]:
    _reset_if_stale_running()
    with _lock:
        return dict(_state)


def is_analysis_running() -> bool:
    _reset_if_stale_running()
    with _lock:
        return _state.get("status") == "running"


def try_begin_analysis() -> bool:
    _reset_if_stale_running()
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
        ok = False
        try:
            logger.info("[analysis-bundle-job] background compute START")
            bundle = compute_fn()
            if bundle:
                try:
                    from signals.cache import get_cached_dashboard, set_analysis_bundle

                    dash = get_cached_dashboard()
                    refresh_ts = dash.get("refresh_ts") if isinstance(dash, dict) else None
                    ok = bool(set_analysis_bundle(bundle, refresh_ts=refresh_ts))
                    logger.info("[analysis-bundle-job] cache write: %s", "ok" if ok else "FAILED")
                except Exception as cache_exc:
                    logger.warning("[analysis-bundle-job] cache write error: %s", cache_exc)
            else:
                logger.warning("[analysis-bundle-job] compute returned empty bundle")
            finish_analysis(success=ok)
            logger.info("[analysis-bundle-job] background compute DONE (success=%s)", ok)
        except Exception as exc:
            logger.exception("[analysis-bundle-job] failed: %s", exc)
            finish_analysis(success=False, error=str(exc))

    global _worker_thread
    t = threading.Thread(target=_worker, daemon=True, name="analysis-bundle-bg")
    with _lock:
        _worker_thread = t
    t.start()
    return True


# ── Forward-tracking-only refresh (single-flight, independent of the full bundle) ──
_ft_lock = threading.Lock()
_ft_thread: threading.Thread | None = None
_ft_state: dict[str, Any] = {"status": "idle", "started_at": None, "finished_at": None, "error": None}


def get_forward_tracking_job_status() -> dict[str, Any]:
    with _ft_lock:
        out = dict(_ft_state)
        out["alive"] = bool(_ft_thread is not None and _ft_thread.is_alive())
        return out


def trigger_forward_tracking_refresh(compute_fn: Callable[[], Any], store_fn: Callable[[Any], Any]) -> bool:
    """Recompute only the forward_tracking slice in a daemon thread. False if one is running.

    The full analysis bundle (paper backfill, insider, validations…) can exceed 10 minutes on
    Railway; forward tracking alone is the part that goes stale daily, so it refreshes on its own.
    """
    global _ft_thread
    with _ft_lock:
        if _ft_thread is not None and _ft_thread.is_alive():
            return False
        _ft_state.update(status="running", started_at=time.time(), finished_at=None, error=None)

    def _worker() -> None:
        try:
            logger.info("[forward-tracking-job] START")
            data = compute_fn()
            if data:
                store_fn(data)
            with _ft_lock:
                _ft_state.update(status="done" if data else "error", finished_at=time.time(),
                                 error=None if data else "empty result")
            logger.info("[forward-tracking-job] DONE (ok=%s)", bool(data))
        except Exception as exc:
            logger.exception("[forward-tracking-job] failed: %s", exc)
            with _ft_lock:
                _ft_state.update(status="error", finished_at=time.time(), error=str(exc))

    t = threading.Thread(target=_worker, daemon=True, name="forward-tracking-bg")
    with _ft_lock:
        _ft_thread = t
    t.start()
    return True
