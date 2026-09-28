"""EPS history counting and FV routing data-sanity gates."""
from unittest.mock import patch

from signals.fv_eps_history import (
    MIN_CLEAN_QUARTERS_SPINOFF,
    MIN_TOTAL_QUARTERS_IPO,
    _is_clean_eps_quarter,
    count_eps_quarter_history,
    counts_from_rows,
)
from signals.fv_house_tiers import tag_entry_tiers_street_anchor
from signals.fv_router import route_fair_value
from signals.valuation_deck import build_valuation_deck


def test_is_clean_eps_quarter():
    assert _is_clean_eps_quarter({"revenue": 1000, "eps": 1.2}) is True
    assert _is_clean_eps_quarter({"revenue": 0, "eps": 1.2}) is False
    assert _is_clean_eps_quarter({"revenue": 1000}) is False


@patch("signals.fv_eps_history.fetch_quarterly_income")
def test_count_eps_quarter_history(mock_fetch):
    mock_fetch.return_value = [
        {"revenue": 100, "eps": 1.0},
        {"revenue": 90, "eps": 0.9},
        {"revenue": 80, "eps": 0.8},
        {"revenue": 70},  # missing eps
    ]
    total, clean = count_eps_quarter_history({}, "SNDK")
    assert total == 4
    assert clean == 3


def test_counts_from_rows_matches_count_eps_quarter_history():
    """counts_from_rows() lets a caller that already fetched rows (fair_value_pipeline.py,
    sharing one fetch_quarterly_income() call with EPS normalization) derive the same
    total/clean counts without a second fetch against the same FMP endpoint."""
    rows = [
        {"revenue": 100, "eps": 1.0},
        {"revenue": 90, "eps": 0.9},
        {"revenue": 70},  # missing eps
    ]
    assert counts_from_rows(rows) == (3, 2)


def test_counts_from_rows_none_input():
    assert counts_from_rows(None) == (None, None)


def test_counts_from_rows_empty_list():
    assert counts_from_rows([]) == (0, 0)


def test_route_spinoff_suppressed_when_clean_lt_4():
    r = route_fair_value("SNDK", ttm_eps=2.0, ntm_eps=3.0, quarters_of_clean_history=2, total_quarters_history=10)
    assert r.fv_suppressed is True
    assert "stub history" in r.fv_suppressed_reason.lower()


def test_route_spinoff_suppressed_when_history_unverified():
    r = route_fair_value("SNDK", ttm_eps=2.0, ntm_eps=3.0, quarters_of_clean_history=None, total_quarters_history=10)
    assert r.fv_suppressed is True
    assert "unverified" in r.fv_suppressed_reason.lower()


def test_route_recent_ipo_suppressed():
    r = route_fair_value("NEWCO", ttm_eps=1.0, ntm_eps=1.5, total_quarters_history=5)
    assert r.fv_suppressed is True
    assert "<8 quarters" in r.fv_suppressed_reason


def test_tag_entry_tiers_street_anchor():
    et = {
        "active_tier_id": "T2",
        "current_assessment": {"label": "Nibble zone", "min_price_to_buy": 100.0},
        "tiers": [{"id": "T2", "label": "T2", "low": 95, "high": 105, "allocation_pct": 10}],
    }
    tagged = tag_entry_tiers_street_anchor(
        et,
        fv_suppressed=True,
        fv_suppressed_reason="REIT — P/FFO required",
        street_anchor_usd=120.0,
        street_anchor_source="fmp_consensus",
    )
    assert tagged is not None
    assert tagged["fv_anchor"]["fv_model_suppressed"] is True
    assert tagged["fv_anchor"]["street_anchor_usd"] == 120.0
    assert "street-anchored" in tagged["current_assessment"]["label"].lower()


@patch("signals.valuation_deck.get_analyst_rating_distribution", return_value=None)
def test_build_valuation_deck_suppressed_street_anchored_house(_mock_ratings):
    entry_tiers = tag_entry_tiers_street_anchor(
        {
            "active_tier_id": "T2",
            "current_assessment": {"label": "Nibble zone", "min_price_to_buy": 352.0},
            "tiers": [{"id": "T2", "label": "T2", "low": 433, "high": 479, "allocation_pct": 5}],
        },
        fv_suppressed=True,
        fv_suppressed_reason="BANK — P/TBV required",
        street_anchor_usd=400.0,
        street_anchor_source="fmp_consensus",
    )
    deck = build_valuation_deck(
        ticker="JPM",
        config={},
        fair_value=400.0,
        current_price=245.0,
        fair_value_vs_external={"fmp_consensus_median_usd": 400.0},
        fair_value_metadata={"fv_suppressed": True, "fv_suppressed_reason": "BANK"},
        entry_tiers=entry_tiers,
        fv_suppressed=True,
        fv_suppressed_reason="BANK — P/TBV required",
    )
    assert deck is not None
    assert deck["model"]["fair_value_usd"] is None
    assert deck["model"]["fv_suppressed"] is True
    assert deck["house"]["fv_street_anchored"] is True
    assert deck["house"]["fv_street_anchor_usd"] == 400.0
    assert deck["house"]["band_anchor_note"] is not None
