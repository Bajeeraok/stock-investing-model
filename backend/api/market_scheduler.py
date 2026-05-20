"""
Weekday ET schedules for pre-market engine + dashboard cache warm (APScheduler).

Enable: MARKET_SCHEDULER_ON=1 (or true/yes/on)

Pre-market (Mon–Fri ET): 4:00, 6:00, 7:00, 8:00, 8:30, 9:00, 9:15
  → writes pre_market_latest.json under DATA_ROOT

Dashboard warm (Mon–Fri ET): 8:30, then every N min from 9:30 through 15:45 (N = DASHBOARD_WARM_INTERVAL_MIN, default 25)
  → runs full pipeline in-process (same as GET /api/dashboard?refresh=true)

After-hours earnings (Mon–Fri ET): 4:30 PM and 6:00 PM — only if portfolio∪watchlist has earnings today
  → writes after_hours_latest.json + merges after_hours_earnings into dashboard cache

Timezone: MARKET_SCHEDULER_TZ (default America/New_York)
"""
from __future__ import annotations

import logging
import os
from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("api.market_scheduler")

_scheduler: BackgroundScheduler | None = None

# Pre-market runs (hour, minute) Eastern, weekdays
PREMARKET_TIMES_ET: tuple[tuple[int, int], ...] = (
    (4, 0),
    (6, 0),
    (7, 0),
    (8, 0),
    (8, 30),
    (9, 0),
    (9, 15),
)


def _dashboard_warm_interval_min() -> int:
    """Minutes between dashboard warm runs (9:30–15:45 ET). Env DASHBOARD_WARM_INTERVAL_MIN, default 25."""
    raw = (os.environ.get("DASHBOARD_WARM_INTERVAL_MIN") or "").strip()
    if raw:
        try:
            return max(10, min(60, int(raw)))
        except ValueError:
            pass
    return 25


def _dashboard_warm_times_et() -> list[tuple[int, int]]:
    """8:30 AM + every N minutes from 9:30 through 15:45 ET."""
    step = _dashboard_warm_interval_min()
    times: list[tuple[int, int]] = [(8, 30)]
    hour, minute = 9, 30
    while (hour, minute) <= (15, 45):
        if (hour, minute) not in times:
            times.append((hour, minute))
        minute += step
        if minute >= 60:
            hour += minute // 60
            minute = minute % 60
    return times


def _run_premarket_job() -> None:
    try:
        from scripts.pre_market_scheduler import run_premarket_snapshot

        result = run_premarket_snapshot(force=False)
        if result is None:
            logger.info("[market-scheduler] pre-market skipped (outside window)")
        else:
            logger.info(
                "[market-scheduler] pre-market ok bias=%s score=%+.3f signals=%d",
                result.get("bias"),
                float(result.get("composite_score") or 0),
                len(result.get("signals") or []),
            )
    except Exception:
        logger.exception("[market-scheduler] pre-market job failed")


def _run_dashboard_warm_job() -> None:
    try:
        from api.routers.dashboard import _compute_full_dashboard_sync

        t0 = __import__("time").perf_counter()
        _compute_full_dashboard_sync()
        logger.info(
            "[market-scheduler] dashboard warm ok (%.0f ms)",
            (__import__("time").perf_counter() - t0) * 1000,
        )
    except Exception:
        logger.exception("[market-scheduler] dashboard warm job failed")


def _run_after_hours_earnings_job(slot: str) -> None:
    try:
        from signals.after_hours_earnings import run_after_hours_earnings_snapshot

        result = run_after_hours_earnings_snapshot(slot=slot)
        if result.get("skipped"):
            logger.info(
                "[market-scheduler] after-hours %s skipped (%s)",
                slot,
                result.get("skip_reason", "none"),
            )
        else:
            logger.info(
                "[market-scheduler] after-hours %s ok %d tickers",
                slot,
                len(result.get("items") or []),
            )
    except Exception:
        logger.exception("[market-scheduler] after-hours %s job failed", slot)


# Earnings-day after-hours quote pass (Mon–Fri ET); skipped when no names report today
AFTER_HOURS_EARNINGS_TIMES_ET: tuple[tuple[str, int, int], ...] = (
    ("430pm", 16, 30),
    ("6pm", 18, 0),
)


def _enabled() -> bool:
    return (os.environ.get("MARKET_SCHEDULER_ON") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def start() -> None:
    global _scheduler
    if not _enabled():
        logger.info(
            "Market scheduler off (set MARKET_SCHEDULER_ON=1 for pre-market + dashboard warm crons)"
        )
        return

    tz_name = (os.environ.get("MARKET_SCHEDULER_TZ") or "America/New_York").strip()
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/New_York")

    from apscheduler.schedulers.background import BackgroundScheduler

    _scheduler = BackgroundScheduler(timezone=tz)

    for hour, minute in PREMARKET_TIMES_ET:
        _scheduler.add_job(
            _run_premarket_job,
            "cron",
            minute=minute,
            hour=hour,
            day_of_week="mon-fri",
            id=f"premarket_{hour:02d}{minute:02d}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=900,
        )

    for hour, minute in _dashboard_warm_times_et():
        _scheduler.add_job(
            _run_dashboard_warm_job,
            "cron",
            minute=minute,
            hour=hour,
            day_of_week="mon-fri",
            id=f"dashboard_warm_{hour:02d}{minute:02d}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1800,
        )

    for slot, hour, minute in AFTER_HOURS_EARNINGS_TIMES_ET:
        _scheduler.add_job(
            partial(_run_after_hours_earnings_job, slot),
            "cron",
            minute=minute,
            hour=hour,
            day_of_week="mon-fri",
            id=f"after_hours_{slot}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=900,
        )

    _scheduler.start()
    warm_times = _dashboard_warm_times_et()
    warm_step = _dashboard_warm_interval_min()
    logger.info(
        "Market scheduler on (%s): pre-market %s; dashboard warm every %d min (%d slots); after-hours earnings %s ET",
        tz_name,
        ", ".join(f"{h}:{m:02d}" for h, m in PREMARKET_TIMES_ET),
        warm_step,
        len(warm_times),
        ", ".join(f"{h}:{m:02d}" for _, h, m in AFTER_HOURS_EARNINGS_TIMES_ET),
    )


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            logger.exception("Market scheduler shutdown")
        _scheduler = None
