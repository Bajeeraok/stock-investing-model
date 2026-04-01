"""
Multi-factor macro regime (FRED + VIX) and optional fusion with SPY HMM bear probability.

Uses existing HTTP FRED client (no fredapi). VIX is passed in from dashboard cross-asset
or resolved via yfinance fallback. Not Bloomberg parity — forward-looking macro confirmation
layer on top of price-based HMM.
"""
from __future__ import annotations

import logging
from typing import Any

from signals.fred_client import (
    SERIES_10Y,
    SERIES_2Y,
    SERIES_HY_OAS,
    get_latest_value,
    get_unrate_mom_pct_change,
)

logger = logging.getLogger(__name__)


def _resolve_vix(config: dict, vix: float | None) -> float | None:
    if vix is not None and vix > 0:
        return float(vix)
    try:
        from signals.fetcher import fetch_yfinance_latest_prices

        px = fetch_yfinance_latest_prices(["^VIX"])
        v = px.get("^VIX")
        if v is not None and v > 0:
            return float(v)
    except Exception as e:
        logger.debug("VIX fallback failed: %s", e)
    return None


def fetch_macro_factors(config: dict, vix: float | None = None) -> dict[str, Any]:
    """
    Latest macro inputs. Missing keys are omitted (caller treats as partial).
    """
    out: dict[str, Any] = {}

    t10 = get_latest_value(config, SERIES_10Y)
    t2 = get_latest_value(config, SERIES_2Y)
    if t10 is not None and t2 is not None:
        out["yield_curve_2s10s"] = round(float(t10 - t2), 3)

    hy = get_latest_value(config, SERIES_HY_OAS)
    if hy is not None:
        out["hy_oas_bp"] = round(float(hy), 2)

    vx = _resolve_vix(config, vix)
    if vx is not None:
        out["vix"] = round(float(vx), 2)

    ur = get_unrate_mom_pct_change(config)
    if ur is not None:
        out["unemployment_mom_pct"] = round(float(ur), 4)

    return out


def classify_macro_regime(factors: dict) -> dict[str, Any]:
    """
    Map factor dict to macro_score 0–100 and coarse BULL / NEUTRAL / BEAR label.
    """
    score = 50.0

    yc = factors.get("yield_curve_2s10s")
    if yc is not None:
        if yc < -0.5:
            score -= 20.0
        elif yc < 0:
            score -= 10.0
        elif yc > 0.5:
            score += 10.0

    hy = factors.get("hy_oas_bp")
    if hy is not None:
        if hy > 500:
            score -= 25.0
        elif hy > 350:
            score -= 10.0
        elif hy < 300:
            score += 10.0

    vx = factors.get("vix")
    if vx is not None:
        if vx > 30:
            score -= 20.0
        elif vx > 20:
            score -= 8.0
        elif vx < 15:
            score += 10.0

    um = factors.get("unemployment_mom_pct")
    if um is not None:
        if um > 0.02:
            score -= 15.0
        elif um < -0.01:
            score += 8.0

    score = max(0.0, min(100.0, score))
    regime = "BULL" if score >= 65 else ("NEUTRAL" if score >= 40 else "BEAR")

    return {
        "macro_regime": regime,
        "macro_score": round(score, 2),
        "factors": factors,
    }


def combine_macro_hmm(
    hmm_bear_pct: float | None,
    macro_score: float,
    hmm_weight: float = 0.40,
    macro_weight: float = 0.60,
) -> dict[str, Any]:
    """
    Blend HMM (price) score with macro score. HMM bear % is converted to bull-ish score: 100 - bear%.
    If hmm_bear_pct is None, returns only macro-based interpretation with combined_score = macro_score.
    """
    w_h = max(0.0, min(1.0, hmm_weight))
    w_m = max(0.0, min(1.0, macro_weight))
    s = w_h + w_m
    if s > 0:
        w_h, w_m = w_h / s, w_m / s

    if hmm_bear_pct is None:
        combined = macro_score
        hmm_score = None
    else:
        bear = max(0.0, min(100.0, float(hmm_bear_pct)))
        hmm_score = 100.0 - bear
        combined = hmm_score * w_h + macro_score * w_m

    regime = (
        "STRONG_BULL" if combined >= 70 else
        "BULL" if combined >= 55 else
        "NEUTRAL" if combined >= 40 else
        "BEAR" if combined >= 25 else
        "STRONG_BEAR"
    )

    return {
        "combined_regime": regime,
        "combined_score": round(combined, 2),
        "hmm_score": round(hmm_score, 2) if hmm_score is not None else None,
        "hmm_weight": round(w_h, 3),
        "macro_weight": round(w_m, 3),
    }


def build_macro_regime_bundle(
    config: dict,
    *,
    vix: float | None = None,
    hmm_bear_pct: float | None = None,
    hmm_weight: float = 0.40,
    macro_weight: float = 0.60,
) -> dict[str, Any]:
    """
    Full snapshot: factors, macro classification, optional HMM fusion.
    """
    factors = fetch_macro_factors(config, vix=vix)
    classified = classify_macro_regime(factors)
    macro_score = float(classified["macro_score"])
    fusion = combine_macro_hmm(
        hmm_bear_pct,
        macro_score,
        hmm_weight=hmm_weight,
        macro_weight=macro_weight,
    )
    return {
        **classified,
        **fusion,
        "hmm_bear_pct_used": hmm_bear_pct,
        "note": "Macro layer uses FRED + VIX; fusion weights configurable. Not investment advice.",
    }
