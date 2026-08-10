"""
Plain-English "why is this stock moving" narrative for ticker detail.

Rule-based only (no LLM) — classifies today's move using data already computed
elsewhere in the pipeline:
  - Stock-specific catalyst (signals.catalyst_detector, via the confidence engine's
    nlp_sentiment layer) — earnings beat/miss, guidance cut/raise, analyst action,
    M&A, legal/regulatory, etc.
  - Broad-market attribution — compares the ticker's move to SPY's same-day move;
    when they track together, the move is macro/market-driven rather than
    company-specific.
  - Scheduled macro events (signals.market_catalysts, FOMC/CPI/NFP/GDP) — cited
    only when a same-day catalyst board is available; framed as "today's macro
    tape", not asserted as the definitive cause.

Deliberately does not fabricate a cause: when neither a stock-specific catalyst
nor a broad-market co-move is detected, the narrative says so plainly rather than
guessing (e.g. "war", "jobs report") without data behind it.
"""
from __future__ import annotations

from typing import Any, Literal

Driver = Literal["stock_specific", "broad_market", "earnings", "unclear"]

# Broad-market co-move thresholds: SPY must have moved meaningfully, and the
# ticker's move must be in the same direction and not wildly larger than SPY's.
_SPY_MEANINGFUL_MOVE_PCT = 0.5
_COMOVE_TOLERANCE_MULT = 2.5


def _spy_comoves(day_change_pct: float | None, spy_day_change_pct: float | None) -> bool:
    if day_change_pct is None or spy_day_change_pct is None:
        return False
    if abs(spy_day_change_pct) < _SPY_MEANINGFUL_MOVE_PCT:
        return False
    same_sign = (day_change_pct >= 0) == (spy_day_change_pct >= 0)
    if not same_sign:
        return False
    # Ticker can move more than SPY (higher beta) but not so much more that the
    # move is clearly idiosyncratic rather than market-driven.
    return abs(day_change_pct) <= _COMOVE_TOLERANCE_MULT * max(abs(spy_day_change_pct), 0.1)


def _macro_citation(market_catalysts: dict[str, Any] | None) -> str | None:
    if not isinstance(market_catalysts, dict):
        return None
    scheduled = market_catalysts.get("scheduled_today") or []
    names = [str(e.get("name")) for e in scheduled if isinstance(e, dict) and e.get("name")]
    summary = market_catalysts.get("summary_line")
    if names and summary:
        return f"Today's macro tape ({', '.join(names[:2])}): {summary}"
    if summary:
        return f"Today's macro tape: {summary}"
    if names:
        return f"Scheduled today: {', '.join(names[:2])} — check for a surprise vs. consensus."
    return None


def build_price_move_narrative(
    *,
    ticker: str | None,
    day_change_pct: float | None,
    spy_day_change_pct: float | None,
    global_market_regime: str | None = None,
    catalyst: dict[str, Any] | None = None,
    market_catalysts: dict[str, Any] | None = None,
    earnings_days_until: int | None = None,
    earnings_days_since: int | None = None,
) -> dict[str, Any]:
    """Classify and explain today's price move. Returns driver/headline/detail/citation."""
    sym = (ticker or "This stock").upper() if ticker else "This stock"
    move_desc = None
    if day_change_pct is not None:
        direction = "up" if day_change_pct >= 0 else "down"
        move_desc = f"{sym} is {direction} {abs(day_change_pct):.1f}% today"

    # 1. Stock-specific catalyst (real classified news event, not a guess)
    if isinstance(catalyst, dict) and catalyst.get("active"):
        friendly = str(catalyst.get("top_event_type") or "news event").lower().replace("_", " ")
        headline_txt = catalyst.get("headline_summary")
        hours = catalyst.get("hours_since_catalyst")
        age = f"{hours:.0f}h ago" if isinstance(hours, (int, float)) and hours < 24 else (
            f"{hours / 24:.0f}d ago" if isinstance(hours, (int, float)) else "recently"
        )
        headline = f"{move_desc + ' — ' if move_desc else ''}looks stock-specific: {friendly} ({age})."
        return {
            "driver": "stock_specific",
            "headline": headline,
            "detail": headline_txt,
            "citation": catalyst.get("override_note"),
        }

    # 2. Recent earnings (no other catalyst matched, but a report just printed)
    if earnings_days_since is not None and 0 <= earnings_days_since <= 2:
        headline = (
            f"{move_desc + ' — ' if move_desc else sym + ' — '}"
            f"likely still digesting its earnings report from {earnings_days_since} day"
            f"{'s' if earnings_days_since != 1 else ''} ago."
        )
        return {
            "driver": "earnings",
            "headline": headline,
            "detail": None,
            "citation": None,
        }

    # 3. Broad market co-move
    if _spy_comoves(day_change_pct, spy_day_change_pct):
        direction = "down with" if (spy_day_change_pct or 0) < 0 else "up with"
        headline = (
            f"{move_desc + ' — ' if move_desc else sym + ' moved '}"
            f"moving {direction} the broader market (SPY {spy_day_change_pct:+.1f}%), "
            "not on company-specific news."
        )
        detail = None
        gmr = (global_market_regime or "").upper()
        if gmr in ("BEAR", "STRONG_BEAR"):
            detail = f"Macro regime reads {gmr.replace('_', ' ').title()} — a broad risk-off tape, not a stock-specific problem."
        elif gmr in ("BULL", "STRONG_BULL"):
            detail = f"Macro regime reads {gmr.replace('_', ' ').title()} — broad risk-on tape lifting most names."
        return {
            "driver": "broad_market",
            "headline": headline,
            "detail": detail,
            "citation": _macro_citation(market_catalysts),
        }

    # 4. No dominant driver identified — say so honestly rather than guess
    if move_desc and day_change_pct is not None and abs(day_change_pct) >= 1.0:
        headline = f"{move_desc} without a clear stock-specific catalyst or broad-market co-move — likely technical (volume, positioning, or a smaller headline not yet classified)."
    else:
        headline = f"{sym}'s move today is modest — no dominant catalyst to flag."
    return {
        "driver": "unclear",
        "headline": headline,
        "detail": None,
        "citation": None,
    }
