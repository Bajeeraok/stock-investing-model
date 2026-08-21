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
        "api.dashboard_warm.compute_signal_warm_sync"
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


def test_compute_post_eod_dashboard_sync_uses_last_run(tmp_path):
    import json

    from api.dashboard_warm import compute_post_eod_dashboard_sync

    full_results = [
        {"ticker": f"T{i}", "composite_buy": 50, "error": False, "close": 100.0}
        for i in range(80)
    ]
    (tmp_path / "last_run.json").write_text(
        json.dumps({"run_results": full_results}),
        encoding="utf-8",
    )
    with patch("config_loader.get_data_root", return_value=tmp_path), patch(
        "scripts.run_daily.min_full_eod_row_count", return_value=50
    ), patch(
        "api.dashboard_warm.compute_signal_warm_sync", return_value={"merged": True}
    ) as warm:
        out = compute_post_eod_dashboard_sync()
    warm.assert_called_once()
    assert warm.call_args.kwargs["prefetched_results"] == full_results
    assert warm.call_args.kwargs["warm_kind"] == "post_eod"
    assert out == {"merged": True}


def test_trigger_post_eod_dashboard_sync():
    from api.dashboard_warm import trigger_post_eod_dashboard_sync

    with patch("api.dashboard_job.is_refresh_running", return_value=False), patch(
        "api.dashboard_job.trigger_background_refresh", return_value=True
    ) as trigger:
        ok = trigger_post_eod_dashboard_sync()
    assert ok is True
    trigger.assert_called_once()


def test_background_refresh_quote_tick_when_signals_fresh():
    from api.dashboard_warm import compute_for_background_refresh
    from signals.time_et import now_iso_et

    cached = {
        "signals": [{"ticker": "AAPL", "close": 100.0}],
        "config": {},
        "data_freshness": {"signals_updated_at": now_iso_et()},
    }
    with patch("alerts.market_hours.is_signal_warm_window", return_value=True), patch(
        "signals.cache.get_cached_dashboard", return_value=None
    ), patch(
        "signals.cache.get_last_dashboard_snapshot", return_value=cached
    ), patch("api.dashboard_warm._signals_warm_skip_if_fresh_min", return_value=60.0), patch(
        "api.dashboard_warm.compute_quote_tick_sync", return_value={"warm_kind": "quote_tick"}
    ) as quote, patch("api.dashboard_warm.compute_signal_warm_sync") as warm:
        out = compute_for_background_refresh()
    quote.assert_called_once()
    warm.assert_not_called()
    assert out["warm_kind"] == "quote_tick"


def test_background_refresh_skipped_overnight():
    from api.dashboard_warm import compute_for_background_refresh

    cached = {"signals": [{"ticker": "AAPL"}], "config": {}}
    with patch("alerts.market_hours.is_signal_warm_window", return_value=False), patch(
        "signals.cache.get_cached_dashboard", return_value=cached
    ), patch("api.dashboard_warm.compute_signal_warm_sync") as warm:
        out = compute_for_background_refresh()
    warm.assert_not_called()
    assert out is cached
