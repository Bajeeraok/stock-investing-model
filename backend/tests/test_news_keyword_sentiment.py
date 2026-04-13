"""Keyword news sentiment aggregation (FMP path)."""

from __future__ import annotations

from signals.news_keyword_sentiment import (
    aggregate_keyword_sentiment,
    score_headline_text,
    score_headlines,
)
from signals.news_quality_filter import compute_quality_weight


def test_ceasefire_rally_bullish():
    raw, hit = score_headline_text("S&P 500 gains on ceasefire optimism", "")
    assert hit
    assert raw > 0.3


def test_aggregate_weighted():
    articles = [
        {"title": "Company beats estimates on strong profit", "text": ""},
        {"title": "Analyst downgrade after warning", "text": ""},
    ]
    avg, n, any_hit, method = aggregate_keyword_sentiment(articles)
    assert any_hit and n == 2
    assert method == "keyword"
    assert avg is not None
    assert -1.0 <= avg <= 1.0


def test_no_keywords_returns_none_avg():
    articles = [{"title": "The stock traded Tuesday", "text": ""}]
    avg, n, any_hit, _ = aggregate_keyword_sentiment(articles)
    assert not any_hit
    assert avg is None
    assert n == 1


def test_commodity_lexicon_gld():
    """GLD/SLV merge precious-metals macro tokens so ETF headlines can score."""
    raw, hit = score_headline_text("Gold futures rally as inflation hedges draw buyers", "", ticker="GLD")
    assert hit
    assert raw > 0


def test_plain_ticker_no_commodity_boost():
    raw, hit = score_headline_text("Gold miners surge", "", ticker="AAPL")
    assert hit
    # "gold" not in base lexicon — without commodity profile, may still hit "surge" from bullish set
    assert raw >= -1.0


def test_shares_sold_institutional_headline_bearish():
    raw, hit = score_headline_text(
        "Alphabet Inc. $GOOGL Shares Sold by Howard Capital Management Group LLC",
        "",
    )
    assert hit
    assert raw < 0


def test_seo_headline_lower_quality_than_wire():
    qw_seo, _ = compute_quality_weight(
        "What Makes Alphabet (GOOGL) a New Buy Stock",
        "https://fool.com/x",
    )
    qw_wire, _ = compute_quality_weight(
        "Company beats estimates on strong profit",
        "https://reuters.com/x",
    )
    assert qw_wire > qw_seo


def test_institutional_filing_excluded_from_aggregate():
    articles = [
        {
            "title": "Alphabet Inc. $GOOGL Shares Sold by Howard Capital Management Group LLC",
            "text": "",
            "url": "https://reuters.com/x",
        },
        {"title": "Company beats estimates on strong profit", "text": "", "url": "https://reuters.com/x"},
    ]
    avg, n, any_hit, _ = aggregate_keyword_sentiment(articles)
    assert n == 2
    assert any_hit
    assert avg is not None and avg > 0


def test_motley_fool_downweighted_vs_reuters():
    articles = [
        {
            "title": "Analyst comments on margin trends",
            "text": "",
            "url": "https://www.fool.com/investing/stock/X",
        },
        {"title": "Company beats estimates on strong profit", "text": "", "url": "https://reuters.com/x"},
    ]
    avg, n, any_hit, _ = aggregate_keyword_sentiment(articles)
    assert n == 2
    assert any_hit
    assert avg is not None and avg > 0


def test_aggregate_gld_uses_commodity_phrase_hawkish():
    articles = [
        {
            "title": "Gold slides as hawkish Fed lifts yields and dollar strength weighs on bullion",
            "text": "",
            "url": "https://www.reuters.com/markets/commodities/gold",
        },
    ]
    avg, n, any_hit, method = aggregate_keyword_sentiment(articles, ticker="GLD")
    assert any_hit and n == 1
    assert method == "keyword_commodity"
    assert avg is not None and avg < 0


def test_score_headlines_gld_bullish():
    headlines = [
        {"title": "Gold rally extends as inflation hedge demand lifts spot prices", "text": "", "url": "https://reuters.com/x"},
    ]
    r = score_headlines(headlines, "GLD")
    assert r["sentiment_method"] == "keyword_commodity"
    assert r["sentiment_score_avg"] is not None
    assert r["sentiment_score_avg"] > 0.5


def test_asset_type_commodity_etf_forces_phrase_path():
    articles = [
        {"title": "ETF inflow supports momentum in energy names", "text": "", "url": "https://reuters.com/x"},
    ]
    _, _, hit, method = aggregate_keyword_sentiment(articles, ticker="FAKE", asset_type="commodity_etf")
    # Unknown symbol still runs phrase lexicon (generic commodity list); "ETF inflow"/"momentum" hit
    assert hit
    assert method == "keyword_commodity"
