"""
Directional regime-shift view from the HMM transition matrix.

Our HMM uses hmmlearn's state indices 0,1,2 ordered by *estimated mean return*
(bear = lowest, transition = mid, bull = highest). This module permutes the
transition matrix and posterior into semantic order [Bull, Transition, Bear]
before applying the multi-step projection in :func:`compute_shift_direction`.
"""
from __future__ import annotations

import numpy as np
from typing import Any, TypedDict

DEFAULT_HORIZON_DAYS = 10

# Semantic indices after permutation [Bull, Transition, Bear]
STATE_BULL = 0
STATE_TRANSITION = 1
STATE_BEAR = 2
STATE_NAMES = {STATE_BULL: "Bull", STATE_TRANSITION: "Transition", STATE_BEAR: "Bear"}


class ShiftDirectionResult(TypedDict, total=False):
    current_state: str
    current_state_prob: float
    shift_prob_total: float
    shift_to_bull_prob: float
    shift_to_bear_prob: float
    shift_to_bull_abs: float
    shift_to_bear_abs: float
    dominant_direction: str
    dominant_direction_confidence: float
    horizon_days: int
    interpretation: str


def _normalize_rows(A: np.ndarray) -> np.ndarray:
    A = np.array(A, dtype=float)
    rs = A.sum(axis=1, keepdims=True)
    rs[rs == 0] = 1.0
    return A / rs


def compute_shift_direction(
    transition_matrix: np.ndarray,
    current_state_probs: np.ndarray,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    uncertainty_threshold: float = 0.60,
) -> ShiftDirectionResult:
    """
    Directional shift probabilities when ``transition_matrix`` and
    ``current_state_probs`` are already in semantic order
    [Bull, Transition, Bear] for indices 0, 1, 2.
    """
    A = _normalize_rows(transition_matrix)
    pi = np.array(current_state_probs, dtype=float)
    if A.shape != (3, 3):
        raise ValueError(f"Expected 3x3 transition matrix, got {A.shape}")
    if pi.shape != (3,):
        raise ValueError(f"Expected 3-state prob vector, got {pi.shape}")
    s = float(pi.sum())
    if s <= 0:
        raise ValueError("current_state_probs must sum to > 0")
    pi = pi / s

    current_state_idx = int(np.argmax(pi))
    current_state_name = STATE_NAMES[current_state_idx]
    current_state_prob = float(pi[current_state_idx])

    A_h = np.linalg.matrix_power(A, int(horizon_days))
    future_probs = pi @ A_h

    prob_stay = float(future_probs[current_state_idx])
    prob_shift = round(1.0 - prob_stay, 4)

    dest_probs = future_probs.copy()
    dest_probs[current_state_idx] = 0.0
    total_away = float(dest_probs.sum())
    if total_away > 1e-8:
        dest_probs_norm = dest_probs / total_away
    else:
        dest_probs_norm = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])

    shift_to_bull = float(dest_probs_norm[STATE_BULL])
    shift_to_bear = float(dest_probs_norm[STATE_BEAR])

    shift_to_bull_abs = round(float(dest_probs[STATE_BULL]), 4)
    shift_to_bear_abs = round(float(dest_probs[STATE_BEAR]), 4)

    # If both sides clear the bar, pick the larger share (order-independent).
    bull_ok = shift_to_bull >= uncertainty_threshold
    bear_ok = shift_to_bear >= uncertainty_threshold
    if bull_ok and bear_ok:
        if shift_to_bull > shift_to_bear:
            dominant = "Bull"
            confidence = round(shift_to_bull, 4)
        elif shift_to_bear > shift_to_bull:
            dominant = "Bear"
            confidence = round(shift_to_bear, 4)
        else:
            dominant = "Uncertain"
            confidence = round(shift_to_bull, 4)
    elif bull_ok:
        dominant = "Bull"
        confidence = round(shift_to_bull, 4)
    elif bear_ok:
        dominant = "Bear"
        confidence = round(shift_to_bear, 4)
    else:
        dominant = "Uncertain"
        confidence = round(max(shift_to_bull, shift_to_bear), 4)

    interpretation = _build_interpretation(
        current_state_name=current_state_name,
        current_state_prob=current_state_prob,
        prob_shift=prob_shift,
        shift_to_bull=shift_to_bull,
        shift_to_bear=shift_to_bear,
        dominant=dominant,
        horizon_days=horizon_days,
    )

    return {
        "current_state": current_state_name,
        "current_state_prob": round(current_state_prob, 4),
        "shift_prob_total": prob_shift,
        "shift_to_bull_prob": round(shift_to_bull, 4),
        "shift_to_bear_prob": round(shift_to_bear, 4),
        "shift_to_bull_abs": shift_to_bull_abs,
        "shift_to_bear_abs": shift_to_bear_abs,
        "dominant_direction": dominant,
        "dominant_direction_confidence": confidence,
        "horizon_days": horizon_days,
        "interpretation": interpretation,
    }


