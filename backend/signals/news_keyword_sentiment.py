"""
Keyword-based sentiment for news headlines (FMP path has no ML scores).

Maps headline + optional snippet text to a raw score in [-1, 1] using
overlaps with bullish/bearish lexicons. Commodity / precious-metal ETFs can
use an additional phrase lexicon (see :func:`score_headlines`).

Per-article weights combine recency decay with ``news_quality_filter``
(domain tier × headline pattern) so SEO sources and filing headlines
do not dominate the aggregate.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, TypedDict

import numpy as np

from signals.news_commodity_lexicon import (
    COMMODITY_LEXICON_TICKERS,
    COMMODITY_PHRASE_SCORER_TICKERS,
    get_commodity_phrase_lexicon,
)
from signals.news_quality_filter import compute_quality_weight

# Re-export for tests / callers
_COMMODITY_LEXICON_TICKERS = COMMODITY_LEXICON_TICKERS

# Compact lexicons — extend over time; keep lowercase tokens after normalize
BULLISH_KEYWORDS = frozenset({
    "beat", "beats", "record", "surge", "surges", "rally", "rallies", "rallying",
    "upgrade", "upgrades", "upgraded", "outperform", "buy", "growth", "profit",
    "profits", "strong", "stronger", "raised", "raises", "exceeds", "exceeded",
    "positive", "optimism", "optimistic", "ceasefire", "partnership",
    "partnerships", "breakthrough", "expands", "expansion", "gain", "gains", "win",
    "wins", "bullish", "upside", "rebound", "recovery", "recoveries", "momentum",
})

BEARISH_KEYWORDS = frozenset({
    "miss", "misses", "downgrade", "downgrades", "downgraded",
    "sell", "sold", "loss", "losses", "decline", "declines", "warning", "warnings",
    "weak", "weaker", "lawsuit", "investigation", "below", "layoff", "layoffs",
    "recession", "risk", "risks", "bearish", "downside", "crash", "selloff",
    "bankruptcy", "probe", "fraud", "slashes", "slashed",
    "reduces", "reduced", "trimmed", "trims", "trimming", "unloaded",
    "drop", "drops", "dropped", "plunge", "plunges", "plunged",
    "tumble", "tumbles", "tumbled", "slump", "slumps",
    # NOTE: "cut"/"cuts", "stake", and "guidance" deliberately excluded as bare
    # words — each is too context-dependent to score on its own ("rate cuts"/
    # "cost cuts" are commonly bullish, "increases stake" is bullish, "raises
    # guidance" is bullish). The genuinely-bearish senses are captured as
    # specific phrases below instead (_BEARISH_PHRASES), which only fire when
    # the negative direction is actually present in the text.
})

# Gold / silver / broad commodity ETF headlines (Yahoo/FMP often cite spot, macro, USD)
COMMODITY_BULLISH_KEYWORDS = frozenset({
    "gold", "silver", "bullion", "precious", "metals", "mining", "miners",
    "inflation", "hedge", "haven", "safe-haven", "safehaven",
    "dxy", "treasury", "cuts",
    "ounces", "ounce", "spot", "commodity", "commodities", "futures",
    "rally", "rallies", "surge", "record", "highs", "breakout",
    "soar", "soars", "soaring", "spike", "spikes", "spiking",
})

COMMODITY_BEARISH_KEYWORDS = frozenset({
    "hawkish", "tightening", "risk-on", "riskon", "slump", "deflation",
    "outflows", "liquidation",
})

# Institutional / 13F-style phrasing (not the same as “stock drops”)
_BEARISH_PHRASES = (
    "competitive threat",
    "competitor win",
    "loses share",
    "losing share",
    "takes share",
    "taking share",
    "market share loss",
    "custom silicon",
    "in-house chip",
    "google tpu",
    "rival chip",

    "shares sold",
    "sold shares",
    "reduces stake",
    "reduce stake",
    "reduced stake",
    "trimming position",
    "trims position",
    "trim position",
    "cuts position",
    "decreases stake",
    "decreased stake",
    "lowers stake",
    # Direction-specific senses of "cut"/"guidance" — the bare words were
    # removed from BEARISH_KEYWORDS (see note there) because they're too
    # often bullish ("rate cuts", "cost cuts", "raises guidance"); these
    # phrases only fire when the actual negative direction is present.
    "guidance cut",
    "cuts guidance",
    "cut guidance",
    "lowered guidance",
    "lowers guidance",
    "guidance miss",
    "missed guidance",
    "below guidance",
    "dividend cut",
    "cuts dividend",
    "cuts jobs",
    "job cuts",
    "shares drop",
    "shares dropped",
    "shares fall",
    "shares plunged",
    "stock drops",
    "stock drop",
    "profit warning",
)

DEFAULT_MIN_QUALITY_WEIGHT = 0.20
_DEFAULT_COMMODITY_TEXT_LIMIT = 500


def norm_ticker_sym(ticker: str | None) -> str:
    return (ticker or "").upper().replace(".", "-").split("-")[0].strip()


def uses_commodity_phrase_lexicon(ticker: str | None, asset_type: str | None = None) -> bool:
    """True when aggregate_keyword_sentiment uses the commodity phrase lexicon first."""
    if (asset_type or "").strip().lower() == "commodity_etf":
        return True
    sym = norm_ticker_sym(ticker)
    return bool(sym) and sym in COMMODITY_PHRASE_SCORER_TICKERS


def article_url(item: dict[str, Any]) -> str:
    """Best-effort URL from FMP / Yahoo / generic news row."""
    if not isinstance(item, dict):
        return ""
    for k in ("url", "link", "article_url", "sourceUrl", "source_url"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def filter_articles_for_scoring(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Back-compat: drop articles below default min quality (used by Alpha Vantage path).

    Prefer :func:`aggregate_keyword_sentiment` which applies quality as weights.
    """
    out: list[dict[str, Any]] = []
    for item in articles:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or item.get("headline") or "").strip()
        qw, _ = compute_quality_weight(title, article_url(item))
        if qw >= DEFAULT_MIN_QUALITY_WEIGHT:
            out.append(item)
    return out


