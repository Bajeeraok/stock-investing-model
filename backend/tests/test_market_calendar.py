"""NYSE market calendar for EOD scheduler."""
from __future__ import annotations

from datetime import date

from signals.market_calendar import is_nyse_holiday, is_us_equity_session_day, nyse_full_holidays


def test_weekend_not_session():
    assert is_us_equity_session_day("2026-07-04") is False  # Saturday


def test_independence_day_observed_2026():
    # July 4 2026 is Saturday — NYSE observes Friday July 3
    assert is_nyse_holiday(date(2026, 7, 3)) is True
    assert is_us_equity_session_day("2026-07-03") is False


def test_regular_trading_day():
    assert is_us_equity_session_day("2026-07-02") is True


def test_good_friday_2026():
    # Good Friday 2026 = April 3
    assert date(2026, 4, 3) in nyse_full_holidays(2026)


def test_christmas_observed_sunday_to_monday():
    # Christmas 2022 Sunday -> observed Monday Dec 26
    assert date(2022, 12, 26) in nyse_full_holidays(2022)
