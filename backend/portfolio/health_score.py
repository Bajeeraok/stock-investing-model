"""
Portfolio Health Score — single 0-100 composite with 5 sub-scores.

Sub-scores (each 0-100):
  1. Concentration  — HHI-based, penalizes single-stock and sector concentration
  2. Correlation    — effective diversification (1 - avg pairwise corr)
  3. Regime alignment — % of portfolio value in bull/constructive positions
  4. Drawdown risk  — 1 minus worst-case stress scenario loss
  5. Tax efficiency — approaching-LTCG and loss-harvesting readiness

Combined: weighted average → 0-100 health score.
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def compute_health_score(
    per_holding: list[dict],
    total_value: float,
    *,
    correlation_matrix: dict | None = None,
    var_cvar: dict | None = None,
    sector_allocation: list[dict] | None = None,
    tax_exits: dict | None = None,
    stress_scenarios: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Compute a single portfolio health score (0-100) with 5 sub-scores.

    All inputs come from existing portfolio doctor / risk model outputs.
    """
    # Consolidate duplicate tickers (multi-account portfolios)
    consolidated_map: dict[str, dict] = {}
    for h in per_holding:
        t = h.get("ticker")
        if not t:
            continue
        if t in consolidated_map:
            c = consolidated_map[t]
            c["value"] = (c.get("value") or 0) + (h.get("value") or 0)
            c["pct"] = (c.get("pct") or 0) + (h.get("pct") or 0)
        else:
            consolidated_map[t] = dict(h)
    per_holding_c = list(consolidated_map.values())

    sub = {}

    # 1. Concentration score (HHI-based)
    sub["concentration"] = _score_concentration(per_holding_c, total_value, sector_allocation)

    # 2. Correlation score
    sub["correlation"] = _score_correlation(per_holding_c, correlation_matrix)

    # 3. Regime alignment
    sub["regime_alignment"] = _score_regime_alignment(per_holding_c, total_value)

    # 4. Drawdown risk
    sub["drawdown_risk"] = _score_drawdown_risk(var_cvar, stress_scenarios)

    # 5. Tax efficiency (use original per_holding for account-level tax status)
    sub["tax_efficiency"] = _score_tax_efficiency(per_holding, tax_exits)

    # Weighted composite
    weights = {
        "concentration": 0.25,
        "correlation": 0.20,
        "regime_alignment": 0.25,
        "drawdown_risk": 0.15,
        "tax_efficiency": 0.15,
    }
    total_w = sum(weights.values())
    composite = sum(sub[k] * weights[k] for k in weights) / total_w
    composite = round(max(0, min(100, composite)), 0)

    # Biggest drag
    worst_key = min(sub, key=sub.get)
    second_worst_key = sorted(sub, key=sub.get)[1] if len(sub) > 1 else worst_key

    drag_notes = []
    if sub[worst_key] < 70:
        drag_notes.append(_drag_explanation(worst_key, sub[worst_key], per_holding_c, sector_allocation, correlation_matrix))
    if sub[second_worst_key] < 70:
        drag_notes.append(_drag_explanation(second_worst_key, sub[second_worst_key], per_holding_c, sector_allocation, correlation_matrix))

    improvement_note = _improvement_note(worst_key, second_worst_key, per_holding_c, sub)

    return {
        "score": int(composite),
        "sub_scores": {k: round(v) for k, v in sub.items()},
        "weights": weights,
        "biggest_drag": drag_notes[0] if drag_notes else None,
        "improvement_note": improvement_note,
    }


def _score_concentration(
    per_holding: list[dict],
    total_value: float,
    sector_allocation: list[dict] | None,
) -> float:
    """HHI-based: perfect diversification (30 equal positions) = 100, single stock = 0."""
    pcts = [h["pct"] for h in per_holding if h.get("pct") is not None and h["pct"] > 0]
    if not pcts:
        return 50.0

    # Position-level HHI
    hhi = sum((p / 100) ** 2 for p in pcts)
    n = len(pcts)
    hhi_min = 1.0 / n if n > 0 else 1.0
    hhi_score = max(0, min(100, (1.0 - (hhi - hhi_min) / (1.0 - hhi_min)) * 100)) if hhi_min < 1.0 else 50

    # Sector concentration penalty
    sector_penalty = 0.0
    if sector_allocation:
        top_sector_pct = max((s.get("pct", 0) for s in sector_allocation), default=0)
        if top_sector_pct > 40:
            sector_penalty = min(20, (top_sector_pct - 40) * 0.8)

    # Top-3 penalty
    sorted_pcts = sorted(pcts, reverse=True)
    top3 = sum(sorted_pcts[:3])
    top3_penalty = max(0, (top3 - 50) * 0.5) if top3 > 50 else 0

    return max(0, min(100, hhi_score - sector_penalty - top3_penalty))