def _phrase_bear_hits(blob: str) -> int:
    b = re.sub(r"\s+", " ", (blob or "").lower())
    return sum(1 for ph in _BEARISH_PHRASES if ph in b)


def _use_commodity_word_lexicon(ticker: str | None) -> bool:
    if not ticker:
        return False
    return norm_ticker_sym(ticker) in COMMODITY_LEXICON_TICKERS


def _normalize_words(text: str) -> set[str]:
    if not text:
        return set()
    s = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return {w for w in s.split() if len(w) >= 2}


def _lexicons_for_ticker(ticker: str | None):
    bull, bear = BULLISH_KEYWORDS, BEARISH_KEYWORDS
    if _use_commodity_word_lexicon(ticker):
        bull = frozenset(bull | COMMODITY_BULLISH_KEYWORDS)
        bear = frozenset(bear | COMMODITY_BEARISH_KEYWORDS)
    return bull, bear


def _recency_weight_publication(published_at: str | None, now: datetime | None = None) -> float:
    """Article-age decay for commodity headlines (<6h full weight, then step down)."""
    if not published_at:
        return 0.7
    try:
        from signals.time_et import now_et, parse_iso_to_et

        if now is None:
            now = now_et()
        pub = parse_iso_to_et(published_at)
        age_hours = (now - pub).total_seconds() / 3600
        if age_hours < 6:
            return 1.0
        if age_hours < 24:
            return 0.8
        if age_hours < 72:
            return 0.6
        return 0.4
    except (ValueError, TypeError, OSError):
        return 0.7


def _score_commodity_phrases(text: str, lexicon: list[tuple[str, int, float]]) -> list[float]:
    text_lower = text.lower()
    hits: list[float] = []
    for phrase, base_score, mult in lexicon:
        if phrase in text_lower:
            hits.append(float(base_score) * float(mult))
    return hits


def _commodity_headline_normalized(
    combined: str,
    lexicon: list[tuple[str, int, float]],
    published_at: str | None,
) -> tuple[float | None, int, float]:
    """Returns (normalized 0..1, hit_count, recency_weight) or (None, 0, rw)."""
    rw = _recency_weight_publication(published_at)
    hit_vals = _score_commodity_phrases(combined, lexicon)
    if not hit_vals:
        return None, 0, rw
    raw = sum(hit_vals) * rw
    clipped = max(-5.0, min(5.0, raw))
    normalized = (clipped + 5.0) / 10.0
    return float(normalized), len(hit_vals), rw


class HeadlineScore(TypedDict):
    title: str
    raw_score: float
    normalized: float
    hit_count: int
    recency_weight: float


class SentimentResult(TypedDict):
    sentiment_score_avg: float | None
    sentiment_method: str
    headline_count: int
    scored_count: int
    scores: list[HeadlineScore]


def score_headlines(
    headlines: list[dict[str, Any]],
    ticker: str,
    *,
    text_char_limit: int = _DEFAULT_COMMODITY_TEXT_LIMIT,
    min_quality_weight: float = DEFAULT_MIN_QUALITY_WEIGHT,
) -> SentimentResult:
    """
    Score headline dicts for commodity / precious-metal ETFs using phrase lexicons.

    Each item may include: title, text/body, url, publishedDate / published_at / date.
    Quality filtering and publication recency match :func:`aggregate_keyword_sentiment`.
    """
    sym = norm_ticker_sym(ticker)
    lexicon = get_commodity_phrase_lexicon(sym)
    scores: list[HeadlineScore] = []

    for h in headlines:
        if not isinstance(h, dict):
            continue
        title = h.get("title") or h.get("headline") or ""
        body = h.get("text") or h.get("body") or h.get("content") or h.get("description") or ""
        pub = h.get("publishedDate") or h.get("published_at") or h.get("date")
        combined = (str(title) + " " + str(body)[:text_char_limit]).strip()
        if not combined:
            continue
        qw, _ = compute_quality_weight(str(title), article_url(h))
        if qw < min_quality_weight:
            continue
        norm, hit_count, rw = _commodity_headline_normalized(combined, lexicon, str(pub) if pub else None)
        if norm is None:
            continue
        raw_vals = _score_commodity_phrases(combined, lexicon)
        raw_pre = float(sum(raw_vals) * rw)
        scores.append(
            HeadlineScore(
                title=str(title)[:120],
                raw_score=round(raw_pre, 4),
                normalized=round(norm, 4),
                hit_count=hit_count,
                recency_weight=round(rw, 2),
            )
        )

    if not scores:
        return SentimentResult(
            sentiment_score_avg=None,
            sentiment_method="none",
            headline_count=len(headlines),
            scored_count=0,
            scores=[],
        )

    avg = sum(s["normalized"] for s in scores) / len(scores)
    return SentimentResult(
        sentiment_score_avg=round(avg, 4),
        sentiment_method="keyword_commodity",
        headline_count=len(headlines),
        scored_count=len(scores),
        scores=scores,
    )


