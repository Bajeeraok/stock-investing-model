"""Pre-IPO watch panel + FMP news filter."""
from __future__ import annotations

from signals.pre_ipo import (
    article_matches_keywords,
    build_pre_ipo_news_block,
    build_pre_ipo_panel,
    dedupe_articles,
    detect_pre_ipo_themes,
    news_keywords_for_company,
    pre_ipo_config,
)


def test_default_companies():
    cfg = pre_ipo_config({})
    assert cfg["enabled"] is True
    assert cfg.get("fetch_news") is True
    assert len(cfg["companies"]) >= 3


def test_build_with_proxy_signals():
    panel = build_pre_ipo_panel(
        {"pre_ipo_watchlist": {"fetch_news": False}},
        results_by_ticker={
            "MSFT": {"ticker": "MSFT", "composite_buy": 72, "regime": "UP", "signal": "HOLD"},
            "NVDA": {"ticker": "NVDA", "composite_buy": 65, "regime": "NEUTRAL", "signal": "HOLD"},
        },
    )
    assert panel["enabled"] is True
    openai = next(i for i in panel["items"] if i["id"] == "openai")
    tickers = {p["ticker"] for p in openai.get("proxy_signals") or []}
    assert "MSFT" in tickers
    assert "NVDA" in tickers


def test_disabled():
    panel = build_pre_ipo_panel({"pre_ipo_watchlist": {"enabled": False}})
    assert panel["enabled"] is False
    assert panel["items"] == []


def test_keyword_filter():
    articles = [
        {"title": "OpenAI raises new funding round", "publishedDate": "2025-05-01"},
        {"title": "Unrelated market wrap", "publishedDate": "2025-05-02"},
    ]
    kws = news_keywords_for_company({"name": "OpenAI", "news_keywords": ["ChatGPT"]})
    hits = [a for a in articles if article_matches_keywords(a, kws)]
    assert len(hits) == 1
    assert "OpenAI" in hits[0]["title"]


def test_news_block_themes_and_sentiment():
    articles = dedupe_articles(
        [
            {
                "title": "Anthropic closes Series E at $61B valuation",
                "text": "Funding round led by investors",
                "publishedDate": "2025-03-15 10:00:00",
                "url": "https://example.com/a",
            },
            {
                "title": "Anthropic partnership with enterprise cloud",
                "publishedDate": "2025-03-14 09:00:00",
            },
        ]
    )
    themes = detect_pre_ipo_themes(articles)
    assert "Funding" in themes
    block = build_pre_ipo_news_block(articles, company_id="anthropic", keywords=["Anthropic"])
    assert block["available"] is True
    assert block["latest"]["title"].startswith("Anthropic")
    assert block["headline_count"] >= 2


def test_fetch_news_off():
    panel = build_pre_ipo_panel({"pre_ipo_watchlist": {"fetch_news": False, "companies": [{"name": "X", "id": "x"}]}})
    assert panel["items"][0].get("news") is None