def _score_correlation(
    per_holding: list[dict],
    correlation_matrix: dict | None,
) -> float:
    """Effective diversification from pairwise correlations."""
    if not correlation_matrix:
        return 60.0  # neutral when unavailable

    try:
        tickers = list(correlation_matrix.keys())
        if len(tickers) < 2:
            return 70.0

        corr_vals = []
        for i, t1 in enumerate(tickers):
            for t2 in tickers[i + 1:]:
                val = correlation_matrix.get(t1, {}).get(t2)
                if val is not None:
                    corr_vals.append(abs(float(val)))

        if not corr_vals:
            return 60.0

        avg_corr = sum(corr_vals) / len(corr_vals)
        n_positions = len([h for h in per_holding if h.get("pct") and h["pct"] > 0])
        effective_positions = n_positions * (1.0 - avg_corr) + avg_corr

        # Score: higher effective positions = better
        if n_positions <= 1:
            return 30.0
        eff_ratio = effective_positions / n_positions
        return max(0, min(100, eff_ratio * 100))
    except Exception:
        return 60.0


def _score_regime_alignment(
    per_holding: list[dict],
    total_value: float,
) -> float:
    """% of portfolio value in constructive (HOLD/ADD, BUY, STRONG BUY, UP) positions."""
    if total_value <= 0:
        return 50.0

    constructive_value = 0.0
    neutral_value = 0.0
    for h in per_holding:
        val = h.get("value") or 0
        regime = (h.get("regime") or "").upper()
        suggestion = (h.get("suggestion") or "").upper()
        action = (h.get("action") or "").upper()

        if regime == "UP" or suggestion in ("HOLD/ADD",) or action in ("BUY", "STRONG BUY"):
            constructive_value += val
        elif regime == "NEUTRAL" or suggestion == "HOLD":
            neutral_value += val

    constructive_pct = constructive_value / total_value * 100
    neutral_pct = neutral_value / total_value * 100

    # Score: 100% constructive = 100, 100% trim = 0
    return max(0, min(100, constructive_pct + neutral_pct * 0.5))


def _score_drawdown_risk(
    var_cvar: dict | None,
    stress_scenarios: list[dict] | None,
) -> float:
    """Lower tail risk = higher score."""
    score = 75.0  # default

    if var_cvar and var_cvar.get("var_95_10day_pct") is not None:
        var_pct = abs(float(var_cvar["var_95_10day_pct"]))
        # var_pct of 5% = good (90), 15% = bad (50), 30% = terrible (20)
        score = max(20, min(95, 95 - var_pct * 3))

    if stress_scenarios:
        worst = min((s.get("impact_pct", 0) for s in stress_scenarios), default=0)
        worst = abs(worst)
        # Worst stress of 20% = decent (75), 40% = concerning (55), 60% = bad (35)
        stress_score = max(20, min(90, 90 - worst * 1.2))
        score = min(score, stress_score)

    return score


def _score_tax_efficiency(
    per_holding: list[dict],
    tax_exits: dict | None,
) -> float:
    """Score based on LTCG eligibility and loss harvesting opportunities."""
    score = 80.0  # default

    if not tax_exits:
        return score

    items = tax_exits.get("items") or tax_exits.get("exits") or []
    if not items:
        return 85.0

    n_approaching = sum(1 for i in items if i.get("status") == "approaching_ltcg")
    n_eligible = sum(1 for i in items if i.get("is_long_term"))
    n_harvestable = sum(1 for i in items if i.get("has_loss") and not i.get("is_long_term"))

    total = len(per_holding)
    if total <= 0:
        return 80.0

    # Penalize positions approaching LTCG that might be trimmed
    approaching_penalty = n_approaching * 5
    # Bonus for eligible LTCG positions
    eligible_bonus = min(15, n_eligible * 3)
    # Bonus for harvestable losses
    harvest_bonus = min(10, n_harvestable * 5)

    return max(30, min(100, score - approaching_penalty + eligible_bonus + harvest_bonus))


