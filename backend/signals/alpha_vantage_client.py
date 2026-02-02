"""
Alpha Vantage News Sentiment client.
Uses NEWS_SENTIMENT API (free tier: 5 req/min, 500/day).
Config: data.alpha_vantage_api_key in config.yaml.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger("signals.alpha_vantage_client")

AV_BASE = "https://www.alphavantage.co/query"


def get_api_key(config: dict) -> str | None:
    return (config.get("data") or {}).get("alpha_vantage_api_key") or config.get("alpha_vantage_api_key") or None


def fetch_news_sentiment(config: dict, ticker: str, limit: int = 10) -> tuple[dict | None, str | None]:
    """
    Fetch news sentiment for a ticker. Returns (summary, error).
    summary: { sentiment_score_avg, sentiment_label, headline_count, headlines: [{ title, score, label }] }
    """
    api_key = get_api_key(config)
    if not api_key or not api_key.strip():
        return None, "No Alpha Vantage API key (add data.alpha_vantage_api_key to config.yaml)"
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker.upper().split("-")[0],  # e.g. BTC-USD -> BTC
        "limit": min(limit, 50),
        "apikey": api_key.strip(),
    }
    url = f"{AV_BASE}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        logger.debug("Alpha Vantage NEWS_SENTIMENT failed: %s", e)
        return None, str(e)
    if isinstance(data, dict) and data.get("Information"):
        return None, data.get("Information", "API message")
    if isinstance(data, dict) and data.get("Error Message"):
        return None, data.get("Error Message", "API error")
    feed = data.get("feed") if isinstance(data, dict) else None
    if not isinstance(feed, list):
        return None, "Unexpected response (no feed)"
    headlines = []
    scores = []
    label_counts = {}
    for item in feed[:limit]:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "")[:120]
        overall = item.get("overall_sentiment_score")
        label = (item.get("overall_sentiment_label") or "Neutral").strip()
        ticker_sent = item.get("ticker_sentiment")
        if isinstance(ticker_sent, list) and ticker_sent:
            ts = ticker_sent[0]
            if isinstance(ts, dict):
                score = ts.get("ticker_sentiment_score")
                if score is not None:
                    try:
                        scores.append(float(score))
                    except (TypeError, ValueError):
                        pass
        if overall is not None:
            try:
                scores.append(float(overall))
            except (TypeError, ValueError):
                pass
        label_counts[label] = label_counts.get(label, 0) + 1
        headlines.append({"title": title, "score": overall, "label": label})
    sentiment_score_avg = round(sum(scores) / len(scores), 3) if scores else None
    sentiment_label = max(label_counts, key=label_counts.get) if label_counts else "Neutral"
    return {
        "ticker": ticker,
        "sentiment_score_avg": sentiment_score_avg,
        "sentiment_label": sentiment_label,
        "headline_count": len(headlines),
        "headlines": headlines[:5],
    }, None


def get_alpha_vantage_sentiment(config: dict, ticker: str) -> tuple[dict | None, str | None]:
    """
    Alias for fetch_news_sentiment; matches data_source_stubs signature.
    """
    return fetch_news_sentiment(config, ticker, limit=10)
