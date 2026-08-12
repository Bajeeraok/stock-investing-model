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
    "ANTHROPIC_API_KEY": ("data", "anthropic_api_key"),
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
            "score": {"buy_min": 70, "sell_max": 30, "buy_min_by_ticker": {}},
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


def portfolio_tickers_from_config(config: dict) -> list[str]:
    """Unique tickers from all portfolios (config + uploaded), uppercase."""
    out: list[str] = []
    portfolios = config.get("portfolios") or {}
    if isinstance(portfolios, dict):
        for account_holdings in portfolios.values():
            if not isinstance(account_holdings, list):
                continue
            for h in account_holdings:
                t = h.get("ticker") if isinstance(h, dict) else h
                if t:
                    out.append(str(t).upper())
    legacy = config.get("portfolio") or []
    if isinstance(legacy, list):
        for h in legacy:
            t = h.get("ticker") if isinstance(h, dict) else h
            if t:
                out.append(str(t).upper())
    return list(dict.fromkeys(out))


def get_public_demo_universe(config: dict) -> list[str]:
    """
    Default tickers for signals when no user login / empty book.
    Used for guest demos and to ensure the app is useful before auth ships.
    """
    demo = config.get("public_demo_universe")
    if isinstance(demo, list) and demo:
        return list(dict.fromkeys(str(t).upper().strip() for t in demo if t))
    watchlist = [str(t).upper() for t in (config.get("watchlist") or []) if t]
    if watchlist:
        return watchlist
    return ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN"]


def has_config_portfolio(config: dict) -> bool:
    """True when config defines at least one holding (pre-auth portfolio source)."""
    return len(portfolio_tickers_from_config(config)) > 0


def get_dashboard_signal_universe(config: dict) -> list[str]:
    """Public demo + watchlist + portfolio — dashboard refresh (no audit cohort)."""
    demo = get_public_demo_universe(config)
    watchlist = [str(t).upper() for t in (config.get("watchlist") or []) if t]
    seen: set[str] = set()
    merged: list[str] = []
    for t in demo + watchlist + portfolio_tickers_from_config(config):
        if t and t not in seen:
            merged.append(t)
            seen.add(t)
    return merged or demo


def get_universe_meta(config: dict) -> dict:
    """API metadata for guest vs linked portfolio (auth will extend this)."""
    portfolio = portfolio_tickers_from_config(config)
    demo = get_public_demo_universe(config)
    guest = not has_config_portfolio(config)
    return {
        "guest_mode": guest,
        "has_config_portfolio": not guest,
        "public_demo_universe": demo,
        "portfolio_ticker_count": len(portfolio),
        "note": (
            "Signals use the public demo universe until you sign in and link a portfolio."
            if guest
            else "Signals combine your portfolio, watchlist, and public demo ETFs."
        ),
    }


def get_eod_signal_universe(config: dict) -> list[str]:
    """Daily EOD / audit run: dashboard universe + fixed audit cohort when enabled."""
    merged = get_dashboard_signal_universe(config)
    seen = set(merged)
    audit_cfg = config.get("signal_audit") or {}
    if audit_cfg.get("enabled") and audit_cfg.get("merge_into_signal_universe", True):
        for t in get_audit_cohort_tickers(config):
            if t not in seen:
                merged.append(t)
                seen.add(t)
    return merged


def get_signal_universe(config: dict) -> list[str]:
    """
    Tickers for daily EOD / run_daily (includes audit cohort when enabled).
    Dashboard refresh uses get_dashboard_signal_universe() instead.
    """
    return get_eod_signal_universe(config)


def _signal_audit_cohort_path(config: dict) -> Path:
    audit_cfg = config.get("signal_audit") or {}
    rel = str(audit_cfg.get("cohort_file") or "config/signal_audit_cohort.yaml").strip()
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / rel
    return path


def load_signal_audit_cohort(config: dict) -> dict:
    """Load cohort YAML: {cohort_tag, categories: {name: [tickers]}}."""
    path = _signal_audit_cohort_path(config)
    if not path.exists():
        return {"cohort_tag": "audit_100", "categories": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {"cohort_tag": "audit_100", "categories": {}}
        return data
    except Exception:
        return {"cohort_tag": "audit_100", "categories": {}}


def get_audit_cohort_tickers(config: dict) -> list[str]:
    """Fixed audit cohort tickers (uppercase, deduped). Empty when signal_audit disabled."""
    audit_cfg = config.get("signal_audit") or {}
    if not audit_cfg.get("enabled"):
        return []
    data = load_signal_audit_cohort(config)
    out: list[str] = []
    seen: set[str] = set()
    categories = data.get("categories") or {}
    if isinstance(categories, dict):
        for tickers in categories.values():
            if not isinstance(tickers, list):
                continue
            for t in tickers:
                sym = str(t).upper().strip()
                if sym and sym not in seen:
                    out.append(sym)
                    seen.add(sym)
    return out


def get_audit_cohort_meta(config: dict) -> dict[str, str]:
    """Map ticker -> category label for audit breakdown."""
    audit_cfg = config.get("signal_audit") or {}
    if not audit_cfg.get("enabled"):
        return {}
    data = load_signal_audit_cohort(config)
    meta: dict[str, str] = {}
    categories = data.get("categories") or {}
    if isinstance(categories, dict):
        for cat, tickers in categories.items():
            if not isinstance(tickers, list):
                continue
            for t in tickers:
                sym = str(t).upper().strip()
                if sym:
                    meta[sym] = str(cat)
    return meta


def get_audit_cohort_tag(config: dict) -> str:
    audit_cfg = config.get("signal_audit") or {}
    if not audit_cfg.get("enabled"):
        return ""
    data = load_signal_audit_cohort(config)
    return str(data.get("cohort_tag") or audit_cfg.get("cohort_tag") or "audit_100")


def get_forward_tracking_tickers(
    config: dict,
    watchlist: list[str] | None = None,
    portfolio_tickers: list[str] | None = None,
) -> list[str]:
    """
    Tickers for forward-tracking stats. Uses audit cohort when enabled (pilot),
    else watchlist + portfolio union.
    """
    audit_cfg = config.get("signal_audit") or {}
    if audit_cfg.get("enabled") and audit_cfg.get("use_cohort_for_forward_tracking", True):
        cohort = get_audit_cohort_tickers(config)
        if cohort:
            return cohort
    wl = [str(t).upper() for t in (watchlist or []) if t]
    pt = [str(t).upper() for t in (portfolio_tickers or []) if t]
    merged = list(dict.fromkeys(wl + pt))
    return merged or ["SPY", "QQQ"]