def _drag_explanation(
    key: str,
    score: float,
    per_holding: list[dict],
    sector_allocation: list[dict] | None,
    correlation_matrix: dict | None,
) -> str:
    """Generate a human-readable explanation for a low sub-score."""
    if key == "concentration":
        sorted_h = sorted([h for h in per_holding if h.get("pct")], key=lambda x: -(x["pct"] or 0))
        top_sector = ""
        if sector_allocation and sector_allocation:
            top_s = sector_allocation[0]
            top_sector = f"{top_s.get('sector', '')} sector at {top_s.get('pct', 0):.1f}%"

        # Effective positions from HHI
        pcts = [h["pct"] for h in sorted_h if h.get("pct") and h["pct"] > 0]
        n = len(pcts)
        eff_n = n
        if pcts:
            hhi = sum((p / 100) ** 2 for p in pcts)
            eff_n = round(1 / hhi, 1) if hhi > 0 else n

        parts = []
        if top_sector:
            parts.append(top_sector)
        if sorted_h and len(sorted_h) >= 2:
            corr_pairs = []
            if correlation_matrix:
                for i, t1 in enumerate(list(correlation_matrix.keys())):
                    for t2 in list(correlation_matrix.keys())[i + 1:]:
                        val = correlation_matrix.get(t1, {}).get(t2)
                        if val is not None and float(val) > 0.85:
                            corr_pairs.append(f"{t1}/{t2} {float(val):.0%}")
            if corr_pairs:
                parts.append(f"{corr_pairs[0]} overlap")
        parts.append(
            f"You have {n} positions but only {eff_n} independent bets"
        )
        return f"{' and '.join(parts[:2])} are reducing your effective diversification. {parts[-1]}." if len(parts) > 1 else parts[0] + "."

    if key == "correlation":
        high_pairs = []
        if correlation_matrix:
            tickers = list(correlation_matrix.keys())
            for i, t1 in enumerate(tickers):
                for t2 in tickers[i + 1:]:
                    val = correlation_matrix.get(t1, {}).get(t2)
                    if val is not None and float(val) > 0.75:
                        high_pairs.append((f"{t1}/{t2}", float(val)))
        high_pairs.sort(key=lambda x: -x[1])
        if high_pairs:
            pair_strs = [f"{p} {v:.0%}" for p, v in high_pairs[:3]]
            return f"Correlation: {', '.join(pair_strs)} overlap reduces effective diversification."
        return "High correlation between holdings reduces effective diversification."

    if key == "regime_alignment":
        down_names = [h["ticker"] for h in per_holding if (h.get("regime") or "").upper() == "DOWN" and h.get("pct")]
        if down_names:
            return f"Regime: {', '.join(down_names[:3])} in DOWN regime — consider trimming."
        return "Multiple positions in non-constructive regime."

    if key == "drawdown_risk":
        return "Portfolio tail risk is elevated — consider reducing high-beta positions."

    if key == "tax_efficiency":
        return "Tax drag — some positions approaching LTCG threshold, review before trimming."

    return f"{key}: score {score:.0f}/100"


def _improvement_note(
    worst: str,
    second_worst: str,
    per_holding: list[dict],
    sub: dict[str, float],
) -> str:
    """One-liner on how to push health above 80."""
    target = 80
    current = sum(sub.values()) / len(sub) if sub else 0
    if current >= target:
        return "Portfolio health is strong — maintain current allocation."

    actions = []
    if worst == "concentration" or second_worst == "concentration":
        top = sorted([h for h in per_holding if h.get("pct")], key=lambda x: -(x["pct"] or 0))
        if top:
            actions.append(f"Trimming {top[0]['ticker']}")
    if worst == "correlation" or second_worst == "correlation":
        actions.append("adding uncorrelated assets")
    if actions:
        return f"{' and '.join(actions)} would push health above {target}."
    return f"Improving {worst.replace('_', ' ')} would push health above {target}."
