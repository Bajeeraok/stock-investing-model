"""Tests for earnings-gated after-hours snapshot."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_tickers_reporting_today_filters_days_until_zero():
    from signals.after_hours_earnings import tickers_reporting_today

    config = {"watchlist": ["AAPL", "MSFT"], "portfolios": {}}

    def fake_earnings(ticker, _config):
        if ticker == "AAPL":
            return {"date": "2026-05-19", "days_until": 0}
        if ticker == "MSFT":
            return {"date": "2026-05-20", "days_until": 1}
        return None

    with patch("signals.providers.get_next_earnings", side_effect=fake_earnings):
        out = tickers_reporting_today(config, universe=["AAPL", "MSFT"])
    assert len(out) == 1
    assert out[0]["ticker"] == "AAPL"


def test_run_snapshot_skipped_when_no_earnings_today():
    from signals.after_hours_earnings import run_after_hours_earnings_snapshot

    config = {"watchlist": ["AAPL"], "portfolios": {}}
    with patch("signals.after_hours_earnings.tickers_reporting_today", return_value=[]):
        result = run_after_hours_earnings_snapshot(slot="test", config=config)
    assert result["skipped"] is True
    assert result["skip_reason"] == "no_earnings_today"


def test_run_snapshot_builds_items():
    from signals.after_hours_earnings import run_after_hours_earnings_snapshot

    config = {"watchlist": ["NVDA"], "portfolios": {}, "data": {}}
    reporting = [{"ticker": "NVDA", "earnings_date": "2026-05-19", "days_until": 0}]
    with patch("signals.after_hours_earnings.tickers_reporting_today", return_value=reporting):
        with patch("signals.after_hours_earnings._prior_closes_from_dashboard_cache", return_value={"NVDA": 100.0}):
            with patch(
                "signals.after_hours_earnings._fetch_live_prices",
                return_value=({"NVDA": 92.0}, "fmp_batch"),
            ):
                with patch("signals.after_hours_earnings._persist_snapshot"):
                    with patch("signals.cache.merge_dashboard_cache_updates", return_value=True):
                        result = run_after_hours_earnings_snapshot(slot="6pm", config=config)
    assert result["skipped"] is False
    assert len(result["items"]) == 1
    assert result["items"][0]["change_pct"] == pytest.approx(-8.0)
