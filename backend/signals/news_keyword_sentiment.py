"""
Keyword-based sentiment for news headlines (FMP path has no ML scores).

Maps headline + optional snippet text to a raw score in [-1, 1] using
overlaps with bullish/bearish lexicons. Not FinBERT-quality, but removes
the constant 0.5 neutral placeholder when real words are present.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np

# Compact lexicons — extend over time; keep lowercase tokens after normalize
BULLISH_KEYWORDS = frozenset({
    "beat", "beats", "record", "surge", "surges", "rally", "rallies", "rallying",
    "upgrade", "upgrades", "upgraded", "outperform", "buy", "growth", "profit",
    "profits", "strong", "stronger", "raised", "raises", "exceeds", "exceeded",
    "positive", "optimism", "optimistic", "ceasefire", "deal", "deals", "partnership",
    "partnerships", "breakthrough", "expands", "expansion", "gain", "gains", "win",
    "wins", "bullish", "upside", "rebound", "recovery", "recoveries", "momentum",
})

BEARISH_KEYWORDS = frozenset({
    "miss", "misses", "cut", "cuts", "downgrade", "downgrades", "downgraded",
    "sell", "loss", "losses", "decline", "declines", "warning", "warnings",
    "weak", "weaker", "lawsuit", "investigation", "below", "layoff", "layoffs",
    "recession", "risk", "risks", "bearish", "downside", "crash", "selloff",
    "bankruptcy", "probe", "fraud", "guidance", "slashes", "slashed",
})


def _normalize_words(text: str) -> set[str]:
    if not text:
        return set()
    s = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return {w for w in s.split() if len(w) >= 2}


def score_headline_text(title: str, text: str = "") -> tuple[float, bool]:
    """
    Return (raw -1..1, hit) for one article. hit=False if no lexicon overlap.
    """
    words = _normalize_words(f"{title} {text or ''}")
    bull = len(words & BULLISH_KEYWORDS)
    bear = len(words & BEARISH_KEYWORDS)
    if bull + bear == 0:
        return 0.0, False
    raw = (bull - bear) / float(bull + bear)
    return float(np.clip(raw, -1.0, 1.0)), True


def aggregate_keyword_sentiment(
    articles: list[dict[str, Any]],
    *,
    decay: float = 0.08,
) -> tuple[float | None, int, bool]:
    """
    Weight recent articles higher (index 0 = newest from FMP).

    Returns:
        (raw_avg in [-1,1] or None if no keyword hits, headline_count, any_hit)
    """
    if not articles:
        return None, 0, False
    scores: list[float] = []
    weights: list[float] = []
    any_hit = False
    for i, item in enumerate(articles):
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or item.get("headline") or "")[:500]
        body = (
            item.get("text")
            or item.get("description")
            or item.get("content")
            or item.get("summary")
            or ""
        )[:2000]
        raw, hit = score_headline_text(title, body)
        if hit:
            any_hit = True
            scores.append(raw)
            weights.append(float(np.exp(-decay * i)))
    if not scores or not weights:
        return None, len(articles), False
    avg = float(np.average(np.array(scores), weights=np.array(weights)))
    return float(np.clip(avg, -1.0, 1.0)), len(articles), True
