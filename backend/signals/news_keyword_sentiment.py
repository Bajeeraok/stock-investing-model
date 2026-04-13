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

# Gold / silver / broad commodity ETF headlines (Yahoo/FMP often cite spot, macro, USD)
COMMODITY_BULLISH_KEYWORDS = frozenset({
    "gold", "silver", "bullion", "precious", "metals", "mining", "miners",
    "inflation", "hedge", "haven", "safe-haven", "safehaven",
    "dxy", "treasury", "cuts",
    "ounces", "ounce", "spot", "commodity", "commodities", "futures",
    "rally", "rallies", "surge", "record", "highs", "breakout",
})

COMMODITY_BEARISH_KEYWORDS = frozenset({
    "hawkish", "tightening", "risk-on", "riskon", "slump", "deflation",
    "outflows", "liquidation",
})

# Tickers that should merge COMMODITY_* with base lexicon (ETF symbols only)
_COMMODITY_LEXICON_TICKERS = frozenset({
    "GLD", "SLV", "IAU", "SGOL", "BAR", "OUNZ", "AAAU", "GLDM", "SIVR", "PSLV",
    "GDX", "GDXJ", "SIL", "RING", "USO", "UNG", "DBC", "COM", "BNO", "UGA",
})


def _use_commodity_lexicon(ticker: str | None) -> bool:
    if not ticker:
        return False
    sym = (ticker or "").upper().replace(".", "-").split("-")[0].strip()
    return sym in _COMMODITY_LEXICON_TICKERS


def _normalize_words(text: str) -> set[str]:
    if not text:
        return set()
    s = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return {w for w in s.split() if len(w) >= 2}


def _lexicons_for_ticker(ticker: str | None):
    bull, bear = BULLISH_KEYWORDS, BEARISH_KEYWORDS
    if _use_commodity_lexicon(ticker):
        bull = frozenset(bull | COMMODITY_BULLISH_KEYWORDS)
        bear = frozenset(bear | COMMODITY_BEARISH_KEYWORDS)
    return bull, bear


def score_headline_text(title: str, text: str = "", *, ticker: str | None = None) -> tuple[float, bool]:
    """
    Return (raw -1..1, hit) for one article. hit=False if no lexicon overlap.
    Commodity ETFs (GLD, SLV, …) merge a macro/precious-metals lexicon with the base set.
    """
    words = _normalize_words(f"{title} {text or ''}")
    lb, dk = _lexicons_for_ticker(ticker)
    bull = len(words & lb)
    bear = len(words & dk)
    if bull + bear == 0:
        return 0.0, False
    raw = (bull - bear) / float(bull + bear)
    return float(np.clip(raw, -1.0, 1.0)), True


def aggregate_keyword_sentiment(
    articles: list[dict[str, Any]],
    *,
    decay: float = 0.08,
    ticker: str | None = None,
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
        raw, hit = score_headline_text(title, body, ticker=ticker)
        if hit:
            any_hit = True
            scores.append(raw)
            weights.append(float(np.exp(-decay * i)))
    if not scores or not weights:
        return None, len(articles), False
    avg = float(np.average(np.array(scores), weights=np.array(weights)))
    return float(np.clip(avg, -1.0, 1.0)), len(articles), True
