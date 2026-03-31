"""
Thrive Alpha Phase 2 — intraday setup, FMP fundamentals (long_term), ATR targets, optional 1m gate.

GET /api/thrive-phase2?ticker=MSFT&fair_value=470&profile=long_term
Uses the same FMP key as the dashboard (`data.fmp_api_key` / `FMP_API_KEY`).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config
from signals.thrive_phase2 import ThriveAlphaPhase2

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_refresh_bool(raw: str | bool) -> bool:
    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    s = str(raw).strip().lower()
    return s in ("true", "1", "yes", "on")


@router.get("/thrive-phase2")
def get_thrive_phase2(
    ticker: str = Query(..., min_length=1, max_length=32, description="Symbol"),
    fair_value: float = Query(..., description="Fair value per share (from your model)"),
    profile: str = Query("long_term", description="long_term | swing | day_short"),
    hmm_bear_pct: float = Query(50.0, ge=0.0, le=100.0),
    interval: str = Query("1h", description="yfinance interval e.g. 1h, 15m"),
    run_backtest: str | bool = Query(
        "false",
        description="For swing/day_short: run ~21d hit-rate gate (slow, ~30s+)",
    ),
    verbose: str | bool = Query("false", description="Print pipeline steps to server log"),
):
    t = ticker.strip().upper()
    if profile not in ("long_term", "swing", "day_short"):
        raise HTTPException(
            status_code=400,
            detail="profile must be one of: long_term, swing, day_short",
        )
    if fair_value <= 0:
        raise HTTPException(status_code=400, detail="fair_value must be positive")

    config = load_config()
    engine = ThriveAlphaPhase2(config)
    try:
        out = engine.analyze(
            t,
            fair_value,
            profile=profile,
            hmm_bear_pct=hmm_bear_pct,
            interval=interval,
            run_backtest=_parse_refresh_bool(run_backtest),
            verbose=_parse_refresh_bool(verbose),
        )
    except Exception as e:
        logger.exception("thrive-phase2 analyze failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    out["module"] = "thrive_phase2"
    return out
