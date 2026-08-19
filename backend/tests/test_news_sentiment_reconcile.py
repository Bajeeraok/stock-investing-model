"""News chip vs headline/card disagreement — display only, no score blend."""

from __future__ import annotations

from signals.catalyst_detector import build_earnings_event_card, merge_known_event_cards
from signals.news_keyword_sentiment import score_headline_text
from signals.news_sentiment_reconcile import reconcile_news_display


def test_bullish_chip_vs_drop_headlines_is_mixed():
    out = reconcile_news_display(
        sentiment_label="Bullish",
        score_0_1=0.72,
        headlines=[
            {"title": "AMD shares drop after warning on data-center demand"},
            {"title": "Analysts flag downside into the print"},
        ],
        cards=[],
        hmm_bull_pct=4.0,
    )
    assert out["disagreement"] is True
    assert out["display_label"] == "Mixed"
    assert "caveat" in (out["caveat"] or "").lower() or "negative" in (out["caveat"] or "").lower()
    assert "4%" in (out["caveat"] or "")


def test_agreeing_bullish_stays_bullish():
    out = reconcile_news_display(
        sentiment_label="Bullish",
        score_0_1=0.7,
        headlines=[{"title": "Company beats estimates on record profit"}],
        cards=[{"direction": "unlocks", "event_type": "EARNINGS_BEAT"}],
    )
    assert out["disagreement"] is False
    assert out["display_label"] == "Bullish"


def test_score_untouched_by_reconcile():
    """Caller keeps score_0_1; reconcile only returns display fields."""
    out = reconcile_news_display(
        sentiment_label="Bullish",
        score_0_1=0.8,
        headlines=[{"title": "Shares drop on profit warning"}],
        cards=[{"direction": "breaks"}],
    )
    assert "score" not in out
    assert out["disagreement"] is True


def test_earnings_calendar_card_is_watch_not_unlock():
    card = build_earnings_event_card(ticker="AMD", days_until=9, report_date="2026-08-27")
    assert card is not None
    assert card["event_type"] == "EARNINGS_CALENDAR"
    assert card["direction"] == "watch"
    assert "does not change bands" in card["draft_note"].lower()


def test_earnings_card_merges_to_front():
    news = [{"event_type": "PT_CUT", "direction": "breaks", "name": "pt cut"}]
    extra = build_earnings_event_card(ticker="AMD", days_until=3)
    merged = merge_known_event_cards(news, extra, max_cards=4)
    assert merged[0]["event_type"] == "EARNINGS_CALENDAR"
    assert len(merged) == 2


def test_shares_drop_scores_bearish():
    raw, hit = score_headline_text("AMD shares drop after profit warning", "")
    assert hit
    assert raw < 0
