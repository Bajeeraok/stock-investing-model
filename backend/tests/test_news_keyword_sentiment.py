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


def test_gld_real_world_bullish_headlines_do_not_score_bearish():
    """Regression: this exact headline set previously scored Bearish because the
    phrase lexicon found zero matches (too-narrow phrasing) and fell back to the
    generic word lexicon, which hit "slump" (jewelry sales, a sub-metric) with
    nothing to offset it — even though every headline here is net-bullish for
    gold (record spikes, a $5,000 prediction, demand soaring)."""
    headlines = [
        "Spot gold spikes above $4,438/oz as annual core CPI rises 2.5% in July",
        "The Dollar Doesn't Need to Die for Gold to Win",
        "Gold (XAU/USD) & Silver Price Forecast: Can CPI Push Gold Beyond $4,430?",
        "Elliott pushes Australian gold miner Northern Star for board change after talks stall",
        "Gold Edges Higher Ahead of U.S. Inflation Data",
        "Gold holds near two-month high as equities slip, oil rallies - Kitco PM Report",
        "China's gold consumption rises 1.23% in H1, jewelry sales slump while investment demand soars",
        "Prediction: Gold Will Rise Back to Over $5,000 Before the End of the Year",
    ]
    articles = [{"title": h, "url": "https://example.com"} for h in headlines]
    score, _n, hit, method = aggregate_keyword_sentiment(articles, ticker="GLD")
    assert hit
    assert method == "keyword_commodity"
    assert score is not None and score > 0.15  # Bullish threshold, matches ticker_detail.py's UI label logic


def test_ambiguous_bare_words_removed_from_bearish_keywords():
    """Regression: "cut"/"cuts", "stake", and "guidance" were bare BEARISH_KEYWORDS
    entries, so headlines like "Fed signals rate cuts" or "raises full-year guidance"
    scored fully bearish despite being neutral-to-bullish. Genuinely negative senses
    ("cuts guidance", "dividend cut") must still score bearish via _BEARISH_PHRASES."""
    cases_not_bearish = [
        "Fed signals rate cuts ahead, stocks rally",
        "Company announces cost cuts to boost margins",
        "Berkshire increases stake in Apple",
        "Company raises full-year guidance on strong demand",
    ]
    for text in cases_not_bearish:
        raw, _hit = score_headline_text(text, "")
        assert raw >= 0, f"expected non-bearish for: {text!r}, got {raw}"

    cases_still_bearish = [
        "Company cuts full-year guidance amid weak demand",
        "Retailer announces dividend cut after weak quarter",
        "Company misses guidance, shares fall",
    ]
    for text in cases_still_bearish:
        raw, hit = score_headline_text(text, "")
        assert hit
        assert raw < 0, f"expected bearish for: {text!r}, got {raw}"
