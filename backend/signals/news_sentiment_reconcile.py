"""Display-only news label vs headline/card stance.

Does not change fused confidence, MOS, gates, or bands. When the chip says
Bullish and the headlines/cards look negative (or the reverse), surface a
caveat instead of blending scores.
"""
from __future__ import annotations

import re
from typing import Any

_BEAR_TITLE = re.compile(
    r"\b(drop|drops|dropped|plunge|plunges|plunged|tumble|tumbles|slump|slumps|"
    r"warning|warnings|miss|misses|downgrade|lawsuit|probe|fraud|selloff|"
    r"crash|layoff)\b",
    re.I,
)
_BULL_TITLE = re.compile(
    r"\b(beat|beats|surge|surges|rally|rallies|upgrade|upgrades|record|"
    r"breakthrough|outperform)\b",
    re.I,
)


def _norm_label(label: str | None) -> str:
    s = (label or "").strip().lower()
    if "bull" in s:
        return "bullish"
    if "bear" in s:
        return "bearish"
    return "neutral"


def headline_title_stance(titles: list[str]) -> str:
    """Majority vote on titles. unknown if no hits."""
    bull = bear = 0
    for t in titles:
        if _BEAR_TITLE.search(t or ""):
            bear += 1
        if _BULL_TITLE.search(t or ""):
            bull += 1
    if bear == 0 and bull == 0:
        return "unknown"
    if bear > bull:
        return "bearish"
    if bull > bear:
        return "bullish"
    return "mixed"


def card_direction_stance(cards: list[dict[str, Any]] | None) -> str:
    unlocks = breaks = 0
    for c in cards or []:
        if not isinstance(c, dict):
            continue
        d = str(c.get("direction") or "").lower()
        if d == "unlocks":
            unlocks += 1
        elif d == "breaks":
            breaks += 1
    if unlocks == 0 and breaks == 0:
        return "unknown"
    if breaks > unlocks:
        return "bearish"
    if unlocks > breaks:
        return "bullish"
    return "mixed"


def reconcile_news_display(
    *,
    sentiment_label: str | None,
    score_0_1: float | None,
    headlines: list[dict[str, Any]] | None,
    cards: list[dict[str, Any]] | None,
    hmm_bull_pct: float | None = None,
) -> dict[str, Any]:
    """Return display_label + optional caveat. Leaves score_0_1 untouched."""
    chip = _norm_label(sentiment_label)
    if chip == "neutral" and score_0_1 is not None:
        if score_0_1 >= 0.55:
            chip = "bullish"
        elif score_0_1 <= 0.45:
            chip = "bearish"

    titles = []
    for h in headlines or []:
        if isinstance(h, dict):
            titles.append(str(h.get("title") or ""))
        elif isinstance(h, str):
            titles.append(h)
    h_stance = headline_title_stance(titles)
    c_stance = card_direction_stance(cards)

    evidence = c_stance if c_stance != "unknown" else h_stance
    disagree = (
        (chip == "bullish" and evidence == "bearish")
        or (chip == "bearish" and evidence == "bullish")
    )

    display = (sentiment_label or "Neutral").strip() or "Neutral"
    caveat = None
    if disagree:
        display = "Mixed"
        if chip == "bullish":
            caveat = (
                "Headlines look negative while the news chip is bullish — "
                "treat this as a caveat, not a buy signal."
            )
        else:
            caveat = (
                "Headlines look constructive while the news chip is bearish — "
                "treat this as a caveat, not a trim signal."
            )
        if hmm_bull_pct is not None:
            caveat += f" Regime is {float(hmm_bull_pct):.0f}% bull."

    return {
        "display_label": display,
        "disagreement": disagree,
        "caveat": caveat,
        "headline_stance": h_stance,
        "card_stance": c_stance,
        "chip_stance": chip,
    }
