"""
Bear-regime score dampening when observed error bands are wide vs bull baseline.

Use for swing / day_short profiles only; long_term is not dampened (bear = opportunity).
"""
from __future__ import annotations

# Bull-market MoE baseline (fraction of price) from long backtest calibration — tune via config if needed
BULL_BASELINE_ERROR_DEFAULT = 0.0061


def apply_bear_dampening(
    score: float,
    hmm_bear_pct: float,
    error_band: float,
    profile: str,
    *,
    bull_baseline_error: float = BULL_BASELINE_ERROR_DEFAULT,
) -> float:
    """
    Reduce score confidence when bear error band is significantly wider than bull baseline.
    Only applies to swing and day_short profiles.
    Long-term profile: bear = opportunity, don't dampen.

    Args:
        score: 0–100 style score (or confidence × 100).
        hmm_bear_pct: HMM bear probability in 0–100 (not 0–1).
        error_band: Observed margin-of-error / uncertainty in bear conditions (same units as baseline).
        profile: long_term | swing | day_short
        bull_baseline_error: reference MoE in calm/bull years (default 0.0061).
    """
    if profile == "long_term":
        return score

    if error_band <= 0 or bull_baseline_error <= 0:
        return score

    bear_ratio = error_band / bull_baseline_error

    if bear_ratio > 3.0 and hmm_bear_pct > 60:
        dampening = min((bear_ratio - 3.0) / 12.5, 0.40)
        dampened = score * (1 - dampening) + 50 * dampening
        return round(float(dampened), 2)

    return score
