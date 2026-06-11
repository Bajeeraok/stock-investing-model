"""
Optional in-process EOD snapshot schedule (APScheduler).
Enable by setting EOD_SCHEDULER_CRON to a 5-field cron expression.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("api.eod_scheduler")
_scheduler: BackgroundScheduler | None = None


def _run_eod_job() -> None:
    try:
        from config_loader import load_config
        from scripts.run_daily import run_eod_snapshot_only

        config = load_config()
        result = run_eod_snapshot_only(config)
        if result.get("error"):
            logger.error("[eod-scheduler] %s", result["error"])
        else:
            logger.info(
                "[eod-scheduler] ok date=%s path=%s tickers=%s",
                result.get("snapshot_date"),
                result.get("snapshot_path"),
                result.get("tickers_count"),
            )
    except Exception:
        logger.exception("[eod-scheduler] job failed")


def start() -> None:
    """Start background scheduler if EOD_SCHEDULER_CRON is set."""
    global _scheduler
    cron = (os.environ.get("EOD_SCHEDULER_CRON") or "").strip()
    if not cron:
        logger.info("EOD scheduler off (set EOD_SCHEDULER_CRON to enable, e.g. 0 20 * * 1-5)")
        return

    parts = cron.split()
    if len(parts) != 5:
        logger.error(
            "EOD_SCHEDULER_CRON must have exactly 5 fields: minute hour day-of-month month day-of-week "
            "(e.g. 0 20 * * 1-5 for 8pm Mon-Fri)"
        )
        return

    tz_name = (os.environ.get("EOD_SCHEDULER_TZ") or "America/New_York").strip()

    # Validate the timezone name before passing to APScheduler.
    # APScheduler 3.x resolves timezone strings via pytz internally — pass the
    # name string directly so pytz handles it. Passing a ZoneInfo object can
    # silently fall back to UTC on slim images where system tzdata is absent.
    import pytz as _pytz
    try:
        _pytz.timezone(tz_name)  # validate; raises UnknownTimeZoneError if bad
    except Exception:
        tz_name = "America/New_York"
        logger.warning("EOD_SCHEDULER_TZ unrecognised; falling back to America/New_York")

    minute, hour, day, month, day_of_week = parts

    from apscheduler.schedulers.background import BackgroundScheduler

    # Pass tz_name string — APScheduler 3.x resolves it via pytz regardless of
    # whether system tzdata or the Python tzdata package is installed.
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
    # Log resolved timezone so Railway logs make it obvious if UTC crept in
    import pytz as _pytz2
    _tz_obj = _pytz2.timezone(tz_name)
    from datetime import datetime as _dt
    _now_local = _dt.now(_tz_obj)
    logger.info(
        "EOD scheduler on: cron=%s tz=%s (now=%s — next fire ~%s:00)",
        cron, tz_name,
        _now_local.strftime("%Y-%m-%d %H:%M %Z"),
        hour,
    )


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            logger.exception("EOD scheduler shutdown")
        _scheduler = None
