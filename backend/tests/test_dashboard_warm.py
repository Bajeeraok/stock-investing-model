"""Tests for retail Phase 1 dashboard warm (quote tick + signal warm)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_get_retail_quote_tickers_unions_holdings():
    from api.dashboard_warm import get_retail_quote_tickers

    config = {
        "watchlist": ["MSFT"],
        "signal_audit": {"enabled": False},
    }
    holdings = [{"ticker": "ORPHAN"}]
    with patch("config_loader.get_eod_signal_universe", return_value=["AAPL", "SPY"]):
        tickers = get_retail_quote_tickers(config, holdings)
    assert tickers == ["AAPL", "SPY", "MSFT", "ORPHAN"]


def test_compute_quote_tick_sync_no_cache():
    from api.dashboard_warm import compute_quote_tick_sync

    with patch("signals.cache.get_cached_dashboard", return_value=None), patch(
        "signals.cache.get_last_dashboard_snapshot", return_value=None
    ):
        assert compute_quote_tick_sync() is None


def test_compute_quote_tick_sync_patches_prices():
    from api.dashboard_warm import compute_quote_tick_sync

    cached = {
        "signals": [{"ticker": "AAPL", "close": 100.0, "error": False}],
        "portfolios": {
            "All": {
                "total_value": 1000,
                "per_holding": [{"ticker": "AAPL", "quantity": 10, "value": 1000}],
            }
        },
        "portfolio": {"per_holding": []},
        "data_freshness": {},
    }
    with patch("api.dashboard_job.is_refresh_running", return_value=False), patch(
        "signals.cache.get_cached_dashboard", return_value=cached
    ), patch("signals.cache.get_last_dashboard_snapshot", return_value=None), patch(
        "api.dashboard_warm.fetch_live_prices", return_value=({"AAPL": 105.0}, False)
    ), patch(
        "signals.cache.merge_dashboard_cache_updates", return_value=True
    ) as merge:
        out = compute_quote_tick_sync()
    assert out is not None
    assert merge.called
    assert out["data_freshness"]["quotes_updated_at"]


def test_refresh_endpoint_starts_async_job():
    from fastapi.testclient import TestClient

    from api.main import app

    shell = {"as_of_date": "2026-06-14", "config": {"watchlist": []}, "data_freshness": {}}
    with patch("signals.cache.get_cached_dashboard", return_value=shell), patch(
        "api.dashboard_warm.compute_for_background_refresh"
    ) as compute_fn, patch("api.dashboard_job.trigger_background_refresh", return_value=True) as trigger:
        client = TestClient(app)
        resp = client.get("/api/dashboard?refresh=true")
    assert resp.status_code == 200
    trigger.assert_called_once()
    assert trigger.call_args[0][0] is compute_fn


def test_compute_signal_warm_falls_back_without_cache():
    from api.dashboard_warm import compute_signal_warm_sync

    with patch("signals.cache.get_cached_dashboard", return_value=None), patch(
        "signals.cache.get_last_dashboard_snapshot", return_value=None
    ), patch("api.routers.dashboard._compute_full_dashboard_sync", return_value={"ok": True}) as full:
        out = compute_signal_warm_sync()
    full.assert_called_once()
    assert out == {"ok": True}
