"""
Weekday ET schedules for pre-market engine + retail dashboard refresh (APScheduler).

Enable: MARKET_SCHEDULER_ON=1 (or true/yes/on)

Pre-market (Mon–Fri ET): 4:00, 6:00, 7:00, 8:00, 8:30, 9:00, 9:15
  → writes pre_market_latest.json under DATA_ROOT

Retail refresh (Mon–Fri ET):
  - Quote tick every DASHBOARD_QUOTE_TICK_MIN (default 5) during regular session (9:30–16:00)
  - Signal warm every DASHBOARD_WARM_INTERVAL_MIN (default 30) from 8:30 through 16:00

After-hours earnings (Mon–Fri ET): 4:30 PM and 6:00 PM — only if portfolio∪watchlist has earnings today
  → writes after_hours_latest.json + merges after_hours_earnings into dashboard cache

Timezone: MARKET_SCHEDULER_TZ (default America/New_York)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, time
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
    """Minutes between signal warm runs (8:30–16:00 ET weekdays). Env DASHBOARD_WARM_INTERVAL_MIN, default 30."""
    raw = (os.environ.get("DASHBOARD_WARM_INTERVAL_MIN") or "").strip()
    if raw:
        try:
            return max(10, min(60, int(raw)))
        except ValueError:
            pass
    return 30


def _dashboard_quote_tick_min() -> int:
    """Minutes between quote ticks during regular session. Env DASHBOARD_QUOTE_TICK_MIN, default 5."""
    raw = (os.environ.get("DASHBOARD_QUOTE_TICK_MIN") or "").strip()
    if raw:
        try:
            return max(1, min(15, int(raw)))
        except ValueError:
            pass
    return 5


def _scheduler_tz():
    tz_name = (os.environ.get("MARKET_SCHEDULER_TZ") or "America/New_York").strip()
    from zoneinfo import ZoneInfo

    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/New_York")


def _is_signal_warm_window() -> bool:
    """Weekday 8:30–16:00 ET — includes pre-open warm at 8:30."""
    from alerts.market_hours import ET, is_weekday

    dt = datetime.now(ET)
    if not is_weekday(dt):
        return False
    t = dt.timetz().replace(tzinfo=None)
    return time(8, 30) <= t < time(16, 0)


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


def _run_signal_warm_job() -> None:
    if not _is_signal_warm_window():
        logger.info("[market-scheduler] signal warm skipped (outside 8:30–16:00 ET weekday window)")
        return
    try:
        from api.dashboard_job import is_refresh_running, trigger_background_refresh
        from api.dashboard_warm import compute_signal_warm_sync

        if is_refresh_running():
            logger.info("[market-scheduler] signal warm skipped — refresh already running")
            return
        t0 = __import__("time").perf_counter()
        started = trigger_background_refresh(compute_signal_warm_sync)
        if not started:
            logger.info("[market-scheduler] signal warm coalesced — refresh already running")
            return
        logger.info(
            "[market-scheduler] signal warm job started (async, %.0f ms to dispatch)",
            (__import__("time").perf_counter() - t0) * 1000,
        )
    except Exception:
        logger.exception("[market-scheduler] signal warm job failed")


def _run_quote_tick_job() -> None:
    try:
        from alerts.market_hours import is_us_market_hours

        if not is_us_market_hours():
            return
        t0 = __import__("time").perf_counter()
        from api.dashboard_warm import compute_quote_tick_sync

        result = compute_quote_tick_sync()
        if result is not None:
            logger.info(
                "[market-scheduler] quote tick ok (%.0f ms)",
                (__import__("time").perf_counter() - t0) * 1000,
            )
    except Exception:
        logger.exception("[market-scheduler] quote tick job failed")


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

    tz = _scheduler_tz()
    tz_name = str(getattr(tz, "key", tz))

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

    warm_step = _dashboard_warm_interval_min()
    quote_step = _dashboard_quote_tick_min()

    _scheduler.add_job(
        _run_signal_warm_job,
        "interval",
        minutes=warm_step,
        id="dashboard_signal_warm",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )

    _scheduler.add_job(
        _run_quote_tick_job,
        "interval",
        minutes=quote_step,
        id="dashboard_quote_tick",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
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
    logger.info(
        "Market scheduler on (%s): pre-market %s; quote tick every %d min (session); "
        "signal warm every %d min (8:30–16:00 ET); after-hours earnings %s ET",
        tz_name,
        ", ".join(f"{h}:{m:02d}" for h, m in PREMARKET_TIMES_ET),
        quote_step,
        warm_step,
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
