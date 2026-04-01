"""Earnings window exclusion helpers."""

from __future__ import annotations

import pandas as pd

from signals.backtest_earnings import (
    prepare_earnings_timestamps,
    should_exclude_bar_for_earnings,
)


def test_should_exclude_within_window():
    ts = prepare_earnings_timestamps(["2024-01-10", "2024-04-15"])
    bar = pd.Timestamp("2024-01-08")
    assert should_exclude_bar_for_earnings(bar, ts, 5)
    bar2 = pd.Timestamp("2024-01-10")
    assert should_exclude_bar_for_earnings(bar2, ts, 5)
    bar3 = pd.Timestamp("2024-01-02")
    assert not should_exclude_bar_for_earnings(bar3, ts, 5)


def test_no_next_earnings():
    ts = prepare_earnings_timestamps(["2020-01-01"])
    bar = pd.Timestamp("2024-06-01")
    assert not should_exclude_bar_for_earnings(bar, ts, 5)
