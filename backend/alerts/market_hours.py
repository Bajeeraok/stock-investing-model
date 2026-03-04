from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketWindow:
    tz: ZoneInfo = ET
    start: time = time(9, 30)
    end: time = time(16, 0)


def is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def is_in_window(dt: datetime, w: MarketWindow) -> bool:
    t = dt.timetz().replace(tzinfo=None)
    return (t >= w.start) and (t < w.end)


def is_us_market_hours(now: datetime | None = None, window: MarketWindow | None = None) -> bool:
    w = window or MarketWindow()
    dt = (now or datetime.now(tz=w.tz)).astimezone(w.tz)
    return is_weekday(dt) and is_in_window(dt, w)


def next_market_open(now: datetime | None = None, window: MarketWindow | None = None) -> datetime:
    w = window or MarketWindow()
    dt = (now or datetime.now(tz=w.tz)).astimezone(w.tz)

    # If today is weekend, jump to Monday
    while not is_weekday(dt):
        dt = (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    open_dt = dt.replace(hour=w.start.hour, minute=w.start.minute, second=0, microsecond=0)
    close_dt = dt.replace(hour=w.end.hour, minute=w.end.minute, second=0, microsecond=0)

    if dt < open_dt:
        return open_dt
    if dt >= close_dt:
        # Next weekday open
        nd = (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        while not is_weekday(nd):
            nd = nd + timedelta(days=1)
        return nd.replace(hour=w.start.hour, minute=w.start.minute, second=0, microsecond=0)
    return dt


def seconds_until_next_scan(
    *,
    scan_interval_seconds: int,
    now: datetime | None = None,
    window: MarketWindow | None = None,
    weekdays_only: bool = True,
    market_hours_only: bool = True,
) -> int:
    w = window or MarketWindow()
    dt = (now or datetime.now(tz=w.tz)).astimezone(w.tz)

    if market_hours_only and not is_in_window(dt, w):
        target = next_market_open(dt, w)
        return max(5, int((target - dt).total_seconds()))

    if weekdays_only and not is_weekday(dt):
        target = next_market_open(dt, w)
        return max(5, int((target - dt).total_seconds()))

    # Align to interval boundary
    epoch = int(dt.timestamp())
    next_epoch = ((epoch // scan_interval_seconds) + 1) * scan_interval_seconds
    return max(5, next_epoch - epoch)

