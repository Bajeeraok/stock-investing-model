"""
Shared structural invalidation level: max(MA200×0.97, 52w-low×0.97) when both exist.

Using the 52-week tail alone can mis-state risk for instruments trading far above a
deep low (e.g. commodity ETFs). Dashboard TL;DR, confidence watch levels, horizon
stops, and the sell-roadmap Immediate row should stay consistent.
"""
from __future__ import annotations


def structural_invalidation_below(
    ma200: float | None,
    low_52w: float | None,
    *,
    fallback: float,
) -> float:
    """
    Primary invalidation reference below price: prefer max(MA200, 52w tail) × 0.97.

    `fallback` is used when MA200 or 52w inputs are missing (typically the same as
    the legacy 52w-based stop, e.g. low_52w × 0.97).
    """
    try:
        ma200_k = float(ma200) if ma200 is not None else None
        tail_k = float(low_52w) * 0.97 if low_52w is not None else None
        if ma200_k is not None and tail_k is not None:
            return max(ma200_k * 0.97, tail_k)
        if ma200_k is not None:
            return ma200_k * 0.97
        if tail_k is not None:
            return tail_k
        return float(fallback)
    except (TypeError, ValueError):
        return float(fallback)
