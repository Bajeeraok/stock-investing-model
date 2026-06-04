"""Tests for backtest tier enhancements."""
from __future__ import annotations

from signals.backtest_tiers import (
    build_primary_kpis,
    effective_earnings_exclusion_config,
    _build_exit_backtest,
    _non_overlapping_rule_sim,
    _stats,
)


def test_effective_earnings_auto_single_stock():
    cfg = {"backtest": {"earnings_exclusion": {"enabled": False, "auto_single_stock": True}}}
    ec = effective_earnings_exclusion_config(cfg, "AAPL")
    assert ec["enabled"] is True
    ec_spy = effective_earnings_exclusion_config(cfg, "SPY")
    assert ec_spy.get("enabled") is False


def test_primary_kpis_good_band():
    result = {
        "mr_spread_6m": {"edge_pct": 3.5, "dip_hit_rate_pct": 90},
        "walk_forward": {"consistency": {6: {"avg_net_return_pct": 11.0, "consistent": True}}},
        "bucket_assignment_stats": {"pct_mean_reverting": 74},
    }
    kpis = build_primary_kpis(result)
    assert kpis["confidence_band"] == "good"
    assert kpis["recommended_horizon_months"] == 6


def test_exit_backtest_underperforms():
    gate_summary = {
        "by_horizon_trading_days": {
            "63": {
                "all_bars": {"mean_fwd_pct": 4.0, "n": 100},
                "composite_sell": {"mean_fwd_pct": 2.0, "n": 50, "hit_rate_pct": 60},
            }
        }
    }
    ex = _build_exit_backtest(gate_summary, 30)
    assert ex["by_horizon_trading_days"]["63"]["trim_avoided_loss"] == "low_score_underperforms"


def test_non_overlapping_sim_respects_one_at_a_time():
    import pandas as pd

    close = pd.Series([100 + i * 0.1 for i in range(400)])
    panel = [
        {"bar_index": 210, "bucket": "70-100", "composite_buy": 75, "gate_cleared": True},
        {"bar_index": 220, "bucket": "70-100", "composite_buy": 76, "gate_cleared": True},
    ]
    res = _non_overlapping_rule_sim(
        panel,
        close,
        transaction_cost=0.003,
        buy_min=70,
        sell_max=30,
        hold_days=21,
        dip_bucket="70-100",
    )
    assert res["n"] == 1


def test_stats_empty():
    assert _stats([])["n"] == 0
