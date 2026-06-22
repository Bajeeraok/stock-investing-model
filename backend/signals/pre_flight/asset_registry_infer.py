"""
Infer AssetMeta from FMP / yfinance company profiles for tickers not in ASSET_REGISTRY.
Used by classify_asset() and scripts/scan_asset_registry.py.
"""

from __future__ import annotations

import re
from typing import Any

from .constants import AssetType
from .models import AssetMeta

# Known commodity / vol instruments (cohort + watchlist patterns)
COMMODITY_ETF_TICKERS = frozenset({
    "GLD", "SLV", "USO", "UNG", "CORN", "WEAT", "URA", "URNM", "COPX", "LIT", "REMX", "PALL", "PPLT",
    "GDX", "GDXJ", "XME", "DBA", "DBC",
})
VOLATILITY_ETF_TICKERS = frozenset({"UVXY", "VXX", "VIXY", "SVXY", "VIXM"})
EQUITY_ETF_TICKERS = frozenset({
    "SPY", "QQQ", "IWM", "DIA", "XLF", "XLK", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE",
    "XLC", "ARKK", "TQQQ", "SOXL", "HYG", "TLT", "OIH", "RSP",
})

DEFENSIVE_SECTORS = frozenset({
    "consumer defensive",
    "consumer staples",
    "utilities",
})
MACRO_SENSITIVE_SECTORS = frozenset({
    "financial services",
    "financials",
    "energy",
    "basic materials",
    "materials",
})
ADR_COUNTRIES = frozenset({
    "cn", "china",
    "tw", "taiwan",
    "nl", "netherlands",
    "dk", "denmark",
    "jp", "japan",
    "kr", "korea",
    "in", "india",
    "br", "brazil",
    "mx", "mexico",
    "il", "israel",
    "gb", "uk", "united kingdom",
    "de", "germany",
    "fr", "france",
    "ch", "switzerland",
    "sg", "singapore",
    "hk", "hong kong",
})
GEOPOLITICAL_ADR_COUNTRIES = frozenset({"cn", "china", "tw", "taiwan", "ru", "russia"})

_COMMODITY_NAME = re.compile(
    r"\b(gold|silver|oil|crude|gas|natural gas|corn|wheat|uranium|copper|lithium|commodity|metals)\b",
    re.I,
)
_VOL_NAME = re.compile(r"\b(vix|volatility|vol\s+index)\b", re.I)


def _norm_ticker(ticker: str) -> str:
    return (ticker or "").upper().strip().replace(".", "-")


def _norm_country(raw: str | None) -> str:
    return (raw or "US").strip().lower()


def _norm_sector(raw: str | None) -> str:
    s = (raw or "").strip()
    if not s:
        return "Unknown"
    low = s.lower()
    mapping = {
        "financial services": "Financials",
        "consumer cyclical": "Consumer Discretionary",
        "consumer defensive": "Consumer Staples",
        "communication services": "Communication Services",
        "healthcare": "Healthcare",
        "health care": "Healthcare",
    }
    return mapping.get(low, s.title())


