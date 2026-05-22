"""
Price series profiling — young listings, spin-offs, extreme 52w ranges.

Fixes misleading MA200 / 52w-low stops when IPO or spin-off prices sit far below spot
(e.g. SNDK Feb 2025 listing ~$36 vs spot $1500+).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from signals.ticker_metadata import get_listing_event, listing_cutoff_date


def _as_series(close: pd.Series | None) -> pd.Series | None:
    if close is None or getattr(close, "empty", True):
        return None
    s = close.dropna()
    return s if len(s) else None


def trim_to_listing_date(ticker: str, close: pd.Series) -> pd.Series:
    """Drop bars before known re-listing / spin-off date."""
    cutoff = listing_cutoff_date(ticker)
    if cutoff is None or close.empty:
        return close
    try:
        idx = close.index
        if hasattr(idx, "tz") and idx.tz is not None:
            trimmed = close[idx >= pd.Timestamp(cutoff, tz=idx.tz)]
        else:
            trimmed = close[idx >= pd.Timestamp(cutoff)]
        return trimmed if len(trimmed) >= 20 else close
    except Exception:
        return close


def analyze_price_series(
    close: pd.Series | None,
    current_price: float | None,
    *,
    ticker: str = "",
) -> dict[str, Any]:
    """
    Profile adjusted OHLCV for horizon / stop / tier math.

    Returns effective_ma200, effective_52w_low, flags, and user-facing warnings.
    """
    s = _as_series(close)
    if s is None or current_price is None or current_price <= 0:
        return {"ok": False}

    s = trim_to_listing_date(ticker, s)
    n = len(s)
    cp = float(current_price)
    tail = s.iloc[-min(252, n):]
    raw_lo = float(tail.min())
    raw_hi = float(tail.max())
    range_ratio = raw_hi / raw_lo if raw_lo > 0 else 1.0

    young_listing = n < 220
    extreme_range = range_ratio >= 4.0
    listing_event = get_listing_event(ticker)

    ma50 = float(s.rolling(min(50, n)).mean().iloc[-1]) if n >= 20 else None
    ma120 = float(s.rolling(min(120, n)).mean().iloc[-1]) if n >= 60 else None
    ma200_raw = float(s.rolling(min(200, n)).mean().iloc[-1]) if n >= 50 else ma50

    effective_ma200 = ma200_raw
    if young_listing or extreme_range:
        # MA200 dominated by IPO/spin-off prices — use slower recent trend for tiers
        effective_ma200 = ma120 or ma50 or ma200_raw

    effective_52w_low = raw_lo
    if raw_lo < cp * 0.4:
        recent_90 = float(s.iloc[-min(90, n):].min())
        effective_52w_low = max(recent_90, cp * 0.55, raw_lo)

    warnings: list[str] = []
    if listing_event:
        warnings.append(listing_event.get("note") or f"{ticker}: recent listing/spin-off — tiers use post-event history only.")
    if young_listing:
        warnings.append(
            f"Only {n} daily bars available — MA200 is partial; long-term tiers use MA{min(120, n)} / recent trend instead."
        )
    if extreme_range:
        warnings.append(
            f"52-week range {range_ratio:.1f}x (${raw_lo:.0f}-${raw_hi:.0f}) — structural stop uses recent lows, not IPO trough."
        )
    if effective_52w_low > raw_lo * 1.05:
        warnings.append(
            f"Adjusted structural floor ${effective_52w_low:.0f} (raw 52w low ${raw_lo:.0f} ignored for stop math)."
        )

    return {
        "ok": True,
        "listing_bars": n,
        "young_listing": young_listing,
        "extreme_52w_range": extreme_range,
        "range_ratio_52w": round(range_ratio, 2),
        "raw_52w_low": round(raw_lo, 2),
        "raw_52w_high": round(raw_hi, 2),
        "raw_ma200": round(ma200_raw, 2) if ma200_raw else None,
        "effective_ma200": round(effective_ma200, 2) if effective_ma200 else None,
        "effective_52w_low": round(effective_52w_low, 2),
        "effective_ma50": round(ma50, 2) if ma50 else None,
        "listing_event": listing_event,
        "warnings": warnings,
    }


def apply_profile_to_levels(
    profile: dict[str, Any],
    *,
    ma200: float | None,
    ma50: float | None,
    low_52w: float | None,
) -> tuple[float | None, float | None, float | None]:
    """Return (ma200, ma50, low_52w) with effective overrides when profile flags issues."""
    if not profile.get("ok"):
        return ma200, ma50, low_52w
    out_ma200 = profile.get("effective_ma200") or ma200
    out_ma50 = profile.get("effective_ma50") or ma50
    out_lo = profile.get("effective_52w_low") or low_52w
    return out_ma200, out_ma50, out_lo
