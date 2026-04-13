"""Tests for news_quality_filter and news_weight_cap."""

from __future__ import annotations

from signals.news_quality_filter import (
    DEFAULT_DOMAIN_WEIGHT,
    compute_quality_weight,
    filter_headlines,
    get_domain_weight,
    get_headline_pattern_weight,
)
from signals.news_weight_cap import (
    NEWS_WEIGHT_FLOOR,
    NEWS_WEIGHT_STANDARD,
    REGIME_CERTAINTY_THRESHOLD,
    REGIME_WEIGHT_STANDARD,
    apply_weight_cap_to_layer_config,
    compute_news_weight,
)


class TestDomainWeights:

    def test_tier_a_reuters(self):
        assert get_domain_weight("reuters.com") == 1.0

    def test_tier_a_bloomberg(self):
        assert get_domain_weight("bloomberg.com") == 1.0

    def test_tier_a_wsj(self):
        assert get_domain_weight("wsj.com") == 1.0

    def test_tier_b_zacks(self):
        assert get_domain_weight("zacks.com") == 0.75

    def test_motley_fool_downweighted(self):
        assert get_domain_weight("fool.com") <= 0.4

    def test_seeking_alpha_mid_tier(self):
        w = get_domain_weight("seekingalpha.com")
        assert 0.4 <= w <= 0.6

    def test_pr_wire_blocked(self):
        assert get_domain_weight("prnewswire.com") == 0.0

    def test_businesswire_blocked(self):
        assert get_domain_weight("businesswire.com") == 0.0

    def test_globenewswire_blocked(self):
        assert get_domain_weight("globenewswire.com") == 0.0

    def test_www_prefix_stripped(self):
        assert get_domain_weight("www.reuters.com") == get_domain_weight("reuters.com")

    def test_full_url_parsed(self):
        assert get_domain_weight("https://www.bloomberg.com/news/article/123") == 1.0

    def test_unknown_domain_default(self):
        w = get_domain_weight("somerandomblog.net")
        assert w == DEFAULT_DOMAIN_WEIGHT

    def test_none_source_default(self):
        assert get_domain_weight(None) == DEFAULT_DOMAIN_WEIGHT


class TestHeadlinePatterns:

    def test_institutional_filing_zero_weight(self):
        w, reason = get_headline_pattern_weight(
            "Alphabet Inc. $GOOGL Shares Sold by Howard Capital Management Group LLC"
        )
        assert w == 0.0
        assert "filing" in reason.lower()

    def test_13f_disclosure_zero_weight(self):
        w, _ = get_headline_pattern_weight(
            "October Effect Ltd Has $1.99 Million Stock Holdings in Alphabet Inc. $GOOGL"
        )
        assert w == 0.0

    def test_question_lead_seo_downweighted(self):
        w, _ = get_headline_pattern_weight(
            "Is Alphabet (GOOGL) a Buy as Wall Street Analysts Look Optimistic?"
        )
        assert w <= 0.4

    def test_what_makes_seo_downweighted(self):
        w, _ = get_headline_pattern_weight(
            "What Makes Alphabet (GOOGL) a New Buy Stock"
        )
        assert w <= 0.4

    def test_got_money_clickbait_downweighted(self):
        w, _ = get_headline_pattern_weight(
            "Got $1,000? Apple vs Alphabet — Only One Deserves Your Money Right Now"
        )
        assert w <= 0.15

    def test_multi_ticker_roundup_downweighted(self):
        w, _ = get_headline_pattern_weight(
            "Trade Strategy For SPY, QQQ, AAPL, MSFT, NVDA, GOOGL, META, And TSLA"
        )
        assert w <= 0.3

    def test_analyst_rating_change_kept(self):
        w, reason = get_headline_pattern_weight(
            "Goldman Sachs upgraded GOOGL to Buy with $420 price target"
        )
        assert w >= 0.7
        assert "analyst" in reason.lower() or "rating" in reason.lower()

    def test_earnings_beat_boosted(self):
        w, reason = get_headline_pattern_weight(
            "Alphabet earnings beat expectations, revenue surpasses $90B"
        )
        assert w > 1.0
        assert "earnings" in reason.lower()

    def test_guidance_raised_boosted(self):
        w, reason = get_headline_pattern_weight(
            "Alphabet raises guidance for Q3 above consensus estimates"
        )
        assert w > 1.0

    def test_antitrust_news_boosted(self):
        w, reason = get_headline_pattern_weight(
            "DOJ antitrust ruling against Alphabet could reshape Google search"
        )
        assert w >= 1.0
        assert "regulatory" in reason.lower()

    def test_ma_deal_boosted(self):
        w, _ = get_headline_pattern_weight(
            "Alphabet acquires AI startup in deal worth $2.5 billion"
        )
        assert w > 1.0

    def test_neutral_headline_unchanged(self):
        w, reason = get_headline_pattern_weight(
            "Alphabet reports Q2 results on July 30"
        )
        assert w == 1.0
        assert reason == ""


