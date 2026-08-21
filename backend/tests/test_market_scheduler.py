"""Dashboard warm schedule from DASHBOARD_WARM_INTERVAL_MIN."""
from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def test_dashboard_warm_default_railway():
    from api.market_scheduler import _dashboard_warm_interval_min

    with patch.dict(
        os.environ,
        {"RAILWAY_ENVIRONMENT": "production"},
        clear=False,
    ):
        os.environ.pop("DASHBOARD_WARM_INTERVAL_MIN", None)
        assert _dashboard_warm_interval_min() == 120


def test_dashboard_warm_interval_clamped():
    from api.market_scheduler import _dashboard_warm_interval_min

    with patch.dict(os.environ, {"DASHBOARD_WARM_INTERVAL_MIN": "5"}):
        assert _dashboard_warm_interval_min() == 30
    with patch.dict(os.environ, {"DASHBOARD_WARM_INTERVAL_MIN": "999"}):
        assert _dashboard_warm_interval_min() == 180


def test_signal_warm_window_weekday_hours():
    from alerts.market_hours import is_signal_warm_window

    assert is_signal_warm_window(datetime(2026, 8, 20, 10, 0, tzinfo=ET)) is True
    assert is_signal_warm_window(datetime(2026, 8, 20, 20, 0, tzinfo=ET)) is False
    assert is_signal_warm_window(datetime(2026, 8, 22, 10, 0, tzinfo=ET)) is False  # Sat


def test_overnight_dashboard_ttl_until_next_warm():
    from signals.cache import _dashboard_ttl_seconds

    with patch("alerts.market_hours.is_signal_warm_window", return_value=False), patch(
        "alerts.market_hours.seconds_until_next_signal_warm_open", return_value=12 * 3600
    ):
        os.environ.pop("DASHBOARD_CACHE_TTL_SECONDS", None)
        ttl = _dashboard_ttl_seconds()
    assert ttl == 12 * 3600
