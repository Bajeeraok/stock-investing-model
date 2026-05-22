"""
Ticker metadata: spin-off / re-listing dates, sector fallbacks, industry→GICS routing.

Used when FMP/yfinance omit sector or when price history needs listing context.
"""
from __future__ import annotations

from datetime import date
from typing import Any

# GICS-style sector title → SPDR ETF
SECTOR_ETF_MAP: dict[str, str] = {
    "technology": "XLK",
    "financial services": "XLF",
    "financials": "XLF",
    "healthcare": "XLV",
    "health care": "XLV",
    "consumer cyclical": "XLY",
    "consumer discretionary": "XLY",
    "consumer defensive": "XLP",
    "consumer staples": "XLP",
    "communication services": "XLC",
    "communications": "XLC",
    "telecommunications": "XLC",
    "energy": "XLE",
    "industrials": "XLI",
    "basic materials": "XLB",
    "materials": "XLB",
    "real estate": "XLRE",
    "utilities": "XLU",
    "semiconductors": "XLK",
    "equity energy": "XLE",
}

# Standard display titles (Title Case)
SECTOR_DISPLAY: dict[str, str] = {
    "technology": "Technology",
    "financial services": "Financials",
    "financials": "Financials",
    "healthcare": "Healthcare",
    "health care": "Healthcare",
    "consumer cyclical": "Consumer Cyclical",
    "consumer discretionary": "Consumer Discretionary",
    "consumer defensive": "Consumer Defensive",
    "consumer staples": "Consumer Staples",
    "communication services": "Communication Services",
    "communications": "Communication Services",
    "telecommunications": "Communication Services",
    "energy": "Energy",
    "industrials": "Industrials",
    "basic materials": "Basic Materials",
    "materials": "Materials",
    "real estate": "Real Estate",
    "utilities": "Utilities",
    "semiconductors": "Technology",
}

# Industry keywords → sector (lowercase substring match)
INDUSTRY_SECTOR_HINTS: list[tuple[str, str]] = [
    ("semiconductor", "Technology"),
    ("computer hardware", "Technology"),
    ("software", "Technology"),
    ("internet content", "Communication Services"),
    ("internet retail", "Consumer Cyclical"),
    ("biotechnology", "Healthcare"),
    ("drug manufacturers", "Healthcare"),
    ("banks", "Financials"),
    ("insurance", "Financials"),
    ("asset management", "Financials"),
    ("capital markets", "Financials"),
    ("oil & gas", "Energy"),
    ("oil and gas", "Energy"),
    ("aerospace", "Industrials"),
    ("railroads", "Industrials"),
    ("discount stores", "Consumer Defensive"),
    ("beverages", "Consumer Defensive"),
    ("reit", "Real Estate"),
    ("real estate", "Real Estate"),
    ("gold", "Basic Materials"),
    ("copper", "Basic Materials"),
    ("steel", "Basic Materials"),
    ("utilities", "Utilities"),
    ("telecom", "Communication Services"),
    ("wireless", "Communication Services"),
]

# Per-ticker overrides when vendors disagree or omit fields
TICKER_SECTOR_FALLBACK: dict[str, dict[str, str]] = {
    "SNDK": {"sector": "Technology", "industry": "Computer Hardware"},
    "WDC": {"sector": "Technology", "industry": "Computer Hardware"},
    "AVGO": {"sector": "Technology", "industry": "Semiconductors"},
    "MU": {"sector": "Technology", "industry": "Semiconductors"},
    "AMAT": {"sector": "Technology", "industry": "Semiconductors"},
    "LRCX": {"sector": "Technology", "industry": "Semiconductors"},
    "KLAC": {"sector": "Technology", "industry": "Semiconductors"},
    "MRVL": {"sector": "Technology", "industry": "Semiconductors"},
    "QCOM": {"sector": "Technology", "industry": "Semiconductors"},
    "TXN": {"sector": "Technology", "industry": "Semiconductors"},
    "INTC": {"sector": "Technology", "industry": "Semiconductors"},
    "AMD": {"sector": "Technology", "industry": "Semiconductors"},
    "NVDA": {"sector": "Technology", "industry": "Semiconductors"},
    "BLK": {"sector": "Financials", "industry": "Asset Management"},
    "BRK-B": {"sector": "Financials", "industry": "Insurance"},
    "BRK.B": {"sector": "Financials", "industry": "Insurance"},
    "SPY": {"sector": "Market", "industry": "S&P 500 Index ETF"},
    "QQQ": {"sector": "Technology", "industry": "Nasdaq 100 Index ETF"},
    "IWM": {"sector": "Small Caps", "industry": "Russell 2000 Index ETF"},
    "GLD": {"sector": "Commodities", "industry": "Gold ETF"},
    "SLV": {"sector": "Commodities", "industry": "Silver ETF"},
}

# Spin-offs / re-listings: trim history before this date when vendor stitches old tickers
LISTING_EVENTS: dict[str, dict[str, Any]] = {
    "SNDK": {
        "listing_date": "2025-02-24",
        "event": "spin_off",
        "parent": "WDC",
        "note": "SanDisk re-listed after WDC spin-off (Feb 2025); ignore pre-2025 history if vendor merges old SNDK.",
    },
}


def normalize_sector_key(raw: str | None) -> str:
    return (raw or "").strip().lower().replace("_", " ")


def sector_from_industry(industry: str | None) -> str | None:
    ind = (industry or "").strip().lower()
    if not ind:
        return None
    for needle, sector in INDUSTRY_SECTOR_HINTS:
        if needle in ind:
            return sector
    return None


def resolve_equity_sector(
    ticker: str,
    *,
    sector: str | None = None,
    industry: str | None = None,
) -> dict[str, str | None]:
    """
    Returns normalized {sector, industry, sector_etf, sector_etf_name}.
    """
    sym = (ticker or "").upper().split("-")[0].replace(".", "-")
    fb = TICKER_SECTOR_FALLBACK.get(sym) or TICKER_SECTOR_FALLBACK.get(sym.replace("-", "."))
    sec_raw = normalize_sector_key(sector)
    ind = (industry or "").strip() or None

    if fb:
        sec_title = fb.get("sector") or "Unknown"
        ind = ind or fb.get("industry")
    elif not sec_raw or sec_raw in ("unknown", "n/a", ""):
        inferred = sector_from_industry(ind)
        sec_title = inferred or "Unknown"
    else:
        sec_title = SECTOR_DISPLAY.get(sec_raw, sec_raw.replace("-", " ").title())

    if sec_title in ("Market", "Commodities", "Small Caps"):
        etf = {"Market": "SPY", "Commodities": "GLD", "Small Caps": "IWM"}.get(sec_title, "SPY")
    else:
        etf = SECTOR_ETF_MAP.get(normalize_sector_key(sec_title), "SPY")

    etf_name = f"{etf} ({sec_title})" if sec_title not in ("Market", "Commodities", "Small Caps") else f"{etf} ({sec_title})"
    return {
        "sector": sec_title,
        "industry": ind,
        "sector_etf": etf,
        "sector_etf_name": etf_name,
    }


def get_listing_event(ticker: str) -> dict[str, Any] | None:
    sym = (ticker or "").upper().split("-")[0]
    return LISTING_EVENTS.get(sym)


def listing_cutoff_date(ticker: str) -> date | None:
    ev = get_listing_event(ticker)
    if not ev or not ev.get("listing_date"):
        return None
    try:
        return date.fromisoformat(str(ev["listing_date"])[:10])
    except ValueError:
        return None