def _float_val(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None  # NaN guard
    except (TypeError, ValueError):
        return None


def _is_etf(ticker: str, profile: dict[str, Any]) -> bool:
    sym = _norm_ticker(ticker)
    if sym in COMMODITY_ETF_TICKERS | VOLATILITY_ETF_TICKERS | EQUITY_ETF_TICKERS:
        return True
    if profile.get("isEtf") is True or profile.get("isFund") is True:
        return True
    name = str(profile.get("companyName") or profile.get("name") or "")
    if " ETF" in name.upper() or name.upper().endswith(" TRUST"):
        return True
    sector = str(profile.get("sector") or "").lower()
    return sector in ("etf", "exchange traded fund")


def _etf_asset_type(ticker: str, profile: dict[str, Any]) -> AssetType:
    sym = _norm_ticker(ticker)
    name = str(profile.get("companyName") or profile.get("name") or sym)
    if sym in VOLATILITY_ETF_TICKERS or sym.startswith("^VIX") or _VOL_NAME.search(name):
        return AssetType.ETF_VOLATILITY
    if sym in COMMODITY_ETF_TICKERS or _COMMODITY_NAME.search(name):
        return AssetType.ETF_COMMODITY
    return AssetType.ETF_EQUITY


def _is_adr(profile: dict[str, Any]) -> bool:
    if profile.get("isAdr") is True:
        return True
    country = _norm_country(profile.get("country"))
    if country in ("us", "usa", "united states", ""):
        return False
    exchange = str(profile.get("exchangeShortName") or profile.get("exchange") or "").upper()
    if country in ADR_COUNTRIES and exchange in ("NYSE", "NASDAQ", "AMEX", "NYSEARCA", "BATS"):
        return True
    return country in ADR_COUNTRIES


def _infer_equity_type(ticker: str, profile: dict[str, Any]) -> AssetType:
    beta = _float_val(profile.get("beta"))
    mkt_cap = _float_val(profile.get("mktCap") or profile.get("marketCap"))
    sector_low = str(profile.get("sector") or "").lower()

    if beta is not None and beta >= 1.85:
        return AssetType.EQUITY_SPECULATIVE
    if mkt_cap is not None and mkt_cap < 5e9 and beta is not None and beta >= 1.45:
        return AssetType.EQUITY_SPECULATIVE

    if sector_low in DEFENSIVE_SECTORS and beta is not None and beta <= 0.9:
        return AssetType.EQUITY_DEFENSIVE
    if sector_low in ("healthcare", "health care") and beta is not None and beta <= 0.75:
        return AssetType.EQUITY_DEFENSIVE

    return AssetType.EQUITY_US


def _macro_fields(sector: str, industry: str | None) -> tuple[bool, str | None]:
    sec = sector.lower()
    ind = (industry or "").lower()
    if sec in MACRO_SENSITIVE_SECTORS:
        if "bank" in ind or sec in ("financial services", "financials"):
            return True, "Interest rates, credit spreads"
        if sec in ("energy",):
            return True, "Oil prices (WTI/Brent), energy sector sentiment"
        if sec in ("basic materials", "materials"):
            return True, "Commodity prices, USD strength"
    return False, None


def _etf_meta(ticker: str, profile: dict[str, Any], asset_type: AssetType) -> AssetMeta:
    name = str(profile.get("companyName") or profile.get("name") or ticker)
    sector = _norm_sector(profile.get("sector")) if profile.get("sector") else f"{name.split()[0]} ETF"
    is_vol = asset_type == AssetType.ETF_VOLATILITY
    is_commodity = asset_type == AssetType.ETF_COMMODITY
    macro, driver = (True, "Macro drivers — see instrument prospectus") if is_commodity else (False, None)
    if is_vol:
        macro, driver = False, None
    return AssetMeta(
        ticker=_norm_ticker(ticker),
        name=name,
        asset_type=asset_type,
        sector=sector,
        insider_data_reliable=False,
        fundamentals_applicable=False,
        ml_applicable=not is_vol,
        macro_sensitive=macro,
        macro_driver=driver,
        insider_note="ETF — no insider activity applicable",
        fundamentals_note="ETF — use NAV / sector view, not EPS/PE",
        ml_note="ML trained on equities — output invalid for volatility instruments" if is_vol else None,
    )


def infer_asset_meta(ticker: str, profile: dict[str, Any]) -> AssetMeta | None:
    """Build AssetMeta from a normalized profile dict. Returns None if profile is empty."""
    sym = _norm_ticker(ticker)
    if not sym or sym.startswith("^"):
        # Index symbols — treat as vol/incompatible
        if "VIX" in sym:
            return AssetMeta(
                ticker=sym,
                name="CBOE Volatility Index",
                asset_type=AssetType.ETF_VOLATILITY,
                sector="Volatility Index",
                insider_data_reliable=False,
                fundamentals_applicable=False,
                ml_applicable=False,
                ml_note="Index symbol — not a tradable equity; use vol ETF proxies (VIXY/UVXY)",
            )
        return None

    if not profile:
        return None

    name = str(profile.get("companyName") or profile.get("name") or profile.get("shortName") or sym)
    sector = _norm_sector(profile.get("sector"))
    industry = (profile.get("industry") or profile.get("industryDisp") or "").strip() or None
    beta = _float_val(profile.get("beta"))
    country_raw = profile.get("country") or "US"
    country = str(country_raw).strip() or "US"

    if _is_etf(sym, profile):
        etf_type = _etf_asset_type(sym, profile)
        return _etf_meta(sym, profile, etf_type)

    if _is_adr(profile):
        country_norm = _norm_country(country_raw)
        geo = country_norm in GEOPOLITICAL_ADR_COUNTRIES
        insider_note = f"{country} ADR — insider disclosure may be limited"
        return AssetMeta(
            ticker=sym,
            name=name,
            asset_type=AssetType.EQUITY_ADR,
            sector=sector,
            country=country,
            beta=beta,
            insider_data_reliable=False,
            insider_note=insider_note,
            geopolitical_risk=geo,
        )

    asset_type = _infer_equity_type(sym, profile)
    macro, driver = _macro_fields(sector, industry)
    sentiment = asset_type == AssetType.EQUITY_SPECULATIVE

    insider_note = None
    if sym in ("BRK-B", "BRK.B"):
        insider_note = "Berkshire rarely trades own stock — insider signal structurally weak"

    return AssetMeta(
        ticker=sym,
        name=name,
        asset_type=asset_type,
        sector=sector,
        country=country,
        beta=beta,
        macro_sensitive=macro,
        macro_driver=driver,
        sentiment_amplified=sentiment,
        insider_data_reliable=insider_note is None,
        insider_note=insider_note,
    )


def fetch_profile_for_classification(ticker: str, config: dict | None = None) -> dict[str, Any] | None:
    """FMP profile first, yfinance info fallback."""
    sym = _norm_ticker(ticker)
    if not sym:
        return None

    cfg = config
    if cfg is None:
        try:
            from config_loader import load_config

            cfg = load_config()
        except Exception:
            cfg = {}

    api_key = None
    try:
        from signals.fmp_client import get_api_key

        api_key = get_api_key(cfg or {})
    except Exception:
        pass

    if api_key and cfg:
        try:
            from signals.fmp_client import fetch_profile

            profile, err = fetch_profile(cfg, sym)
            if not err and profile:
                return profile
        except Exception:
            pass

    try:
        import yfinance as yf

        info = (yf.Ticker(sym).info or {}) if yf else {}
        if info:
            return {
                "companyName": info.get("longName") or info.get("shortName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "beta": info.get("beta"),
                "mktCap": info.get("marketCap"),
                "country": info.get("country"),
                "exchangeShortName": info.get("exchange"),
                "isEtf": info.get("quoteType") == "ETF",
            }
    except Exception:
        pass

    return None


def infer_asset_meta_from_ticker(ticker: str, config: dict | None = None) -> AssetMeta | None:
    """Fetch profile and infer AssetMeta (network call)."""
    profile = fetch_profile_for_classification(ticker, config)
    if not profile and _norm_ticker(ticker).startswith("^"):
        return infer_asset_meta(ticker, {})
    if not profile:
        return None
    return infer_asset_meta(ticker, profile)
