"""
Load config merged with user overrides (additional tickers, uploaded portfolios).
Environment variables override config.yaml for API keys (use for Railway/deploy).
Local: config.yaml. Production: set FMP_API_KEY, FRED_API_KEY, etc. in env.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

# Env var -> config path. Env takes precedence over config.yaml.
_API_KEY_ENV_MAP = {
    "FMP_API_KEY": ("data", "fmp_api_key"),
    "FRED_API_KEY": ("data", "fred_api_key"),
    "TRADINGECONOMICS_API_KEY": ("data", "tradingeconomics_api_key"),
    "ALPHA_VANTAGE_API_KEY": ("data", "alpha_vantage_api_key"),
    "BENZINGA_API_KEY": ("data", "benzinga_api_key"),
    "ETF_FLOWS_API_KEY": ("data", "etf_flows_api_key"),
    "POLYGON_API_KEY": ("data", "polygon_api_key"),
    "FINNHUB_API_KEY": ("data", "finnhub_apikey"),
    "OPENAI_API_KEY": ("data", "openai_api_key"),
}

ROOT = Path(__file__).resolve().parent


def get_data_root() -> Path:
    """
    Data directory for EOD snapshots, last_run.json, etc.
    Set DATA_ROOT to a persistent path (e.g. mounted volume) so data survives restarts (Railway, Docker).
    """
    raw = os.environ.get("DATA_ROOT", "").strip()
    if raw:
        return Path(raw).resolve()
    return (ROOT / "data").resolve()


def _overrides_path() -> Path:
    return get_data_root() / "user_overrides.json"


def _load_overrides() -> dict:
    if not _overrides_path().exists():
        return {"additional_tickers": [], "uploaded_portfolios": {}}
    try:
        with open(_overrides_path()) as f:
            return json.load(f)
    except Exception:
        return {"additional_tickers": [], "uploaded_portfolios": {}}


def _save_overrides(data: dict) -> None:
    p = _overrides_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, indent=2)


def load_config(merge_overrides: bool = True) -> dict:
    """Load config.yaml, optionally merged with user overrides."""
    config_path = ROOT / "config" / "config.yaml"
    if not config_path.exists():
        config = {
            "watchlist": ["SPY", "QQQ", "GLD", "SLV", "AAPL", "MSFT"],
            "score": {"buy_min": 70, "sell_max": 30},
            "regime": {"up_min": 60, "down_max": 40},
            "data": {"period": "5y"},
        }
    else:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

    _overlay_env_api_keys(config)
    if not merge_overrides:
        return config

    overrides = _load_overrides()
    add_tickers = overrides.get("additional_tickers") or []
    uploaded = overrides.get("uploaded_portfolios") or {}

    # Merge watchlist
    base_watchlist = config.get("watchlist") or []
    merged_watchlist = list(dict.fromkeys([str(t).upper() for t in base_watchlist] + [str(t).upper() for t in add_tickers]))

    # Merge portfolios: config portfolios + uploaded
    config_portfolios = config.get("portfolios") or {}
    if isinstance(config_portfolios, dict):
        merged_portfolios = dict(config_portfolios)
    else:
        merged_portfolios = {}
    # Legacy "portfolio" (flat list) -> treat as "Default"
    legacy = config.get("portfolio")
    if isinstance(legacy, list) and legacy and "Default" not in merged_portfolios:
        merged_portfolios["Default"] = [h if isinstance(h, dict) else {"ticker": h, "quantity": 1} for h in legacy]
    for name, holdings in uploaded.items():
        if isinstance(holdings, list):
            merged_portfolios[name] = holdings

    config = dict(config)
    config["watchlist"] = merged_watchlist
    config["portfolios"] = merged_portfolios
    _overlay_env_api_keys(config)
    return config


def _overlay_env_api_keys(config: dict) -> None:
    """Override config API keys with env vars when set (Railway/deploy)."""
    for env_name, (section, key) in _API_KEY_ENV_MAP.items():
        val = os.getenv(env_name)
        if val and str(val).strip():
            if section not in config:
                config[section] = {}
            config[section][key] = val.strip()


def add_ticker(ticker: str) -> bool:
    """Add ticker to user overrides. Returns True if added."""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    data = _load_overrides()
    add = data.get("additional_tickers") or []
    if ticker in add:
        return False
    add.append(ticker)
    data["additional_tickers"] = add
    _save_overrides(data)
    return True


def remove_ticker(ticker: str) -> bool:
    """Remove ticker from user overrides."""
    ticker = ticker.strip().upper()
    data = _load_overrides()
    add = data.get("additional_tickers") or []
    if ticker not in add:
        return False
    data["additional_tickers"] = [t for t in add if t != ticker]
    _save_overrides(data)
    return True


def add_uploaded_portfolio(name: str, holdings: list[dict]) -> None:
    """Add or replace uploaded portfolio."""
    data = _load_overrides()
    data["uploaded_portfolios"] = data.get("uploaded_portfolios") or {}
    data["uploaded_portfolios"][name] = holdings
    _save_overrides(data)


def get_additional_tickers() -> list[str]:
    return _load_overrides().get("additional_tickers") or []
