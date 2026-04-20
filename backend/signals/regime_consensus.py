"""
Regime consensus: cross-signal vote across HMM, MA structure, composite score,
macro regime, and breadth/RS trend.

Answers "do independent regime signals agree?" — a prerequisite for regime validation.
Each source maps to BULL | NEUTRAL | BEAR and votes with a pre-set weight.
"""
from __future__ import annotations

from typing import Any

# --- direction normalization ---------------------------------------------------

_DIR: dict[str, str] = {
    # HMM state labels
    "BULL": "BULL", "STRONG_BULL": "BULL",
    "BEAR": "BEAR", "STRONG_BEAR": "BEAR",
    "TRANSITION": "NEUTRAL",
    # MA regime (get_regime_ma / get_global_market_regime)
    "UP": "BULL", "UP-HV": "BULL",
    "DOWN": "BEAR",
    "SIDE": "NEUTRAL", "NEUTRAL": "NEUTRAL",
    # Composite regime (get_regime)
    # UP / DOWN already above; NEUTRAL already above
    # Macro regime (dashboard macro_regime string)
    "RISK-ON": "BULL", "RISK_ON": "BULL",
    "RISK-OFF": "BEAR", "RISK_OFF": "BEAR",
    "Risk-On": "BULL", "Risk-Off": "BEAR",
    # Breadth RS tech_leadership (Rising / Flat / Falling)
    "RISING": "BULL", "Rising": "BULL",
    "FALLING": "BEAR", "Falling": "BEAR",
    "FLAT": "NEUTRAL", "Flat": "NEUTRAL",
}

# Source weights (must sum to 1.0 or will be renormalized over available sources)
_WEIGHTS: dict[str, float] = {
    "hmm":         0.30,   # Probabilistic — most sophisticated
    "ma_cross":    0.25,   # Structural MA alignment — lagging but reliable
    "composite":   0.20,   # Own composite score regime
    "macro":       0.15,   # VIX + real yield macro overlay
    "breadth_rs":  0.10,   # Tech leadership / RS trend — weakest proxy
}


def _to_dir(value: str | None) -> str | None:
    if not value:
        return None
    return _DIR.get(str(value).strip(), None)


def _hmm_prob_to_dir(bull_prob: float | None) -> str | None:
    if bull_prob is None:
        return None
    if bull_prob >= 0.55:
        return "BULL"
    if bull_prob <= 0.40:
        return "BEAR"
    return "NEUTRAL"


def compute_regime_consensus(
    *,
    hmm_bull_prob: float | None = None,
    ma_regime: str | None = None,
    composite_regime: str | None = None,
    macro_regime: str | None = None,
    tech_leadership: str | None = None,
) -> dict[str, Any]:
    """
    Cross-validate up to 5 independent regime signals and return a consensus.

    Parameters
    ----------
    hmm_bull_prob   : HMM bull-state probability (0-1).
    ma_regime       : MA-structure regime string (UP / DOWN / SIDE / BULL / BEAR /
                      TRANSITION / STRONG_BULL / STRONG_BEAR).
    composite_regime: Score-derived regime (UP / NEUTRAL / DOWN).
    macro_regime    : Macro overlay (Risk-On / Neutral / Risk-Off).
    tech_leadership : Breadth/RS trend (Rising / Flat / Falling).

    Returns
    -------
    consensus_direction : BULL | NEUTRAL | BEAR  (weighted-majority winner)
    consensus_score     : float 0-1 (weight fraction voting for winner)
    signals             : per-source direction (None = data missing)
    weights             : per-source weight (before renorm)
    dissenting          : list of sources that disagree with the winner
    available_n         : number of sources with data
    """
    raw: dict[str, str | None] = {
        "hmm":        _hmm_prob_to_dir(hmm_bull_prob),
        "ma_cross":   _to_dir(ma_regime),
        "composite":  _to_dir(composite_regime),
        "macro":      _to_dir(macro_regime),
        "breadth_rs": _to_dir(tech_leadership),
    }

    available = {k: v for k, v in raw.items() if v is not None}

    if not available:
        return {
            "consensus_direction": "NEUTRAL",
            "consensus_score": 0.5,
            "signals": raw,
            "weights": _WEIGHTS,
            "dissenting": [],
            "available_n": 0,
        }

    total_w = sum(_WEIGHTS[k] for k in available)
    if total_w <= 0:
        total_w = 1.0

    votes: dict[str, float] = {"BULL": 0.0, "NEUTRAL": 0.0, "BEAR": 0.0}
    for k, direction in available.items():
        votes[direction] += _WEIGHTS[k] / total_w

    winner = max(votes, key=lambda d: votes[d])
    consensus_score = round(votes[winner], 3)
    dissenting = [k for k, v in available.items() if v != winner]

    return {
        "consensus_direction": winner,
        "consensus_score": consensus_score,
        "signals": raw,
        "weights": _WEIGHTS,
        "dissenting": dissenting,
        "available_n": len(available),
    }
