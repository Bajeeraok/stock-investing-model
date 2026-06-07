"""
Retail alerts chained to dashboard Refresh — same bands/gates as signals, one 15m pipeline.

- Action book (get_dashboard_signal_universe): fresh signal rows + synced horizon_levels.
- Audit cohort (100): price-only snapshots + cached bands from last EOD/sync (no full recompute).
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from scanner.engine import MarketSnapshot, ScanEngine
from scanner.horizon_levels import read_horizon_levels
from scanner.store import ScannerStore
from scanner.ticker_universe import ScanTier, TICKER_META

logger = logging.getLogger("scanner.dashboard_alerts")


def _alert_settings(config: dict) -> dict[str, Any]:
    a = (config or {}).get("alerts") or {}
    return {
        "enabled": a.get("evaluate_on_dashboard_refresh", True) is not False,
        "include_audit_cohort": a.get("include_audit_cohort_on_refresh", True) is not False,
    }


def _watchlist_set(config: dict) -> set[str]:
    from config_loader import portfolio_tickers_from_config

    wl = {str(t).upper() for t in (config.get("watchlist") or []) if t}
    for t in portfolio_tickers_from_config(config):
        wl.add(str(t).upper())
    return wl


def _macro_flag_from_results(results: list[dict]) -> str:
    for r in results or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("ticker") or "").upper() == "SPY":
            g = r.get("_global_market_regime")
            if g:
                gsu = str(g).upper()
                if "BEAR" in gsu or gsu == "DOWN":
                    return "RISK_OFF"
                if "BULL" in gsu or gsu == "UP":
                    return "RISK_ON"
    return "NEUTRAL"


def snapshot_from_signal_row(row: dict, *, watchlist: set[str], vix: float = 18.0) -> MarketSnapshot | None:
    """Build scanner snapshot from a dashboard signal row (fresh bands/gates on this ticker)."""
    ticker = str(row.get("ticker") or "").upper().strip()
    if not ticker or row.get("error"):
        return None
    try:
        price = float(row.get("close") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    meta = TICKER_META.get(ticker)
    try:
        chg = float(row.get("change_pct") or row.get("price_change_pct") or 0)
    except (TypeError, ValueError):
        chg = 0.0
    regime = str(row.get("regime") or "NEUTRAL").upper()
    try:
        score = float(row.get("composite_buy") or 50)
    except (TypeError, ValueError):
        score = 50.0
    er = row.get("earnings_days_until")
    try:
        er_days = int(er) if er is not None else None
    except (TypeError, ValueError):
        er_days = None
    atr_pct = 2.5
    try:
        atr = row.get("atr14") or row.get("atr_pct")
        if atr is not None and float(row.get("close") or price) > 0:
            atr_pct = float(atr) / float(price) * 100.0 if float(atr) < 50 else float(atr)
    except (TypeError, ValueError):
        pass
    ml = row.get("ml_short_prob")
    ml_short = None
    if ml is not None:
        try:
            pv = float(ml)
            ml_short = pv * 100.0 if pv <= 1.0 else pv
        except (TypeError, ValueError):
            pass
    return MarketSnapshot(
        symbol=ticker,
        price=price,
        price_change_pct=chg,
        regime=regime,
        regime_confidence=score,
        iv_rank=50.0,
        iv_percentile=50.0,
        call_put_flow_ratio=1.0,
        er_days_away=er_days,
        vix=float(vix),
        atr_pct=max(0.5, float(atr_pct)),
        support_level=round(price * 0.95, 2),
        kelly_base=0.05,
        in_watchlist=ticker in watchlist,
        scan_tier=meta.tier if meta else ScanTier.TIER1_CORE,
        sector=meta.sector if meta else "Unknown",
        ml_prob_short=ml_short,
    )


def snapshot_from_price_only(
    ticker: str,
    price: float,
    *,
    watchlist: set[str],
    vix: float = 18.0,
    regime: str = "NEUTRAL",
    regime_confidence: float = 50.0,
) -> MarketSnapshot | None:
    """Cohort-only path: cached bands in horizon_levels, live price for cross checks."""
    ticker = ticker.upper().strip()
    if not ticker or price <= 0:
        return None
    meta = TICKER_META.get(ticker)
    return MarketSnapshot(
        symbol=ticker,
        price=float(price),
        price_change_pct=0.0,
        regime=regime,
        regime_confidence=regime_confidence,
        iv_rank=50.0,
        iv_percentile=50.0,
        call_put_flow_ratio=1.0,
        er_days_away=None,
        vix=float(vix),
        atr_pct=2.5,
        support_level=round(price * 0.95, 2),
        kelly_base=0.05,
        in_watchlist=ticker in watchlist,
        scan_tier=meta.tier if meta else ScanTier.TIER1_CORE,
        sector=meta.sector if meta else "Unknown",
        ml_prob_short=None,
    )


def _cohort_only_with_bands(
    audit_tickers: set[str],
    dashboard_tickers: set[str],
    levels: dict[str, dict],
) -> list[str]:
    out: list[str] = []
    for t in sorted(audit_tickers):
        if t in dashboard_tickers:
            continue
        if t not in levels or not levels[t]:
            continue
        out.append(t)
    return out


def _fetch_prices_for_tickers(tickers: list[str], config: dict, existing: dict[str, float] | None) -> dict[str, float]:
    prices = dict(existing or {})
    missing = [t for t in tickers if t not in prices or not prices.get(t)]
    if not missing:
        return prices
    try:
        from signals.fmp_client import fetch_batch_quote, get_fmp_api_key

        if get_fmp_api_key(config):
            batch, err = fetch_batch_quote(config, missing)
            if batch and not err:
                for sym, row in batch.items():
                    p = row.get("price")
                    if p is not None:
                        try:
                            prices[str(sym).upper()] = float(p)
                        except (TypeError, ValueError):
                            pass
                return prices
    except Exception as e:
        logger.debug("cohort alert batch quote: %s", e)
    try:
        from signals.live_prices import fetch_yfinance_latest_prices

        yf = fetch_yfinance_latest_prices(missing)
        for k, v in (yf or {}).items():
            prices[str(k).upper()] = float(v)
    except Exception as e:
        logger.debug("cohort alert yfinance: %s", e)
    return prices


def run_retail_alerts_from_dashboard_refresh(
    results: list[dict],
    config: dict,
    data_root: Path,
    *,
    prices_by_ticker: dict[str, float] | None = None,
    vix: float | None = None,
) -> dict[str, Any]:
    """
    Evaluate retail alerts after horizon_levels sync on dashboard Refresh.
    Returns summary for logs / optional API payload.
    """
    settings = _alert_settings(config)
    if not settings["enabled"]:
        return {"skipped": True, "reason": "evaluate_on_dashboard_refresh disabled"}

    from config_loader import get_audit_cohort_tickers, get_dashboard_signal_universe

    data_root = Path(data_root)
    watchlist = _watchlist_set(config)
    dashboard_universe = {str(t).upper() for t in get_dashboard_signal_universe(config)}
    audit_universe: set[str] = set()
    if settings["include_audit_cohort"]:
        audit_universe = {str(t).upper() for t in get_audit_cohort_tickers(config)}

    rows_by_ticker: dict[str, dict] = {}
    for r in results or []:
        if isinstance(r, dict) and r.get("ticker") and not r.get("error"):
            rows_by_ticker[str(r["ticker"]).upper()] = r

    vix_level = float(vix) if vix is not None else 18.0
    for item in results or []:
        if isinstance(item, dict) and str(item.get("ticker") or "").upper() in ("VIX", "^VIX"):
            # not used for vix level from row typically
            pass
    macro_flag = _macro_flag_from_results(results)

    snaps: list[MarketSnapshot] = []
    for t in sorted(dashboard_universe):
        row = rows_by_ticker.get(t)
        if row:
            snap = snapshot_from_signal_row(row, watchlist=watchlist, vix=vix_level)
            if snap:
                snaps.append(snap)

    levels = read_horizon_levels(data_root)
    cohort_only = _cohort_only_with_bands(audit_universe, dashboard_universe, levels)
    price_map = _fetch_prices_for_tickers(
        cohort_only,
        config,
        {str(k).upper(): float(v) for k, v in (prices_by_ticker or {}).items()},
    )
    spy_row = rows_by_ticker.get("SPY")
    cohort_regime = str((spy_row or {}).get("regime") or "NEUTRAL")
    cohort_conf = float((spy_row or {}).get("composite_buy") or 50) if spy_row else 50.0
    for t in cohort_only:
        p = price_map.get(t)
        if p is None or p <= 0:
            continue
        snap = snapshot_from_price_only(
            t,
            p,
            watchlist=watchlist,
            vix=vix_level,
            regime=cohort_regime,
            regime_confidence=cohort_conf,
        )
        if snap:
            snaps.append(snap)

    if not snaps:
        return {"skipped": True, "reason": "no snapshots", "dashboard_tickers": len(dashboard_universe)}

    store = ScannerStore(data_root)
    appended = 0

    def on_alert(a) -> None:
        nonlocal appended
        if a.id in store.load_dismissed():
            return
        store.append_alert(a)
        appended += 1

    engine = ScanEngine()
    run = engine.run(
        snaps=snaps,
        macro_flag=macro_flag,
        watchlist=watchlist,
        on_alert=on_alert,
        data_root=data_root,
        enable_options_alerts=False,
    )

    now = datetime.now().isoformat()
    store.write_stats(
        {
            "as_of": now,
            "source": "dashboard_refresh",
            "universe_size": len(snaps),
            "dashboard_tickers": len(dashboard_universe),
            "cohort_price_only": len(cohort_only),
            "alerts_appended": appended,
            "last_scan_at": run.get("started_at") or now,
        }
    )

    summary = {
        "skipped": False,
        "as_of": now,
        "snapshots": len(snaps),
        "dashboard_tickers": len(dashboard_universe),
        "cohort_price_only_evaluated": sum(1 for s in snaps if s.symbol in cohort_only),
        "alerts_appended": appended,
        "alerts_generated": run.get("alerts_generated"),
        "alerts_surfaced": run.get("alerts_surfaced"),
    }
    logger.info("[dashboard] retail alerts after refresh: %s", summary)
    return summary
