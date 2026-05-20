"""Dashboard warm schedule from DASHBOARD_WARM_INTERVAL_MIN."""
from __future__ import annotations

import os
from unittest.mock import patch


def test_dashboard_warm_default_25_min():
    from api.market_scheduler import _dashboard_warm_interval_min, _dashboard_warm_times_et

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DASHBOARD_WARM_INTERVAL_MIN", None)
        assert _dashboard_warm_interval_min() == 25
        times = _dashboard_warm_times_et()
    assert times[0] == (8, 30)
    assert times[1] == (9, 30)
    assert (9, 55) in times
    assert len(times) == 17


def test_dashboard_warm_15_min():
    from api.market_scheduler import _dashboard_warm_interval_min, _dashboard_warm_times_et

    with patch.dict(os.environ, {"DASHBOARD_WARM_INTERVAL_MIN": "15"}):
        assert _dashboard_warm_interval_min() == 15
        times = _dashboard_warm_times_et()
    assert (9, 45) in times
    assert (10, 0) in times
    assert len(times) == 27


def test_dashboard_warm_interval_clamped():
    from api.market_scheduler import _dashboard_warm_interval_min

    with patch.dict(os.environ, {"DASHBOARD_WARM_INTERVAL_MIN": "5"}):
        assert _dashboard_warm_interval_min() == 10
    with patch.dict(os.environ, {"DASHBOARD_WARM_INTERVAL_MIN": "999"}):
        assert _dashboard_warm_interval_min() == 60
