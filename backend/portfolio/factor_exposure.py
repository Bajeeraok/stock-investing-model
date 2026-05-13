"""
Factor exposure breakdown — portfolio-level factor tilts using fundamental proxies.

Factors:
  - Momentum: 12-month price return
  - Value:    1 / trailing PE (high PE = low value)
  - Size:     log(market cap) inverted (small = high score)
  - Growth:   forward PE discount vs trailing PE, or revenue growth
  - Quality:  ROE + operating margin

Each holding gets a 0-100 percentile score per factor, then
portfolio exposure = weighted average of scores.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# ETFs get fixed factor profiles
_ETF_PROFILES: dict[str, dict[str, float]] = {
    "SPY":  {"momentum": 50, "value": 50, "size": 10, "growth": 50, "quality": 60},
    "QQQ":  {"momentum": 70, "value": 25, "size": 10, "growth": 75, "quality": 65},
    "IWM":  {"momentum": 40, "value": 55, "size": 90, "growth": 40, "quality": 40},
    "GLD":  {"momentum": 50, "value": 0,  "size": 0,  "growth": 0,  "quality": 0},
    "SLV":  {"momentum": 50, "value": 0,  "size": 0,  "growth": 0,  "quality": 0},
    "OIH":  {"momentum": 40, "value": 65, "size": 50, "growth": 30, "quality": 45},
}


def _score_momentum(return_12m: float | None) -> float:
    """0-100 score based on 12-month return. 0%=50, +50%=85, -30%=20."""
    if return_12m is None:
        return 50
    return max(0, min(100, 50 + return_12m * 0.7))


def _score_value(pe: float | None) -> float:
    """0-100 score: PE 10 = 90 (deep value), PE 30 = 50, PE 60+ = 10 (expensive)."""
    if pe is None or pe <= 0:
        return 30  # negative/missing PE → uncertain
    if pe < 5:
        return 95
    if pe > 80:
        return 5
    return max(5, min(95, 100 - pe * 1.2))


def _score_size(mkt_cap: float | None) -> float:
    """0-100: small-cap (high score) to mega-cap (low score). $1B=80, $100B=30, $1T=10."""
    if mkt_cap is None or mkt_cap <= 0:
        return 50
    log_cap = math.log10(max(1e6, mkt_cap))
    # log10(1B) = 9, log10(100B) = 11, log10(1T) = 12
    return max(5, min(95, 130 - log_cap * 10))


def _score_growth(forward_pe: float | None, trailing_pe: float | None) -> float:
    """High growth = forward PE < trailing PE (earnings expected to grow)."""
    if forward_pe and trailing_pe and forward_pe > 0 and trailing_pe > 0:
        discount = (trailing_pe - forward_pe) / trailing_pe * 100
        return max(0, min(100, 50 + discount * 2))
    return 50


def _score_quality(roe: float | None, op_margin: float | None) -> float:
    """ROE > 20% and margin > 25% = high quality."""
    score = 50.0
    if roe is not None:
        score += max(-30, min(30, (roe - 15) * 1.5))
    if op_margin is not None:
        score += max(-20, min(20, (op_margin - 20) * 1.0))
    return max(0, min(100, score))


def compute_factor_exposure(
    per_holding: list[dict],
    total_value: float,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    Compute portfolio-level factor exposure from per-holding fundamentals.

    Returns {
      portfolio_factors: {momentum, value, size, growth, quality},
      per_holding: [{ticker, weight_pct, factors: {...}}],
      dominant_factor, note
    }
    """
    config = config or {}
    holdings = [
        (h["ticker"], h.get("pct", 0) or 0, h.get("value", 0) or 0)
        for h in per_holding
        if h.get("ticker") and h.get("pct") and h["pct"] > 0
    ]

    if not holdings or total_value <= 0:
        return {"portfolio_factors": {}, "per_holding": [], "dominant_factor": None, "note": None}

    per_h_factors: list[dict] = []

    for ticker, weight_pct, value in holdings:
        # Check ETF shortcut
        if ticker in _ETF_PROFILES:
            factors = dict(_ETF_PROFILES[ticker])
            per_h_factors.append({"ticker": ticker, "weight_pct": round(weight_pct, 1), "factors": factors})
            continue

        # Fetch fundamentals
        profile = None
        metrics = None
        return_12m = None

        try:
            from signals.fmp_client import fetch_profile, fetch_key_metrics_ttm
            profile, _ = fetch_profile(config, ticker)
            metrics, _ = fetch_key_metrics_ttm(config, ticker)
        except Exception:
            pass

        # 12-month return from price history
        try:
            from signals.fetcher import fetch_ohlcv_safe
            close = fetch_ohlcv_safe(ticker, "1y")
            if close is not None and len(close) >= 200:
                return_12m = (float(close.iloc[-1]) - float(close.iloc[0])) / float(close.iloc[0]) * 100
        except Exception:
            pass

        pe = None
        forward_pe = None
        mkt_cap = None
        roe = None
        op_margin = None

        if metrics:
            pe = _safe_float(metrics.get("peRatioTTM"))
            forward_pe = _safe_float(metrics.get("forwardPE") or metrics.get("peRatioTTM"))
            roe = _safe_float(metrics.get("roeTTM"))
            if roe and abs(roe) < 1:
                roe = roe * 100
            op_margin = _safe_float(metrics.get("operatingCashFlowPerShareTTM"))

        if profile:
            mkt_cap = _safe_float(profile.get("mktCap"))
            if pe is None:
                pe = _safe_float(profile.get("peRatio"))
            if forward_pe is None:
                forward_pe = pe

        factors = {
            "momentum": round(_score_momentum(return_12m)),
            "value": round(_score_value(pe)),
            "size": round(_score_size(mkt_cap)),
            "growth": round(_score_growth(forward_pe, pe)),
            "quality": round(_score_quality(roe, op_margin)),
        }

        per_h_factors.append({"ticker": ticker, "weight_pct": round(weight_pct, 1), "factors": factors})

    # Portfolio-level weighted average
    factor_names = ["momentum", "value", "size", "growth", "quality"]
    portfolio_factors: dict[str, float] = {}

    total_weight = sum(h["weight_pct"] for h in per_h_factors)
    for f in factor_names:
        if total_weight > 0:
            weighted = sum(
                h["weight_pct"] * h["factors"].get(f, 50) for h in per_h_factors
            ) / total_weight
            portfolio_factors[f] = round(weighted)
        else:
            portfolio_factors[f] = 50

    # Dominant factor
    dominant = max(portfolio_factors, key=portfolio_factors.get) if portfolio_factors else None

    # Build note
    high_factors = [f for f, v in portfolio_factors.items() if v >= 65]
    low_factors = [f for f, v in portfolio_factors.items() if v <= 35]

    note_parts = []
    if high_factors:
        note_parts.append(f"Tilted toward {', '.join(high_factors)}")
    if low_factors:
        note_parts.append(f"underweight {', '.join(low_factors)}")
    note = " — ".join(note_parts) if note_parts else None

    return {
        "portfolio_factors": portfolio_factors,
        "per_holding": per_h_factors,
        "dominant_factor": dominant,
        "note": note,
    }


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None
