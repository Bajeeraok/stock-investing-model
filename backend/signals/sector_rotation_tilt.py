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