class TestComputeQualityWeight:

    def test_pr_wire_zero_regardless_of_title(self):
        qw, _ = compute_quality_weight(
            "Alphabet Announces Q2 Results",
            "prnewswire.com",
        )
        assert qw == 0.0

    def test_reuters_earnings_beat_high_weight(self):
        qw, _ = compute_quality_weight(
            "Alphabet earnings beat Wall Street estimates by wide margin",
            "reuters.com",
        )
        assert qw >= 1.0

    def test_fool_seo_headline_very_low(self):
        qw, _ = compute_quality_weight(
            "Is Alphabet a Buy Right Now?",
            "fool.com",
        )
        assert qw <= 0.2

    def test_unknown_domain_seo_headline_low(self):
        qw, _ = compute_quality_weight(
            "Top 10 Stocks to Buy This Week",
            "somesite.com",
        )
        assert qw <= 0.35

    def test_unknown_domain_neutral_headline_default(self):
        qw, _ = compute_quality_weight(
            "Alphabet Q2 ad revenue in focus ahead of earnings",
            None,
        )
        assert qw == DEFAULT_DOMAIN_WEIGHT


class TestFilterHeadlines:

    HEADLINES = [
        {"title": "Alphabet earnings beat expectations by 8%",
         "url": "reuters.com"},
        {"title": "Is Alphabet a Buy? Wall Street Analysts Look Optimistic",
         "url": "fool.com"},
        {"title": "Alphabet Inc. $GOOGL Shares Sold by Howard Capital",
         "url": "insidearbitrage.com"},
        {"title": "Alphabet raises full-year guidance above consensus",
         "url": "wsj.com"},
        {"title": "Got $1,000? Apple vs Alphabet — Only One Deserves Your Money",
         "url": "247wallst.com"},
    ]

    def test_returns_list(self):
        result = filter_headlines(self.HEADLINES)
        assert isinstance(result, list)

    def test_quality_weight_field_added(self):
        result = filter_headlines(self.HEADLINES)
        for h in result:
            assert "quality_weight" in h
            assert "quality_reason" in h

    def test_zero_quality_excluded(self):
        result = filter_headlines(self.HEADLINES, min_quality=0.15)
        titles = [h["title"] for h in result]
        assert not any("Shares Sold by" in t for t in titles)

    def test_high_quality_headlines_kept(self):
        result = filter_headlines(self.HEADLINES, min_quality=0.15)
        titles = [h["title"] for h in result]
        assert any("earnings beat" in t for t in titles)
        assert any("raises full-year guidance" in t for t in titles)

    def test_min_quality_zero_keeps_all(self):
        result = filter_headlines(self.HEADLINES, min_quality=0.0)
        assert len(result) == len(self.HEADLINES)

    def test_original_fields_preserved(self):
        result = filter_headlines(self.HEADLINES)
        for h in result:
            assert "title" in h
            assert "url" in h


