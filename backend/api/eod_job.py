"""
Single-flight background full EOD snapshot (~100 tickers).
Used by the 8pm scheduler and as a safety net after dashboard refresh post-close.

Fix vs 489bd45: do not burn the day on a single failed/skipped attempt — retry with cooldown.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("api.eod_job")

# Retry cooldown after a failed/skipped attempt (seconds). Prevents stampede, allows recovery.
_RETRY_COOLDOWN_SEC = 15 * 60

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "last_success_date": None,
    "last_attempt_ts": 0.0,
    "last_attempt_date": None,
    "last_result": None,
    "last_signal_audit": None,
}


def is_eod_job_running() -> bool:
    with _lock:
        return bool(_state.get("running"))


def record_signal_audit_result(signal_audit: dict | None, *, date_str: str) -> None:
    """
    Both callers of run_eod_snapshot_only() (the 8pm cron in eod_scheduler.py and this
    module's own safety-net thread) only ever checked the snapshot-save result's top-level
    "error"/"skipped" — never result["signal_audit"], the sub-result from
    persist_daily_signal_logs() nested inside the same call. That made a signal-audit
    logging failure or skip (e.g. the <90%-cohort-capture-ratio gate in
    log_signal_audit_from_results) completely invisible: the scheduler logs "[eod-scheduler]
    ok" either way, since the snapshot itself did save fine. Confirmed live: signal-audit's
    last captured day sat 2+ trading days behind the actual (correctly current) EOD snapshot
    date, with nothing surfacing why. This at least makes the next such gap visible via
    GET /api/eod/status instead of requiring a server-log dig to notice at all.
    """
    if not isinstance(signal_audit, dict):
        return
    with _lock:
        _state["last_signal_audit"] = {
            "date": date_str,
            "ok": not (signal_audit.get("error") or signal_audit.get("skipped")),
            "error": signal_audit.get("error"),
            "skipped": signal_audit.get("skipped"),
            "reason": signal_audit.get("reason"),
            "appended": signal_audit.get("appended"),
        }


def eod_job_state() -> dict[str, Any]:
    with _lock:
        return {
            "running": bool(_state.get("running")),
            "last_success_date": _state.get("last_success_date"),
            "last_attempt_date": _state.get("last_attempt_date"),
            "last_result": _state.get("last_result"),
            "last_signal_audit": _state.get("last_signal_audit"),
            "retry_cooldown_sec": _RETRY_COOLDOWN_SEC,
        }


def last_completed_session_date(
    now: datetime | None = None,
    *,
    min_hour_et: int = 20,
) -> str:
    """
    Market date the in-process job should persist.

    Before 8pm ET on a session day, today's close is not final — use the previous
    NYSE session. After 8pm, use today. Weekends/holidays always use the last session.
    """
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore

    from scripts.run_daily import is_us_equity_session_day

    if now is None:
        now = datetime.now(ZoneInfo("America/New_York"))
    today = now.date() if hasattr(now, "date") else datetime.strptime(now.strftime("%Y-%m-%d"), "%Y-%m-%d").date()
    today_s = today.isoformat()
    hour = int(getattr(now, "hour", 0))
    if hour >= min_hour_et and is_us_equity_session_day(today_s):
        return today_s
    d = today - timedelta(days=1)
    for _ in range(14):
        s = d.isoformat()
        if is_us_equity_session_day(s):
            return s
        d -= timedelta(days=1)
    return today_s


def _start_full_eod_thread(date_str: str, *, force_retry: bool = False) -> bool:
    with _lock:
        if _state.get("running"):
            return False
        if _state.get("last_success_date") == date_str:
            return False
        now_ts = time.time()
        last_ts = float(_state.get("last_attempt_ts") or 0)
        last_date = _state.get("last_attempt_date")
        if (
            not force_retry
            and last_date == date_str
            and (now_ts - last_ts) < _RETRY_COOLDOWN_SEC
        ):
            return False
        _state["running"] = True
        _state["last_attempt_ts"] = now_ts
        _state["last_attempt_date"] = date_str
        _state["last_result"] = "started"

    def _worker() -> None:
        ok = False
        reason = None
        try:
            from config_loader import load_config
            from scripts.run_daily import run_eod_snapshot_only

            logger.info("[eod-job] background full EOD START date=%s", date_str)
            result = run_eod_snapshot_only(load_config(), snapshot_date=date_str)
            record_signal_audit_result(result.get("signal_audit"), date_str=date_str)
            if result.get("error"):
                reason = f"error:{result['error']}"
                logger.error("[eod-job] failed: %s", result["error"])
            elif result.get("skipped"):
                reason = f"skipped:{result.get('reason') or 'unknown'}"
                logger.info("[eod-job] skipped: %s", result.get("reason"))
                if result.get("reason") == "full_snapshot_exists":
                    ok = True
            else:
                ok = True
                reason = "ok"
                logger.info(
                    "[eod-job] ok date=%s tickers=%s path=%s",
                    result.get("snapshot_date"),
                    result.get("tickers_count"),
                    result.get("snapshot_path"),
                )
        except Exception:
            reason = "exception"
            logger.exception("[eod-job] background run failed")
        finally:
            with _lock:
                _state["running"] = False
                _state["last_result"] = reason
                if ok:
                    _state["last_success_date"] = date_str
            if ok:
                try:
                    from alerts.market_hours import is_signal_warm_window
                    from api.dashboard_warm import trigger_post_eod_dashboard_sync

                    if is_signal_warm_window():
                        queued = trigger_post_eod_dashboard_sync()
                        logger.info("[eod-job] post-EOD dashboard cache sync queued=%s", queued)
                    else:
                        logger.info(
                            "[eod-job] EOD ok — deferred post-EOD dashboard sync until weekday 8:30 ET"
                        )
                except Exception:
                    logger.exception("[eod-job] post-EOD dashboard cache sync failed to queue")

    threading.Thread(target=_worker, name="eod-full-snapshot", daemon=True).start()
    return True


def trigger_full_eod_background_if_missing(
    *,
    min_hour_et: int = 20,
    force_retry: bool = False,
) -> bool:
    """
    Start full EOD in a daemon thread when the last completed session snapshot is missing.
    Returns True if a new background job was started.

    Before 8pm ET this backfills the prior session (Railway often misses 8pm if the
    process was asleep or restarted). After 8pm it runs today's session.

    Retries after failure/skip once _RETRY_COOLDOWN_SEC has elapsed (unless force_retry).
    """
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore

    try:
        from config_loader import load_config
        from scripts.run_daily import full_eod_snapshot_exists

        now = datetime.now(ZoneInfo("America/New_York"))
        date_str = last_completed_session_date(now, min_hour_et=min_hour_et)
        config = load_config()
        if full_eod_snapshot_exists(date_str, config):
            with _lock:
                _state["last_success_date"] = date_str
            return False
    except Exception as exc:
        logger.debug("[eod-job] preflight skipped: %s", exc)
        return False

    return _start_full_eod_thread(date_str, force_retry=force_retry)
