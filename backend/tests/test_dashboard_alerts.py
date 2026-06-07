"""Retail alerts after dashboard Refresh — dashboard universe + audit cohort price-only."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scanner.dashboard_alerts import (
    run_retail_alerts_from_dashboard_refresh,
    snapshot_from_signal_row,
)
from scanner.horizon_levels import write_horizon_levels
from scanner.store import ScannerStore


def test_snapshot_from_signal_row_skips_errors():
    assert snapshot_from_signal_row({"ticker": "X", "error": "fail"}, watchlist=set()) is None
    snap = snapshot_from_signal_row(
        {"ticker": "AAPL", "close": 180.0, "regime": "UP", "composite_buy": 72},
        watchlist={"AAPL"},
    )
    assert snap is not None
    assert snap.symbol == "AAPL"
    assert snap.price == 180.0
    assert snap.in_watchlist is True


def test_run_retail_alerts_after_refresh_dashboard_row(tmp_path: Path):
    write_horizon_levels(
        tmp_path,
        {
            "AAPL": {
                "short": {
                    "entry_low": 175.0,
                    "entry_high": 185.0,
                    "stop_loss": 174.0,
                    "target": 200.0,
                    "horizon_label": "Short-term",
                }
            }
        },
    )
    config = {
        "watchlist": ["AAPL"],
        "alerts": {"evaluate_on_dashboard_refresh": True, "include_audit_cohort_on_refresh": False},
    }
    results = [
        {"ticker": "SPY", "close": 500.0, "regime": "UP", "_global_market_regime": "UP"},
        {
            "ticker": "AAPL",
            "close": 180.0,
            "regime": "UP",
            "composite_buy": 70,
            "st_band": {"low": 175.0, "high": 185.0},
        },
    ]

    with patch("config_loader.get_dashboard_signal_universe", return_value=["AAPL", "SPY"]):
        summary = run_retail_alerts_from_dashboard_refresh(
            results,
            config,
            tmp_path,
            prices_by_ticker={"AAPL": 180.0, "SPY": 500.0},
        )

    assert summary.get("skipped") is False
    assert summary.get("snapshots", 0) >= 2
    store = ScannerStore(tmp_path)
    alerts = store.load_alerts(limit=50)
    assert any(a.get("ticker") == "AAPL" for a in alerts)


def test_cohort_only_price_path(tmp_path: Path):
    write_horizon_levels(
        tmp_path,
        {
            "COST": {
                "short": {
                    "entry_low": 900.0,
                    "entry_high": 920.0,
                    "stop_loss": 895.0,
                    "target": 950.0,
                    "horizon_label": "Short-term",
                }
            }
        },
    )
    config = {
        "watchlist": [],
        "alerts": {"evaluate_on_dashboard_refresh": True, "include_audit_cohort_on_refresh": True},
    }
    results = [{"ticker": "SPY", "close": 500.0, "regime": "NEUTRAL"}]

    with patch("config_loader.get_dashboard_signal_universe", return_value=["SPY"]):
        with patch("config_loader.get_audit_cohort_tickers", return_value=["COST", "SPY"]):
            summary = run_retail_alerts_from_dashboard_refresh(
                results,
                config,
                tmp_path,
                prices_by_ticker={"SPY": 500.0, "COST": 910.0},
            )

    assert summary.get("cohort_price_only_evaluated", 0) == 1
    stats_path = tmp_path / "scanner" / "stats.json"
    assert stats_path.exists()
    stats = json.loads(stats_path.read_text())
    assert stats.get("source") == "dashboard_refresh"


def test_disabled_via_config(tmp_path: Path):
    config = {"alerts": {"evaluate_on_dashboard_refresh": False}}
    out = run_retail_alerts_from_dashboard_refresh([], config, tmp_path)
    assert out.get("skipped") is True
