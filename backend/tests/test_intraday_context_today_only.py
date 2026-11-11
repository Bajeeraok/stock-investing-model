import datetime as dt
from unittest import mock

import pandas as pd

from signals import market_catalysts as mc


def _hist(day: str):
    idx = pd.date_range(f"{day} 09:30", periods=3, freq="5min", tz="America/New_York")
    return pd.DataFrame({"Open": [100.0, 101.0, 102.0], "Close": [100.5, 101.5, 102.5]}, index=idx)


def _run(day: str, now: dt.datetime):
    fake = mock.MagicMock()
    fake.Ticker.return_value.history.return_value = _hist(day)
    with mock.patch.dict("sys.modules", {"yfinance": fake}):
        return mc._intraday_context([], now=now)


def test_premarket_ignores_prior_session_bars():
    now = dt.datetime(2026, 11, 11, 8, 30)
    assert _run("2026-11-10", now) is None


def test_rth_uses_today_bars():
    now = dt.datetime(2026, 11, 11, 10, 0)
    out = _run("2026-11-11", now)
    assert out["spy_open"] == 100.0 and out["spy_last"] == 102.5