class TestComputeNewsWeight:

    def test_below_threshold_no_change(self):
        news_w, regime_w, reason = compute_news_weight(
            hmm_bull_probability=0.18,
            hmm_bear_probability=0.82,
        )
        assert news_w == NEWS_WEIGHT_STANDARD
        assert regime_w == REGIME_WEIGHT_STANDARD
        assert "not certain" in reason

    def test_bear_100_tapers_to_floor(self):
        news_w, regime_w, reason = compute_news_weight(
            hmm_bull_probability=0.0,
            hmm_bear_probability=1.0,
        )
        assert news_w == NEWS_WEIGHT_FLOOR
        assert regime_w == round(REGIME_WEIGHT_STANDARD + (NEWS_WEIGHT_STANDARD - NEWS_WEIGHT_FLOOR), 4)
        assert "100%" in reason
        assert "bear" in reason

    def test_bull_100_tapers_to_floor(self):
        news_w, _, reason = compute_news_weight(
            hmm_bull_probability=1.0,
            hmm_bear_probability=0.0,
        )
        assert news_w == NEWS_WEIGHT_FLOOR
        assert "bull" in reason

    def test_at_threshold_no_change(self):
        news_w, _, _ = compute_news_weight(
            hmm_bull_probability=0.10,
            hmm_bear_probability=REGIME_CERTAINTY_THRESHOLD,
        )
        assert abs(news_w - NEWS_WEIGHT_STANDARD) < 0.001

    def test_weight_sum_preserved(self):
        original_sum = NEWS_WEIGHT_STANDARD + REGIME_WEIGHT_STANDARD
        for bear_prob in [0.90, 0.95, 1.0]:
            news_w, regime_w, _ = compute_news_weight(
                hmm_bull_probability=1 - bear_prob,
                hmm_bear_probability=bear_prob,
            )
            assert abs((news_w + regime_w) - original_sum) < 0.001

    def test_no_regime_data_no_change(self):
        news_w, regime_w, reason = compute_news_weight(
            hmm_bull_probability=None,
            hmm_bear_probability=None,
        )
        assert news_w == NEWS_WEIGHT_STANDARD
        assert regime_w == REGIME_WEIGHT_STANDARD
        assert "no regime" in reason

    def test_only_bear_provided(self):
        news_w, _, _ = compute_news_weight(
            hmm_bull_probability=None,
            hmm_bear_probability=1.0,
        )
        assert news_w == NEWS_WEIGHT_FLOOR

    def test_news_weight_never_below_floor(self):
        for bear in [0.9, 0.95, 0.99, 1.0]:
            news_w, _, _ = compute_news_weight(
                hmm_bull_probability=1 - bear,
                hmm_bear_probability=bear,
            )
            assert news_w >= NEWS_WEIGHT_FLOOR


class TestApplyWeightCap:

    BASE_WEIGHTS = {
        "hmm_regime":       0.15,
        "pattern_score":    0.15,
        "lgbm_probability": 0.20,
        "options_sentiment": 0.15,
        "insider_activity": 0.15,
        "fundamentals":     0.10,
        "news_sentiment":   0.10,
    }

    def test_bear_100_reduces_news_increases_regime(self):
        adjusted, reason = apply_weight_cap_to_layer_config(
            self.BASE_WEIGHTS,
            hmm_bull_probability=0.0,
            hmm_bear_probability=1.0,
        )
        assert adjusted["news_sentiment"] == NEWS_WEIGHT_FLOOR
        assert adjusted["hmm_regime"] > self.BASE_WEIGHTS["hmm_regime"]
        assert "100%" in reason

    def test_total_weight_unchanged(self):
        original_total = sum(self.BASE_WEIGHTS.values())
        adjusted, _ = apply_weight_cap_to_layer_config(
            self.BASE_WEIGHTS,
            hmm_bull_probability=0.0,
            hmm_bear_probability=1.0,
        )
        assert abs(sum(adjusted.values()) - original_total) < 0.001

    def test_other_layers_untouched(self):
        adjusted, _ = apply_weight_cap_to_layer_config(
            self.BASE_WEIGHTS,
            hmm_bull_probability=0.0,
            hmm_bear_probability=1.0,
        )
        for key in ["pattern_score", "lgbm_probability", "options_sentiment",
                    "insider_activity", "fundamentals"]:
            assert adjusted[key] == self.BASE_WEIGHTS[key]

    def test_missing_key_returns_unchanged(self):
        bad_weights = {"some_layer": 0.5, "other_layer": 0.5}
        adjusted, reason = apply_weight_cap_to_layer_config(
            bad_weights,
            hmm_bull_probability=0.0,
            hmm_bear_probability=1.0,
        )
        assert adjusted == bad_weights
        assert "not found" in reason

    def test_googl_morning_bear_82_no_change(self):
        adjusted, reason = apply_weight_cap_to_layer_config(
            self.BASE_WEIGHTS,
            hmm_bull_probability=0.18,
            hmm_bear_probability=0.82,
        )
        assert adjusted["news_sentiment"] == self.BASE_WEIGHTS["news_sentiment"]
        assert "not certain" in reason

    def test_googl_afternoon_bear_100_triggers_cap(self):
        adjusted, _ = apply_weight_cap_to_layer_config(
            self.BASE_WEIGHTS,
            hmm_bull_probability=0.0,
            hmm_bear_probability=1.0,
        )
        assert adjusted["news_sentiment"] < self.BASE_WEIGHTS["news_sentiment"]
        assert adjusted["hmm_regime"] > self.BASE_WEIGHTS["hmm_regime"]
