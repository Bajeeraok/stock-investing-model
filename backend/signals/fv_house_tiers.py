"""
Tag long-term entry tiers when model FV is suppressed but bands use street consensus.
"""
from __future__ import annotations

from typing import Any


def tag_entry_tiers_street_anchor(
    entry_tiers: dict[str, Any] | None,
    *,
    fv_suppressed: bool,
    fv_suppressed_reason: str = "",
    street_anchor_usd: float | None = None,
    street_anchor_source: str | None = None,
) -> dict[str, Any] | None:
    """
    When model FV is suppressed, tiers may still be computed from analyst consensus.
    Surface that explicitly so UI/copy does not imply a validated model fair value.
    """
    if not isinstance(entry_tiers, dict):
        return entry_tiers
    if not fv_suppressed or not street_anchor_usd or street_anchor_usd <= 0:
        return entry_tiers

    et = dict(entry_tiers)
    src = street_anchor_source or "street_consensus"
    anchor_note = (
        f"Model FV unavailable ({fv_suppressed_reason or 'suppressed'}). "
        f"Tier bands anchored to {src.replace('_', ' ')} ${street_anchor_usd:.2f} — "
        "not a validated intrinsic value."
    )

    et["fv_anchor"] = {
        "source": "street_consensus",
        "street_anchor_usd": round(float(street_anchor_usd), 2),
        "street_anchor_source": src,
        "fv_model_suppressed": True,
        "fv_suppressed_reason": fv_suppressed_reason or None,
        "band_anchor_note": anchor_note,
    }

    ca = dict(et.get("current_assessment") or {})
    label = str(ca.get("label") or "").strip()
    suffix = " (street-anchored — model FV unavailable)"
    if suffix.lower() not in label.lower():
        ca["label"] = f"{label}{suffix}" if label else "Street-anchored tiers — model FV unavailable"
    ca["fv_model_suppressed"] = True
    ca["fv_street_anchored"] = True
    et["current_assessment"] = ca
    return et
