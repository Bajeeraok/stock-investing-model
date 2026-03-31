"""
Hurst/regime weights and optional score-inversion diagnostic (bucket stats).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config
from signals.fetcher import fetch_ohlcv_safe
from signals.signal_inversion import (
    BucketStats,
    RawSignals,
    compute_hurst_exponent,
    classify_regime,
    get_regime_weights,
    run_inversion_diagnostic,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class BucketStatIn(BaseModel):
    bucket: str = Field(..., description="strong | buy | neutral | weak")
    mean_return: float
    hit_rate: float = 0.0
    n: int


class SignalDiagnosticsBody(BaseModel):
    bucket_stats: list[BucketStatIn] = Field(default_factory=list)
    horizon: str = "3m"
    raw_signals: dict[str, float] | None = None


def _diagnostics_enabled() -> bool:
    cfg = load_config()
    sd = (cfg.get("retail") or {}).get("signal_diagnostics") or {}
    return bool(sd.get("enabled", True))


@router.get("/signal-diagnostics/{ticker}")
async def get_signal_diagnostics(ticker: str):
    """
    Hurst exponent, asset regime classification, and regime-specific signal weights.
    For full inversion detection, POST bucket_stats from your backtest.
    """
    if not _diagnostics_enabled():
        raise HTTPException(status_code=404, detail="Signal diagnostics disabled in config (retail.signal_diagnostics.enabled).")
    ticker = ticker.upper().strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    config = load_config()
    period = (config.get("data") or {}).get("period", "2y") or "2y"
    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close.dropna()) < 120:
        raise HTTPException(
            status_code=422,
            detail="Insufficient price history for Hurst (need ~120+ daily closes).",
        )
    s = close.dropna()
    hurst = compute_hurst_exponent(s)
    regime = classify_regime(hurst)
    weights = get_regime_weights(regime)
    return {
        "ticker": ticker,
        "hurst_exponent": round(hurst, 4),
        "asset_regime": regime.value,
        "regime_weights": weights.as_dict(),
        "inversion_check": None,
        "hint": "POST the same path with JSON body { bucket_stats: [...] } for inversion detection.",
    }


@router.post("/signal-diagnostics/{ticker}")
async def post_signal_diagnostics(ticker: str, body: SignalDiagnosticsBody):
    """
    Full diagnostic: Hurst + regime weights + optional inversion guard + optional regime-aware score.
    """
    if not _diagnostics_enabled():
        raise HTTPException(status_code=404, detail="Signal diagnostics disabled in config (retail.signal_diagnostics.enabled).")
    ticker = ticker.upper().strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="Invalid ticker")
    config = load_config()
    period = (config.get("data") or {}).get("period", "2y") or "2y"
    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close.dropna()) < 120:
        raise HTTPException(
            status_code=422,
            detail="Insufficient price history for Hurst (need ~120+ daily closes).",
        )

    stats = [
        BucketStats(
            bucket=b.bucket,
            mean_return=b.mean_return,
            hit_rate=b.hit_rate,
            n=b.n,
        )
        for b in body.bucket_stats
    ]
    raw = None
    if body.raw_signals:
        try:
            raw = RawSignals(
                hmm_regime=float(body.raw_signals.get("hmm_regime", 50)),
                momentum=float(body.raw_signals.get("momentum", 50)),
                technicals=float(body.raw_signals.get("technicals", 50)),
                fundamentals=float(body.raw_signals.get("fundamentals", 50)),
                options_sentiment=float(body.raw_signals.get("options_sentiment", 50)),
                insider_activity=float(body.raw_signals.get("insider_activity", 50)),
                news_sentiment=float(body.raw_signals.get("news_sentiment", 50)),
            )
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid raw_signals: {e}") from e

    try:
        report = run_inversion_diagnostic(
            ticker,
            close.dropna(),
            stats,
            current_signals=raw,
            horizon=body.horizon,
        )
    except Exception as e:
        logger.exception("signal-diagnostics failed for %s", ticker)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return report
