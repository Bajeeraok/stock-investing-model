"""
Market scenarios (what-if): historical event reaction stats for upcoming events.
Uses 12–13y of history to compute typical next-day move around FOMC, CPI, etc.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# FOMC meeting dates (sample 2012–2024, 8 per year) for historical reaction stats.
# Source: Federal Reserve meeting calendar. Expand as needed.
FOMC_DATES = [
    "2012-01-25", "2012-03-13", "2012-04-25", "2012-06-20", "2012-08-01", "2012-09-13", "2012-10-24", "2012-12-12",
    "2013-01-30", "2013-03-20", "2013-05-01", "2013-06-19", "2013-07-31", "2013-09-18", "2013-10-30", "2013-12-18",
    "2014-01-29", "2014-03-19", "2014-04-30", "2014-06-18", "2014-07-30", "2014-09-17", "2014-10-29", "2014-12-17",
    "2015-01-28", "2015-03-18", "2015-04-29", "2015-06-17", "2015-07-29", "2015-09-17", "2015-10-28", "2015-12-16",
    "2016-01-27", "2016-03-16", "2016-04-27", "2016-06-15", "2016-07-27", "2016-09-21", "2016-11-02", "2016-12-14",
    "2017-02-01", "2017-03-15", "2017-05-03", "2017-06-14", "2017-07-26", "2017-09-20", "2017-11-01", "2017-12-13",
    "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13", "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19", "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    "2020-01-29", "2020-03-15", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
]

# Map calendar event name/keywords to event type for lookup
EVENT_TYPE_KEYWORDS = {
    "FOMC": ["fomc", "fed", "federal reserve", "interest rate", "monetary policy"],
    "CPI": ["cpi", "inflation", "consumer price"],
    "NFP": ["nfp", "non-farm", "employment", "jobs report"],
    "GDP": ["gdp", "gross domestic"],
}


def _classify_event(name: str) -> str | None:
    """Classify event by name into FOMC, CPI, NFP, GDP, or None."""
    if not name:
        return None
    n = name.lower()
    for event_type, keywords in EVENT_TYPE_KEYWORDS.items():
        if any(k in n for k in keywords):
            return event_type
    return None


def get_event_reaction_stats(
    event_type: str,
    symbol: str = "SPY",
    period: str = "13y",
) -> dict | None:
    """
    Compute historical next-day reaction stats for event_type (e.g. FOMC).
    Returns { avg_return_pct, std_pct, pct_positive, n_events, rationale } or None.
    """
    if event_type != "FOMC":
        # Only FOMC has built-in dates for now; CPI/NFP could be added via FRED or similar
        return None
    import numpy as np
    from signals.fetcher import fetch_ohlcv_safe
    import pandas as pd

    close = fetch_ohlcv_safe(symbol, period)
    if close is None or len(close) < 100:
        return None
    close = close.sort_index()
    idx = close.index

    returns_1d = []
    for d_str in FOMC_DATES:
        try:
            d_target = pd.Timestamp(d_str).date()
        except Exception:
            continue
        try:
            # Match by date; idx.date is array of dates for DatetimeIndex
            mask = np.array([(x.date() if hasattr(x, "date") else x) >= d_target for x in idx])
            on_or_after = idx[mask]
        except Exception:
            continue
        if len(on_or_after) == 0:
            continue
        event_day = on_or_after[0]
        try:
            event_close = float(close.loc[event_day])
        except Exception:
            continue
        # Next trading day
        later = idx[idx > event_day]
        if len(later) == 0:
            continue
        next_day = later[0]
        try:
            next_close = float(close.loc[next_day])
        except Exception:
            continue
        if event_close and event_close > 0:
            ret_pct = 100 * (next_close - event_close) / event_close
            returns_1d.append(ret_pct)
    if len(returns_1d) < 5:
        return None
    arr = np.array(returns_1d)
    avg = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    pct_pos = 100 * np.mean(arr > 0)
    return {
        "avg_return_pct": round(avg, 2),
        "std_pct": round(std, 2),
        "pct_positive": round(pct_pos, 1),
        "n_events": len(returns_1d),
        "rationale": f"Based on {len(returns_1d)} {event_type} events ({period}); SPY next-day avg {avg:+.2f}%, σ={std:.2f}%.",
    }


def get_upcoming_event_scenarios(
    calendar_events: list[dict],
    period_long: str = "13y",
    symbol: str = "SPY",
) -> list[dict]:
    """
    For each upcoming calendar event, attach historical reaction stats (if available).
    calendar_events: [{ date, name, event?, ... }] from economic calendar.
    Returns list of { date, name, event_type, scenario } where scenario has avg_return_pct, std_pct, pct_positive, n_events, rationale.
    """
    out = []
    seen = set()
    for ev in (calendar_events or [])[:20]:
        name = (ev.get("name") or ev.get("event") or "").strip()
        date_str = ev.get("date")
        if not name or not date_str:
            continue
        key = (date_str, name[:50])
        if key in seen:
            continue
        seen.add(key)
        event_type = _classify_event(name)
        scenario = None
        if event_type:
            scenario = get_event_reaction_stats(event_type, symbol=symbol, period=period_long)
        out.append({
            "date": date_str,
            "name": name,
            "event_type": event_type or "Other",
            "scenario": scenario,
        })
    return out
