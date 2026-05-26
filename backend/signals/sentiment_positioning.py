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


CNN_FNG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CACHE_KEY = "sentiment:fear_greed"
SPY_PC_CACHE_KEY = "sentiment:spy_put_call"
TTL_SECONDS = 6 * 3600
SPY_PC_TTL_SECONDS = 3600


def _put_call_from_config(config: dict | None) -> dict[str, Any] | None:
    cfg = ((config or {}).get("retail") or {}).get("sentiment") or {}
    raw = cfg.get("put_call_ratio")
    if raw is None:
        return None
    try:
        ratio = round(float(raw), 3)
    except (TypeError, ValueError):
        return None
    read = _positioning_read(ratio)
    return {
        "ratio": ratio,
        "pc_oi_ratio": None,
        "source": "config override (update from CBOE or broker aggregate)",
        **read,
    }


def _positioning_read(ratio: float) -> dict[str, str]:
    """Retail plain-English for equity put/call ratio (volume-based)."""
    if ratio >= 1.2:
        return {
            "signal": "ELEVATED_FEAR",
            "plain_english": (
                f"Put/Call {ratio:.2f} — elevated hedging; often contrarian buy zone if bull regime intact."
            ),
        }
    if ratio >= 0.8:
        return {
            "signal": "MODERATE_HEDGE",
            "plain_english": (
                f"Put/Call {ratio:.2f} — moderate hedging, not extreme fear."
            ),
        }
    if ratio >= 0.65:
        return {
            "signal": "NEUTRAL",
            "plain_english": (
                f"Put/Call {ratio:.2f} — near balanced; positioning not a major tailwind or headwind."
            ),
        }
    return {
        "signal": "COMPLACENCY",
        "plain_english": (
            f"Put/Call {ratio:.2f} — call-heavy; crowd less hedged — trim extended winners if greedy."
        ),
    }


def _fetch_spy_put_call_yfinance() -> dict[str, Any] | None:
    """Nearest-expiry SPY option volume P/C — free proxy for market positioning."""
    try:
        from signals.options_signals import fetch_options_signals

        opts = fetch_options_signals("SPY")
        if opts.get("error"):
            logger.debug("SPY put/call: %s", opts.get("error"))
            return None
        ratio = opts.get("pc_ratio")
        if ratio is None:
            return None
        ratio_f = round(float(ratio), 3)
        read = _positioning_read(ratio_f)
        out: dict[str, Any] = {
            "ratio": ratio_f,
            "pc_oi_ratio": opts.get("pc_oi_ratio"),
            "source": "SPY options (yfinance, nearest expiry)",
            **read,
        }
        if opts.get("options_label"):
            out["options_label"] = opts["options_label"]
        return out
    except Exception as e:
        logger.debug("SPY put/call fetch failed: %s", e)
        return None


def _spy_put_call_positioning(config: dict | None) -> dict[str, Any] | None:
    manual = _put_call_from_config(config)
    if manual:
        return manual
    from signals.cache import get_cached, set_cached

    cached = get_cached(SPY_PC_CACHE_KEY)
    if isinstance(cached, dict) and cached.get("ratio") is not None:
        return cached
    live = _fetch_spy_put_call_yfinance()
    if live:
        set_cached(SPY_PC_CACHE_KEY, live, SPY_PC_TTL_SECONDS)
    return live


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
    """Fear & Greed index, SPY put/call positioning, optional AAII config overrides."""
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
    spy_put_call = _spy_put_call_positioning(config)

    positioning_parts: list[str] = []
    if spy_put_call and spy_put_call.get("plain_english"):
        positioning_parts.append(spy_put_call["plain_english"])
    if contrarian.get("plain_english"):
        positioning_parts.append(contrarian["plain_english"])

    return {
        "fear_greed": fng,
        "aaii": aaii,
        "spy_put_call": spy_put_call,
        "contrarian": contrarian,
        "plain_english": " ".join(positioning_parts) if positioning_parts else contrarian.get("plain_english"),
    }
