from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from signals.market_calendar import latest_completed_session, series_last_bar_stale

ET = ZoneInfo("America/New_York")


def test_latest_completed_session():
    assert latest_completed_session(datetime(2026, 10, 26, 20, 1, tzinfo=ET)) == date(2026, 10, 26)
    assert latest_completed_session(datetime(2026, 10, 26, 11, 0, tzinfo=ET)) == date(2026, 10, 23)
    assert latest_completed_session(datetime(2026, 10, 24, 11, 27, tzinfo=ET)) == date(2026, 10, 23)


def test_series_last_bar_stale():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-10-22", "2026-10-23"]))
    assert series_last_bar_stale(s, date(2026, 10, 26))
    assert not series_last_bar_stale(s, date(2026, 10, 23))
