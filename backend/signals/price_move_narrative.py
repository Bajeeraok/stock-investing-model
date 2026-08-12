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

Volume and RSI (both already computed upstream, no extra fetch) add a second
layer of plain-English color to every branch — especially "unclear," which
would otherwise be a dead end: even with no identified catalyst, "on 2.1x
average volume" or "RSI 74, already overbought" is a real, data-backed fact
worth surfacing rather than silence.
"""
from __future__ import annotations

from typing import Any, Literal

Driver = Literal["stock_specific", "broad_market", "earnings", "unclear"]

# Broad-market co-move thresholds: SPY must have moved meaningfully, and the
# ticker's move must be in the same direction and not wildly larger than SPY's.
_SPY_MEANINGFUL_MOVE_PCT = 0.5
_COMOVE_TOLERANCE_MULT = 2.5


def _volume_phrase(volume_ratio: float | None) -> str | None:
    """Plain-English volume color — only when it's actually notable (near-1x isn't worth a sentence)."""
    if volume_ratio is None or volume_ratio <= 0:
        return None
    if volume_ratio >= 2.0:
        return f"Volume is running {volume_ratio:.1f}x average — a real spike, consistent with the move getting noticed."
    if volume_ratio >= 1.4:
        return f"Volume is {volume_ratio:.1f}x average — somewhat elevated."
    if volume_ratio <= 0.6:
        return f"Volume is only {volume_ratio:.1f}x average — a quiet, low-conviction session."
    return None


def _rsi_phrase(rsi: float | None) -> str | None:
    """Plain-English momentum color — only when RSI is actually stretched, not mid-range noise."""
    if rsi is None:
        return None
    if rsi >= 70:
        return f"RSI is {rsi:.0f} — already technically overbought, so this move extends an already-stretched setup."
    if rsi <= 30:
        return f"RSI is {rsi:.0f} — technically oversold, so this is happening from an already-beaten-down level."
    return None


def _join_detail(*parts: str | None) -> str | None:
    joined = " ".join(p for p in parts if p)
    return joined or None


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


# Gold/commodity-FX names track the dollar, not equities — SPY is frequently the
# wrong cross-asset comparison for them (a quiet equity tape says nothing about
# a real DXY-driven gold move). DXY's day-to-day range also runs smaller than
# SPY's, so it needs its own (tighter) "meaningful move" bar, not SPY's.
_DXY_MEANINGFUL_MOVE_PCT = 0.3
_DXY_COMOVE_TOLERANCE_MULT = 3.0


def _dxy_comoves(day_change_pct: float | None, dxy_day_change_pct: float | None) -> bool:
    """Gold/USD-sensitive assets typically move opposite the dollar (DXY up -> gold down)."""
    if day_change_pct is None or dxy_day_change_pct is None:
        return False
    if abs(dxy_day_change_pct) < _DXY_MEANINGFUL_MOVE_PCT:
        return False
    opposite_sign = (day_change_pct >= 0) != (dxy_day_change_pct >= 0)
    if not opposite_sign:
        return False
    return abs(day_change_pct) <= _DXY_COMOVE_TOLERANCE_MULT * max(abs(dxy_day_change_pct), 0.1)


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
    volume_ratio: float | None = None,
    rsi: float | None = None,
    dxy_day_change_pct: float | None = None,
    cross_asset_badges: list[str] | None = None,
) -> dict[str, Any]:
    """Classify and explain today's price move. Returns driver/headline/detail/citation."""
    sym = (ticker or "This stock").upper() if ticker else "This stock"
    move_desc = None
    if day_change_pct is not None:
        direction = "up" if day_change_pct >= 0 else "down"
        move_desc = f"{sym} is {direction} {abs(day_change_pct):.1f}% today"

    vol_phrase = _volume_phrase(volume_ratio)
    rsi_phrase = _rsi_phrase(rsi)

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
            "detail": _join_detail(headline_txt, vol_phrase),
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
            "detail": _join_detail(vol_phrase, rsi_phrase),
            "citation": None,
        }

    # 3. Dollar co-move — checked before the generic SPY comparison, since gold/
    # USD-sensitive names track DXY far more directly than the equity tape. A
    # quiet SPY session (e.g. +0.2%, below the "meaningful" bar) says nothing
    # about a real DXY-driven gold move, which SPY-only comparison would miss
    # entirely and fall through to "unclear."
    is_dollar_sensitive = bool(cross_asset_badges) and any(
        b in cross_asset_badges for b in ("gold-sensitive", "USD-sensitive")
    )
    if is_dollar_sensitive and _dxy_comoves(day_change_pct, dxy_day_change_pct):
        headline = (
            f"{move_desc + ' — ' if move_desc else sym + ' moved '}"
            f"tracking the dollar inversely (DXY {dxy_day_change_pct:+.1f}%) — a classic gold/commodity-FX "
            "dynamic, not a stock-specific catalyst."
        )
        return {
            "driver": "broad_market",
            "headline": headline,
            "detail": _join_detail(vol_phrase),
            "citation": None,
        }

    # 4. Broad market (equity) co-move
    if _spy_comoves(day_change_pct, spy_day_change_pct):
        direction = "down with" if (spy_day_change_pct or 0) < 0 else "up with"
        headline = (
            f"{move_desc + ' — ' if move_desc else sym + ' moved '}"
            f"moving {direction} the broader market (SPY {spy_day_change_pct:+.1f}%), "
            "not on company-specific news."
        )
        regime_note = None
        gmr = (global_market_regime or "").upper()
        if gmr in ("BEAR", "STRONG_BEAR"):
            regime_note = f"Macro regime reads {gmr.replace('_', ' ').title()} — a broad risk-off tape, not a stock-specific problem."
        elif gmr in ("BULL", "STRONG_BULL"):
            regime_note = f"Macro regime reads {gmr.replace('_', ' ').title()} — broad risk-on tape lifting most names."
        return {
            "driver": "broad_market",
            "headline": headline,
            "detail": _join_detail(regime_note, vol_phrase),
            "citation": _macro_citation(market_catalysts),
        }

    # 5. No dominant driver identified — say so honestly rather than guess, but
    # volume/RSI are real, data-backed facts even when no catalyst was found.
    if move_desc and day_change_pct is not None and abs(day_change_pct) >= 1.0:
        headline = f"{move_desc} without a clear stock-specific catalyst or broad-market co-move — likely technical (volume, positioning, or a smaller headline not yet classified)."
    else:
        headline = f"{sym}'s move today is modest — no dominant catalyst to flag."
    return {
        "driver": "unclear",
        "headline": headline,
        "detail": _join_detail(vol_phrase, rsi_phrase),
        "citation": None,
    }
