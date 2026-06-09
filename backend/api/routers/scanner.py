from __future__ import annotations

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from scanner.engine import ScannerAdapter
from scanner.store import ScannerStore
from scanner.data_provider import make_default_provider
from scanner.ticker_universe import AlertType, ScanPriority, TIER1_SYMBOLS, TIER1_UNIVERSE, SURFACING_THRESHOLDS

logger = logging.getLogger("api.scanner")
router = APIRouter()

ROOT = Path(__file__).resolve().parent.parent.parent
_adapter: Optional[ScannerAdapter] = None


def get_adapter() -> ScannerAdapter:
    global _adapter
    if _adapter is None:
        _adapter = ScannerAdapter(store=ScannerStore(data_root=ROOT / "data"))
    return _adapter


def startup_scanner() -> None:
    """
    Start the scanner scheduler inside the FastAPI process.
    Default: enabled (no Railway worker required).
    Set SCANNER_AUTOSTART=false to disable.
    """
    if os.getenv("SCANNER_AUTOSTART", "true").lower() != "true":
        logger.info("[scanner] autostart disabled (SCANNER_AUTOSTART=false)")
        return
    a = get_adapter()
    snaps, wl, macro = make_default_provider()
    a.start(data_provider=snaps, watchlist_provider=wl, macro_provider=macro)
    logger.info("[scanner] started")


def shutdown_scanner() -> None:
    try:
        get_adapter().stop()
    except Exception:
        pass


@router.get("/scanner/alerts")
def get_alerts(
    limit: int = Query(50, ge=1, le=200),
    ticker: Optional[str] = Query(None),
    priority: Optional[str] = Query(None, description="CRITICAL | HIGH | MEDIUM | LOW"),
    dismissed: bool = Query(False),
):
    pr = None
    if priority:
        try:
            pr = ScanPriority[priority.upper()]
        except KeyError:
            raise HTTPException(400, f"Invalid priority: {priority}")
    return get_adapter().get_alerts(limit=limit, ticker=ticker, priority=pr, include_dismissed=dismissed)


@router.post("/scanner/alerts/{alert_id}/dismiss")
def dismiss(alert_id: str):
    get_adapter().dismiss(alert_id)
    return {"dismissed": True, "alert_id": alert_id}


@router.get("/scanner/stats")
def stats():
    return {
        **(get_adapter().stats or {}),
        "universe_size": len(TIER1_SYMBOLS),
        "as_of": __import__("signals.time_et", fromlist=["now_iso_et"]).now_iso_et(),
    }


@router.get("/scanner/universe")
def universe():
    return {
        "total": len(TIER1_UNIVERSE),
        "tickers": [{"symbol": t.symbol, "name": t.name, "sector": t.sector, "tier": t.tier, "min_price": t.min_price} for t in TIER1_UNIVERSE],
    }


@router.get("/scanner/thresholds")
def thresholds():
    from dataclasses import asdict
    return {k.value: asdict(v) for k, v in SURFACING_THRESHOLDS.items()}

