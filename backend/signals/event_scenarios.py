"""
Market scenarios (what-if): historical event reaction stats for upcoming events.
Uses 12–13y of history to compute typical next-day move around FOMC, CPI, NFP, etc.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# FOMC meeting dates (sample 2012–2024, 8 per year) for historical reaction stats.
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

EVENT_TYPE_KEYWORDS = {
    "FOMC": ["fomc", "fed", "federal reserve", "interest rate", "monetary policy"],
    "CPI": ["cpi", "inflation", "consumer price"],
    "NFP": ["nfp", "non-farm", "employment", "jobs report"],
    "GDP": ["gdp", "gross domestic"],
}


def _classify_event(name: str) -> str | None:
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
    Historical reaction stats for FOMC, CPI, NFP (and GDP when dated).
    Prefers precomputed market_flip_stats.json; falls back to live computation.
    """
    et = (event_type or "").upper()
    if et not in ("FOMC", "CPI", "NFP", "GDP"):
        return None

    try:
        from signals.market_flip_stats import load_market_flip_stats, stats_for_event_type

        cached = load_market_flip_stats()
        pre = stats_for_event_type(et, cached)
        if pre and pre.get("n_events", 0) >= 5:
            return {
                "avg_return_pct": pre.get("avg_return_pct"),
                "avg_same_day_pct": pre.get("avg_same_day_pct"),
                "std_pct": pre.get("std_pct"),
                "pct_positive": pre.get("pct_positive"),
                "n_events": pre.get("n_events"),
                "pct_gap_fade": pre.get("pct_gap_fade"),
                "gap_fade": pre.get("gap_fade"),
                "rationale": pre.get("rationale"),
            }
    except Exception as e:
        logger.debug("get_event_reaction_stats cache: %s", e)

    try:
        from signals.market_flip_stats import compute_event_day_stats, event_dates_for_type, _fetch_ohlc_frame

        dates = event_dates_for_type(et)
        if not dates:
            return None
        spy = _fetch_ohlc_frame(symbol, period)
        stats = compute_event_day_stats(et, dates, spy)
        if not stats:
            return None
        return {
            "avg_return_pct": stats.get("avg_return_pct"),
            "avg_same_day_pct": stats.get("avg_same_day_pct"),
            "std_pct": stats.get("std_pct"),
            "pct_positive": stats.get("pct_positive"),
            "n_events": stats.get("n_events"),
            "pct_gap_fade": stats.get("pct_gap_fade"),
            "gap_fade": stats.get("gap_fade"),
            "rationale": stats.get("rationale"),
        }
    except Exception as e:
        logger.debug("get_event_reaction_stats compute: %s", e)
        return None


def get_upcoming_event_scenarios(
    calendar_events: list[dict],
    period_long: str = "13y",
    symbol: str = "SPY",
) -> list[dict]:
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
