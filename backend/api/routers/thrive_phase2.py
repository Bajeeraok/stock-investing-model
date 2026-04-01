"""
Thrive Alpha Phase 2 — intraday setup, FMP fundamentals (long_term), ATR targets, optional 1m gate.

GET /api/thrive-phase2?ticker=MSFT&fair_value=470&profile=long_term
Uses the same FMP key as the dashboard (`data.fmp_api_key` / `FMP_API_KEY`).

Responses are cached 15m in Redis (when configured). Use refresh=true to bypass.
Rate limit: 30 requests/minute per client IP (abuse protection).
"""
from __future__ import annotations

import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config
from signals.cache import cached_thrive_phase2
from signals.thrive_phase2 import ThriveAlphaPhase2

logger = logging.getLogger(__name__)

router = APIRouter()

# Sliding window: max requests per IP per minute (in-process; multi-worker = per worker)
_RATE_BUCKETS: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 30
_RATE_WINDOW_SEC = 60.0


def _parse_refresh_bool(raw: str | bool) -> bool:
    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    s = str(raw).strip().lower()
    return s in ("true", "1", "yes", "on")


def _rate_allow(client_ip: str) -> bool:
    now = time.time()
    bucket = _RATE_BUCKETS[client_ip]
    while bucket and bucket[0] < now - _RATE_WINDOW_SEC:
        bucket.pop(0)
    if len(bucket) >= _RATE_LIMIT:
        return False
    bucket.append(now)
    return True


@router.get("/thrive-phase2")
def get_thrive_phase2(
    request: Request,
    ticker: str = Query(..., min_length=1, max_length=32, description="Symbol"),
    fair_value: float = Query(..., description="Fair value per share (from your model)"),
    profile: str = Query("long_term", description="long_term | swing | day_short"),
    hmm_bear_pct: float = Query(50.0, ge=0.0, le=100.0),
    interval: str = Query("1h", description="yfinance interval e.g. 1h, 15m"),
    run_backtest: str | bool = Query(
        "false",
        description="For swing/day_short: run ~21d hit-rate gate (slow, ~30s+)",
    ),
    refresh: str | bool = Query("false", description="Bypass Redis cache (same params)"),
    verbose: str | bool = Query("false", description="Print pipeline steps to server log"),
):
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_allow(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests — try again in a minute.",
        )

    t = ticker.strip().upper()
    if profile not in ("long_term", "swing", "day_short"):
        raise HTTPException(
            status_code=400,
            detail="profile must be one of: long_term, swing, day_short",
        )
    if fair_value <= 0:
        raise HTTPException(status_code=400, detail="fair_value must be positive")

    config = load_config()
    force_refresh = _parse_refresh_bool(refresh)
    rb = _parse_refresh_bool(run_backtest)
    vb = _parse_refresh_bool(verbose)

    cache_parts = (
        t,
        profile,
        f"{fair_value:.4f}",
        interval,
        str(int(hmm_bear_pct)),
        str(rb),
    )

    def _run():
        engine = ThriveAlphaPhase2(config)
        return engine.analyze(
            t,
            fair_value,
            profile=profile,
            hmm_bear_pct=hmm_bear_pct,
            interval=interval,
            run_backtest=rb,
            verbose=vb,
        )

    try:
        out = cached_thrive_phase2(cache_parts, _run, force_refresh=force_refresh)
    except Exception as e:
        logger.exception("thrive-phase2 analyze failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    out["module"] = "thrive_phase2"
    out["cache_bypassed"] = force_refresh
    return out
