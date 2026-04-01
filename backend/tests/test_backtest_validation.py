"""Backtest validation: MR inversion skip when pct is derived from counts."""

from __future__ import annotations

from signals.backtest_validation import validate_backtest_result


def test_year_inversion_skipped_when_pct_missing_but_mr_counts_full():
    """Older cache may omit pct_mean_reverting; counts still imply MR-dominated."""
    bt = {
        "schema_version": 2,
        "bucket_assignment_stats": {
            "n_bars_scored": 1000,
            "mean_reverting_bar_count": 1000,
            "trending_bar_count": 0,
            "pct_mean_reverting": None,
            "pct_trending": None,
        },
        "by_year": {
            "2025": {
                "70-100": {3: {"avg_return_pct": 10.0}},
                "0-30": {3: {"avg_return_pct": 20.0}},
            }
        },
    }
    v = validate_backtest_result(bt)
    assert not any("Score inversion" in i for i in v["issues"])


def test_year_inversion_flagged_when_trending_dominated():
    bt = {
        "bucket_assignment_stats": {
            "n_bars_scored": 1000,
            "mean_reverting_bar_count": 100,
            "trending_bar_count": 900,
            "pct_mean_reverting": 10.0,
            "pct_trending": 90.0,
        },
        "by_year": {
            "2025": {
                "70-100": {3: {"avg_return_pct": 10.0}},
                "0-30": {3: {"avg_return_pct": 20.0}},
            }
        },
    }
    v = validate_backtest_result(bt)
    assert any("Score inversion" in i for i in v["issues"])
