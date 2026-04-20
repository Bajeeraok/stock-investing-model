"""
Regime validation: combines consensus + persistence + divergence + reliability
into a single validation result consumed by the confidence engine and dashboard.

Issues addressed:
  3 — Validation gate: consensus + persistence → validated flag + weight adjustment
  5 — Live reliability score from historical hit rates (regime_hit_rates.json)
  6 — Unified divergence severity (replaces scattered ma_conflict / regime_tension_note)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HIT_RATES_FILE = "regime_hit_rates.json"

# Weight adjustment multipliers applied to the regime_hmm layer inside confidence_engine.
# Reduces how much an unvalidated / diverging regime drives the final confidence score.
WEIGHT_ADJUSTMENTS: dict[str, float] = {
    "validated_high_consensus": 1.10,   # ≥0.80 consensus + confirmed — boost slightly
    "validated":                1.00,   # normal path
    "unvalidated_new":          0.85,   # regime just appeared, no conflict yet
    "unvalidated_mild":         0.75,   # mild cross-signal divergence
    "unvalidated_moderate":     0.60,   # moderate divergence
    "unvalidated_severe":       0.45,   # severe HMM vs MA / cross-signal conflict
}


# ---------------------------------------------------------------------------
# Issue 6: Unified divergence severity
# ---------------------------------------------------------------------------

def compute_divergence_severity(
    hmm_conflict_severity: str | None,
    consensus_score: float,
    consensus_direction: str,
    hmm_direction: str | None,
) -> str:
    """
    Unified divergence severity that replaces the scattered ma_conflict flag and
    regime_tension_note with a single categorical label.

    Inputs
    ------
    hmm_conflict_severity : 'HIGH' | 'MEDIUM' | 'LOW' | 'none' from validate_regime().
    consensus_score       : fraction of cross-signal weight agreeing on winner (0-1).
    consensus_direction   : winning direction from compute_regime_consensus().
    hmm_direction         : HMM's own direction vote (may differ from consensus winner).

    Returns
    -------
    'NONE' | 'MILD' | 'MODERATE' | 'SEVERE'
    """
    cs_upper = (hmm_conflict_severity or "none").upper()

    # SEVERE: HMM explicitly overridden by MA structure (HIGH severity from validate_regime)
    # OR strong cross-signal disagreement where HMM and consensus winner differ
    hmm_disagrees = (hmm_direction is not None) and (hmm_direction != consensus_direction)
    if cs_upper == "HIGH" or (consensus_score < 0.42 and hmm_disagrees):
        return "SEVERE"

    # MODERATE: medium MA conflict OR poor cross-signal agreement
    if cs_upper == "MEDIUM" or consensus_score < 0.54:
        return "MODERATE"

    # MILD: low MA conflict OR below the "clear consensus" threshold
    if cs_upper == "LOW" or consensus_score < 0.65:
        return "MILD"

    return "NONE"


# ---------------------------------------------------------------------------
# Issue 3: Validation gate
# ---------------------------------------------------------------------------

def build_regime_validation(
    consensus: dict[str, Any],
    persistence: dict[str, Any],
    hmm_data: dict[str, Any] | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """
    Combine consensus + persistence + divergence severity + historical reliability
    into a single validation result.

    Parameters
    ----------
    consensus   : output of regime_consensus.compute_regime_consensus()
    persistence : output of regime_persistence.compute_regime_persistence()
    hmm_data    : full HMM payload from hmm_regime.get_hmm_regime() (optional)
    data_root   : backend/data root for regime_hit_rates.json lookup

    Returns
    -------
    validated                   : bool — True when consensus ≥ 0.60 AND regime confirmed
    consensus_direction         : BULL | NEUTRAL | BEAR
    consensus_score             : float 0-1
    days_stable                 : int
    regime_confirmed            : bool (days_stable >= min_confirmed_days)
    divergence_severity         : NONE | MILD | MODERATE | SEVERE
    confidence_weight_adjustment: float — multiplier for regime_hmm layer weight
    weight_adjustment_key       : str — which bucket was chosen
    dissenting_signals          : list[str]
    signals                     : per-source direction dict
    available_signals_n         : int
    previous_regime             : str | None
    previous_regime_duration    : int | None
    streak_start_date           : str | None
    regime_reliability          : dict | None — from historical hit rates
    summary                     : human-readable one-liner
    """
    consensus_score     = float(consensus.get("consensus_score") or 0.5)
    consensus_direction = str(consensus.get("consensus_direction") or "NEUTRAL")
    days_stable         = int(persistence.get("days_stable") or 0)
    confirmed           = bool(persistence.get("regime_confirmed", False))

    hmm_direction = (consensus.get("signals") or {}).get("hmm")

    # Extract HMM MA-conflict severity from hmm_data (various payload shapes)
    hmm_conflict: str | None = None
    if isinstance(hmm_data, dict):
        # validate_regime output may be embedded at top level or under "ma_conflict"
        hmm_conflict = hmm_data.get("conflict_severity")
        if not hmm_conflict:
            mc = hmm_data.get("ma_conflict")
            if isinstance(mc, dict):
                hmm_conflict = mc.get("conflict_severity")

    divergence = compute_divergence_severity(
        hmm_conflict, consensus_score, consensus_direction, hmm_direction
    )

    # --- Validation gate ---
    validated = consensus_score >= 0.60 and confirmed

    # --- Weight adjustment key ---
    if validated and consensus_score >= 0.80:
        adj_key = "validated_high_consensus"
    elif validated:
        adj_key = "validated"
    elif divergence == "SEVERE":
        adj_key = "unvalidated_severe"
    elif divergence == "MODERATE":
        adj_key = "unvalidated_moderate"
    elif divergence == "MILD":
        adj_key = "unvalidated_mild"
    else:
        adj_key = "unvalidated_new"

    adj = WEIGHT_ADJUSTMENTS[adj_key]

    # --- Issue 5: Live reliability lookup ---
    current_regime = str(persistence.get("current_regime") or consensus_direction)
    hmm_bull_prob: float | None = None
    if isinstance(hmm_data, dict):
        try:
            bp = hmm_data.get("bull_probability")
            if bp is not None:
                hmm_bull_prob = float(bp)
        except (TypeError, ValueError):
            pass

    reliability: dict[str, Any] | None = None
    try:
        reliability = get_regime_reliability(current_regime, hmm_bull_prob, data_root=data_root)
    except Exception as exc:
        logger.debug("regime_reliability lookup failed: %s", exc)

    # --- Human summary ---
    if validated:
        summary = (
            f"{consensus_direction} validated — "
            f"consensus {consensus_score:.0%}, stable {days_stable}d, "
            f"divergence {divergence}"
        )
    else:
        parts: list[str] = []
        if not confirmed:
            parts.append(f"only {days_stable}d stable (need {persistence.get('min_confirmed_days', 5)}+)")
        if consensus_score < 0.60:
            parts.append(f"cross-signal agreement {consensus_score:.0%}")
        summary = (
            f"{consensus_direction} NOT validated — "
            + ("; ".join(parts) or "insufficient data")
            + f"; divergence {divergence}"
        )

    return {
        "validated":                    validated,
        "consensus_direction":          consensus_direction,
        "consensus_score":              round(consensus_score, 3),
        "days_stable":                  days_stable,
        "regime_confirmed":             confirmed,
        "divergence_severity":          divergence,
        "confidence_weight_adjustment": round(adj, 3),
        "weight_adjustment_key":        adj_key,
        "dissenting_signals":           list(consensus.get("dissenting") or []),
        "signals":                      dict(consensus.get("signals") or {}),
        "available_signals_n":          int(consensus.get("available_n") or 0),
        "previous_regime":              persistence.get("previous_regime"),
        "previous_regime_duration":     persistence.get("previous_regime_duration"),
        "streak_start_date":            persistence.get("streak_start_date"),
        "regime_reliability":           reliability,
        "summary":                      summary,
    }


# ---------------------------------------------------------------------------
# Issue 5: Historical regime reliability lookup
# ---------------------------------------------------------------------------

def get_regime_reliability(
    regime: str,
    hmm_bull_prob: float | None = None,
    horizons: list[int] | None = None,
    data_root: Path | None = None,
) -> dict[str, Any] | None:
    """
    Look up historical forward-return accuracy for `regime` from regime_hit_rates.json.

    Returns None when the file hasn't been built yet (run backtest_regime.py first).
    The confidence bucket (low/medium/high) is derived from hmm_bull_prob when available.
    """
    if data_root is None:
        data_root = Path(__file__).resolve().parent.parent / "data"
    path = data_root / _HIT_RATES_FILE
    if not path.exists():
        return None

    try:
        with open(path) as f:
            rates: dict = json.load(f)
    except Exception as exc:
        logger.debug("regime_hit_rates load failed: %s", exc)
        return None

    regime_key = str(regime).upper().strip()
    entry = rates.get(regime_key)
    if not isinstance(entry, dict):
        return None

    # Confidence bucket from HMM bull probability
    bucket = "medium"
    if hmm_bull_prob is not None:
        if hmm_bull_prob >= 0.75:
            bucket = "high"
        elif hmm_bull_prob <= 0.35:
            bucket = "low"

    hz = horizons or [20, 60]
    result: dict[str, Any] = {"regime": regime_key, "confidence_bucket": bucket}

    for h in hz:
        key = f"{h}d"
        # Prefer confidence-stratified stats; fall back to overall
        bucket_entry = (entry.get("by_confidence") or {}).get(bucket, {}).get(key)
        overall_entry = entry.get(key)
        chosen = bucket_entry or overall_entry
        if chosen:
            result[f"hit_rate_{key}_pct"]   = chosen.get("hit_rate_pct")
            result[f"avg_return_{key}_pct"] = chosen.get("avg_return_pct")
            result[f"n_{key}"]              = chosen.get("n")

    return result if len(result) > 2 else None
