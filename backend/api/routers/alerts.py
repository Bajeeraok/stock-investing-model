from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Query

logger = logging.getLogger("api.alerts")
router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent


@router.get("/alerts/status")
def alerts_status():
    """Worker status (last scan time, duration, etc.)."""
    try:
        from alerts.events import AlertEventStore
        store = AlertEventStore(data_root=ROOT / "data")
        return store.read_status() or {"status": "no_status"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/alerts/feed")
def alerts_feed(limit: int = Query(200, ge=1, le=1000)):
    """Recent alerts feed (most recent first)."""
    try:
        from alerts.events import AlertEventStore
        store = AlertEventStore(data_root=ROOT / "data")
        return {"events": store.read_events(limit=limit)}
    except Exception as e:
        return {"events": [], "error": str(e)}


@router.get("/alerts/latest")
def alerts_latest():
    """Latest watchlist scan snapshot (macro + per-symbol signals)."""
    try:
        from alerts.events import AlertEventStore
        store = AlertEventStore(data_root=ROOT / "data")
        return store.read_latest() or {"status": "no_latest"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

