"""
Crowd positioning — CNN Fear & Greed (+ optional AAII overrides from config).

Weekly/daily cache; no paid AAII subscription required for Fear & Greed.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

CNN_FNG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CACHE_KEY = "sentiment:fear_greed"
TTL_SECONDS = 6 * 3600


def _fetch_cnn_fear_greed() -> dict[str, Any] | None:
    try:
        import urllib.request

        req = urllib.request.Request(
            CNN_FNG_URL,
            headers={"User-Agent": "ThriveAlpha/1.0 (retail decision support)"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        logger.debug("CNN Fear & Greed fetch failed: %s", e)
        return None

    fg = data.get("fear_and_greed") or {}
    score = fg.get("score")
    rating = fg.get("rating") or fg.get("rating_description")
    if score is None:
        hist = data.get("fear_and_greed_historical") or {}
        pts = hist.get("data") or []
        if pts:
            last = pts[-1]
            score = last.get("y") or last.get("score")
            rating = rating or last.get("rating")
    if score is None:
        return None
    try:
        score_f = round(float(score), 1)
    except (TypeError, ValueError):
        return None
    return {
        "score": score_f,
        "rating": str(rating or _score_to_rating(score_f)),
        "source": "CNN Fear & Greed",
    }


def _score_to_rating(score: float) -> str:
    if score <= 25:
        return "Extreme Fear"
    if score <= 45:
        return "Fear"
    if score <= 55:
        return "Neutral"
    if score <= 75:
        return "Greed"
    return "Extreme Greed"


def _contrarian_read(score: float | None, rating: str | None) -> dict[str, str]:
    if score is None:
        return {"signal": "UNKNOWN", "plain_english": "Sentiment data unavailable."}
    r = (rating or "").lower()
    if score <= 25 or "extreme fear" in r:
        return {
            "signal": "CONTRARIAN_BUY",
            "plain_english": (
                "Extreme fear — historically a better zone to add quality names slowly, "
                "not panic sell. Size small until tape stabilizes."
            ),
        }
    if score <= 40 or r == "fear":
        return {
            "signal": "CAUTIOUS_BUY",
            "plain_english": "Fear elevated — patient buyers get better entries; avoid chasing green days.",
        }
    if score >= 75 or "extreme greed" in r:
        return {
            "signal": "CAUTION",
            "plain_english": (
                "Extreme greed — crowd complacent; trim extended winners and tighten stops on new trades."
            ),
        }
    if score >= 60 or r == "greed":
        return {
            "signal": "NEUTRAL_CAUTION",
            "plain_english": "Greed rising — hold core but don't add aggressively at highs.",
        }
    return {
        "signal": "NEUTRAL",
        "plain_english": "Sentiment mid-range — stock picking matters more than crowd mood.",
    }


def _aaii_from_config(config: dict | None) -> dict[str, Any] | None:
    cfg = ((config or {}).get("retail") or {}).get("sentiment") or {}
    bull = cfg.get("aaii_bull_pct")
    bear = cfg.get("aaii_bear_pct")
    if bull is None and bear is None:
        return None
    try:
        bull_f = float(bull) if bull is not None else None
        bear_f = float(bear) if bear is not None else None
    except (TypeError, ValueError):
        return None
    note = None
    if bull_f is not None and bull_f >= 45:
        note = "AAII bulls elevated — contrarian caution on new aggressive adds."
    elif bear_f is not None and bear_f >= 45:
        note = "AAII bears elevated — washout fear; aligns with contrarian buy zone if fundamentals intact."
    return {
        "bull_pct": bull_f,
        "bear_pct": bear_f,
        "source": "config override (update weekly from aaii.com)",
        "note": note,
    }


def get_crowd_positioning(config: dict | None = None) -> dict[str, Any]:
    """Fear & Greed index + optional AAII config overrides."""
    from signals.cache import get_cached, set_cached

    cached = get_cached(CACHE_KEY)
    fng = cached if isinstance(cached, dict) and cached.get("score") is not None else None
    if fng is None:
        fng = _fetch_cnn_fear_greed()
        if fng:
            set_cached(CACHE_KEY, fng, TTL_SECONDS)

    score = fng.get("score") if fng else None
    rating = fng.get("rating") if fng else None
    contrarian = _contrarian_read(score, rating)
    aaii = _aaii_from_config(config)

    return {
        "fear_greed": fng,
        "aaii": aaii,
        "contrarian": contrarian,
        "plain_english": contrarian.get("plain_english"),
    }
