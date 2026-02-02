"""
Placeholder clients for data sources – add API keys in config and implement.
See DATA_SOURCES.md for integration status.
"""

from __future__ import annotations


def get_tradingeconomics_calendar(config: dict, days: int = 7) -> tuple[list, str | None]:
    """TradingEconomics economic calendar. Placeholder – add api_key to config."""
    api_key = config.get("data", {}).get("tradingeconomics_api_key")
    if not api_key:
        return [], "No TradingEconomics API key (add data.tradingeconomics_api_key)"
    # TODO: implement https://tradingeconomics.com/api
    return [], "Not implemented yet"


def get_alpha_vantage_sentiment(config: dict, ticker: str) -> tuple[dict | None, str | None]:
    """Alpha Vantage news sentiment. Implemented in alpha_vantage_client."""
    from signals.alpha_vantage_client import get_alpha_vantage_sentiment as _fetch
    return _fetch(config, ticker)


def get_fred_series(config: dict, series_id: str) -> tuple[list | None, str | None]:
    """FRED (Federal Reserve) economic data. Placeholder – add api_key to config."""
    api_key = config.get("data", {}).get("fred_api_key")
    if not api_key:
        return None, "No FRED API key (free at fred.stlouisfed.org)"
    # TODO: implement FRED API – yields, inflation expectations, real rates
    return None, "Not implemented yet"


def get_cboe_gvz(config: dict) -> tuple[float | None, str | None]:
    """CBOE Gold Volatility Index (GVZ). Placeholder – options market expects big move."""
    # CBOE data may be available via yfinance (^GVZ) or paid API
    # TODO: fetch ^GVZ, compare to historical avg for "elevated" flag
    return None, "Not implemented yet"


def get_cftc_cot(config: dict, symbol: str = "gold") -> tuple[dict | None, str | None]:
    """CFTC Commitment of Traders – speculative vs commercial positioning. Implemented in cot_client."""
    from signals.cot_client import get_cftc_cot as _get_cftc_cot
    return _get_cftc_cot(config, symbol)


def get_etf_flows(config: dict, symbols: list[str] | None = None) -> tuple[list[dict] | None, str | None]:
    """
    ETF flows (SPY, QQQ, GLD, sector ETFs). Placeholder – add API key when you have a provider.
    Config: data.etf_flows_api_key (optional; some providers are paid).
    Returns (list of { symbol, flow_pct, flow_usd, ... }, error).
    """
    api_key = (config.get("data") or {}).get("etf_flows_api_key") or config.get("etf_flows_api_key")
    if not api_key or not str(api_key).strip():
        return None, "No ETF flows API key (add data.etf_flows_api_key for paid/systematic feeds)"
    # TODO: wire to provider (e.g. ETF issuers, Nasdaq Data Link, or alt-data) when key is set
    return None, "Not implemented yet (placeholder for ETF flows provider)"
