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


def _gc_after_jobs_enabled() -> bool:
    raw = (os.environ.get("MEMORY_GC_AFTER_JOBS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


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
        collected = gc.collect()
    stats["gc_collected"] = collected
    stats["rss_mb_after"] = process_rss_mb()
    return stats


def process_rss_mb() -> float | None:
    """Resident set size in MB (Linux / Railway). None when unavailable."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # Linux: ru_maxrss is kilobytes; macOS: bytes
        rss = usage.ru_maxrss
        if rss > 10_000_000:
            return round(rss / (1024 * 1024), 1)
        return round(rss / 1024, 1)
    except Exception:
        pass
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024, 1)
    except Exception:
        pass
    return None


def memory_snapshot() -> dict[str, Any]:
    """Lightweight stats for GET /api/health/memory."""
    snap: dict[str, Any] = {"rss_mb": process_rss_mb()}
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
