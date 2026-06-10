"""Institutional 13F conviction filter — passive filer exclusion, normalization."""

from __future__ import annotations

from signals.institutional_conviction import (
    compute_institutional_conviction_filter,
    is_passive_filer,
)


def test_passive_filer_blackrock():
    assert is_passive_filer("BlackRock Inc.")
    assert is_passive_filer("Vanguard Capital Management LLC")


def test_active_filer_not_passive():
    assert not is_passive_filer("Berkshire Hathaway Inc.")
    assert not is_passive_filer("Citadel Advisors LLC")


def test_edgar_active_net_delta_and_float_norm():
    bundle = {
        "edgar_13f": {
            "source": "sec_edgar_13f",
            "period_ending": "2025-12-31",
            "prior_period_ending": "2025-09-30",
            "top_holder_changes": [
                {
                    "filer": "Berkshire Hathaway Inc",
                    "shares": 350608 + 1000000,
                    "prior_shares": 1000000,
                    "change_pct": 35.06,
                },
                {
                    "filer": "Vanguard Group Inc",
                    "shares": 2000000,
                    "prior_shares": 1500000,
                    "change_pct": 33.33,
                },
            ],
        }
    }
    out = compute_institutional_conviction_filter(
        bundle,
        float_shares=100_000_000,
        avg_daily_volume=5_000_000,
        quarter_price_change_pct=-8.0,
        config={},
    )
    assert out["net_shares_active"] == 350608
    assert out["passive_filers_excluded"] == 1
    assert out["verdict"] == "supports"
    assert out["buy_the_dip"] is True
    assert out["role"] == "conviction_filter"
    assert out["pct_of_float"] is not None
    assert out["pct_of_adv"] is not None


def test_distribution_concerns():
    bundle = {
        "edgar_13f": {
            "top_holder_changes": [
                {
                    "filer": "Tiger Global Management",
                    "shares": 500000,
                    "prior_shares": 900000,
                    "change_pct": -44.4,
                },
            ],
        }
    }
    out = compute_institutional_conviction_filter(bundle, config={})
    assert out["net_shares_active"] == -400000
    assert out["verdict"] == "concerns"


def test_yahoo_fallback_rows():
    bundle = {
        "institutional_ownership": {
            "top_holders": [
                {"holder": "Coatue Management", "shares": 1100000, "pct_change_qoq": 12.5},
            ],
        },
    }
    out = compute_institutional_conviction_filter(bundle, config={})
    assert out["net_shares_active"] is not None
    assert out["net_shares_active"] > 0
