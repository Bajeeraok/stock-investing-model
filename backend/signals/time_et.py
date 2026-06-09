"""
Eastern Time (America/New_York) for app timestamps.

All stored/API-facing timestamps use ET — not UTC. Vendor payloads may arrive in UTC;
parse with parse_iso_to_et() and store or compare in ET.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    return datetime.now(ET)


def today_est() -> str:
    """Calendar date in Eastern (YYYY-MM-DD) — EOD filenames, audit dates."""
    return now_et().strftime("%Y-%m-%d")


def now_iso_et() -> str:
    """ISO-8601 with offset, e.g. 2026-06-08T22:56:30-04:00."""
    return now_et().isoformat(timespec="seconds")


def format_et_display(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Human-readable ET time; suffix ET/EST/EDT from tz name."""
    dt = now_et()
    tz = dt.tzname() or "ET"
    label = tz if tz in ("EST", "EDT") else "ET"
    return f"{dt.strftime(fmt)} {label}"


def format_et_compact() -> str:
    """Filename-safe stamp: 20260608T225630-0400."""
    dt = now_et()
    return dt.strftime("%Y%m%dT%H%M%S") + dt.strftime("%z")


def parse_iso_to_et(iso: str) -> datetime:
    """Parse ISO string (Z or offset) and return ET-aware datetime."""
    s = str(iso).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(ET)
