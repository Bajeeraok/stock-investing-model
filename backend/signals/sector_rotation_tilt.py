"""
Sector rotation tilt — leading/lagging sector ETFs vs SPY with rotate toward/away copy.
"""
from __future__ import annotations

from typing import Any

from signals.breadth_rs import _rs_ratio, _rs_trend, compute_rs_and_trend
from signals.fetcher import fetch_ohlcv_safe

_SECTOR_ETFS: tuple[tuple[str, str], ...] = (
    ("XLK", "Technology"),
    ("XLF", "Financials"),
    ("XLE", "Energy"),
    ("XLI", "Industrials"),
    ("XLV", "Health Care"),
    ("XLY", "Consumer Discretionary"),
    ("XLP", "Consumer Staples"),
    ("XLU", "Utilities"),
)


_RS_CACHE: dict[str, Any] = {}
_RS_CACHE_DATE: str | None = None


def sector_relative_strength(sector_etf: str | None, period: str = "6mo") -> dict[str, Any] | None:
    """Per-ticker sector RS vs SPY: the ticker's own sector ETF's RS ratio and
    its fast/slow trend — the sector-level composite feature that previously
    only existed at market level (build_sector_rotation_tilt).

    Returns {etf, rs_vs_spy, trend, ret_20d_pct} or None. Per-UTC-day cached —
    one Yahoo pull per sector ETF per day across the whole EOD batch.
    """
    from datetime import datetime, timezone

    etf = str(sector_etf or "").upper()
    if not etf or etf == "SPY":
        return None
    global _RS_CACHE_DATE
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _RS_CACHE_DATE != today:
        _RS_CACHE.clear()
        _RS_CACHE_DATE = today
    if etf in _RS_CACHE:
        return _RS_CACHE[etf]

    out = None
    try:
        spy = fetch_ohlcv_safe("SPY", period)
        series = fetch_ohlcv_safe(etf, period)
        ratio = _rs_ratio(series, spy) if series is not None and spy is not None else None
        if ratio is not None and len(ratio):
            ret_20d = None
            if series is not None and len(series) > 21:
                ret_20d = round(100.0 * (float(series.iloc[-1]) / float(series.iloc[-21]) - 1.0), 2)
            out = {
                "etf": etf,
                "rs_vs_spy": round(float(ratio.iloc[-1]), 4),
                "trend": _rs_trend(ratio),
                "ret_20d_pct": ret_20d,
            }
    except Exception:
        out = None
    _RS_CACHE[etf] = out
    return out


def build_sector_rotation_tilt(period: str = "6mo") -> dict[str, Any]:
    rs_base = compute_rs_and_trend(period=period)
    spy = fetch_ohlcv_safe("SPY", period)
    sectors: list[dict[str, Any]] = []

    for etf, name in _SECTOR_ETFS:
        series = fetch_ohlcv_safe(etf, period)
        ratio = _rs_ratio(series, spy) if series is not None and spy is not None else None
        trend = _rs_trend(ratio) if ratio is not None else "Flat"
        rs_val = round(float(ratio.iloc[-1]), 4) if ratio is not None and len(ratio) else None
        sectors.append({"etf": etf, "name": name, "trend": trend, "rs_vs_spy": rs_val})

    leading = [s for s in sectors if s["trend"] == "Rising"]
    lagging = [s for s in sectors if s["trend"] == "Falling"]
    leading.sort(key=lambda x: x.get("rs_vs_spy") or 0, reverse=True)
    lagging.sort(key=lambda x: x.get("rs_vs_spy") or 0)

    rotate_toward = [s["name"] for s in leading[:2]]
    rotate_away = [s["name"] for s in lagging[:2]]

    tech_lead = rs_base.get("trend_xlk") or "Flat"
    breadth = rs_base.get("trend_rsp") or "Flat"

    if rotate_toward and rotate_away:
        plain = (
            f"Leading: {', '.join(rotate_toward)}. Lagging: {', '.join(rotate_away)}. "
            "Tilt new adds toward leaders; avoid chasing laggards unless mean-reversion thesis."
        )
    elif rotate_toward:
        plain = f"Rotation favors {', '.join(rotate_toward)} — align new buys with strength."
    elif rotate_away:
        plain = f"Weakness in {', '.join(rotate_away)} — don't add there without a catalyst."
    else:
        plain = "Sector trends mixed — stock selection over sector beta."

    return {
        "sectors": sectors,
        "leading": leading[:3],
        "lagging": lagging[:3],
        "rotate_toward": rotate_toward,
        "rotate_away": rotate_away,
        "tech_leadership": tech_lead,
        "breadth_proxy_trend": breadth,
        "plain_english": plain,
    }
