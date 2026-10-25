"""
Optional in-process EOD snapshot schedule (APScheduler).

Enable via (first match wins):
  1. EOD_SCHEDULER_CRON — 5-field cron (e.g. 0 20 * * 1-5)
  2. config.yaml eod_schedule_time + eod_schedule_tz (default 20:00 America/New_York, Mon–Fri)
Disable: EOD_SCHEDULER_OFF=1
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("api.eod_scheduler")
_scheduler: BackgroundScheduler | None = None


def _scheduler_disabled() -> bool:
    return (os.environ.get("EOD_SCHEDULER_OFF") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def unix_dow_field_to_apscheduler(day_of_week: str) -> str:
    """
    APScheduler 3 weekday numbers are Mon=0 … Sun=6.
    UNIX cron (and our docs) use Sun=0 … Sat=6, so ``1-5`` means Mon–Fri there
    but Tuesday–Saturday inside APScheduler — Mondays never fire.

    Map the common UNIX Mon–Fri forms to APScheduler ``mon-fri``.
    """
    raw = (day_of_week or "").strip().lower()
    if raw in ("1-5", "1,2,3,4,5"):
        return "mon-fri"
    return day_of_week


def resolve_eod_schedule() -> tuple[str, str] | None:
    """
    Return (cron_5field, tz_name) or None when scheduling should stay off.
    """
    if _scheduler_disabled():
        return None

    cron = (os.environ.get("EOD_SCHEDULER_CRON") or "").strip()
    tz_name = (os.environ.get("EOD_SCHEDULER_TZ") or "").strip() or "America/New_York"
    if cron:
        parts = cron.split()
        if len(parts) == 5:
            parts[4] = unix_dow_field_to_apscheduler(parts[4])
            cron = " ".join(parts)
        return cron, tz_name

    try:
        from config_loader import load_config

        config = load_config()
        if config.get("eod_scheduler_enabled") is False:
            return None
        schedule_time = str(config.get("eod_schedule_time") or "20:00").strip()
        tz_name = str(config.get("eod_schedule_tz") or "America/New_York").strip()
        parts = schedule_time.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"invalid eod_schedule_time: {schedule_time!r}")
        cron = f"{minute} {hour} * * mon-fri"
        return cron, tz_name
    except Exception as e:
        logger.warning("EOD schedule from config failed (%s) — scheduler off", e)
        return None


def _run_eod_job() -> None:
    eod_ok = False
    try:
        from config_loader import load_config
        from scripts.run_daily import run_eod_snapshot_only

        config = load_config()
        result = run_eod_snapshot_only(config)
        try:
            from api.eod_job import record_signal_audit_result

            record_signal_audit_result(
                result.get("signal_audit"), date_str=str(result.get("snapshot_date") or "")
            )
        except Exception:
            pass
        if result.get("error"):
            logger.error("[eod-scheduler] %s", result["error"])
            # Allow eod_job safety-net to retry soon (do not leave a sticky "success" day).
            try:
                from api.eod_job import trigger_full_eod_background_if_missing

                trigger_full_eod_background_if_missing(min_hour_et=20, force_retry=True)
            except Exception:
                pass
        elif result.get("skipped"):
            logger.info("[eod-scheduler] skipped — %s", result.get("reason") or "unknown")
        else:
            eod_ok = True
            sa = result.get("signal_audit") or {}
            if isinstance(sa, dict) and (sa.get("error") or sa.get("skipped")):
                logger.warning(
                    "[eod-scheduler] EOD snapshot ok but signal_audit logging %s: %s",
                    "errored" if sa.get("error") else "skipped",
                    sa.get("error") or sa.get("reason") or "unknown",
                )
            logger.info(
                "[eod-scheduler] ok date=%s path=%s tickers=%s",
                result.get("snapshot_date"),
                result.get("snapshot_path"),
                result.get("tickers_count"),
            )
    except Exception:
        logger.exception("[eod-scheduler] job failed")
        try:
            from api.eod_job import trigger_full_eod_background_if_missing

            trigger_full_eod_background_if_missing(min_hour_et=20, force_retry=True)
        except Exception:
            pass
    finally:
        try:
            from signals.process_memory import process_rss_mb, release_process_caches

            stats = release_process_caches(aggressive=True)
            logger.info("[eod-scheduler] memory hygiene rss_mb=%s stats=%s", process_rss_mb(), stats)
        except Exception:
            logger.debug("[eod-scheduler] memory hygiene skipped", exc_info=True)

    if eod_ok:
        # FMP consensus vintages: revision signals can only be backtested from history we save.
        try:
            import threading

            from config_loader import load_config as _lc
            from signals.alpha.estimates_snapshot import run as _snap_estimates

            threading.Thread(
                target=lambda: logger.info("[eod-scheduler] estimates snapshot %s", _snap_estimates(_lc())),
                daemon=True,
                name="fmp-estimates-snapshot",
            ).start()
        except Exception:
            logger.exception("[eod-scheduler] estimates snapshot failed to start")
        # New snapshot → recompute forward tracking now (daily 1d calls, per-ticker index)
        # instead of waiting for someone to open Analysis/Track and hit the staleness check.
        try:
            from api.routers.dashboard import _ensure_forward_tracking_refresh

            _ensure_forward_tracking_refresh()
            logger.info("[eod-scheduler] forward-tracking refresh queued after new snapshot")
        except Exception:
            logger.exception("[eod-scheduler] forward-tracking refresh failed to queue")
        try:
            from alerts.market_hours import is_signal_warm_window
            from api.dashboard_warm import trigger_post_eod_dashboard_sync

            if is_signal_warm_window():
                queued = trigger_post_eod_dashboard_sync()
                logger.info("[eod-scheduler] post-EOD dashboard cache sync queued=%s", queued)
            else:
                logger.info(
                    "[eod-scheduler] EOD ok — deferred post-EOD dashboard sync until weekday 8:30 ET"
                )
        except Exception:
            logger.exception("[eod-scheduler] post-EOD dashboard cache sync failed to queue")


def start() -> None:
    """Start background scheduler when env or config enables EOD."""
    global _scheduler
    resolved = resolve_eod_schedule()
    if not resolved:
        if _scheduler_disabled():
            logger.info("EOD scheduler off (EOD_SCHEDULER_OFF is set)")
        else:
            logger.info(
                "EOD scheduler off (set EOD_SCHEDULER_CRON or eod_schedule_time in config.yaml)"
            )
        return

    cron, tz_name = resolved
    parts = cron.split()
    if len(parts) != 5:
        logger.error(
            "EOD schedule must have exactly 5 cron fields: minute hour day-of-month month day-of-week "
            "(got %r)",
            cron,
        )
        return

    import pytz as _pytz

    try:
        _pytz.timezone(tz_name)
    except Exception:
        tz_name = "America/New_York"
        logger.warning("EOD_SCHEDULER_TZ unrecognised; falling back to America/New_York")

    minute, hour, day, month, day_of_week = parts
    day_of_week = unix_dow_field_to_apscheduler(day_of_week)

    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler(timezone=tz_name)
    _scheduler.add_job(
        _run_eod_job,
        "cron",
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        id="eod_snapshot",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    _tz_obj = _pytz.timezone(tz_name)
    from datetime import datetime as _dt

    _now_local = _dt.now(_tz_obj)
    next_run = None
    try:
        job = _scheduler.get_job("eod_snapshot")
        if job is not None and job.next_run_time is not None:
            next_run = job.next_run_time.isoformat()
    except Exception:
        next_run = None
    logger.info(
        "EOD scheduler on: cron=%s tz=%s now=%s next_run_at=%s",
        cron,
        tz_name,
        _now_local.strftime("%Y-%m-%d %H:%M %Z"),
        next_run,
    )


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            logger.exception("EOD scheduler shutdown")
        _scheduler = None


def scheduler_status() -> dict:
    """
    Introspection for GET /api/eod/status — whether the in-process APScheduler is alive.
    """
    resolved = resolve_eod_schedule()
    out: dict = {
        "enabled": resolved is not None,
        "running": False,
        "cron": None,
        "tz": None,
        "next_run_at": None,
        "job_id": "eod_snapshot",
        "off_reason": None,
    }
    if not resolved:
        if _scheduler_disabled():
            out["off_reason"] = "EOD_SCHEDULER_OFF is set"
        else:
            out["off_reason"] = "no EOD_SCHEDULER_CRON and config schedule unavailable"
        return out

    cron, tz_name = resolved
    out["cron"] = cron
    out["tz"] = tz_name
    if _scheduler is None:
        out["off_reason"] = "scheduler object is None (startup may have failed)"
        return out
    try:
        out["running"] = bool(_scheduler.running)
        job = _scheduler.get_job("eod_snapshot")
        if job is not None and job.next_run_time is not None:
            out["next_run_at"] = job.next_run_time.isoformat()
    except Exception as e:
        out["off_reason"] = f"status read failed: {e}"
    return out
