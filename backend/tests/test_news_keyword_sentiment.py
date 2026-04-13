"""Keyword news sentiment aggregation (FMP path)."""

from __future__ import annotations

from signals.news_keyword_sentiment import aggregate_keyword_sentiment, score_headline_text


def test_ceasefire_rally_bullish():
    raw, hit = score_headline_text("S&P 500 gains on ceasefire optimism", "")
    assert hit
    assert raw > 0.3


def test_aggregate_weighted():
    articles = [
        {"title": "Company beats estimates on strong profit", "text": ""},
        {"title": "Analyst downgrade after warning", "text": ""},
    ]
    avg, n, any_hit = aggregate_keyword_sentiment(articles)
    assert any_hit and n == 2
    assert avg is not None
    assert -1.0 <= avg <= 1.0


def test_no_keywords_returns_none_avg():
    articles = [{"title": "The stock traded Tuesday", "text": ""}]
    avg, n, any_hit = aggregate_keyword_sentiment(articles)
    assert not any_hit
    assert avg is None
    assert n == 1
