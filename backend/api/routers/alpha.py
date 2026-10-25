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
