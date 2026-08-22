"""Tests for scenario_integrity — MU-style non-exclusive / modal / fact bugs."""
from __future__ import annotations

from signals.scenario_integrity import (
    cross_check_regime_triggers,
    enforce_base_modal,
    finalize_scenarios,
    normalize_probabilities,
    portfolio_ev_pct,
    sanitize_event_triggers,
    scenario_probability_sum,
)


def _mu_like_raw() -> list[dict]:
    """Reproduce the MU valuation-deck screenshot weights (sum ≈ 1.97)."""
    return [
        {
            "scenario_type": "bull",
            "name": "Bull Case",
            "trigger": "Regime upgrade + ML confirmation",
            "probability": 0.45,
            "return_pct": 127.6,
            "is_base": False,
        },
        {
            "scenario_type": "base",
            "name": "Base Case",
            "trigger": "Current signals hold",
            "probability": 0.35,
            "return_pct": 55.2,
            "is_base": True,
        },
        {
            "scenario_type": "specific",
            "name": "Momentum Squeeze",
            "trigger": "Short interest >20% + positive catalyst",
            "probability": 0.40,
            "return_pct": 17.0,
            "is_base": False,
        },
        {
            "scenario_type": "specific",
            "name": "Fed Pivot (Risk-On)",
            "trigger": "Fed signals pause/cut cycle",
            "probability": 0.48,
            "return_pct": 15.0,
            "is_base": False,
        },
        {
            "scenario_type": "specific",
            "name": "Institutional Exit",
            "trigger": "Major fund filing 13G/D showing reduced stake",
            "probability": 0.13,
            "return_pct": -7.0,
            "is_base": False,
        },
        {
            "scenario_type": "bear",
            "name": "Bear Case",
            "trigger": "Regime deterioration + ML miss",
            "probability": 0.16,
            "return_pct": -15.9,
            "is_base": False,
        },
    ]


def test_raw_mu_probs_sum_near_two():
    assert abs(scenario_probability_sum(_mu_like_raw()) - 1.97) < 0.01


def test_normalize_exclusive_sum_one():
    out = normalize_probabilities(_mu_like_raw())
    assert abs(scenario_probability_sum(out) - 1.0) < 0.015


def test_base_modal_enforced():
    out = enforce_base_modal(_mu_like_raw())
    base = next(s for s in out if s["is_base"])
    bull = next(s for s in out if s["scenario_type"] == "bull")
    bear = next(s for s in out if s["scenario_type"] == "bear")
    assert base["probability"] >= bull["probability"] - 1e-9
    assert base["probability"] >= bear["probability"] - 1e-9


def test_squeeze_dropped_when_si_low():
    out = sanitize_event_triggers(
        _mu_like_raw(),
        {"short_pct": 0.02, "squeeze_risk": "low"},
    )
    names = [s["name"] for s in out]
    assert "Momentum Squeeze" not in names
    exit_row = next(s for s in out if s["name"] == "Institutional Exit")
    assert "13G/D showing" not in exit_row["trigger"]
    assert "risk" in exit_row["trigger"].lower() or "reduces" in exit_row["trigger"].lower()


def test_squeeze_kept_when_si_elevated():
    out = sanitize_event_triggers(
        _mu_like_raw(),
        {"short_pct": 0.18, "squeeze_risk": "elevated"},
    )
    squeeze = next(s for s in out if s["name"] == "Momentum Squeeze")
    assert "18.0%" in squeeze["trigger"] or "18%" in squeeze["trigger"]
    assert ">20%" not in squeeze["trigger"]


def test_bull_capped_when_hmm_stormy():
    out = cross_check_regime_triggers(
        _mu_like_raw(),
        {"bull": 0.0, "bear": 0.2, "transition": 0.8},
    )
    bull = next(s for s in out if s["scenario_type"] == "bull")
    assert bull["probability"] <= 0.09
    assert "conditional" in bull["trigger"].lower() or "0%" in bull["trigger"]


def test_finalize_mu_like_end_to_end():
    out = finalize_scenarios(
        _mu_like_raw(),
        hmm_probs={"bull": 0.0, "bear": 0.15, "transition": 0.85},
        short_interest={"short_pct": 0.025, "squeeze_risk": "low"},
    )
    assert abs(scenario_probability_sum(out) - 1.0) < 0.015
    names = [s["name"] for s in out]
    assert "Momentum Squeeze" not in names

    base = next(s for s in out if s.get("is_base") or s.get("scenario_type") == "base")
    bull = next(s for s in out if s.get("scenario_type") == "bull")
    bear = next(s for s in out if s.get("scenario_type") == "bear")
    assert base["probability"] >= bull["probability"] - 1e-9
    assert base["probability"] >= bear["probability"] - 1e-9
    # Absolute modal among all remaining scenarios
    assert base["probability"] >= max(s["probability"] for s in out) - 1e-9
    assert bull["probability"] < 0.20  # stormy tape cannot keep 45% upgrade odds

    ev = portfolio_ev_pct(out)
    assert ev is not None
    # Old bug: Σ(p×r)/Σ(p) ≈ +44% on raw non-exclusive weights.
    # Exclusive EV after integrity must be well below that.
    assert ev < 40.0
