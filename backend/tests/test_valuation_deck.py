"""Valuation deck and analyst rating distribution."""
from unittest.mock import patch

from signals.analyst_ratings import gap_badge, normalize_rating_distribution, street_primary_usd
from signals.valuation_deck import build_valuation_deck


def test_normalize_fmp_ratings():
    raw = {"strongBuy": 12, "buy": 18, "hold": 5, "sell": 1, "strongSell": 0}
    d = normalize_rating_distribution(raw, "fmp")
    assert d is not None
    assert d["total"] == 36
    assert d["bullish_pct"] == round(100 * 30 / 36, 1)


def test_street_primary_fmp_first():
    fve = {
        "fmp_consensus_median_usd": 560.0,
        "yahoo_12m_mean_usd": 550.0,
        "fmp_median_is_range_midpoint": False,
    }
    usd, label = street_primary_usd(fve)
    assert usd == 560.0
    assert "FMP" in label


def test_gap_badge_thresholds():
    assert gap_badge(15) == "ok"
    assert gap_badge(-25) == "review"
    assert gap_badge(45) == "caution"


@patch("signals.valuation_deck.get_analyst_rating_distribution", return_value=None)
def test_build_valuation_deck_minimal(_mock_ratings):
    deck = build_valuation_deck(
        ticker="MSFT",
        config={},
        fair_value=470.0,
        current_price=450.0,
        fair_value_vs_external={
            "fmp_consensus_median_usd": 561.0,
            "fmp_consensus_low_usd": 520.0,
            "fmp_consensus_high_usd": 600.0,
            "yahoo_12m_mean_usd": 555.0,
        },
        fair_value_metadata={"method_used": "forward_pe_blend", "methodology_summary": "Growth blend"},
        entry_tiers={
            "active_tier_id": "T1",
            "current_assessment": {"label": "Nibble zone", "min_price_to_buy": 352.0},
            "tiers": [{"id": "T1", "label": "T1", "low": 433, "high": 479, "allocation_pct": 5}],
        },
        ttm_pe=35.0,
        forward_pe=28.0,
        one_answer={"action_today": "wait_for_pullback"},
    )
    assert deck is not None
    assert deck["model"]["gap_badge"] == "ok"
    assert deck["house"]["min_price_to_buy"] == 352.0
    assert deck["scout_street_alert"] is False
    assert deck["street"]["median_usd"] == 561.0
    assert deck["street"]["high_usd"] == 600.0
    assert deck["street"]["low_usd"] == 520.0
    assert deck["street"]["median_return_pct"] is not None
