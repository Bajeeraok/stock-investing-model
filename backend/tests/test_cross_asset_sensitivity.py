"""Cross-asset badges must be distinctive vs SPY, not a 60d |ρ| ≥ 0.25 noise tag."""
from __future__ import annotations

from signals.cross_asset_sensitivity import badges_from_correlations


def test_equity_like_gld_corr_is_not_gold_sensitive():
    # AMD-style: mild GLD corr that SPY also has
    badges = badges_from_correlations(gld=0.28, uup=0.10, vix=-0.42, spy_gld=0.31, spy_uup=0.05, spy_vix=-0.48)
    assert "gold-sensitive" not in badges
    assert "volatility-sensitive" not in badges


def test_true_gold_proxy_still_badges():
    badges = badges_from_correlations(gld=0.82, uup=-0.55, vix=0.20, spy_gld=0.30, spy_uup=-0.20, spy_vix=-0.45)
    assert "gold-sensitive" in badges
    assert "USD-sensitive" in badges
