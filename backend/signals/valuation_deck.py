"""
Valuation deck payload: Street (ANR/EE proxy) + Model (RV/FA) + House (tiers/MOS).
"""
from __future__ import annotations

from typing import Any

from signals.analyst_ratings import (
    gap_badge,
    get_analyst_rating_distribution,
    street_primary_usd,
)


def _sector_pe_default(config: dict) -> float:
    return float((config.get("fair_value") or {}).get("sector_pe_default", 28.0))


def _relative_valuation_line(
    ttm_pe: float | None,
    forward_pe: float | None,
    sector_pe: float,
) -> str | None:
    parts: list[str] = []
    if ttm_pe is not None and ttm_pe > 0 and sector_pe > 0:
        ratio = ttm_pe / sector_pe
        if ratio > 1.15:
            parts.append(f"TTM P/E {ttm_pe:.1f}× — rich vs sector ~{sector_pe:.0f}×")
        elif ratio < 0.85:
            parts.append(f"TTM P/E {ttm_pe:.1f}× — cheap vs sector ~{sector_pe:.0f}×")
        else:
            parts.append(f"TTM P/E {ttm_pe:.1f}× — near sector ~{sector_pe:.0f}×")
    if forward_pe is not None and forward_pe > 0 and sector_pe > 0:
        fr = forward_pe / sector_pe
        if fr > 1.2:
            parts.append(f"Fwd P/E {forward_pe:.1f}× elevated")
        elif fr < 0.9:
            parts.append(f"Fwd P/E {forward_pe:.1f}× below sector norm")
    return " · ".join(parts) if parts else None


def build_valuation_deck(
    *,
    ticker: str,
    config: dict,
    fair_value: float,
    current_price: float,
    fair_value_vs_external: dict | None,
    fair_value_metadata: dict | None,
    entry_tiers: dict | None,
    ttm_pe: float | None = None,
    forward_pe: float | None = None,
    one_answer: dict | None = None,
    eps_fwd: float | None = None,
    eps_dispersion: float | None = None,
) -> dict[str, Any] | None:
    """Build valuation_deck for investor_summary (UI ValuationDeck)."""
    fve = fair_value_vs_external if isinstance(fair_value_vs_external, dict) else {}
    street_usd, street_label = street_primary_usd(fve)
    pct_vs_street = None
    if street_usd and street_usd > 0 and fair_value > 0:
        pct_vs_street = round(100.0 * (fair_value - street_usd) / street_usd, 1)

    ratings = get_analyst_rating_distribution(config, ticker)
    sector_pe = _sector_pe_default(config)
    rel_line = _relative_valuation_line(ttm_pe, forward_pe, sector_pe)

    median_usd = fve.get("fmp_consensus_median_usd")
    if median_usd is None and street_usd:
        median_usd = street_usd
    high_usd = fve.get("fmp_consensus_high_usd")
    low_usd = fve.get("fmp_consensus_low_usd")
    analyst_count = (ratings or {}).get("total") if ratings else None

    def _ret_pct(target: float | None) -> float | None:
        if target is None or current_price <= 0:
            return None
        return round(100.0 * (float(target) - current_price) / current_price, 1)

    median_return_pct = _ret_pct(median_usd if median_usd else None)
    high_return_pct = _ret_pct(high_usd if high_usd else None)
    low_return_pct = _ret_pct(low_usd if low_usd else None)

    meta = fair_value_metadata if isinstance(fair_value_metadata, dict) else {}
    method = meta.get("method_used")
    methodology = meta.get("methodology_summary")
    if methodology and len(str(methodology)) > 220:
        methodology = str(methodology)[:217] + "…"

    house: dict[str, Any] = {}
    if isinstance(entry_tiers, dict):
        ca = entry_tiers.get("current_assessment") or {}
        tiers = entry_tiers.get("tiers") or []
        active = entry_tiers.get("active_tier_id")
        house = {
            "active_tier_id": active,
            "assessment_label": ca.get("label"),
            "min_price_to_buy": ca.get("min_price_to_buy"),
            "above_full_mos_ceiling": ca.get("above_full_mos_ceiling"),
            "margin_of_safety_pct": ca.get("margin_of_safety_pct"),
            "tiers_summary": [
                {
                    "id": t.get("id"),
                    "label": t.get("label"),
                    "low": t.get("low"),
                    "high": t.get("high"),
                    "allocation_pct": t.get("allocation_pct"),
                }
                for t in tiers
                if isinstance(t, dict)
            ],
        }

    action_today = (one_answer or {}).get("action_today") if isinstance(one_answer, dict) else None
    scout_alert = False
    if ratings and action_today in ("hold", "wait_for_pullback", "no_new_position"):
        if (ratings.get("bullish_pct") or 0) >= 55:
            scout_alert = True
    if pct_vs_street is not None and gap_badge(pct_vs_street) == "caution":
        scout_alert = True

    has_street = street_usd is not None or fve.get("fmp_consensus_low_usd") is not None
    has_model = fair_value > 0
    has_house = bool(house.get("tiers_summary"))
    if not has_street and not has_model and not has_house:
        return None

    return {
        "street": {
            "primary_usd": round(street_usd, 2) if street_usd else None,
            "primary_label": street_label or None,
            "median_usd": round(float(median_usd), 2) if median_usd else None,
            "low_usd": low_usd,
            "high_usd": high_usd,
            "median_return_pct": median_return_pct,
            "high_return_pct": high_return_pct,
            "low_return_pct": low_return_pct,
            "analyst_count": analyst_count,
            "yahoo_mean_usd": fve.get("yahoo_12m_mean_usd"),
            "ratings": ratings,
            "eps_fwd": eps_fwd,
            "eps_dispersion": eps_dispersion,
        },
        "model": {
            "fair_value_usd": round(fair_value, 2) if fair_value > 0 else None,
            "pct_vs_street_primary": pct_vs_street,
            "gap_badge": gap_badge(pct_vs_street),
            "method_used": method,
            "methodology_summary": methodology,
            "relative_valuation_line": rel_line,
            "ttm_pe": ttm_pe,
            "forward_pe": forward_pe,
            "sector_pe_reference": sector_pe,
        },
        "house": house,
        "scout_street_alert": scout_alert,
        "disclaimer": "Street = context only. House tiers and model FV drive sizing — not analyst targets.",
    }
