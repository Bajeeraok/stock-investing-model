"""
Named historical stress tests — apply beta-adjusted shocks from past events.

Events: 2008 GFC, 2020 COVID, 2022 rate hike, 2000 dot-com.
Per-holding impact based on sector beta proxies.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Historical peak-to-trough drawdowns for SPY in each crisis
NAMED_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "2022 rate hike",
        "spy_drawdown_pct": -25.4,
        "sector_multipliers": {
            "Technology": 1.35, "Communication Services": 1.30,
            "Consumer Discretionary": 1.25, "Real Estate": 1.20,
            "Health Care": 0.80, "Consumer Staples": 0.65,
            "Utilities": 0.60, "Energy": 0.40,
            "Financials": 1.00, "Industrials": 0.95, "Materials": 0.90,
        },
    },
    {
        "name": "COVID Mar 2020",
        "spy_drawdown_pct": -33.9,
        "sector_multipliers": {
            "Technology": 0.85, "Communication Services": 0.90,
            "Consumer Discretionary": 1.20, "Real Estate": 1.10,
            "Health Care": 0.75, "Consumer Staples": 0.70,
            "Utilities": 0.80, "Energy": 1.80,
            "Financials": 1.30, "Industrials": 1.15, "Materials": 1.10,
        },
    },
    {
        "name": "Dot-com 2000",
        "spy_drawdown_pct": -49.1,
        "sector_multipliers": {
            "Technology": 1.60, "Communication Services": 1.50,
            "Consumer Discretionary": 1.10, "Real Estate": 0.70,
            "Health Care": 0.65, "Consumer Staples": 0.50,
            "Utilities": 0.45, "Energy": 0.60,
            "Financials": 0.90, "Industrials": 0.85, "Materials": 0.80,
        },
    },
    {
        "name": "GFC 2008",
        "spy_drawdown_pct": -56.8,
        "sector_multipliers": {
            "Technology": 1.10, "Communication Services": 1.00,
            "Consumer Discretionary": 1.30, "Real Estate": 1.50,
            "Health Care": 0.70, "Consumer Staples": 0.55,
            "Utilities": 0.65, "Energy": 1.20,
            "Financials": 1.60, "Industrials": 1.15, "Materials": 1.20,
        },
    },
]

# Ticker-to-sector mapping for ETFs and common names
_ETF_SECTOR_MAP = {
    "SPY": "Index", "QQQ": "Technology", "IWM": "Index",
    "GLD": "Commodities", "SLV": "Commodities", "OIH": "Energy",
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Health Care", "XLP": "Consumer Staples",
}

_COMMODITY_MULTIPLIERS = {
    "2022 rate hike": 0.30, "COVID Mar 2020": -0.40,
    "Dot-com 2000": 0.20, "GFC 2008": 0.10,
}

_INDEX_MULTIPLIERS = {
    "2022 rate hike": 1.00, "COVID Mar 2020": 1.00,
    "Dot-com 2000": 1.00, "GFC 2008": 1.00,
}


def compute_stress_tests(
    per_holding: list[dict],
    total_value: float,
    sector_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """
    Run named historical stress tests on the portfolio.

    Returns list of {name, portfolio_impact_pct, per_holding: [{ticker, impact_pct, impact_dollars}]}
    """
    if not per_holding or total_value <= 0:
        return []

    sector_map = sector_map or {}

    # Resolve sector for each holding
    holding_sectors: dict[str, str] = {}
    for h in per_holding:
        t = h.get("ticker", "")
        if t in _ETF_SECTOR_MAP:
            holding_sectors[t] = _ETF_SECTOR_MAP[t]
        elif t in sector_map:
            holding_sectors[t] = sector_map[t]
        else:
            try:
                from signals.providers import get_sector_and_industry
                info = get_sector_and_industry(t)
                if info and info.get("sector"):
                    holding_sectors[t] = info["sector"]
                    sector_map[t] = info["sector"]
            except Exception:
                pass

    results: list[dict] = []
    for scenario in NAMED_SCENARIOS:
        name = scenario["name"]
        spy_dd = scenario["spy_drawdown_pct"]
        sector_mults = scenario["sector_multipliers"]

        portfolio_impact = 0.0
        per_h: list[dict] = []

        for h in per_holding:
            t = h.get("ticker", "")
            val = h.get("value") or 0
            if val <= 0:
                continue

            sector = holding_sectors.get(t, "Unknown")
            if sector == "Commodities":
                mult = _COMMODITY_MULTIPLIERS.get(name, 0.5)
            elif sector == "Index":
                mult = _INDEX_MULTIPLIERS.get(name, 1.0)
            else:
                mult = sector_mults.get(sector, 1.0)

            impact_pct = round(spy_dd * mult, 1)
            impact_dollars = round(val * impact_pct / 100, 0)
            portfolio_impact += impact_dollars

            per_h.append({
                "ticker": t,
                "sector": sector,
                "impact_pct": impact_pct,
                "impact_dollars": impact_dollars,
            })

        portfolio_impact_pct = round(portfolio_impact / total_value * 100, 1) if total_value > 0 else 0

        results.append({
            "name": name,
            "spy_drawdown_pct": spy_dd,
            "portfolio_impact_pct": portfolio_impact_pct,
            "portfolio_impact_dollars": round(portfolio_impact, 0),
            "per_holding": sorted(per_h, key=lambda x: x["impact_dollars"]),
            "survivors": [p["ticker"] for p in per_h if abs(p["impact_pct"]) < abs(spy_dd) * 0.6],
        })

    return results
