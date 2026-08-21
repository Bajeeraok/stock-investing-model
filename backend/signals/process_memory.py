"""
In-process memory hygiene for long-running Railway / uvicorn workers.

Python GC runs automatically; this module releases *our* retained caches (OHLCV,
HMM models) and optionally calls gc.collect() after heavy dashboard jobs.
"""
from __future__ import annotations

import gc
import logging
import os
from typing import Any

logger = logging.getLogger("signals.process_memory")


def dashboard_parallel_max_workers() -> int:
    """Cap ThreadPoolExecutor workers during dashboard compute (lower on Railway)."""
    raw = (os.environ.get("DASHBOARD_PARALLEL_MAX_WORKERS") or "").strip()
    if raw:
        try:
            return max(2, min(16, int(raw)))
        except ValueError:
            pass
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_NAME"):
        return 4
    return 12


def _gc_after_jobs_enabled() -> bool:
    raw = (os.environ.get("MEMORY_GC_AFTER_JOBS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _malloc_trim() -> bool:
    """Return freed heap pages to the OS (Linux glibc). No-op elsewhere."""
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6")
        return bool(libc.malloc_trim(0))
    except Exception:
        return False


def release_process_caches(*, aggressive: bool = False) -> dict[str, Any]:
    """
    Drop expired / excess in-process caches. Returns counts for logging / health.
    aggressive=True also clears HMM in-memory model cache (refetched from disk on next use).
    """
    stats: dict[str, Any] = {}

    try:
        from signals.fetcher import prune_info_cache

        stats["info"] = prune_info_cache()
    except Exception as e:
        stats["info"] = {"error": str(e)}

    try:
        from signals.fetcher import clear_ohlcv_cache, prune_ohlcv_cache

        stats["ohlcv"] = clear_ohlcv_cache() if aggressive else prune_ohlcv_cache()
    except Exception as e:
        stats["ohlcv"] = {"error": str(e)}

    if aggressive:
        try:
            from signals.fetcher import clear_yfinance_process_caches

            stats["yfinance"] = clear_yfinance_process_caches()
        except Exception as e:
            stats["yfinance"] = {"error": str(e)}
        try:
            from signals.forward_tracking import clear_eod_snapshot_mem_cache

            stats["eod_snapshot_mem"] = clear_eod_snapshot_mem_cache()
        except Exception as e:
            stats["eod_snapshot_mem"] = {"error": str(e)}
        try:
            from signals.providers import clear_providers_lru_caches

            stats["providers_lru"] = clear_providers_lru_caches()
        except Exception as e:
            stats["providers_lru"] = {"error": str(e)}
        try:
            from signals.hmm_regime import trim_hmm_model_cache

            stats["hmm_models"] = trim_hmm_model_cache(keep=0)
        except Exception as e:
            stats["hmm_models"] = {"error": str(e)}
        try:
            from signals.ml_models import trim_lgbm_model_cache

            stats["lgbm_models"] = trim_lgbm_model_cache(keep=0)
        except Exception as e:
            stats["lgbm_models"] = {"error": str(e)}

    collected = 0
    if _gc_after_jobs_enabled():
        collected = gc.collect(2)
    stats["gc_collected"] = collected
    if aggressive:
        stats["malloc_trim"] = _malloc_trim()
    rss = process_rss_snapshot()
    stats["rss_mb"] = rss.get("rss_mb")
    stats["rss_mb_peak"] = rss.get("rss_mb_peak")
    # Back-compat for log parsers expecting rss_mb_after
    stats["rss_mb_after"] = rss.get("rss_mb")
    return stats


def _read_proc_rss_kb() -> int | None:
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return None


def _read_peak_rss_kb() -> int | None:
    """Linux ru_maxrss is peak RSS in KB; macOS uses bytes."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = usage.ru_maxrss
        if rss > 10_000_000:
            return int(rss / 1024)
        return int(rss)
    except Exception:
        return None


def process_rss_mb() -> float | None:
    """Current resident set size in MB (Linux / Railway). None when unavailable."""
    kb = _read_proc_rss_kb()
    if kb is not None:
        return round(kb / 1024, 1)
    peak_kb = _read_peak_rss_kb()
    if peak_kb is not None:
        return round(peak_kb / 1024, 1)
    return None


def process_rss_snapshot() -> dict[str, float | None]:
    """Current RSS + process peak RSS (for post-job logs and /api/health/memory)."""
    current_kb = _read_proc_rss_kb()
    peak_kb = _read_peak_rss_kb()
    return {
        "rss_mb": round(current_kb / 1024, 1) if current_kb is not None else None,
        "rss_mb_peak": round(peak_kb / 1024, 1) if peak_kb is not None else None,
    }


def memory_snapshot() -> dict[str, Any]:
    """Lightweight stats for GET /api/health/memory."""
    rss = process_rss_snapshot()
    snap: dict[str, Any] = dict(rss)
    try:
        from signals.fetcher import info_cache_stats, ohlcv_cache_stats

        snap["ohlcv_cache"] = ohlcv_cache_stats()
        snap["info_cache"] = info_cache_stats()
    except Exception as e:
        snap["ohlcv_cache"] = {"error": str(e)}
    try:
        from signals.hmm_regime import hmm_model_cache_stats

        snap["hmm_model_cache"] = hmm_model_cache_stats()
    except Exception as e:
        snap["hmm_model_cache"] = {"error": str(e)}
    try:
        from signals.ml_models import lgbm_model_cache_stats

        snap["lgbm_model_cache"] = lgbm_model_cache_stats()
    except Exception as e:
        snap["lgbm_model_cache"] = {"error": str(e)}
    return snap


def _idle_trim_interval_sec() -> float:
    raw = (os.environ.get("MEMORY_IDLE_TRIM_SEC") or "").strip()
    if raw:
        try:
            return max(60.0, min(3600.0, float(raw)))
        except ValueError:
            pass
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_NAME"):
        return 900.0  # 15 min
    return 0.0  # off locally unless env set


def _idle_trim_rss_mb() -> float:
    raw = (os.environ.get("MEMORY_IDLE_TRIM_RSS_MB") or "").strip()
    if raw:
        try:
            return max(400.0, float(raw))
        except ValueError:
            pass
    return 1200.0


def start_idle_memory_trim_loop() -> bool:
    """
    Daemon: when no dashboard refresh is running and RSS is high, aggressively
    release in-process caches + malloc_trim. Does not fix native fragmentation
    entirely, but knocks the sawtooth down between warms.
    """
    import threading
    import time

    interval = _idle_trim_interval_sec()
    if interval <= 0:
        return False

    def _loop() -> None:
        while True:
            time.sleep(interval)
            try:
                from api.dashboard_job import is_refresh_running

                if is_refresh_running():
                    continue
            except Exception:
                pass
            rss = process_rss_mb()
            if rss is None or rss < _idle_trim_rss_mb():
                continue
            try:
                stats = release_process_caches(aggressive=True)
                logger.info(
                    "[memory] idle trim rss_before=%.0f stats=%s",
                    rss,
                    {k: stats.get(k) for k in ("ohlcv", "hmm_models", "lgbm_models", "rss_mb", "malloc_trim")},
                )
            except Exception:
                logger.debug("[memory] idle trim failed", exc_info=True)

    threading.Thread(target=_loop, name="memory-idle-trim", daemon=True).start()
    logger.info(
        "[memory] idle trim loop on interval=%.0fs threshold_rss_mb=%.0f",
        interval,
        _idle_trim_rss_mb(),
    )
    return True
