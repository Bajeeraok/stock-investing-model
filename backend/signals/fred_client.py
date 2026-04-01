"""
FRED (Federal Reserve Economic Data) client.
Free API key at https://fred.stlouisfed.org/docs/api/api_key.html
Fetches yields, inflation expectations, real yield proxy for macro regime.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger("signals.fred_client")

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Standard series IDs
SERIES_10Y = "DGS10"           # 10-Year Treasury Constant Maturity Rate (%)
SERIES_2Y = "DGS2"             # 2-Year Treasury (optional)
SERIES_INFLATION_EXP = "T10YIE" # 10-Year Breakeven Inflation Rate (%)
SERIES_FEDFUNDS = "FEDFUNDS"   # Federal Funds Effective Rate (monthly)
SERIES_CPI = "CPIAUCSL"        # CPI All Urban (monthly, index)
SERIES_UNRATE = "UNRATE"       # Unemployment Rate (monthly)
# ICE BofA US High Yield Option-Adjusted Spread (daily, %); stress often >500 bp historically
SERIES_HY_OAS = "BAMLH0A0HYM2"


def get_api_key(config: dict) -> str | None:
    return (config.get("data") or {}).get("fred_api_key") or config.get("fred_api_key") or None


def fetch_series_range(
    config: dict, series_id: str, start_date: str, end_date: str | None = None
) -> tuple[list[dict], str | None]:
    """
    Fetch historical observations for a FRED series.
    start_date, end_date: YYYY-MM-DD. end_date defaults to today.
    Returns (observations, error). observations: list of {date, value}, oldest first.
    """
    import datetime
    api_key = get_api_key(config)
    if not api_key:
        return [], "No FRED API key"
    if end_date is None:
        end_date = datetime.date.today().isoformat()
    url = (
        f"{FRED_BASE}?series_id={series_id}"
        f"&api_key={api_key}&file_type=json"
        f"&observation_start={start_date}&observation_end={end_date}"
        f"&sort_order=asc"
    )
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        logger.debug("FRED request failed: %s", e)
        return [], str(e)
    obs = data.get("observations") if isinstance(data, dict) else None
    if not isinstance(obs, list):
        return [], "Unexpected response"
    return obs, None


def fetch_series(config: dict, series_id: str, limit: int = 1) -> tuple[list[dict], str | None]:
    """
    Fetch latest observations for a FRED series.
    Returns (observations, error). observations: list of {date, value}.
    """
    api_key = get_api_key(config)
    if not api_key:
        return [], "No FRED API key"
    url = (
        f"{FRED_BASE}?series_id={series_id}"
        f"&api_key={api_key}&file_type=json&sort_order=desc&limit={limit}"
    )
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        logger.debug("FRED request failed: %s", e)
        return [], str(e)
    obs = data.get("observations") if isinstance(data, dict) else None
    if not isinstance(obs, list):
        return [], "Unexpected response"
    return obs, None


def get_unrate_mom_pct_change(config: dict) -> float | None:
    """
    Month-over-month % change in unemployment rate (latest vs prior FRED print).
    Positive = unemployment rising (typically risk-off).
    """
    obs, err = fetch_series(config, SERIES_UNRATE, limit=2)
    if err or not obs or len(obs) < 2:
        return None
    vals: list[float] = []
    for row in obs[:2]:
        raw = row.get("value")
        if raw is None or raw == ".":
            continue
        try:
            vals.append(float(raw))
        except (TypeError, ValueError):
            return None
    if len(vals) < 2 or vals[1] == 0:
        return None
    return (vals[0] - vals[1]) / abs(vals[1])


def get_latest_value(config: dict, series_id: str) -> float | None:
    """Return latest observation value as float, or None."""
    obs, err = fetch_series(config, series_id, limit=1)
    if err or not obs:
        return None
    raw = obs[0].get("value")
    if raw is None or raw == ".":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def get_10y_yield(config: dict) -> float | None:
    """10-Year Treasury yield (%). Uses FRED DGS10."""
    return get_latest_value(config, SERIES_10Y)


def get_inflation_expectations(config: dict) -> float | None:
    """10-Year breakeven inflation rate (%). Uses FRED T10YIE."""
    return get_latest_value(config, SERIES_INFLATION_EXP)


def get_real_yield_proxy(config: dict, nominal_10y: float | None = None) -> float | None:
    """
    Real yield proxy = 10Y nominal - 10Y inflation expectations (%).
    If nominal_10y not provided, fetches from FRED DGS10.
    """
    infl = get_inflation_expectations(config)
    if infl is None:
        return None
    nom = nominal_10y if nominal_10y is not None else get_10y_yield(config)
    if nom is None:
        return None
    return round(nom - infl, 2)


def get_fred_macro_snapshot(config: dict) -> dict[str, Any]:
    """
    Fetch a small macro snapshot from FRED for regime/guidelines.
    Returns dict with keys: 10y_yield, inflation_exp, real_yield_proxy, fed_funds (if available).
    """
    out = {}
    api_key = get_api_key(config)
    if not api_key:
        return out
    nom = get_10y_yield(config)
    if nom is not None:
        out["10y_yield"] = nom
    infl = get_inflation_expectations(config)
    if infl is not None:
        out["inflation_exp"] = infl
    if nom is not None and infl is not None:
        out["real_yield_proxy"] = round(nom - infl, 2)
    fed = get_latest_value(config, SERIES_FEDFUNDS)
    if fed is not None:
        out["fed_funds"] = fed
    return out