def _aggregate_commodity_phrase_sentiment(
    articles: list[dict[str, Any]],
    *,
    ticker: str | None,
    decay: float,
    min_quality_weight: float,
    text_char_limit: int,
) -> tuple[float | None, int, bool]:
    sym = norm_ticker_sym(ticker)
    if not sym:
        return None, len(articles), False
    lexicon = get_commodity_phrase_lexicon(sym)
    norms: list[float] = []
    wts: list[float] = []
    any_hit = False
    for orig_i, item in enumerate(articles):
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
        combined = (title + " " + body[:text_char_limit]).strip()
        if not combined:
            continue
        qw, _ = compute_quality_weight(title, article_url(item))
        if qw < min_quality_weight:
            continue
        pub = item.get("publishedDate") or item.get("published_at") or item.get("date")
        norm, _hits, rw = _commodity_headline_normalized(combined, lexicon, str(pub) if pub else None)
        if norm is None:
            continue
        any_hit = True
        norms.append(float(norm))
        wts.append(float(np.exp(-decay * orig_i)) * qw)
    if not norms or not wts:
        return None, len(articles), False
    avg_norm = float(np.average(np.array(norms), weights=np.array(wts)))
    raw_out = 2.0 * avg_norm - 1.0
    return float(np.clip(raw_out, -1.0, 1.0)), len(articles), True


def score_headline_text(title: str, text: str = "", *, ticker: str | None = None) -> tuple[float, bool]:
    """
    Return (raw -1..1, hit) for one article. hit=False if no lexicon overlap.
    Commodity ETFs (GLD, SLV, …) merge a macro/precious-metals word lexicon with the base set.
    """
    combined = f"{title} {text or ''}"
    words = _normalize_words(combined)
    lb, dk = _lexicons_for_ticker(ticker)
    bull = len(words & lb)
    bear = len(words & dk)
    bear += _phrase_bear_hits(combined) * 2
    if bull + bear == 0:
        return 0.0, False
    raw = (bull - bear) / float(bull + bear)
    return float(np.clip(raw, -1.0, 1.0)), True


def _aggregate_word_based_keyword_sentiment(
    articles: list[dict[str, Any]],
    *,
    decay: float,
    ticker: str | None,
    min_quality_weight: float,
) -> tuple[float | None, int, bool]:
    scores: list[float] = []
    weights: list[float] = []
    any_hit = False
    for orig_i, item in enumerate(articles):
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
        qw, _ = compute_quality_weight(title, article_url(item))
        if qw < min_quality_weight:
            continue
        raw, hit = score_headline_text(title, body, ticker=ticker)
        if hit:
            any_hit = True
            scores.append(raw)
            weights.append(float(np.exp(-decay * orig_i)) * qw)
    if not scores or not weights:
        return None, len(articles), False
    avg = float(np.average(np.array(scores), weights=np.array(weights)))
    return float(np.clip(avg, -1.0, 1.0)), len(articles), True


def aggregate_keyword_sentiment(
    articles: list[dict[str, Any]],
    *,
    decay: float = 0.08,
    ticker: str | None = None,
    min_quality_weight: float = DEFAULT_MIN_QUALITY_WEIGHT,
    asset_type: str | None = None,
    text_char_limit: int = _DEFAULT_COMMODITY_TEXT_LIMIT,
) -> tuple[float | None, int, bool, str]:
    """
    Weight recent articles higher (index 0 = newest from FMP).
    Commodity ETFs use phrase lexicons first; if no phrase hits, falls back to word lexicon.

    Returns:
        (raw_avg in [-1,1] or None, headline_count, any_hit, method)
        method is ``keyword_commodity`` or ``keyword``.
    """
    if not articles:
        return None, 0, False, "keyword"

    if uses_commodity_phrase_lexicon(ticker, asset_type):
        r = _aggregate_commodity_phrase_sentiment(
            articles,
            ticker=ticker,
            decay=decay,
            min_quality_weight=min_quality_weight,
            text_char_limit=text_char_limit,
        )
        if r[0] is not None and r[2]:
            return (*r, "keyword_commodity")

    w = _aggregate_word_based_keyword_sentiment(
        articles,
        decay=decay,
        ticker=ticker,
        min_quality_weight=min_quality_weight,
    )
    return (*w, "keyword")
