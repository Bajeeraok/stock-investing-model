"""
Earnings season pulse — calendar density + recent beat/miss proxy from FMP.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

CACHE_KEY = "earnings:season_pulse"
TTL_SECONDS = 12 * 3600

# Mega-cap sample when watchlist is small — density proxy for "season heat"
_DENSITY_SAMPLE = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "UNH", "XOM",
    "LLY", "AVGO", "MA", "HD", "COST", "NFLX", "AMD", "CRM", "ORCL", "BAC",
)


def _fmp_api_key(config: dict | None) -> str | None:
    key = ((config or {}).get("data") or {}).get("fmp_api_key")
    return (key or "").strip() or None


def _fetch_json(url: str) -> Any:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "ThriveAlpha/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _calendar_counts(api_key: str, symbols: list[str], from_d: str, to_d: str) -> int:
    """Count distinct symbols with an earnings date in range (batched by symbol)."""
    count = 0
    for sym in symbols[:24]:
        try:
            url = (
                f"https://financialmodelingprep.com/api/v3/earning_calendar"
                f"?symbol={sym}&from={from_d}&to={to_d}&apikey={api_key}"
            )
            rows = _fetch_json(url)
            if isinstance(rows, list) and rows:
                count += 1
        except Exception:
            continue
    return count


def _beat_rate_proxy(api_key: str, symbols: list[str]) -> dict[str, Any] | None:
    """Recent surprises: epsActual vs epsEstimated for sample tickers."""
    beats = misses = 0
    for sym in symbols[:12]:
        try:
            url = f"https://financialmodelingprep.com/api/v3/earnings-surprises/{sym}?apikey={api_key}"
            rows = _fetch_json(url)
            if not isinstance(rows, list) or not rows:
                continue
            row = rows[0]
            act = row.get("actualEarningResult") or row.get("epsActual")
            est = row.get("estimatedEarning") or row.get("epsEstimated")
            if act is None or est is None:
                continue
            if float(act) >= float(est):
                beats += 1
            else:
                misses += 1
        except Exception:
            continue
    total = beats + misses
    if total < 3:
        return None
    pct = round(100 * beats / total, 0)
    return {
        "beat_pct": pct,
        "sample_n": total,
        "beats": beats,
        "misses": misses,
    }


def _phase_label(upcoming_count: int, recent_count: int) -> str:
    if upcoming_count >= 8:
        return "PEAK"
    if upcoming_count >= 4 or recent_count >= 6:
        return "ACTIVE"
    if upcoming_count >= 1:
        return "LATE"
    return "OFF-SEASON"


def get_earnings_season_pulse(config: dict | None = None) -> dict[str, Any]:
    from signals.cache import get_cached, set_cached

    cached = get_cached(CACHE_KEY)
    if isinstance(cached, dict) and cached.get("phase"):
        return cached

    api_key = _fmp_api_key(config)
    symbols = list(_DENSITY_SAMPLE)
    try:
        from config_loader import get_signal_universe

        uni = get_signal_universe(config or {})
        if uni:
            symbols = list(dict.fromkeys(list(uni) + list(_DENSITY_SAMPLE)))[:30]
    except Exception:
        pass

    today = date.today()
    from_next = today.isoformat()
    to_next = (today + timedelta(days=14)).isoformat()
    from_recent = (today - timedelta(days=14)).isoformat()
    to_recent = today.isoformat()

    upcoming_count = 0
    recent_count = 0
    beat_proxy = None

    if api_key:
        try:
            upcoming_count = _calendar_counts(api_key, symbols, from_next, to_next)
            recent_count = _calendar_counts(api_key, symbols, from_recent, to_recent)
            beat_proxy = _beat_rate_proxy(api_key, symbols)
        except Exception as e:
            logger.debug("earnings_season_pulse FMP: %s", e)

    phase = _phase_label(upcoming_count, recent_count)

    if beat_proxy and beat_proxy["beat_pct"] >= 65:
        mood = "POSITIVE"
        plain = (
            f"Earnings season {phase.lower()} — recent beat rate ~{beat_proxy['beat_pct']:.0f}% "
            "in sample; dips on in-line reports may be buyable if macro stable."
        )
    elif beat_proxy and beat_proxy["beat_pct"] <= 45:
        mood = "NEGATIVE"
        plain = (
            f"Earnings season {phase.lower()} — misses dominating (~{100 - beat_proxy['beat_pct']:.0f}% miss rate). "
            "Trim before reports; don't add into unknown prints."
        )
    elif phase == "PEAK":
        mood = "BUSY"
        plain = "Peak earnings window — reduce size into reports; wait for reaction before adding."
    elif phase == "OFF-SEASON":
        mood = "QUIET"
        plain = "Light earnings calendar — macro and tape matter more than single-stock prints."
    else:
        mood = "MIXED"
        plain = f"Earnings season {phase.lower()} — stock-specific reactions; follow trim-before-close on holdings."

    out = {
        "phase": phase,
        "mood": mood,
        "upcoming_reports_14d": upcoming_count,
        "recent_reports_14d": recent_count,
        "beat_rate": beat_proxy,
        "plain_english": plain,
        "data_note": "Density from watchlist + mega-cap sample; beat rate from latest FMP surprises.",
    }
    set_cached(CACHE_KEY, out, TTL_SECONDS)
    return out
