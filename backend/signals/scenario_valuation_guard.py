"""
Cap scenario targets and trim bull probabilities when spot is far above model fair value.

Fixes contradictions like NBIS: Model FV ~$141, spot ~$287, but "Earnings Beat" at $318 (72%).
When price already exceeds analyst high, tactical scenarios should not imply sustained upside.
"""

from __future__ import annotations

from typing import Any

BULL_SCENARIO_NAMES = frozenset({
    "Bull Case",
    "Earnings Beat",
    "Fed Rate Cut",
    "Momentum Squeeze",
    "Fed Pivot (Risk-On)",
    "Dividend Increase",
    "Geopolitical De-escalation",
    "Sector Rotation",
})


def _is_bull_scenario(scen: dict[str, Any]) -> bool:
    if scen.get("return_pct", 0) < 0:
        return False
    st = str(scen.get("scenario_type") or "")
    if st == "bear":
        return False
    if st == "bull" or scen.get("name") in BULL_SCENARIO_NAMES:
        return True
    return scen.get("return_pct", 0) >= 0 and st != "bear"


def _upside_cap(
    price: float,
    fair_value: float | None,
    analyst_targets: dict[str, Any] | None,
) -> float | None:
    """Highest plausible tactical upside target when spot is already rich."""
    if price <= 0:
        return None

    at = analyst_targets or {}
    analyst_high = _sf(at.get("high"))
    analyst_median = _sf(at.get("median") or at.get("mean"))

    if analyst_high and price > analyst_high:
        # Already above street high — tactical pop only (earnings drift), not a new bull leg
        return min(analyst_high * 1.05, price * 1.08)

    if analyst_high:
        return analyst_high

    if analyst_median and price > analyst_median:
        return analyst_median * 1.05

    fv = fair_value if fair_value and fair_value > 0 else None
    if fv:
        return min(fv * 1.15, price * 1.10)

    return price * 1.10 if price > 0 else None


def _sf(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
        return x if x == x and x > 0 else None
    except (TypeError, ValueError):
        return None


def premium_vs_fv_pct(price: float, fair_value: float | None) -> float | None:
    fv = _sf(fair_value)
    if not fv or price <= 0:
        return None
    return round((price / fv - 1) * 100, 1)


def apply_valuation_guards_to_scenarios(
    scenarios: list[dict[str, Any]],
    *,
    price: float,
    fair_value: float | None,
    analyst_targets: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Mutates scenario dicts in place: caps upside targets, downweights bull probabilities.
    Returns (scenarios, summary metadata for API/UI).
    """
    premium = premium_vs_fv_pct(price, fair_value)
    summary: dict[str, Any] = {
        "fair_value": fair_value,
        "premium_vs_fv_pct": premium,
    }

    cap = _upside_cap(price, fair_value, analyst_targets)
    summary["upside_cap"] = round(cap, 2) if cap else None

    prob_discount = 0.0
    if premium is not None and premium > 20:
        prob_discount = min(0.50, (premium - 20) / 120)
        summary["valuation_note"] = (
            f"Spot ${price:.0f} is {premium:.0f}% above model FV "
            f"(${fair_value:.0f}) — bull scenario targets capped and probabilities trimmed."
        )
    elif cap and price > (cap or 0) * 0.98:
        summary["valuation_note"] = (
            f"Spot is above Wall Street high — upside scenarios show tactical range only, "
            f"not a new bull leg."
        )

    for scen in scenarios:
        if not _is_bull_scenario(scen):
            continue

        pt = _sf(scen.get("price_target"))
        if pt and cap and pt > cap:
            old_pt = pt
            scen["price_target"] = round(cap, 2)
            scen["return_pct"] = round((cap / price - 1) * 100, 1)
            scen["valuation_capped"] = True
            cap_note = f"Capped from ${old_pt:.0f} — price rich vs model FV / street"
            scen["macro_note"] = (
                f"{scen['macro_note']} · {cap_note}" if scen.get("macro_note") else cap_note
            )

        if prob_discount > 0:
            old_p = float(scen.get("probability") or 0)
            scen["probability"] = round(max(0.05, old_p * (1 - prob_discount)), 2)
            scen["valuation_prob_adjusted"] = True

    return scenarios, summary


def apply_valuation_context_to_earnings_target(
    et: dict[str, Any],
    *,
    price: float,
    fair_value: float | None,
    analyst_targets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Annotate 1-day earnings move band when spot is far above fundamental anchors."""
    if not et.get("available") or price <= 0:
        return et

    premium = premium_vs_fv_pct(price, fair_value)
    at = analyst_targets or {}
    analyst_high = _sf(at.get("high"))

    notes: list[str] = []
    if premium is not None and premium > 25:
        notes.append(
            f"1-day reaction band only — model FV ${fair_value:.0f} is {abs(premium):.0f}% below spot; "
            "a positive earnings move does not fix long-term overvaluation."
        )
    if analyst_high and price > analyst_high:
        notes.append(
            f"Spot ${price:.0f} is above analyst high ${analyst_high:.0f} — upside band is historical "
            "volatility, not a validated price target."
        )

    if notes:
        et = dict(et)
        et["valuation_context"] = " ".join(notes)
        et["is_tactical_only"] = True
    return et
