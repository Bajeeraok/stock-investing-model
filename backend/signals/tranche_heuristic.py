"""
Dynamic long-horizon tranche weights (T1 MA200 / T2 MOS / T3 tail).

Single source of truth for:
  - horizon_entry_calculator long-term position_sizing
  - trade roadmap allocation copy (via tranche_policy summary)

Heuristic: nearer to MA200 + lower ATR% + higher model confidence → more weight on
T1/T2 (starter + core); extended above MA200 + elevated vol + low confidence → shift
mass toward T3 (tail reserve). Same story as roadmap allocation_note.
"""
from __future__ import annotations

from typing import Any


def _largest_remainder_round_three(w1: float, w2: float, w3: float) -> tuple[int, int, int]:
    """Round three positive weights to integers summing to 100."""
    s = w1 + w2 + w3
    if s <= 0:
        return 25, 50, 25
    p = [100.0 * w1 / s, 100.0 * w2 / s, 100.0 * w3 / s]
    fl = [int(x) for x in p]
    rem = 100 - sum(fl)
    order = sorted(range(3), key=lambda i: p[i] - fl[i], reverse=True)
    for k in range(rem):
        fl[order[k]] += 1
    return int(fl[0]), int(fl[1]), int(fl[2])


def compute_long_horizon_tier_percentages(
    *,
    current_price: float,
    ma200: float | None,
    atr: float | None,
    model_confidence_pct: float | None,
) -> dict[str, Any]:
    """
    Returns t1_pct, t2_pct, t3_pct (sum 100) plus diagnostic fields.
    """
    conf_f = 0.5
    if model_confidence_pct is not None:
        try:
            conf_f = max(0.0, min(1.0, float(model_confidence_pct) / 100.0))
        except (TypeError, ValueError):
            pass

    ext = 0.0
    if ma200 is not None and ma200 > 0 and current_price > 0:
        ext = max(0.0, (float(current_price) / float(ma200) - 1.0) * 100.0)

    atr_pct = 2.0
    if atr is not None and current_price and current_price > 0:
        try:
            atr_pct = float(atr) / float(current_price) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    # 0–1 stress: extended above MA200 + elevated realized vol
    extension_stress = min(1.0, ext / 12.0)
    vol_stress = min(1.0, max(0.0, atr_pct - 1.5) / 4.0)
    stress = min(
        1.0,
        0.52 * extension_stress + 0.33 * vol_stress + 0.15 * (1.0 - conf_f),
    )

    # Base weights (starter / core / tail)
    w1, w2, w3 = 25.0, 50.0, 25.0
    shift = stress * 22.0
    w1 -= shift * 0.38
    w2 -= shift * 0.57
    w3 += shift

    conf_boost = (conf_f - 0.5) * 10.0
    w1 += conf_boost * 0.45
    w2 += conf_boost * 0.45
    w3 -= conf_boost * 0.90
    w1 = max(5.0, w1)
    w2 = max(10.0, w2)
    w3 = max(5.0, w3)

    t1, t2, t3 = _largest_remainder_round_three(w1, w2, w3)

    summary = (
        f"T1/T2/T3 = {t1}% / {t2}% / {t3}% of target — "
        f"extension vs MA200 {ext:+.1f}%, ATR/price {atr_pct:.1f}%, "
        f"model confidence {conf_f * 100:.0f}% (stress {stress:.2f}). "
        "Extended / high vol → smaller front-load, larger tail slice."
    )

    return {
        "t1_pct": t1,
        "t2_pct": t2,
        "t3_pct": t3,
        "ext_ma200_pct": round(ext, 2),
        "atr_pct_of_price": round(atr_pct, 2),
        "stress01": round(stress, 3),
        "model_confidence_pct": round(conf_f * 100, 1),
        "summary_line": summary,
    }


def roadmap_allocation_note_for_timeline(timeline_key: str, policy: dict[str, Any] | None) -> str | None:
    """Map buy-roadmap row to tier emphasis using shared T1/T2/T3 weights."""
    if not policy:
        return None
    t1 = policy.get("t1_pct")
    t2 = policy.get("t2_pct")
    t3 = policy.get("t3_pct")
    summary = policy.get("summary_line") or ""
    lead = {
        "today": f"Aligns with starter / MA200 tier emphasis (~{t1}% T1 weight in long-horizon plan).",
        "days_1_10": f"Same near-term band — patience; tier plan still T1≈{t1}%, T2≈{t2}%, T3≈{t3}%.",
        "week_2_4": f"Short swing adds: mostly Tier 1 (MA200) lane — ~{t1}% of staged target in plan.",
        "1_3_months": f"Core scaling aligns with Tier 2 (~{t2}% in plan).",
        "3_6_months": f"Structural core: Tier 1–2 mix (~{t1}% + ~{t2}% in plan).",
        "6_12_months": f"Tail / stress sleeve — Tier 3 ~{t3}% reserved for rare breaks.",
    }.get(timeline_key, f"Staged plan T1/T2/T3 = {t1}% / {t2}% / {t3}%.")
    return f"{lead} {summary}".strip()
