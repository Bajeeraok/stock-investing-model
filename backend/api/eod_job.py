"""
Single-flight background full EOD snapshot (~100 tickers).
Used by the 8pm scheduler and as a safety net after dashboard refresh post-close.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("api.eod_job")

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "last_trigger_date": None}


def is_eod_job_running() -> bool:
    with _lock:
        return bool(_state.get("running"))


def trigger_full_eod_background_if_missing(*, min_hour_et: int = 20) -> bool:
    """
    Start full EOD in a daemon thread when today's full cohort snapshot is missing.
    Returns True if a new background job was started.
    """
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from config_loader import load_config
        from scripts.run_daily import full_eod_snapshot_exists, is_us_equity_session_day

        now = datetime.now(ZoneInfo("America/New_York"))
        date_str = now.strftime("%Y-%m-%d")
        if not is_us_equity_session_day(date_str):
            return False
        if now.hour < min_hour_et:
            return False

        config = load_config()
        if full_eod_snapshot_exists(date_str, config):
            return False
    except Exception as exc:
        logger.debug("[eod-job] preflight skipped: %s", exc)
        return False

    with _lock:
        if _state.get("running"):
            return False
        if _state.get("last_trigger_date") == date_str:
            return False
        _state["running"] = True
        _state["last_trigger_date"] = date_str

    def _worker() -> None:
        try:
            from config_loader import load_config
            from scripts.run_daily import run_eod_snapshot_only

            logger.info("[eod-job] background full EOD START date=%s", date_str)
            result = run_eod_snapshot_only(load_config(), snapshot_date=date_str)
            if result.get("error"):
                logger.error("[eod-job] failed: %s", result["error"])
            elif result.get("skipped"):
                logger.info("[eod-job] skipped: %s", result.get("reason"))
            else:
                logger.info(
                    "[eod-job] ok date=%s tickers=%s path=%s",
                    result.get("snapshot_date"),
                    result.get("tickers_count"),
                    result.get("snapshot_path"),
                )
        except Exception:
            logger.exception("[eod-job] background run failed")
        finally:
            with _lock:
                _state["running"] = False

    threading.Thread(target=_worker, name="eod-full-snapshot", daemon=True).start()
    return True
