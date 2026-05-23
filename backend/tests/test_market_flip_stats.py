"""Tests for market flip stats (P1)."""
from __future__ import annotations

import datetime as dt

from signals.event_scenarios import get_event_reaction_stats
from signals.market_flip_stats import (
    compute_gap_fade_stats,
    event_dates_for_type,
    generate_cpi_dates,
    generate_nfp_dates,
    load_market_flip_stats,
    stats_for_event_type,
)


def test_nfp_dates_first_friday():
    dates = generate_nfp_dates(dt.date(2024, 1, 1), dt.date(2024, 3, 31))
    assert "2024-01-05" in dates
    assert "2024-02-02" in dates
    assert "2024-03-01" in dates


def test_cpi_dates_monthly():
    dates = generate_cpi_dates(dt.date(2024, 1, 1), dt.date(2024, 2, 28))
    assert len(dates) == 2
    assert all(d.startswith("2024-") for d in dates)


def test_load_seed_flip_stats():
    stats = load_market_flip_stats()
    assert stats is not None
    assert "CPI" in (stats.get("events") or {})
    cpi = stats_for_event_type("CPI", stats)
    assert cpi is not None
    assert cpi.get("pct_gap_fade") is not None


def test_get_event_reaction_stats_cpi_from_cache():
    stats = get_event_reaction_stats("CPI")
    assert stats is not None
    assert stats.get("n_events", 0) >= 5
    assert "pct_gap_fade" in stats or stats.get("gap_fade")


def test_gap_fade_computation_synthetic():
    import pandas as pd

    idx = pd.date_range("2024-01-01", periods=25, freq="B")
    closes = [100.0]
    opens = [100.0]
    for i in range(1, 25):
        prev = closes[-1]
        if i % 2 == 0:
            opens.append(prev + 2)  # gap up
            closes.append(prev - 1)  # close below prior → fade
        else:
            opens.append(prev - 2)  # gap down
            closes.append(prev + 1)  # close above prior → fade
    df = pd.DataFrame({"open": opens, "close": closes}, index=idx)
    dates = [idx[i].strftime("%Y-%m-%d") for i in range(1, 12)]
    out = compute_gap_fade_stats(dates, df, label="test")
    assert out is not None
    assert out["n_events"] >= 5
    assert out["pct_gap_fade"] >= 50


def test_fomc_dates_available():
    dates = event_dates_for_type("FOMC", dt.date(2023, 1, 1), dt.date(2024, 12, 31))
    assert len(dates) >= 8
