"""Tests for signals.catalyst_detector module."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from signals.catalyst_detector import (
    CatalystPayload,
    detect_catalysts,
    _classify_headline,
)


from signals.time_et import now_et


def _make_article(title: str, hours_ago: float = 2.0, url: str = "https://reuters.com/x") -> dict:
    pub = now_et() - timedelta(hours=hours_ago)
    return {
        "title": title,
        "publishedDate": pub.isoformat(),
        "url": url,
    }


class TestClassifyHeadline:
    def test_ma_deal(self):
        hits = _classify_headline("Intel and Apple reach preliminary agreement for chip manufacturing deal")
        types = [t for t, _ in hits]
        assert any(t in ("M&A", "MAJOR_DEAL", "PARTNERSHIP") for t in types)

    def test_earnings_beat(self):
        hits = _classify_headline("NVDA earnings beat expectations: revenue surpasses $40B")
        types = [t for t, _ in hits]
        assert "EARNINGS_BEAT" in types or "EARNINGS_BLOWOUT" in types

    def test_fda_approval(self):
        hits = _classify_headline("FDA approves new drug from Pfizer for rare disease")
        types = [t for t, _ in hits]
        assert "FDA_APPROVAL" in types

    def test_no_catalyst(self):
        hits = _classify_headline("Markets close mixed on light trading volume")
        assert len(hits) == 0

    def test_regulatory_action(self):
        hits = _classify_headline("DOJ antitrust probe targets Google search monopoly")
        types = [t for t, _ in hits]
        assert "REGULATORY_ACTION" in types

    def test_analyst_upgrade(self):
        hits = _classify_headline("Goldman upgrades AAPL to buy, raises price target")
        types = [t for t, _ in hits]
        assert "ANALYST_UPGRADE" in types or "PT_RAISE" in types


class TestDetectCatalysts:
    def test_empty_articles(self):
        result = detect_catalysts([], "AAPL")
        assert isinstance(result, CatalystPayload)
        assert not result.active
        assert result.events == []

    def test_old_article_ignored(self):
        article = _make_article("Intel acquires major chip division", hours_ago=72)
        result = detect_catalysts([article], "INTC")
        assert not result.active

    def test_recent_ma_detected(self):
        article = _make_article(
            "Intel and Apple reach preliminary agreement for foundry deal worth $10B",
            hours_ago=6,
        )
        result = detect_catalysts([article], "INTC")
        assert result.active
        assert result.top_event_type == "M&A"
        assert result.top_impact == 3
        assert "catalyst active" in (result.override_note or "").lower()

    def test_earnings_blowout(self):
        article = _make_article(
            "NVDA earnings crush estimates with blowout revenue of $45B",
            hours_ago=3,
        )
        result = detect_catalysts([article], "NVDA")
        assert result.active
        assert result.top_event_type == "EARNINGS_BLOWOUT"

    def test_bearish_catalyst_note(self):
        article = _make_article(
            "SEC charges company with fraud in accounting scandal",
            hours_ago=5,
        )
        result = detect_catalysts([article], "XYZ")
        assert result.active
        assert "negative event" in (result.override_note or "").lower()

    def test_min_impact_filter(self):
        article = _make_article(
            "Analyst raises price target to $200",
            hours_ago=4,
        )
        result = detect_catalysts([article], "AAPL", min_impact=2)
        assert not result.active

    def test_multiple_events_sorted_by_impact(self):
        articles = [
            _make_article("Analyst upgraded to buy", hours_ago=5),
            _make_article("Company acquires rival in $5B deal worth celebrating", hours_ago=2),
        ]
        result = detect_catalysts(articles, "TEST")
        assert result.active
        assert result.top_event_type == "M&A"
        assert len(result.events) >= 1

    def test_custom_max_age(self):
        article = _make_article(
            "Intel acquires major division in landmark deal",
            hours_ago=30,
        )
        result_default = detect_catalysts([article], "INTC", max_age_hours=48)
        result_tight = detect_catalysts([article], "INTC", max_age_hours=24)
        assert result_default.active
        assert not result_tight.active

    def test_catalyst_payload_fields(self):
        article = _make_article(
            "FDA approves breakthrough therapy for rare disease",
            hours_ago=10,
        )
        result = detect_catalysts([article], "PFE")
        assert result.active
        assert result.headline_summary is not None
        assert result.hours_since_catalyst is not None
        assert result.hours_since_catalyst < 12
