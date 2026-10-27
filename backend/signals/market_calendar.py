"""
US equity session calendar — weekdays minus NYSE full-day closures.

Used by EOD scheduler / run_daily to skip saving snapshots on exchange holidays
(when duplicate EOD dates would produce 0% forward returns).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

EST = ZoneInfo("America/New_York")


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """nth occurrence of weekday (0=Mon) in month."""
    d = date(year, month, 1)
    shift = (weekday - d.weekday()) % 7
    d = d + timedelta(days=shift + 7 * (n - 1))
    return d


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _observe_fixed_holiday(year: int, month: int, day: int) -> date:
    """
    NYSE weekend observation for fixed-date holidays.
    Sat -> Fri; Sun -> Mon; otherwise same day.
    """
    d = date(year, month, day)
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def nyse_full_holidays(year: int) -> set[date]:
    """NYSE full-day closures for a calendar year (observed dates)."""
    holidays: set[date] = set()

    holidays.add(_observe_fixed_holiday(year, 1, 1))   # New Year's
    holidays.add(_nth_weekday(year, 1, 0, 3))        # MLK — 3rd Mon Jan
    holidays.add(_nth_weekday(year, 2, 0, 3))        # Presidents — 3rd Mon Feb
    holidays.add(_easter_sunday(year) - timedelta(days=2))  # Good Friday
    holidays.add(_last_weekday(year, 5, 0))            # Memorial — last Mon May
    holidays.add(_observe_fixed_holiday(year, 6, 19))  # Juneteenth
    holidays.add(_observe_fixed_holiday(year, 7, 4))   # Independence Day
    holidays.add(_nth_weekday(year, 9, 0, 1))         # Labor — 1st Mon Sep
    holidays.add(_nth_weekday(year, 11, 3, 4))       # Thanksgiving — 4th Thu Nov
    holidays.add(_observe_fixed_holiday(year, 12, 25))  # Christmas

    return holidays


def is_nyse_holiday(d: date) -> bool:
    return d in nyse_full_holidays(d.year)


def is_us_equity_session_day(date_str: str | None = None) -> bool:
    """
    True when NYSE would have a regular full session (Mon–Fri, not exchange holiday).
    Uses America/New_York calendar date when date_str omitted.
    """
    if date_str:
        d = _parse_date(date_str)
        if d is None:
            return False
    else:
        d = datetime.now(EST).date()
    if d.weekday() >= 5:
        return False
    return not is_nyse_holiday(d)


def next_us_equity_session_day(from_date: date) -> date:
    """First session day on or after from_date."""
    d = from_date
    for _ in range(366):
        if is_us_equity_session_day(d.isoformat()):
            return d
        d += timedelta(days=1)
    return from_date


def latest_completed_session(now=None, close_hour: int = 16, close_minute: int = 15) -> date:
    """Most recent NYSE session whose close has passed (ET). Before 4:15pm ET → prior session."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    now = now or datetime.now(ZoneInfo("America/New_York"))
    d = now.date()
    if (now.hour, now.minute) < (close_hour, close_minute):
        d -= timedelta(days=1)
    while d.weekday() >= 5 or is_nyse_holiday(d):
        d -= timedelta(days=1)
    return d


def series_last_bar_stale(series, expected: date) -> bool:
    """True when a date-indexed price series ends before the expected session."""
    try:
        import pandas as pd

        return pd.Timestamp(series.index[-1]).date() < expected
    except Exception:
        return False

