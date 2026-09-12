"""Tests for signals.manual_catalysts — bookmarklet-clipped articles feeding the catalyst pipeline."""
from __future__ import annotations

import pytest

from signals import manual_catalysts as mc


@pytest.fixture
def catalysts_file(tmp_path, monkeypatch):
    p = tmp_path / "manual_catalysts.json"
    monkeypatch.setattr(mc, "_path", lambda: p)
    return p


def test_add_and_read_back_round_trip(catalysts_file):
    row = mc.add_manual_article(
        "amzn", title="Is Amazon a Buy?", text="Some long analysis about Amazon.", url="https://example.com/a"
    )
    assert row["title"] == "Is Amazon a Buy?"
    data = mc._load()
    assert "AMZN" in data
    assert data["AMZN"][0]["text"] == "Some long analysis about Amazon."


def test_missing_title_or_text_raises(catalysts_file):
    with pytest.raises(ValueError):
        mc.add_manual_article("AMZN", title="", text="body")
    with pytest.raises(ValueError):
        mc.add_manual_article("AMZN", title="title", text="")


def test_missing_ticker_raises(catalysts_file):
    with pytest.raises(ValueError):
        mc.add_manual_article("", title="t", text="b")


def test_caps_articles_per_ticker(catalysts_file):
    for i in range(mc.MAX_ARTICLES_PER_TICKER + 5):
        mc.add_manual_article("AMZN", title=f"Article {i}", text=f"body {i}")
    data = mc._load()
    assert len(data["AMZN"]) == mc.MAX_ARTICLES_PER_TICKER
    # most-recent-first: the last one added should be at index 0
    assert data["AMZN"][0]["title"] == f"Article {mc.MAX_ARTICLES_PER_TICKER + 4}"


def test_caps_text_length(catalysts_file):
    huge = "x" * (mc.MAX_TEXT_CHARS + 500)
    row = mc.add_manual_article("AMZN", title="Long one", text=huge)
    assert len(row["text"]) == mc.MAX_TEXT_CHARS


def test_manual_cards_uses_real_classifier_when_it_matches(catalysts_file):
    """An article whose text actually matches an existing event pattern should be
    categorized by the real classifier, not fall back to a generic note."""
    mc.add_manual_article(
        "AMZN",
        title="Amazon reports earnings beat, raises guidance",
        text="Amazon posted an earnings beat this quarter and raised full-year guidance.",
    )
    cards = mc.manual_cards_for_ticker("AMZN")
    assert len(cards) == 1
    assert cards[0]["event_type"] != "MANUAL_NOTE"
    assert cards[0]["origin"] == "manual"


def test_manual_cards_falls_back_to_generic_note_when_nothing_matches(catalysts_file):
    """A long-form opinion piece that matches none of the hard-news regexes must still
    produce a visible card — not silently vanish (the bug this module exists to avoid)."""
    mc.add_manual_article(
        "AMZN",
        title="Is Amazon a Buy or a Trap for Retail Investors?",
        text="A general discussion of Amazon's long-term prospects, valuation, and moat.",
    )
    cards = mc.manual_cards_for_ticker("AMZN")
    assert len(cards) == 1
    assert cards[0]["event_type"] == "MANUAL_NOTE"
    assert cards[0]["name"] == "Analyst Note"
    assert cards[0]["origin"] == "manual"
    assert "Amazon a Buy" in cards[0]["mechanism"]


def test_manual_cards_for_unknown_ticker_is_empty(catalysts_file):
    assert mc.manual_cards_for_ticker("ZZZZ") == []


def test_manual_cards_respects_max_cards(catalysts_file):
    for i in range(5):
        mc.add_manual_article("AMZN", title=f"General thoughts {i}", text=f"analysis body {i}")
    cards = mc.manual_cards_for_ticker("AMZN", max_cards=2)
    assert len(cards) == 2
