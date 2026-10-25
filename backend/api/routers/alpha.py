"""Benchmark-relative alpha endpoints: pooled-model picks, model metrics, cohorts, drift."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()
ALPHA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "alpha"


def _read_json(name: str) -> dict | None:
    p = ALPHA_DIR / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@router.get("/alpha/picks")
def alpha_picks():
    return _read_json("latest_picks.json") or {"picks": [], "note": "run scripts/alpha_daily.py"}


@router.get("/alpha/model")
def alpha_model():
    return _read_json("pooled_model.json") or {"note": "run scripts/train_alpha_model.py"}


@router.get("/alpha/cohorts")
def alpha_cohorts():
    return _read_json("cohort_expectancy.json") or {"cohorts": {}, "note": "run scripts/build_cohort_expectancy.py"}


@router.get("/alpha/drift")
def alpha_drift():
    return _read_json("drift_report.json") or {"status": "unknown", "note": "run scripts/alpha_daily.py"}


@router.get("/allocation")
def alpha_allocation() -> dict:
    """SPY core / satellite split from the trend-regime rule (see signals/alpha/core_satellite.py)."""
    from signals.alpha.core_satellite import allocation, satellite_validated
    from config_loader import load_config
    from signals.fetcher import _fetch_index_etf_history_frame

    hist = _fetch_index_etf_history_frame("SPY", "2y")
    if hist is None or hist.empty:
        return {"status": "unavailable"}
    cfg = (load_config() or {}).get("core_satellite") or {}
    out = allocation(hist["Close"], satellite_validated=satellite_validated(ALPHA_DIR), cfg=cfg)
    out["backtest"] = _read_json("regime_allocation_backtest.json")
    return out
