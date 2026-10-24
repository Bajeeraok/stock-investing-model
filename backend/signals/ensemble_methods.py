"""
Ensemble signal combination using weighted averaging and stacking.

Implements industry-standard ensemble methods:
1. Simple averaging across horizons
2. Weighted averaging by horizon confidence
3. Stacking with meta-learner (optional)

This follows ML best practices: ensemble methods reduce variance and improve
generalization by combining multiple models.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def ensemble_simple_average(
    short_prob: float | None,
    medium_prob: float | None,
    long_prob: float | None,
) -> float | None:
    """
    Simple average of horizon probabilities.
    
    Baseline ensemble method - treats all horizons equally.
    """
    probs = [p for p in (short_prob, medium_prob, long_prob) if p is not None]
    if not probs:
        return None
    return float(np.mean(probs))


def ensemble_weighted_average(
    short_prob: float | None,
    medium_prob: float | None,
    long_prob: float | None,
    *,
    short_weight: float = 0.4,
    medium_weight: float = 0.35,
    long_weight: float = 0.25,
) -> float | None:
    """
    Weighted average by horizon confidence.
    
    Weights reflect relative importance: short-term timing > medium-term swing > long-term thesis.
    Weights sum to 1.0 and can be tuned via backtesting.
    """
    probs = []
    weights = []
    
    if short_prob is not None:
        probs.append(float(short_prob))
        weights.append(short_weight)
    if medium_prob is not None:
        probs.append(float(medium_prob))
        weights.append(medium_weight)
    if long_prob is not None:
        probs.append(float(long_prob))
        weights.append(long_weight)
    
    if not probs:
        return None
    
    # Normalize weights
    total_weight = sum(weights)
    if total_weight == 0:
        return None
    
    normalized_weights = [w / total_weight for w in weights]
    return float(np.average(probs, weights=normalized_weights))


def ensemble_confidence_weighted(
    short_prob: float | None,
    medium_prob: float | None,
    long_prob: float | None,
    short_confidence: float | None = None,
    medium_confidence: float | None = None,
    long_confidence: float | None = None,
) -> float | None:
    """
    Weighted average where weights are per-horizon confidence scores.
    
    Uses the model's own confidence estimates to weight each horizon.
    Higher confidence horizons get more weight in the ensemble.
    """
    probs = []
    weights = []
    
    if short_prob is not None:
        probs.append(float(short_prob))
        weights.append(float(short_confidence or 0.5))
    if medium_prob is not None:
        probs.append(float(medium_prob))
        weights.append(float(medium_confidence or 0.5))
    if long_prob is not None:
        probs.append(float(long_prob))
        weights.append(float(long_confidence or 0.5))
    
    if not probs:
        return None
    
    total_weight = sum(weights)
    if total_weight == 0:
        return None
    
    normalized_weights = [w / total_weight for w in weights]
    return float(np.average(probs, weights=normalized_weights))


def ensemble_majority_vote(
    short_signal: str | None,
    medium_signal: str | None,
    long_signal: str | None,
) -> str | None:
    """
    Majority vote across horizon signals (BUY/SELL/HOLD).
    
    Converts discrete signals to ensemble decision.
    """
    signals = [s for s in (short_signal, medium_signal, long_signal) if s is not None]
    if not signals:
        return None
    
    # Count votes
    from collections import Counter
    counts = Counter(signals)
    
    # Return most common, or None if tie
    most_common = counts.most_common()
    if len(most_common) == 1:
        return most_common[0][0]
    
    # Handle ties: prefer BUY > HOLD > SELL
    if most_common[0][1] == most_common[1][1]:
        # Tie - use priority
        for priority in ("BUY", "HOLD", "SELL"):
            if priority in signals:
                return priority
    
    return most_common[0][0]


def ensemble_dynamic_weighting(
    short_prob: float | None,
    medium_prob: float | None,
    long_prob: float | None,
    *,
    regime_bull_pct: float | None = None,
    volatility_factor: float = 1.0,
) -> float | None:
    """
    Dynamic weighting based on market conditions.
    
    In bull markets: weight short-term more (momentum matters)
    In bear markets: weight long-term more (valuation matters)
    High volatility: weight medium-term more (swing trading)
    """
    if regime_bull_pct is None:
        regime_bull_pct = 50.0
    
    # Base weights
    if regime_bull_pct >= 60:
        # Bull: emphasize short-term momentum
        w_short, w_medium, w_long = 0.5, 0.3, 0.2
    elif regime_bull_pct <= 40:
        # Bear: emphasize long-term valuation
        w_short, w_medium, w_long = 0.2, 0.3, 0.5
    else:
        # Neutral: balanced
        w_short, w_medium, w_long = 0.35, 0.35, 0.3
    
    # Adjust for volatility
    if volatility_factor > 1.5:
        # High vol: more weight to medium-term swing
        w_short *= 0.8
        w_medium *= 1.2
    elif volatility_factor < 0.8:
        # Low vol: more weight to long-term (trend following)
        w_short *= 0.7
        w_long *= 1.3
    
    # Normalize
    total = w_short + w_medium + w_long
    w_short /= total
    w_medium /= total
    w_long /= total
    
    return ensemble_weighted_average(
        short_prob, medium_prob, long_prob,
        short_weight=w_short,
        medium_weight=w_medium,
        long_weight=w_long,
    )


def apply_ensemble_to_signal(
    signal_data: dict[str, Any],
    *,
    method: str = "weighted_average",
    regime_bull_pct: float | None = None,
    volatility_factor: float = 1.0,
) -> dict[str, Any]:
    """
    Apply ensemble method to signal data and return enhanced signal.
    
    Args:
        signal_data: Dictionary with ml_horizons containing short/medium/long probs
        method: Ensemble method to use
        regime_bull_pct: HMM bull % for dynamic weighting
        volatility_factor: Volatility multiplier for dynamic weighting
    
    Returns:
        Enhanced signal_data with ensemble probability added
    """
    ml_horizons = signal_data.get("ml_horizons") or {}
    if not isinstance(ml_horizons, dict):
        return signal_data
    
    short_h = ml_horizons.get("short") or {}
    medium_h = ml_horizons.get("medium") or {}
    long_h = ml_horizons.get("long") or {}
    
    short_prob = short_h.get("prob") or short_h.get("prob_raw")
    medium_prob = medium_h.get("prob") or medium_h.get("prob_raw")
    long_prob = long_h.get("prob") or long_h.get("prob_raw")
    
    if method == "simple_average":
        ensemble_prob = ensemble_simple_average(short_prob, medium_prob, long_prob)
    elif method == "weighted_average":
        ensemble_prob = ensemble_weighted_average(short_prob, medium_prob, long_prob)
    elif method == "confidence_weighted":
        ensemble_prob = ensemble_confidence_weighted(
            short_prob, medium_prob, long_prob,
            short_confidence=short_h.get("confidence"),
            medium_confidence=medium_h.get("confidence"),
            long_confidence=long_h.get("confidence"),
        )
    elif method == "dynamic":
        ensemble_prob = ensemble_dynamic_weighting(
            short_prob, medium_prob, long_prob,
            regime_bull_pct=regime_bull_pct,
            volatility_factor=volatility_factor,
        )
    else:
        logger.warning(f"Unknown ensemble method: {method}, using weighted_average")
        ensemble_prob = ensemble_weighted_average(short_prob, medium_prob, long_prob)
    
    if ensemble_prob is not None:
        signal_data["ensemble_prob"] = round(ensemble_prob, 4)
        signal_data["ensemble_method"] = method
    
    return signal_data
