"""
FastAPI backend for Stock Investing Model dashboard.
Run from backend folder: cd backend && uvicorn api.main:app --reload --port 8002
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

EST = ZoneInfo("America/New_York")


class ESTFormatter(logging.Formatter):
    """Format log timestamps in Eastern (EST/EDT)."""
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=EST)
        fmt = datefmt or self.datefmt or "%Y-%m-%d %H:%M:%S"
        return dt.strftime(fmt)


# Configure logging with EST timestamps
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(ESTFormatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
logger = logging.getLogger("api")

try:
    from signals.fetcher import configure_yfinance_log_noise

    configure_yfinance_log_noise()
except Exception:
    pass

logger.info("Backend starting: setting up paths...")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logger.info("Backend: importing FastAPI and middleware...")
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


def _sanitize_floats(obj: Any) -> Any:
    """Recursively replace non-finite floats (inf, -inf, nan) with None so json.dumps never raises."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_floats(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    """JSONResponse that strips inf/nan before serialization."""
    def render(self, content: Any) -> bytes:
        return json.dumps(
            _sanitize_floats(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

logger.info("Backend: importing dashboard router...")
from api.routers import dashboard, chat, alerts, scanner, signal_diagnostics, thrive_phase2, push, income_book, dev_tools, article_ingest, alpha
from api import eod_scheduler

logger.info("Backend: imports complete.")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        logger.info("→ %s %s", request.method, request.url.path)
        try:
            response = await call_next(request)
            logger.info("← %s %s %s", request.method, request.url.path, response.status_code)
            return response
        except Exception as e:
            # logger.exception includes traceback; prefix with type for quick grep in Railway logs
            logger.exception(
                "← %s %s ERROR [%s]: %s",
                request.method,
                request.url.path,
                type(e).__name__,
                e,
            )
            raise


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    startup()
    try:
        yield
    finally:
        shutdown()


app = FastAPI(
    lifespan=_lifespan,
    title="Stock Investing Model API",
    description="Decision-support dashboard for retail investors",
    version="1.0.0",
    default_response_class=SafeJSONResponse,
)

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001")
app.add_middleware(RequestLogMiddleware)
# Compress JSON responses — dashboard / analysis / ticker-detail payloads run to several MB and
# every byte to the web service (or browser) is billed egress on Railway. The Next proxy reads
# res.text(), which transparently decompresses, so no client change is needed.
from starlette.middleware.gzip import GZipMiddleware  # noqa: E402

app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(income_book.router, prefix="/api", tags=["income-book"])
app.include_router(dev_tools.router, prefix="/api", tags=["dev"])
app.include_router(thrive_phase2.router, prefix="/api", tags=["thrive-phase2"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(alerts.router, prefix="/api", tags=["alerts"])
app.include_router(scanner.router, prefix="/api", tags=["scanner"])
app.include_router(signal_diagnostics.router, prefix="/api", tags=["signal-diagnostics"])
app.include_router(push.router, prefix="/api", tags=["push"])
app.include_router(article_ingest.router, prefix="/api", tags=["ingest"])
app.include_router(alpha.router, prefix="/api", tags=["alpha"])


def _warm_dashboard_background():
    """Optional: after delay, GET WARM_DASHBOARD_URL to populate Redis (same as cron warm script)."""
    delay_s = float((os.getenv("WARM_DASHBOARD_DELAY_SECONDS") or "8").strip() or "8")
    url = (os.getenv("WARM_DASHBOARD_URL") or "").strip()
    if not url:
        return
    if "refresh=" not in url:
        url = f"{url}{'&' if '?' in url else '?'}refresh=true"
    time.sleep(max(1.0, delay_s))
    try:
        import requests

        r = requests.get(url, timeout=900)
        logger.info("Warm dashboard: %s → HTTP %s", url[:80], r.status_code)
    except Exception as e:
        logger.warning("Warm dashboard failed (%s): %s", url[:80], e)


def _startup_background_refresh(delay_s: float = 10.0, max_age_min: float = 20.0) -> None:
    """
    In-process startup refresh.  Runs after `delay_s` seconds so the app is
    fully listening before the heavy compute starts.

    Skips the refresh when the cached dashboard is fresher than `max_age_min`
    minutes (env: STARTUP_REFRESH_MAX_AGE_MIN, default 20) — avoids a
    redundant recompute on rapid restarts / health-check bounces.

    Set STARTUP_REFRESH_ENABLED=0 to disable entirely.
    """
    enabled = (os.getenv("STARTUP_REFRESH_ENABLED") or "1").strip().lower()
    if enabled in ("0", "false", "no", "off"):
        return

    override_age = os.getenv("STARTUP_REFRESH_MAX_AGE_MIN")
    if override_age:
        try:
            max_age_min = float(override_age)
        except ValueError:
            pass

    time.sleep(max(1.0, delay_s))

    try:
        from alerts.market_hours import is_signal_warm_window

        if not is_signal_warm_window():
            logger.info(
                "[startup] outside 8:30–16:00 ET — skip heavy refresh; serving last snapshot until next warm window"
            )
            return
    except Exception:
        pass

    # Check cache freshness before triggering
    try:
        from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot
        cached = get_cached_dashboard() or get_last_dashboard_snapshot()
        if cached and isinstance(cached, dict):
            as_of = cached.get("as_of_date") or cached.get("run_date")
            if as_of:
                import datetime as _dt
                try:
                    ts = _dt.datetime.fromisoformat(str(as_of).rstrip("Z"))
                    age_min = (_dt.datetime.utcnow() - ts).total_seconds() / 60.0
                    if age_min < max_age_min:
                        logger.info(
                            "[startup] dashboard cache is %.0f min old (< %.0f min threshold) — skipping auto-refresh",
                            age_min, max_age_min,
                        )
                        return
                    logger.info(
                        "[startup] dashboard cache is %.0f min old — triggering background refresh",
                        age_min,
                    )
                except Exception:
                    pass
    except Exception:
        pass

    try:
        from api.dashboard_warm import compute_for_background_refresh
        from api.dashboard_job import trigger_background_refresh

        started = trigger_background_refresh(compute_for_background_refresh)
        if started:
            logger.info("[startup] background dashboard refresh triggered")
        else:
            logger.info("[startup] background dashboard refresh already running — skipped")
    except Exception as e:
        logger.warning("[startup] background refresh failed to start: %s", e)


def startup():
    logger.info("FastAPI server startup complete. Listening for requests on /api/*")
    try:
        import asyncio
        from api.dashboard_hub import set_event_loop

        set_event_loop(asyncio.get_event_loop())
    except Exception as e:
        logger.warning("Dashboard WebSocket hub loop setup failed: %s", e)
    try:
        scanner.startup_scanner()
    except Exception as e:
        logger.warning("Scanner startup failed: %s", e)
    # Always trigger in-process background refresh on startup (if cache is stale).
    # Falls back to no-op when cache is fresh (<20 min) or already running.
    threading.Thread(target=_startup_background_refresh, name="startup-refresh", daemon=True).start()
    # Legacy HTTP-based warm (optional, requires WARM_DASHBOARD_ON_STARTUP=1 + WARM_DASHBOARD_URL)
    if (os.getenv("WARM_DASHBOARD_ON_STARTUP") or "").strip().lower() in ("1", "true", "yes", "on"):
        t = threading.Thread(target=_warm_dashboard_background, name="warm-dashboard", daemon=True)
        t.start()
    try:
        eod_scheduler.start()
    except Exception as e:
        logger.warning("EOD scheduler failed to start: %s", e)

    def _startup_eod_catchup(delay_s: float | None = None) -> None:
        # After the 8pm ET session, catch up quickly so a late deploy still writes today.
        if delay_s is None:
            try:
                from datetime import datetime
                from zoneinfo import ZoneInfo

                hour = datetime.now(ZoneInfo("America/New_York")).hour
                delay_s = 15.0 if hour >= 20 else 90.0
            except Exception:
                delay_s = 90.0
        time.sleep(delay_s)
        try:
            from api.eod_job import trigger_full_eod_background_if_missing

            queued = trigger_full_eod_background_if_missing(min_hour_et=20)
            logger.info("[startup] stale EOD session catch-up queued=%s (delay=%.0fs)", queued, delay_s)
        except Exception as e:
            logger.warning("[startup] EOD catch-up failed: %s", e)

    threading.Thread(target=_startup_eod_catchup, name="eod-catchup", daemon=True).start()
    try:
        from signals.process_memory import start_idle_memory_trim_loop

        start_idle_memory_trim_loop()
    except Exception as e:
        logger.warning("Idle memory trim failed to start: %s", e)
    try:
        from api import market_scheduler

        market_scheduler.start()
    except Exception as e:
        logger.warning("Market scheduler failed to start: %s", e)


def shutdown():
    try:
        eod_scheduler.shutdown()
    except Exception:
        pass
    try:
        from api import market_scheduler

        market_scheduler.shutdown()
    except Exception:
        pass
    try:
        scanner.shutdown_scanner()
    except Exception:
        pass
    try:
        from signals.cache import close_redis_pool

        close_redis_pool()
    except Exception:
        pass
    try:
        from signals.http_session import close_requests_session

        close_requests_session()
    except Exception:
        pass


@app.get("/api/health")
def health():
    from signals.time_et import now_iso_et
    from api.eod_scheduler import scheduler_status

    sched = scheduler_status()
    return {
        "status": "ok",
        "timestamp": now_iso_et(),
        "eod_scheduler": {
            "enabled": sched.get("enabled"),
            "running": sched.get("running"),
            "cron": sched.get("cron"),
            "tz": sched.get("tz"),
            "next_run_at": sched.get("next_run_at"),
            "off_reason": sched.get("off_reason"),
        },
    }


@app.get("/api/health/memory")
def health_memory():
    """Process RSS + in-process cache sizes (Railway memory debugging)."""
    from signals.process_memory import memory_snapshot
    from signals.time_et import now_iso_et

    snap = memory_snapshot()
    snap["status"] = "ok"
    snap["timestamp"] = now_iso_et()
    return snap
