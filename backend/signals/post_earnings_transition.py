"""
Post-earnings transition signal.

Detects whether recent earnings were a beat or miss (within 5 trading days)
and generates a transition signal combining:
  - EPS surprise % from FMP earnings-surprises
  - Post-earnings price action (return since earnings date)
  - Volume spike ratio (post vs pre-earnings)

Does NOT override existing verdicts — produces an advisory payload
that downstream consumers use to annotate signals.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_MAX_DAYS_SINCE = 5


@dataclass
class PostEarningsSignal:
    """Advisory signal generated within N days of an earnings report."""
    active: bool = False
    beat_or_miss: str | None = None        # "beat", "miss", "inline"
    eps_surprise_pct: float | None = None   # (actual - estimated) / |estimated| * 100
    actual_eps: float | None = None
    estimated_eps: float | None = None
    earnings_date: str | None = None
    days_since: int | None = None
    price_reaction_pct: float | None = None  # post-earnings return %
    volume_ratio: float | None = None        # post-day vol / 20d pre avg
    transition_note: str | None = None
    signal_direction: str | None = None      # "bullish", "bearish", "neutral"


def _fetch_latest_surprise(config: dict, ticker: str) -> dict | None:
    """Fetch most recent row from FMP earnings-surprises endpoint."""
    try:
        from signals.fmp_client import get_api_key, _request, BASE_V3
    except ImportError:
        return None
    api_key = get_api_key(config)
    if not api_key:
        return None
    sym = (ticker or "").upper().replace(".", "-").split("-")[0]
    url = f"{BASE_V3}/earnings-surprises/{sym}"
    data, err = _request(url, api_key)
    if err or not isinstance(data, list) or not data:
        return None
    for row in data:
        if not isinstance(row, dict):
            continue
        actual = row.get("actualEarningResult")
        estimated = row.get("estimatedEarning")
        if actual is not None and estimated is not None:
            return row
    return None


def compute_post_earnings_signal(
    ticker: str,
    config: dict,
    *,
    earnings_context: dict | None = None,
) -> PostEarningsSignal:
    """
    Build a post-earnings transition signal.

    `earnings_context` should come from the confidence engine's existing
    earnings tracking:
      - most_recent_earnings_date
      - days_since_earnings
      - post_earnings_return_pct
      - post_earnings_volume_ratio
    """
    if not earnings_context:
        return PostEarningsSignal()

    days_since = earnings_context.get("days_since_earnings")
    if days_since is None or days_since > _MAX_DAYS_SINCE:
        return PostEarningsSignal()

    earnings_date = earnings_context.get("most_recent_earnings_date")
    price_reaction = earnings_context.get("post_earnings_return_pct")
    volume_ratio = earnings_context.get("post_earnings_volume_ratio")

    # Try to get actual/estimated EPS from FMP
    actual_eps = None
    estimated_eps = None
    eps_surprise_pct = None
    beat_or_miss = None

    try:
        surprise_row = _fetch_latest_surprise(config, ticker)
        if surprise_row:
            actual_eps = _safe_float(surprise_row.get("actualEarningResult"))
            estimated_eps = _safe_float(surprise_row.get("estimatedEarning"))
            if actual_eps is not None and estimated_eps is not None and abs(estimated_eps) > 0.001:
                eps_surprise_pct = round((actual_eps - estimated_eps) / abs(estimated_eps) * 100, 1)
                if eps_surprise_pct > 5:
                    beat_or_miss = "beat"
                elif eps_surprise_pct < -5:
                    beat_or_miss = "miss"
                else:
                    beat_or_miss = "inline"
    except Exception:
        logger.debug("Could not fetch earnings surprise for %s", ticker)

    # Fallback: infer beat/miss from price action if EPS data unavailable
    if beat_or_miss is None and price_reaction is not None:
        if price_reaction > 3.0:
            beat_or_miss = "beat"
        elif price_reaction < -3.0:
            beat_or_miss = "miss"
        else:
            beat_or_miss = "inline"

    if beat_or_miss is None:
        return PostEarningsSignal()

    # Determine signal direction from combination of EPS + price action
    signal_direction = _infer_direction(beat_or_miss, price_reaction, eps_surprise_pct)

    # Build transition note
    transition_note = _build_note(
        ticker, beat_or_miss, eps_surprise_pct, price_reaction,
        volume_ratio, days_since, signal_direction,
    )

    return PostEarningsSignal(
        active=True,
        beat_or_miss=beat_or_miss,
        eps_surprise_pct=eps_surprise_pct,
        actual_eps=actual_eps,
        estimated_eps=estimated_eps,
        earnings_date=earnings_date,
        days_since=days_since,
        price_reaction_pct=round(price_reaction, 2) if price_reaction is not None else None,
        volume_ratio=round(volume_ratio, 2) if volume_ratio is not None else None,
        transition_note=transition_note,
        signal_direction=signal_direction,
    )


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _infer_direction(
    beat_or_miss: str,
    price_reaction: float | None,
    eps_surprise_pct: float | None,
) -> str:
    """Combine EPS outcome + price reaction into a directional signal."""
    pr = price_reaction or 0.0
    eps = eps_surprise_pct or 0.0

    if beat_or_miss == "beat":
        if pr >= 0:
            return "bullish"
        # Beat but selling off — "sell the news" pattern
        if pr < -5:
            return "bearish"
        return "neutral"

    if beat_or_miss == "miss":
        if pr <= 0:
            return "bearish"
        # Miss but rallying — "buy the dip" / low bar pattern
        if pr > 5:
            return "bullish"
        return "neutral"

    # Inline
    if abs(pr) < 2:
        return "neutral"
    return "bullish" if pr > 0 else "bearish"


def _build_note(
    ticker: str,
    beat_or_miss: str,
    eps_surprise_pct: float | None,
    price_reaction: float | None,
    volume_ratio: float | None,
    days_since: int | None,
    signal_direction: str,
) -> str:
    """Build a human-readable transition note."""
    parts: list[str] = [f"{ticker} reported earnings"]

    if days_since is not None:
        parts.append(f"{days_since} day{'s' if days_since != 1 else ''} ago")

    if beat_or_miss == "beat":
        if eps_surprise_pct is not None:
            parts.append(f"\u2014 beat by {eps_surprise_pct:+.1f}%")
        else:
            parts.append("\u2014 earnings beat")
    elif beat_or_miss == "miss":
        if eps_surprise_pct is not None:
            parts.append(f"\u2014 missed by {eps_surprise_pct:+.1f}%")
        else:
            parts.append("\u2014 earnings miss")
    else:
        parts.append("\u2014 roughly inline with estimates")

    if price_reaction is not None:
        parts.append(f"Stock {price_reaction:+.1f}% since report.")
    if volume_ratio is not None and volume_ratio > 1.5:
        parts.append(f"Volume {volume_ratio:.1f}x normal.")

    # Actionable guidance
    if signal_direction == "bullish":
        parts.append(
            "Post-earnings momentum is positive \u2014 signal upgrading; "
            "consider the updated regime for entry decisions."
        )
    elif signal_direction == "bearish":
        parts.append(
            "Post-earnings reaction is negative \u2014 signal adjusting downward; "
            "wait for price to stabilize before trusting pre-earnings levels."
        )
    else:
        parts.append(
            "Post-earnings reaction is muted \u2014 existing signal levels remain valid; "
            "watch for follow-through in the next few sessions."
        )

    return " ".join(parts)