def compute_shift_direction_semantic(
    transition_matrix: np.ndarray,
    current_state_probs: np.ndarray,
    bull_idx: int,
    transition_idx: int,
    bear_idx: int,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    uncertainty_threshold: float = 0.60,
) -> ShiftDirectionResult | None:
    """
    Same as :func:`compute_shift_direction` but accepts hmmlearn component indices
    (bear/trans/bull indices from mean-return ordering in ``hmm_regime``).
    """
    try:
        A_m = np.asarray(transition_matrix, dtype=float)
        pi_m = np.asarray(current_state_probs, dtype=float)
        order = np.array([bull_idx, transition_idx, bear_idx], dtype=int)
        A = A_m[np.ix_(order, order)]
        pi = pi_m[order]
        return compute_shift_direction(
            A, pi, horizon_days=horizon_days, uncertainty_threshold=uncertainty_threshold
        )
    except Exception:
        return None


def _build_interpretation(
    current_state_name: str,
    current_state_prob: float,
    prob_shift: float,
    shift_to_bull: float,
    shift_to_bear: float,
    dominant: str,
    horizon_days: int,
) -> str:
    shift_pct = round(prob_shift * 100)
    bull_pct = round(shift_to_bull * 100)
    bear_pct = round(shift_to_bear * 100)
    cur_pct = round(current_state_prob * 100)

    if prob_shift < 0.20:
        return (
            f"Regime stable — {current_state_name} ({cur_pct}% probability). "
            f"Only {shift_pct}% chance of shift within {horizon_days} days (HMM projection)."
        )

    if dominant == "Bull":
        direction_str = f"shift mass leans Bull ({bull_pct}% of non-sticky mass)"
    elif dominant == "Bear":
        direction_str = f"shift mass leans Bear ({bear_pct}% of non-sticky mass)"
    else:
        direction_str = (
            f"direction mixed — Bull {bull_pct}% vs Bear {bear_pct}% of non-sticky mass"
        )

    return (
        f"{shift_pct}% estimated probability of leaving the dominant state bucket within "
        f"{horizon_days} days (marginal HMM). If mass moves: {direction_str}. "
        f"Current: {current_state_name} ({cur_pct}%)."
    )


def from_hmmlearn_model(
    model: Any,
    observations: np.ndarray,
    bull_idx: int,
    transition_idx: int,
    bear_idx: int,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> ShiftDirectionResult | None:
    """Posterior from ``predict_proba(observations)`` last row + semantic index map."""
    try:
        posteriors = model.predict_proba(observations)
        current = posteriors[-1]
        tm = getattr(model, "transmat_", None)
        if tm is None:
            return None
        return compute_shift_direction_semantic(
            tm, current, bull_idx, transition_idx, bear_idx, horizon_days=horizon_days
        )
    except Exception:
        return None


def build_ui_payload(result: ShiftDirectionResult) -> dict[str, Any]:
    """Compact payload for API / UI (percent-scale shift_prob matches 0–1 in result)."""
    d = result.get("dominant_direction", "Uncertain")
    conf = float(result.get("dominant_direction_confidence") or 0.0)

    if d == "Bull":
        label = f"Likely Bull ({round(conf * 100)}%)"
        color = "green"
    elif d == "Bear":
        label = f"Likely Bear ({round(conf * 100)}%)"
        color = "red"
    else:
        label = "Direction uncertain"
        color = "amber"

    sb = float(result.get("shift_to_bull_prob") or 0.0)
    sbr = float(result.get("shift_to_bear_prob") or 0.0)
    trans_mass = round(max(0.0, 1.0 - sb - sbr), 4)

    return {
        "shift_probability": result.get("shift_prob_total"),
        "shift_direction": {
            "bull": sb,
            "bear": sbr,
            "transition_cycle": trans_mass,
            "dominant": d,
            "dominant_confidence": conf,
            "label": label,
            "color": color,
        },
        "horizon_days": result.get("horizon_days", DEFAULT_HORIZON_DAYS),
        "interpretation": result.get("interpretation", ""),
        "current_state": result.get("current_state"),
    }


def _nvda_example() -> None:
    A = np.array(
        [
            [0.85, 0.12, 0.03],
            [0.12, 0.58, 0.30],
            [0.05, 0.15, 0.80],
        ]
    )
    pi = np.array([0.01, 0.99, 0.00])
    result = compute_shift_direction(A, pi, horizon_days=10)
    payload = build_ui_payload(result)
    print("=== Example (fixed semantic order) ===")
    print(result)
    print(payload)


if __name__ == "__main__":
    _nvda_example()
