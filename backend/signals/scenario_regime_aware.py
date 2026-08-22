"""
signals/scenario_regime_aware.py  — Fix #3

PROBLEM:
    Scenario Analysis shows +47.9% portfolio-weighted EV for NVDA and SPY
    with 5 bullish / 1 bearish scenario weights even when HMM is Bear/Trans 99%.
    Scenario probabilities are anchored to analyst consensus + ML signal strength
    but not adjusted for current regime. A stock in 99% bear transition should not
    show the same bull scenario weights as a stock in 80% bull regime.

FIX:
    Apply regime-based probability adjustment to scenario weights.
    - Bull scenarios get downweighted when regime is Bear/Trans
    - Bear scenarios get upweighted accordingly
    - Total probabilities still sum to 1
    - Adjustment is soft (not a hard override) — preserves analyst signal
      but tempers extreme optimism in bear regimes

DESIGN:
    regime_factor = f(hmm_bull_prob, hmm_bear_prob)
    bull_scenario_weight *= regime_factor
    bear_scenario_weight *= (2 - regime_factor)
    renormalize to sum = 1
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Literal


ScenarioType = Literal[
    "bull_case", "base_case", "earnings_beat", "fed_rate_cut",
    "earnings_miss", "bear_case", "tail_risk", "sector_rotation"
]

BULL_SCENARIOS = {"bull_case", "earnings_beat", "fed_rate_cut", "sector_rotation"}
BEAR_SCENARIOS = {"bear_case", "earnings_miss", "tail_risk"}


@dataclass
class Scenario:
    name: str
    scenario_type: ScenarioType
    base_probability: float     # analyst/ML-derived prob before regime adjustment
    target_price: float
    return_pct: float
    description: str


@dataclass
class AdjustedScenario:
    name: str
    scenario_type: ScenarioType
    base_probability: float         # original
    adjusted_probability: float     # after regime adjustment
    regime_adjustment_factor: float # how much it moved
    target_price: float
    return_pct: float
    description: str
    weighted_ev: float              # adjusted_prob * return_pct


def compute_regime_factor(
    hmm_bull_prob: float | None,
    hmm_bear_prob: float | None,
    hmm_trans_prob: float | None = None,
) -> tuple[float, str]:
    """
    Compute regime adjustment factor for scenario probabilities.

    Returns (factor, description) where:
        factor > 1.0 → bull scenarios get upweighted
        factor < 1.0 → bull scenarios get downweighted
        factor = 1.0 → no adjustment (neutral regime)

    Range: [0.3, 1.7] — soft bounds to preserve analyst signal
    """
    if hmm_bull_prob is None and hmm_bear_prob is None:
        return 1.0, "no regime data — no adjustment"

    bull  = hmm_bull_prob  if hmm_bull_prob  is not None else 0.33
    bear  = hmm_bear_prob  if hmm_bear_prob  is not None else 0.33
    trans = hmm_trans_prob if hmm_trans_prob is not None else max(0, 1 - bull - bear)

    # Net regime score: bull - bear, range [-1, 1]
    # Trans is treated as slightly bear-leaning (uncertainty = caution)
    net_regime = bull - bear - (trans * 0.3)
    net_regime = float(np.clip(net_regime, -1.0, 1.0))

    # Map to factor: neutral at 0 → 1.0, full bull → 1.7, full bear → 0.3
    factor = 1.0 + (net_regime * 0.7)
    factor = float(np.clip(factor, 0.3, 1.7))

    # Description
    if factor > 1.2:
        desc = f"Bull regime ({bull*100:.0f}%) → bull scenarios upweighted ×{factor:.2f}"
    elif factor < 0.8:
        desc = f"Bear regime ({bear*100:.0f}%) → bull scenarios downweighted ×{factor:.2f}"
    elif trans > 0.50:
        desc = f"Transition regime ({trans*100:.0f}%) → mild bear tilt ×{factor:.2f}"
    else:
        desc = f"Neutral regime → minimal adjustment ×{factor:.2f}"

    return factor, desc


def adjust_scenario_probabilities(
    scenarios: list[Scenario],
    hmm_bull_prob: float | None,
    hmm_bear_prob: float | None,
    hmm_trans_prob: float | None = None,
    min_bull_prob: float = 0.03,    # floor — never zero out bull scenarios
    min_bear_prob: float = 0.03,    # floor — never zero out bear scenarios
) -> tuple[list[AdjustedScenario], dict]:
    """
    Apply regime-aware probability adjustment to scenario list.

    Parameters
    ----------
    scenarios       : list[Scenario] — analyst/ML-derived scenarios
    hmm_bull_prob   : float | None
    hmm_bear_prob   : float | None
    hmm_trans_prob  : float | None
    min_bull_prob   : float — minimum probability floor for bull scenarios
    min_bear_prob   : float — minimum probability floor for bear scenarios

    Returns
    -------
    (adjusted_scenarios, summary_dict)
    """
    factor, factor_desc = compute_regime_factor(
        hmm_bull_prob, hmm_bear_prob, hmm_trans_prob
    )

    # Apply adjustment
    raw_adjusted = []
    for s in scenarios:
        stype = s.scenario_type
        if stype in BULL_SCENARIOS:
            adj_prob = s.base_probability * factor
            adj_prob = max(adj_prob, min_bull_prob)
        elif stype in BEAR_SCENARIOS:
            inv_factor = 2.0 - factor   # inverts: bear = 0.3 → inv = 1.7
            adj_prob = s.base_probability * inv_factor
            adj_prob = max(adj_prob, min_bear_prob)
        else:
            # Neutral scenarios (base_case) — small adjustment toward bear in bear regime.
            # Floor so UI never shows "Base Case · 0% prob" after renormalization.
            adj_prob = s.base_probability * (1.0 + (factor - 1.0) * 0.3)
            adj_prob = max(adj_prob, max(0.08, 0.35 * float(s.base_probability or 0.0)))

        raw_adjusted.append((s, adj_prob))

    # Renormalize so total = 1.0
    total = sum(p for _, p in raw_adjusted)
    if total <= 0:
        total = 1.0

    adjusted_scenarios = []
    weighted_ev_total = 0.0

    # Re-floor base after renorm so UI never shows Base Case · 0% prob.
    POST_RENORM_BASE_FLOOR = 0.08
    renormed = []
    for s, raw_prob in raw_adjusted:
        adj_prob = raw_prob / total
        if s.scenario_type == "base_case" or "base" in (s.name or "").lower():
            adj_prob = max(adj_prob, POST_RENORM_BASE_FLOOR)
        renormed.append((s, adj_prob))
    total2 = sum(p for _, p in renormed) or 1.0

    for s, raw_prob in renormed:
        adj_prob = raw_prob / total2
        adj_factor = adj_prob / s.base_probability if s.base_probability > 0 else 1.0
        wev = adj_prob * s.return_pct
        weighted_ev_total += wev

        adjusted_scenarios.append(AdjustedScenario(
            name=s.name,
            scenario_type=s.scenario_type,
            base_probability=round(s.base_probability, 4),
            adjusted_probability=round(adj_prob, 4),
            regime_adjustment_factor=round(adj_factor, 3),
            target_price=s.target_price,
            return_pct=s.return_pct,
            description=s.description,
            weighted_ev=round(wev, 4),
        ))

    # Sort: bearish first if in bear regime, bullish first if in bull regime
    if factor < 1.0:
        adjusted_scenarios.sort(
            key=lambda x: (x.scenario_type not in BEAR_SCENARIOS, -x.adjusted_probability)
        )
    else:
        adjusted_scenarios.sort(key=lambda x: -x.adjusted_probability)

    summary = {
        "regime_factor":           round(factor, 3),
        "regime_factor_desc":      factor_desc,
        "portfolio_weighted_ev":   round(weighted_ev_total, 4),
        "portfolio_weighted_ev_pct": f"{weighted_ev_total*100:+.1f}%",
        "bull_scenario_count":     sum(1 for s in adjusted_scenarios if s.scenario_type in BULL_SCENARIOS),
        "bear_scenario_count":     sum(1 for s in adjusted_scenarios if s.scenario_type in BEAR_SCENARIOS),
        "regime_note": (
            "Scenario probabilities adjusted for current HMM regime. "
            "Base probabilities from analyst consensus + ML signal strength."
            if factor != 1.0 else
            "No regime adjustment applied (neutral regime)."
        ),
    }

    return adjusted_scenarios, summary


# ── Worked examples matching today's session ──────────────────────────────

def _nvda_example():
    """NVDA: Trans 99%, Bull 1%, Bear 0%."""
    scenarios = [
        Scenario("Bull Case",       "bull_case",     0.34, 400.00, 112.6, "Regime upgrade + ML confirmation"),
        Scenario("Base Case",       "base_case",     0.14, 275.00,  46.2, "Current signals hold"),
        Scenario("Earnings Beat",   "earnings_beat", 0.29, 214.48,  14.0, "EPS surprise >5%"),
        Scenario("Fed Rate Cut",    "fed_rate_cut",  0.19, 212.60,  13.0, "25-50bps cut"),
        Scenario("Earnings Miss",   "earnings_miss", 0.05, 188.14,   0.0, "EPS miss >3%"),
        Scenario("Bear Case",       "bear_case",     0.05, 170.32,  -9.5, "Regime deterioration"),
    ]

    print("=== NVDA: Trans 99% (Bull 1%, Bear 0%) ===")
    print(f"Base EV (unadjusted): "
          f"{sum(s.base_probability * s.return_pct for s in scenarios):+.1f}%")

    adj, summary = adjust_scenario_probabilities(
        scenarios,
        hmm_bull_prob=0.01,
        hmm_bear_prob=0.00,
        hmm_trans_prob=0.99,
    )

    print(f"Regime factor: {summary['regime_factor']} — {summary['regime_factor_desc']}")
    print(f"Adjusted EV: {summary['portfolio_weighted_ev_pct']}")
    print("\nAdjusted probabilities:")
    for s in adj:
        arrow = "↓" if s.adjusted_probability < s.base_probability else "↑"
        print(f"  {s.name:20s}: {s.base_probability*100:.0f}% → "
              f"{s.adjusted_probability*100:.0f}% {arrow}")


def _spy_example():
    """SPY: Bull 84%, Bear 16% — the miscalibrated case."""
    scenarios = [
        Scenario("Bull Case",     "bull_case",     0.40, 780.00,  13.7, "Regime holds + macro clears"),
        Scenario("Base Case",     "base_case",     0.25, 720.00,   4.9, "Range-bound"),
        Scenario("Fed Rate Cut",  "fed_rate_cut",  0.20, 740.00,   7.8, "Dovish pivot"),
        Scenario("Earnings Miss", "earnings_miss", 0.10, 640.00,  -6.7, "Earnings disappointment"),
        Scenario("Bear Case",     "bear_case",     0.05, 580.00, -15.4, "Regime breakdown"),
    ]

    print("\n=== SPY: Bull 84%, Bear 16% (current — possibly miscalibrated) ===")
    adj, summary = adjust_scenario_probabilities(
        scenarios,
        hmm_bull_prob=0.84,
        hmm_bear_prob=0.16,
        hmm_trans_prob=0.00,
    )
    print(f"Regime factor: {summary['regime_factor']} — {summary['regime_factor_desc']}")
    print(f"Adjusted EV: {summary['portfolio_weighted_ev_pct']}")

    print("\n=== SPY: If HMM were correctly Bear 70% ===")
    adj2, summary2 = adjust_scenario_probabilities(
        scenarios,
        hmm_bull_prob=0.10,
        hmm_bear_prob=0.70,
        hmm_trans_prob=0.20,
    )
    print(f"Regime factor: {summary2['regime_factor']} — {summary2['regime_factor_desc']}")
    print(f"Adjusted EV: {summary2['portfolio_weighted_ev_pct']}")
    print("\nAdjusted probabilities (corrected regime):")
    for s in adj2:
        arrow = "↓" if s.adjusted_probability < s.base_probability else "↑"
        print(f"  {s.name:20s}: {s.base_probability*100:.0f}% → "
              f"{s.adjusted_probability*100:.0f}% {arrow}")


if __name__ == "__main__":
    _nvda_example()
    _spy_example()
