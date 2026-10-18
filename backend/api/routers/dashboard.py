"""
Dashboard API - exposes all model features as JSON.

Performance (2026-05):
  - GET /api/dashboard/shell — instant read from Redis (never runs full compute on navigation)
  - GET /api/dashboard?refresh=true — manual full recompute (Refresh button)
  - Stale-while-revalidate: serves dashboard:last snapshot + background job on cache miss
  - GET /api/dashboard/status — poll while background refresh runs

Lazy-loaded on frontend (tab open):
  - Signals: GET /api/dashboard/signals-panel
  - Opportunities + doctor adds: GET /api/dashboard/opportunities-bundle (when opportunities_bundle_enabled)
  - Analysis (paper, insider, forward tracking, validation): GET /api/dashboard/analysis-bundle
  - Pre-market: PreMarketPanel → GET /api/pre-market (Markets tab)
  - Accuracy / Backtest: on mount in Analysis tab
"""
from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile, WebSocket

# Circuit breaker: after a 402 on FMP batch-quote, skip retries for 2 hours.
# Resets on process restart or when the 2-hour window expires.
_fmp_batch_quote_disabled_until: float = 0.0  # monotonic timestamp
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

logger = logging.getLogger("api.dashboard")

ROOT = Path(__file__).resolve().parent.parent.parent
sys_path = list(__import__("sys").path)
if str(ROOT) not in sys_path:
    __import__("sys").path.insert(0, str(ROOT))

import yaml
from behavior.thesis import load_theses, get_nudge
from behavior.what_changed import what_changed
from opportunity.scanner import run_opportunity_scan
from portfolio.doctor import portfolio_report, allocation_recommendations
from portfolio.performance import compute_performance_vs_benchmark
from config_loader import (
    add_ticker as _add_ticker,
    add_uploaded_portfolio,
    get_dashboard_signal_universe,
    get_data_root,
    get_forward_tracking_tickers,
    get_risk_profile,
    get_signal_universe,
    get_universe_meta,
    load_config,
    remove_ticker as _remove_ticker,
    set_risk_profile,
)
from scripts.run_daily import (
    load_last_run,
    run_eod_snapshot_only,
    run_signals,
    save_last_run,
    maybe_save_eod_from_last_run,
)
from scripts.accuracy_price_targets import run_accuracy_and_save
from signals.cross_asset import (
    run_crypto_signals,
    run_cross_asset_daily,
    compute_cross_asset_guidelines,
    normalize_vix_close_price,
)
from signals.breadth_rs import get_market_regime, apply_rotation_step_down
from signals.typical_move import typical_move_for_symbols
from signals.next_day_bias import next_day_outlook_for_symbols, run_next_day_backtest
from signals.premarket import run_premarket_snapshot
from signals.indicator_validation import validate_indicators_vs_external
from signals.indicator_comparison import run_indicator_comparison
from signals.forward_tracking import get_forward_tracking
from signals.model_health import build_model_health
from signals.fmp_client import (
    fetch_batch_quote,
    fetch_economic_calendar,
    fetch_treasury_rates,
    get_10y_rate,
    get_api_key as get_fmp_api_key,
    run_fmp_plan_check,
)
from signals.fred_client import get_real_yield_proxy
from signals.cot_client import get_cot_extremes_for_guidelines
from signals.fetcher import fetch_yfinance_latest_prices, fetch_ohlcv_safe
from signals.providers import MAJOR_INDEX_ETFS
from signals.confidence_engine import run_confidence
from signals.event_scenarios import get_upcoming_event_scenarios
from signals.macro_analog import get_macro_analog
from signals.market_forecast_brief import build_market_forecast_brief

try:
    from signals.tier1_api_bridge import generate_tier1_payload
    from signals.tier1_risk_engine import RiskTolerance
except ImportError:
    generate_tier1_payload = None
    RiskTolerance = None


def _forward_tracking_params(config: dict) -> dict[str, int]:
    ft = (config.get("forward_tracking") or {}) if isinstance(config, dict) else {}
    return {
        "max_pairs_per_horizon": int(ft.get("max_pairs_per_horizon", 60)),
        "max_records": int(ft.get("max_records_response", 2000)),
    }


# Kept identical to allocation_recommendations()'s max_position_pct table
# (backend/portfolio/doctor.py) so the Tier1 fallback's concentration cap agrees with
# the primary portfolio-doctor engine instead of an independent hardcoded number.
_TIER1_MAX_POSITION_PCT_BY_PROFILE = {"conservative": 15, "moderate": 20, "aggressive": 25}


def _tier1_lightweight_fallback(
    report: dict,
    results: list[dict],
    *,
    portfolio_value: float,
    risk_profile: str = "moderate",
) -> dict[str, Any]:
    """
    Portfolio-only risk payload when Tier 1 yfinance path fails or is unavailable.
    Ensures Risk Management tab is not empty when holdings exist.
    """
    max_position_pct = _TIER1_MAX_POSITION_PCT_BY_PROFILE.get(risk_profile, 20)
    per_holding = [h for h in (report.get("per_holding") or []) if isinstance(h, dict) and h.get("ticker")]
    if not per_holding or portfolio_value <= 0:
        return {}

    results_by_ticker = {r["ticker"]: r for r in results if isinstance(r, dict) and r.get("ticker") and not r.get("error")}

    position_sizing: list[dict] = []
    drawdown_sim: list[dict] = []
    earnings_impacts: list[dict] = []
    import re as _re

    for h in per_holding:
        ticker = str(h["ticker"]).upper()
        value = float(h.get("value") or 0)
        if value <= 0:
            continue
        sig = results_by_ticker.get(ticker) or {}
        rs = sig.get("risk_sizing") or {}
        price = float(sig.get("close") or h.get("price") or 0)
        stop_pct = float(rs.get("stop_pct") or 10)
        stop_price = round(price * (1 - stop_pct / 100), 2) if price > 0 else None
        position_sizing.append({
            "ticker": ticker,
            "recommended_dollars": rs.get("size_dollars") or round(portfolio_value * 0.01, 0),
            "recommended_shares": rs.get("shares") or (max(1, int(value / price)) if price > 0 else 0),
            "max_position_dollars": round(portfolio_value * max_position_pct / 100, 0),
            "current_pct": round(100 * value / portfolio_value, 1),
            "target_pct": min(10.0, round(100 * value / portfolio_value, 1)),
            "risk_per_trade_dollars": rs.get("risk_budget_dollars") or round(portfolio_value * 0.01, 0),
            "stop_loss_price": stop_price,
            "take_profit_price": round(price * 1.08, 2) if price > 0 else None,
            "kelly_fraction": 0.0,
            "adjusted_fraction": 0.0,
            "sizing_rationale": "Config-based risk sizing (1% risk preset) — full Tier 1 engine unavailable.",
            "warning": None,
        })
        drawdown_sim.append({
            "ticker": ticker,
            "current_price": price,
            "position_value": round(value, 0),
            "scenarios": [
                {
                    "label": "-10%",
                    "price_target": round(price * 0.90, 2) if price > 0 else 0,
                    "pct_change": -10.0,
                    "portfolio_impact_dollars": round(-value * 0.10, 0),
                    "portfolio_impact_pct": round(-10 * value / portfolio_value, 2),
                    "probability": 0.35,
                    "description": "Moderate pullback scenario (estimated).",
                },
                {
                    "label": "-20%",
                    "price_target": round(price * 0.80, 2) if price > 0 else 0,
                    "pct_change": -20.0,
                    "portfolio_impact_dollars": round(-value * 0.20, 0),
                    "portfolio_impact_pct": round(-20 * value / portfolio_value, 2),
                    "probability": 0.15,
                    "description": "Stress scenario (estimated).",
                },
            ],
            "max_loss_dollars": round(value * 0.25, 0),
            "max_loss_pct": round(-25 * value / portfolio_value / 100, 3),
            "breakeven_price": float(h.get("cost_basis") or price or 0),
            "atr_14": round(price * 0.02, 2) if price > 0 else 0,
            "historical_max_drawdown_pct": -20.0,
        })
        note = sig.get("earnings_note") or ""
        m = _re.search(r"Earnings in (\d+) days", note)
        if m:
            days = int(m.group(1))
            earnings_impacts.append({
                "ticker": ticker,
                "next_earnings_date": "",
                "days_to_earnings": days,
                "expected_move_pct": 6.0,
                "historical_avg_move": 5.0,
                "beat_rate_pct": 50.0,
                "position_recommendation": "TRIM" if days <= 2 else "REDUCE" if days <= 7 else "WATCH",
                "suggested_action": "Trim 15–20% before close prior day" if days <= 2 else "Reduce size into report",
                "iv_percentile": 50.0,
                "last_4_quarters": [],
                "risk_rating": "HIGH" if days <= 3 else "MEDIUM" if days <= 14 else "LOW",
            })

    weights = [float(h.get("value") or 0) / portfolio_value for h in per_holding if float(h.get("value") or 0) > 0]
    hhi = sum(w * w for w in weights) if weights else 0.0
    top3_pct = sum(sorted(weights, reverse=True)[:3]) * 100 if weights else 0.0
    holdings_out = [
        {"ticker": str(h["ticker"]).upper(), "value": float(h.get("value") or 0), "sector": h.get("sector")}
        for h in per_holding if float(h.get("value") or 0) > 0
    ]
    recs: list[str] = []
    if top3_pct > 50:
        recs.append(f"Top 3 holdings = {top3_pct:.0f}% — consider trimming largest if thesis weakens.")
    if hhi > 0.18:
        recs.append("Portfolio is concentrated — add a diversifier or rebalance.")

    concentration = {
        "holdings": holdings_out,
        "effective_positions": max(1, int(round(1 / hhi))) if hhi > 0 else len(holdings_out),
        "herfindahl_index": round(hhi, 4),
        "correlation_alerts": [],
        "sector_weights": {},
        "top_risk_contributors": [h["ticker"] for h in sorted(holdings_out, key=lambda x: x["value"], reverse=True)[:3]],
        "diversification_score": max(0, min(100, round(100 * (1 - hhi)))),
        "recommendations": recs,
        "is_concentrated": top3_pct > 50 or hhi > 0.20,
    }

    return {
        "position_sizing": position_sizing,
        "drawdown_sim": drawdown_sim,
        "exit_levels": [],
        "exit_levels_by_horizon": {"short": [], "medium": [], "long": []},
        "earnings_impacts": earnings_impacts,
        "concentration": concentration,
        "tier1_fallback": True,
    }


router = APIRouter()

# Retail copy: data / methodology limits (override via config known_limits: list)
DEFAULT_KNOWN_LIMITS = [
    "Price targets and bands are model output, not guarantees.",
    "Backtests can reflect survivorship bias unless universe membership is configured.",
    "FMP fundamentals and analyst estimates often lag filings; not full point-in-time.",
    "No live options flow or dark-pool data — options layers are approximations where shown.",
    "Macro (FRED) and Yahoo prices are delayed vs premium real-time feeds.",
]


def _load_config():
    return load_config()


def _build_signal_scores(results: list[Any] | None) -> list[dict]:
    """Light rows for Overview chart when full `signals` is omitted from HTTP."""
    out: list[dict] = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        out.append({
            "ticker": r.get("ticker"),
            "composite_buy": r.get("composite_buy"),
            "regime": r.get("regime"),
            "error": r.get("error"),
        })
    return out


def _build_tactical_breakouts(results: list[Any] | None, config: dict) -> list[dict]:
    try:
        from signals.velocity_engine import build_tactical_breakouts_from_results

        return build_tactical_breakouts_from_results(results or [], config=config, limit=8)
    except Exception:
        return []


def _build_event_risk_strip(results: list[Any] | None, config: dict) -> dict:
    try:
        from config_loader import portfolio_tickers_from_config
        from signals.event_risk_strip import build_event_risk_strip

        return build_event_risk_strip(
            results or [],
            config,
            watchlist_tickers=[str(t).upper() for t in (config.get("watchlist") or []) if t],
            portfolio_tickers=portfolio_tickers_from_config(config),
        )
    except Exception as e:
        logger.debug("event_risk_strip build failed: %s", e)
        return {"rows": [], "message": str(e), "rank_note": None}


def _build_hunter_panel_payload(
    results: list[Any] | None,
    config: dict,
    *,
    signal_universe: list[str],
    as_of: str | None,
) -> dict:
    try:
        from config_loader import portfolio_tickers_from_config
        from signals.hunter_panel import build_hunter_panel

        return build_hunter_panel(
            results or [],
            portfolio_tickers=portfolio_tickers_from_config(config),
            watchlist_tickers=[str(t).upper() for t in (config.get("watchlist") or []) if t],
            signal_universe=signal_universe,
            as_of=as_of,
        )
    except Exception as e:
        logger.debug("hunter_panel build failed: %s", e)
        return {"candidate_count": 0, "candidates": [], "message": str(e)}


def _opportunities_bundle_enabled(config: dict) -> bool:
    """When false: skip lazy opportunity scan; Portfolio Doctor add ideas disabled."""
    v = config.get("opportunities_bundle_enabled", True)
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "no", "off")
    return bool(v)


def _empty_opportunities_bundle(*, enabled: bool = False) -> dict:
    return {
        "enabled": enabled,
        "opportunities": [],
        "portfolio_doctor_recommendations": {},
    }


def _is_dashboard_warming() -> bool:
    """True when first/full compute is running and no Redis dashboard payload exists yet."""
    from api.dashboard_job import is_refresh_running
    from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot

    if get_cached_dashboard() or get_last_dashboard_snapshot():
        return False
    return is_refresh_running()


def _doctor_recommendations_for_portfolios(
    config: dict,
    portfolios_out: dict,
    results: list,
    opportunities: list,
    confidence_by_ticker: dict,
) -> dict:
    doctor_cfg = dict(config.get("portfolio_doctor") or {})
    doctor_cfg["model_rules"] = config.get("model_rules") or {}
    doctor_cfg["cash_deploy_min_score"] = config.get("cash_deploy_min_score", 70)
    # User-persisted risk profile overrides the static config default — same value the
    # Tier1 Kelly engine (generate_tier1_payload) and its fallback are resolved from.
    doctor_cfg["risk_appetite"] = get_risk_profile(config)
    out: dict = {}
    for pname, rep in portfolios_out.items():
        try:
            out[pname] = allocation_recommendations(
                report=rep,
                results=results,
                opportunities=opportunities,
                doctor_cfg=doctor_cfg,
                confidence_by_ticker=confidence_by_ticker,
            )
        except Exception as e:
            logger.debug("portfolio_doctor %s: %s", pname, e)
    return out


def _holdings_from_config(config: dict) -> list:
    """Same holdings list as main dashboard (multi-account + fallback)."""
    holdings: list = []
    portfolios = config.get("portfolios", {})
    if portfolios and isinstance(portfolios, dict):
        for account_name, account_holdings in portfolios.items():
            if isinstance(account_holdings, list):
                for h in account_holdings:
                    entry = dict(h) if isinstance(h, dict) else {"ticker": h, "quantity": 1}
                    entry["account"] = account_name
                    holdings.append(entry)
    if not holdings:
        portfolio = config.get("portfolio", [])
        if isinstance(portfolio, list) and portfolio and isinstance(portfolio[0], dict):
            holdings = portfolio
        else:
            holdings = [{"ticker": t, "quantity": 1} for t in config.get("watchlist", [])]
    return holdings


def compute_opportunities_bundle() -> dict | None:
    """
    Run opportunity scan + Portfolio Doctor adds using the last cached dashboard (signals + portfolios).
    Called from GET /api/dashboard/opportunities-bundle (lazy load, Option A).
    """
    config = _load_config()
    if not _opportunities_bundle_enabled(config):
        return _empty_opportunities_bundle(enabled=False)

    try:
        from signals.cache import get_cached_dashboard

        cached = get_cached_dashboard()
        if not cached or not isinstance(cached.get("signals"), list):
            return None
    except Exception as e:
        logger.debug("opportunities-bundle: cache read failed: %s", e)
        return None

    results = list(cached["signals"])
    portfolios_out = cached.get("portfolios")
    if not isinstance(portfolios_out, dict) or not portfolios_out:
        return None

    holdings = _holdings_from_config(config)
    portfolio_tickers = [h.get("ticker") if isinstance(h, dict) else h for h in holdings]

    opp_cfg = config.get("opportunity_criteria", {}) or {}
    universe = config.get("opportunity_universe") or []
    t0 = time.perf_counter()
    try:
        opportunities = run_opportunity_scan(
            universe=universe if universe else None,
            period=config.get("data", {}).get("period", "5y"),
            min_score=opp_cfg.get("min_score", 80),
            require_regime_up=opp_cfg.get("require_regime_up", True),
            min_rsi=opp_cfg.get("min_rsi", 50),
            max_rsi=opp_cfg.get("max_rsi", 70),
            require_price_above_ma200=True,
            min_macd_hist=opp_cfg.get("min_macd_hist", 0),
            up_min=config.get("regime", {}).get("up_min", 60),
            down_max=config.get("regime", {}).get("down_max", 40),
            exclude_from_watchlist=portfolio_tickers,
            max_results=opp_cfg.get("max_results", 25),
            min_volume_ratio=opp_cfg.get("min_volume_ratio", 0.5),
            exclude_earnings_days=opp_cfg.get("exclude_earnings_days"),
            config=config,
        )
    except Exception as e:
        logger.warning("opportunities-bundle scan: %s", e)
        opportunities = []

    logger.info(
        "[opportunities-bundle] scan DONE (%d opps, %.0f ms)",
        len(opportunities),
        (time.perf_counter() - t0) * 1000,
    )

    confidence_by_ticker: dict = {}
    for r in results:
        if not isinstance(r, dict) or r.get("error") or not r.get("ticker"):
            continue
        pc = r.get("plan_confidence")
        pa = r.get("plan_action")
        if pc is not None:
            try:
                confidence_by_ticker[r["ticker"]] = {"confidence": float(pc), "action": pa}
            except (TypeError, ValueError):
                pass

    portfolio_tickers_set = {h.get("ticker") if isinstance(h, dict) else h for h in holdings}
    add_candidate_tickers = list(
        dict.fromkeys(
            [o.get("ticker") for o in opportunities if o.get("ticker") and o.get("ticker") not in portfolio_tickers_set]
        )
    )
    t0c = time.perf_counter()
    for ticker in add_candidate_tickers:
        if ticker in confidence_by_ticker:
            continue
        try:
            conf = run_confidence(ticker, config=config)
            if conf.get("confidence") is not None:
                confidence_by_ticker[ticker] = conf
        except Exception as e:
            logger.debug("opportunities-bundle confidence %s: %s", ticker, e)
    if add_candidate_tickers:
        logger.info(
            "[opportunities-bundle] add-candidate confidence (%.0f ms)",
            (time.perf_counter() - t0c) * 1000,
        )

    portfolio_doctor_recommendations = _doctor_recommendations_for_portfolios(
        config, portfolios_out, results, opportunities, confidence_by_ticker
    )

    return {
        "enabled": True,
        "opportunities": opportunities,
        "portfolio_doctor_recommendations": portfolio_doctor_recommendations,
    }


def _eod_snapshot_signal_rows(snap: dict | None) -> list[dict]:
    """EOD JSON uses run_results; older paths may use signals/results."""
    if not isinstance(snap, dict):
        return []
    for key in ("signals", "results", "run_results"):
        rows = snap.get(key)
        if isinstance(rows, list) and rows:
            return [r for r in rows if isinstance(r, dict) and r.get("ticker")]
    return []


def _min_full_eod_rows(config: dict) -> int:
    """Minimum row count for a full 8pm EOD cohort (~100 tickers), not dashboard refresh (~43)."""
    try:
        from config_loader import get_eod_signal_universe

        eod_n = len(get_eod_signal_universe(config))
        return max(50, int(eod_n * 0.75))
    except Exception:
        return 75


def _is_thin_eod_snapshot(snap: dict | None, min_full: int) -> bool:
    """True when snapshot is a dashboard-only refresh, not the full EOD universe."""
    if not isinstance(snap, dict):
        return True
    meta = snap.get("metadata") or {}
    if meta.get("dashboard_only"):
        return True
    if str(snap.get("universe") or "").lower() == "dashboard":
        return True
    rows = _eod_snapshot_signal_rows(snap)
    tc = snap.get("tickers_count")
    count = int(tc) if tc is not None else len(rows)
    return count < min_full


def _snap_as_of(snap: dict, fallback: str | None = None) -> str | None:
    return snap.get("run_date") or snap.get("snapshot_date") or fallback


_EOD_SNAPSHOT_SCAN_LIMIT = 14


def _pick_best_eod_snapshot(
    config: dict,
    *,
    date: str = "latest",
    allow_thin: bool = False,
) -> tuple[list[dict], str | None, str]:
    """
    Pick the richest EOD snapshot for the universe panel.
    Skips thin dashboard-only files (e.g. Sunday Refresh) when a fuller snapshot exists.
    """
    import json as _json
    from pathlib import Path

    min_full = _min_full_eod_rows(config)

    if date != "latest":
        eod_dir = Path(get_data_root()) / "eod"
        candidate = eod_dir / f"{date}.json"
        if candidate.exists():
            try:
                raw = _json.loads(candidate.read_text(encoding="utf-8"))
                rows = _eod_snapshot_signal_rows(raw)
                if rows:
                    return rows, _snap_as_of(raw, date), f"eod_disk:{candidate.name}"
            except Exception:
                pass
        try:
            from signals.cache import get_eod_snapshot_redis

            snap = get_eod_snapshot_redis(date)
            rows = _eod_snapshot_signal_rows(snap)
            if rows:
                return rows, _snap_as_of(snap, date), f"eod_redis:{date}"
        except Exception:
            pass
        return [], None, "none"

    best_rows: list[dict] = []
    best_as_of: str | None = None
    best_source = "none"
    thin_best: tuple[list[dict], str | None, str] = ([], None, "none")

    def _consider(snap: dict | None, source: str, date_hint: str | None = None) -> None:
        nonlocal best_rows, best_as_of, best_source, thin_best
        if not isinstance(snap, dict):
            return
        rows = _eod_snapshot_signal_rows(snap)
        if not rows:
            return
        as_of = _snap_as_of(snap, date_hint)
        if _is_thin_eod_snapshot(snap, min_full):
            if len(rows) > len(thin_best[0]):
                thin_best = (rows, as_of, source)
            return
        if len(rows) > len(best_rows):
            best_rows = rows
            best_as_of = as_of
            best_source = source

    try:
        from signals.cache import get_eod_snapshot_redis, list_eod_dates_redis

        # Newest first; stop at the first full (non-thin) hit so we don't pull
        # every historical multi‑MB blob (Redis socket timeouts on Railway).
        for d in sorted(list_eod_dates_redis() or [], reverse=True)[:_EOD_SNAPSHOT_SCAN_LIMIT]:
            _consider(get_eod_snapshot_redis(d), f"eod_redis:{d}", d)
            if best_rows:
                break
    except Exception as e:
        logger.debug("[eod-pick] redis scan: %s", e)

    if not best_rows:
        try:
            eod_dir = Path(get_data_root()) / "eod"
            if eod_dir.exists():
                for path in sorted(eod_dir.glob("*.json"), reverse=True)[:_EOD_SNAPSHOT_SCAN_LIMIT]:
                    try:
                        raw = _json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    _consider(raw, f"eod_disk:{path.name}", path.stem)
                    if best_rows:
                        break
        except Exception as e:
            logger.debug("[eod-pick] disk scan: %s", e)

    if best_rows:
        return best_rows, best_as_of, best_source
    if allow_thin and thin_best[0]:
        return thin_best
    return [], None, "none"


def _resolve_universe_cache_rows(config: dict, dashboard_results: list[dict]) -> tuple[list[dict], str]:
    """
    Universe panel (~100 tickers) should come from the EOD snapshot when available.
    Dashboard refresh only runs get_dashboard_signal_universe() (~43 tickers).
    """
    best_rows: list[dict] = list(dashboard_results or [])
    best_source = "dashboard"

    eod_rows, _, eod_source = _pick_best_eod_snapshot(config, allow_thin=False)
    if len(eod_rows) > len(best_rows):
        best_rows = eod_rows
        best_source = eod_source

    return best_rows, best_source


def _forward_tracking_staleness_days(bundle: dict | None) -> float | None:
    """Days between a bundle's forward_tracking.meta.eod_date_last and the live EOD index's
    newest known date. None when either side is unavailable (can't judge staleness).

    Exists because compute_analysis_bundle's three cache-hit tiers below only ever checked
    *presence*, not *freshness* — any one of them succeeding (which, once the dashboard's own
    cache is warm, is always) permanently short-circuits before ever reaching the heavy
    recompute section, including when that heavy section is what's calling this very function
    (see the force-bypass this enables). Confirmed live: forward_tracking sat 8 weeks behind
    the live EOD snapshot index (stuck 2026-08-02 vs. actual 2026-09-25) because of exactly
    this — the "dashboard cache hit" tier kept re-validating and re-caching the same baked-in
    stale value from api.dashboard_shell.build_analysis_bundle(), which does no recomputation
    at all (it only lifts whatever forward_tracking key the cached dashboard blob already has —
    itself a deferred-only field the regular 2h dashboard warm cycle never refreshes).
    """
    if not isinstance(bundle, dict):
        return None
    ft = bundle.get("forward_tracking")
    last = (ft or {}).get("meta", {}).get("eod_date_last") if isinstance(ft, dict) else None
    if not last:
        return None
    try:
        from datetime import date

        from signals.cache import build_eod_snapshot_index

        snaps = build_eod_snapshot_index()
        live_latest = snaps[0]["date"] if snaps else None
        if not live_latest:
            return None
        d_last = date.fromisoformat(str(last)[:10])
        d_live = date.fromisoformat(str(live_latest)[:10])
        return (d_live - d_last).days
    except Exception:
        return None


# Beyond this, a cached bundle is treated as stale enough to self-heal in the background —
# generous over a normal weekend/holiday gap (2-3 days) so it only fires on real staleness.
_FORWARD_TRACKING_STALE_DAYS = 5


def compute_analysis_bundle(*, allow_heavy: bool = True, force: bool = False) -> dict | None:
    """
    Lazy Analysis tab: insider, forward tracking, paper trading summary, model validation, etc.
    Uses cached dashboard signals; merges results back into Redis when computed.

    When allow_heavy=False (HTTP fast path), only returns data already in Redis — never runs
    the multi-minute paper-trading backfill synchronously.

    force=True skips all three cache-hit tiers below and goes straight to the heavy compute —
    used by the background job specifically so a *deliberate* refresh request can't be silently
    swallowed by its own cache the way _ensure_analysis_background_compute()'s trigger always
    used to be (see _forward_tracking_staleness_days's docstring for the trap this closes).
    """
    try:
        from signals.cache import (
            assemble_analysis_slices,
            get_analysis_bundle,
            get_cached_dashboard,
            get_last_dashboard_snapshot,
            merge_dashboard_cache_updates,
            set_analysis_bundle,
        )
        from api.dashboard_shell import build_analysis_bundle, empty_analysis_bundle

        cached = get_cached_dashboard() or get_last_dashboard_snapshot()

        if not force:
            # Fast path — dedicated Redis keys (never deserialize the full dashboard blob).
            assembled = assemble_analysis_slices()
            if assembled:
                assembled = _patch_stale_paper_trading(assembled)
                stale_days = _forward_tracking_staleness_days(assembled)
                logger.info("[analysis-bundle] slice cache hit (assembled)%s",
                            f" — STALE {stale_days}d, triggering background refresh" if (stale_days or 0) > _FORWARD_TRACKING_STALE_DAYS else "")
                if (stale_days or 0) > _FORWARD_TRACKING_STALE_DAYS:
                    _ensure_analysis_background_compute()
                return assembled

            dedicated = get_analysis_bundle()
            if dedicated:
                dedicated = _patch_stale_paper_trading(dedicated)
                stale_days = _forward_tracking_staleness_days(dedicated)
                logger.info("[analysis-bundle] dedicated cache hit%s",
                            f" — STALE {stale_days}d, triggering background refresh" if (stale_days or 0) > _FORWARD_TRACKING_STALE_DAYS else "")
                if (stale_days or 0) > _FORWARD_TRACKING_STALE_DAYS:
                    _ensure_analysis_background_compute()
                return dedicated

            if not cached or not isinstance(cached.get("signals"), list):
                return None

            refresh_ts = cached.get("refresh_ts") if isinstance(cached, dict) else None
            dedicated = get_analysis_bundle(refresh_ts=refresh_ts)
            if dedicated:
                dedicated = _patch_stale_paper_trading(dedicated)
                stale_days = _forward_tracking_staleness_days(dedicated)
                logger.info("[analysis-bundle] dedicated cache hit (refresh_ts match)%s",
                            f" — STALE {stale_days}d, triggering background refresh" if (stale_days or 0) > _FORWARD_TRACKING_STALE_DAYS else "")
                if (stale_days or 0) > _FORWARD_TRACKING_STALE_DAYS:
                    _ensure_analysis_background_compute()
                return dedicated

            if cached.get("analysis_deferred") is False:
                partial = build_analysis_bundle(cached)
                pt = partial.get("paper_trading") if isinstance(partial.get("paper_trading"), dict) else {}
                recent = pt.get("recent") if isinstance(pt.get("recent"), list) else []
                if (
                    pt.get("summary") is not None
                    and partial.get("forward_tracking") is not None
                    and len(recent) > 0
                ):
                    stale_days = _forward_tracking_staleness_days(partial)
                    is_stale = (stale_days or 0) > _FORWARD_TRACKING_STALE_DAYS
                    logger.info("[analysis-bundle] dashboard cache hit%s",
                                f" — STALE {stale_days}d, will NOT re-cache; triggering background refresh" if is_stale else "")
                    if is_stale:
                        # Don't re-cache a known-stale value here — that's exactly what kept
                        # this trap alive (a fresh TTL on the same old data, forever). Still
                        # return it so the UI has something, but let the heavy path (forced,
                        # below/via the background trigger) be the one to actually cache next.
                        _ensure_analysis_background_compute()
                        return partial
                    try:
                        set_analysis_bundle(partial, refresh_ts=refresh_ts)
                    except Exception:
                        pass
                    return partial

            if not allow_heavy:
                return None
    except Exception as e:
        logger.debug("analysis-bundle: cache read failed: %s", e)
        return None

    # force=True jumps straight here without ever validating `cached` above (that check lives
    # inside the `if not force:` block, which force=True skips entirely) — needed unconditionally
    # since the heavy compute below indexes cached["signals"] directly.
    if not cached or not isinstance(cached.get("signals"), list):
        return None

    config = _load_config()
    data_root = get_data_root()
    results = list(cached["signals"])
    holdings = _holdings_from_config(config)
    watchlist = config.get("watchlist", [])
    portfolio_tickers = [h.get("ticker") if isinstance(h, dict) else h for h in holdings]
    watchlist_tickers_for_insider = list(dict.fromkeys([r.get("ticker") for r in results if r.get("ticker")]))[:15]
    paper_trading: dict = dict(cached.get("paper_trading") or {})

    t0 = time.perf_counter()
    parallel_results: dict = {}

    def _task_insider():
        try:
            from signals.edgar_insider import run_insider_flow
            from signals.cache import cached_edgar_insider_flow
            if watchlist_tickers_for_insider:
                out = cached_edgar_insider_flow(
                    watchlist_tickers_for_insider,
                    lambda: run_insider_flow(watchlist_tickers_for_insider, max_form4_per_ticker=5, days_lookback=90),
                )
                return ("insider_flow", out if isinstance(out, dict) else {"insider_buys": [], "insider_sells": [], "ticker_activities": [], "message": "No data"})
            return ("insider_flow", {"insider_buys": [], "insider_sells": [], "ticker_activities": [], "message": None})
        except Exception as e:
            return ("insider_flow", {"insider_buys": [], "insider_sells": [], "ticker_activities": [], "message": str(e)})

    def _task_fmp_plan():
        try:
            return ("fmp_plan_status", run_fmp_plan_check(config))
        except Exception:
            return ("fmp_plan_status", {"has_key": False, "available": [], "unavailable": []})

    def _task_forward_tracking():
        try:
            ft_tickers = get_forward_tracking_tickers(config, watchlist, portfolio_tickers)
            ft_params = _forward_tracking_params(config)
            return ("forward_tracking", get_forward_tracking(
                data_root=data_root,
                tickers=ft_tickers,
                horizons=[5, 20, 60],
                max_pairs_per_horizon=ft_params["max_pairs_per_horizon"],
                max_records=ft_params["max_records"],
                config=config,
            ))
        except Exception as e:
            return ("forward_tracking", {"records": [], "summary_by_horizon": {}, "summary_by_signal": {}, "summary_by_gates": {}, "message": str(e)})

    def _task_paper_trading_async():
        try:
            from config_loader import get_dashboard_signal_universe
            from signals.paper_trade_logger import PaperTradeLogger
            pt_cfg = (config.get("paper_trading") or {}) if isinstance(config, dict) else {}
            min_done = int(pt_cfg.get("min_completed_for_summary", 60))
            min_buy = int(pt_cfg.get("min_actionable_buy_summary", 8))
            bench_sym = str(pt_cfg.get("benchmark_ticker", "SPY"))
            backfill_days = int(pt_cfg.get("backfill_from_eod_days", 90))
            horizon_days = int(pt_cfg.get("horizon_trading_days", 20))
            pt_exec_cfg = (pt_cfg.get("execution") or {}) if isinstance(pt_cfg, dict) else {}
            pt = PaperTradeLogger(data_root=data_root, execution_cfg=pt_exec_cfg)
            paper_universe = set(get_dashboard_signal_universe(config))
            existing_pt = cached.get("paper_trading") if isinstance(cached.get("paper_trading"), dict) else {}
            has_summary = isinstance(existing_pt.get("summary"), dict)
            if has_summary:
                backfill = {"skipped": True, "reason": "summary already in cache"}
            else:
                backfill = pt.backfill_from_eod_snapshots(
                    allowed_tickers=paper_universe,
                    max_days=backfill_days,
                    horizon_trading_days=horizon_days,
                    config=config,
                )
            sync = pt.sync_targets_stops_from_results(results)
            mtm = pt.mark_to_market()
            mtm_history_sync = pt.sync_mtm_history_from_eod(max_days=backfill_days)
            mtm_history_log = pt.append_mtm_history()
            fill = pt.fill_outcomes()
            summary = pt.get_performance_summary(min_completed=min_done, min_actionable=min_buy, benchmark=bench_sym)
            recent = pt.enrich_trades_with_benchmark(pt.get_recent(limit=1000), benchmark=bench_sym)
            mtm_history = pt.get_mtm_history_map(recent or [], limit_per_trade=30)
            equity_curve = pt.get_completed_equity_curve(max_points=400)
            return ("paper_trading_async", {
                "backfill": backfill,
                "sync_targets": sync, "mtm": mtm,
                "mtm_history_sync": mtm_history_sync,
                "mtm_history_log": mtm_history_log,
                "fill": fill, "summary": summary, "recent": recent, "mtm_history": mtm_history,
                "equity_curve": equity_curve,
            })
        except Exception as e:
            logger.debug("analysis-bundle paper trading: %s", e)
            return ("paper_trading_async", None)

    def _task_regime_validation():
        try:
            from signals.regime_consensus import compute_regime_consensus
            from signals.regime_persistence import compute_regime_persistence
            from signals.regime_validation import build_regime_validation
            from signals.regime import get_regime

            market_regime_data = cached.get("market_regime") if isinstance(cached.get("market_regime"), dict) else {}
            macro_regime = cached.get("macro_regime")
            spy_row = next(
                (r for r in results if isinstance(r, dict) and str(r.get("ticker") or "").upper() == "SPY"),
                None,
            )
            hmm_bull_prob = None
            hmm_data_spy = None
            if spy_row:
                conf = spy_row.get("confidence") or {}
                if isinstance(conf, dict):
                    hmm_data_spy = conf.get("hmm")
                    if isinstance(hmm_data_spy, dict):
                        try:
                            hmm_bull_prob = float(hmm_data_spy.get("bull_probability") or 0)
                        except (TypeError, ValueError):
                            pass
            ma_regime = None
            if isinstance(hmm_data_spy, dict):
                ma_regime = hmm_data_spy.get("ma_regime") or hmm_data_spy.get("resolved_regime")
            if not ma_regime:
                ma_regime = next(
                    (r.get("_global_market_regime") for r in results if isinstance(r, dict) and r.get("_global_market_regime")),
                    None,
                )
            composite_regime = None
            try:
                spy_score = float((spy_row or {}).get("composite_buy") or 50)
                composite_regime = get_regime(spy_score)
            except Exception:
                pass
            tech_leadership = market_regime_data.get("tech_leadership")
            consensus = compute_regime_consensus(
                hmm_bull_prob=hmm_bull_prob,
                ma_regime=ma_regime,
                composite_regime=composite_regime,
                macro_regime=macro_regime,
                tech_leadership=tech_leadership,
            )
            persistence = compute_regime_persistence(
                current_regime=consensus["consensus_direction"],
                data_root=data_root,
            )
            validation = build_regime_validation(
                consensus=consensus,
                persistence=persistence,
                hmm_data=hmm_data_spy,
                data_root=data_root,
            )
            return ("regime_validation", validation)
        except Exception as exc:
            return ("regime_validation", {"validated": None, "summary": str(exc), "error": True})

    def _task_confidence_calibration():
        try:
            from signals.confidence_calibration import build_calibration_report, calibration_report_to_dict
            report = build_calibration_report(data_root)
            return ("confidence_calibration", calibration_report_to_dict(report))
        except Exception as e:
            return ("confidence_calibration", {"buckets": [], "note": str(e)})

    def _task_model_audit():
        try:
            from signals.signal_audit_store import build_model_audit_payload
            # Outcome resolution scans EOD history — defer to EOD cron; too slow for HTTP/background bundle.
            return ("model_audit", build_model_audit_payload(config, data_root=data_root, resolve_outcomes=False))
        except Exception as e:
            logger.debug("analysis-bundle model_audit: %s", e)
            return ("model_audit", {"enabled": False, "message": str(e)})

    specs = [
        _task_insider, _task_fmp_plan, _task_forward_tracking,
        _task_paper_trading_async, _task_regime_validation, _task_confidence_calibration,
        _task_model_audit,
    ]
    from signals.process_memory import dashboard_parallel_max_workers

    _par = dashboard_parallel_max_workers()
    with ThreadPoolExecutor(max_workers=min(_par, len(specs))) as ex:
        futures = [ex.submit(fn) for fn in specs]
        for fut in as_completed(futures):
            try:
                key, value = fut.result()
                parallel_results[key] = value
            except Exception as e:
                logger.debug("analysis-bundle task failed: %s", e)

    forward_tracking = parallel_results.get("forward_tracking", {"records": [], "summary_by_horizon": {}, "summary_by_signal": {}, "summary_by_gates": {}, "message": None})
    paper_async = parallel_results.get("paper_trading_async")
    if paper_async:
        paper_trading["sync_targets"] = paper_async.get("sync_targets")
        paper_trading["mtm"] = paper_async.get("mtm")
        paper_trading["mtm_history_sync"] = paper_async.get("mtm_history_sync")
        paper_trading["mtm_history_log"] = paper_async.get("mtm_history_log")
        paper_trading["backfill"] = paper_async.get("backfill")
        paper_trading["fill"] = paper_async.get("fill")
        paper_trading["summary"] = paper_async.get("summary")
        paper_trading["recent"] = paper_async.get("recent")
        paper_trading["mtm_history"] = paper_async.get("mtm_history")
        paper_trading["equity_curve"] = paper_async.get("equity_curve") or []

    paper_vs_backtest_drift = None
    try:
        from signals.paper_vs_backtest_drift import build_paper_vs_backtest_drift
        paper_vs_backtest_drift = build_paper_vs_backtest_drift(forward_tracking, data_root)
    except Exception as e:
        logger.debug("analysis-bundle drift: %s", e)

    next_day_outlook = cached.get("next_day_outlook") or []
    indicator_validation = []
    try:
        indicator_validation = validate_indicators_vs_external(next_day_outlook)
    except Exception as e:
        logger.debug("analysis-bundle indicator_validation: %s", e)

    indicator_comparisons = []
    try:
        compare_tickers = ["SPY", "QQQ", "GLD", "SLV"]
        our_by_ticker = {
            r["ticker"]: {
                "close": r.get("close"),
                "rsi": r.get("rsi"),
                "ma20": r.get("ma20"),
                "ma50": r.get("ma50"),
                "macd_hist": r.get("macd_hist"),
            }
            for r in results
            if not r.get("error") and r.get("ticker") in compare_tickers
        }
        indicator_comparisons = run_indicator_comparison(
            config, our_by_ticker, next_day_outlook, tickers=compare_tickers
        )
    except Exception as e:
        logger.debug("analysis-bundle indicator_comparisons: %s", e)

    bundle = {
        "forward_tracking": forward_tracking,
        "regime_validation": parallel_results.get("regime_validation", {"validated": None, "summary": "Not computed"}),
        "confidence_calibration": parallel_results.get("confidence_calibration", {"buckets": [], "note": "Not computed"}),
        "paper_trading": paper_trading,
        "paper_vs_backtest_drift": paper_vs_backtest_drift,
        "insider_flow": parallel_results.get("insider_flow", {"insider_buys": [], "insider_sells": [], "ticker_activities": [], "message": None}),
        "indicator_validation": indicator_validation,
        "indicator_comparisons": indicator_comparisons,
        "fmp_plan_status": parallel_results.get("fmp_plan_status", {}),
        "model_audit": parallel_results.get("model_audit", {"enabled": False, "message": "Not computed"}),
        "analysis_deferred": False,
    }
    logger.info("[analysis-bundle] DONE (%.0f ms)", (time.perf_counter() - t0) * 1000)
    try:
        merge_dashboard_cache_updates(bundle)
    except Exception as e:
        logger.debug("analysis-bundle cache merge failed: %s", e)
    try:
        from signals.cache import set_analysis_bundle

        set_analysis_bundle(bundle, refresh_ts=cached.get("refresh_ts") if isinstance(cached, dict) else None)
    except Exception as e:
        logger.debug("analysis-bundle dedicated cache set failed: %s", e)
    return bundle if bundle else empty_analysis_bundle()


def _slim_analysis_for_http(bundle: dict) -> dict:
    """Cap large arrays before JSON encode — prevents gateway 502 on oversized responses."""
    from signals.cache import _sanitize_for_json

    out = dict(bundle)
    ft = out.get("forward_tracking")
    if isinstance(ft, dict):
        ft = dict(ft)
        records = ft.get("records")
        if isinstance(records, list) and len(records) > 500:
            ft["records"] = records[:500]
            meta = dict(ft.get("meta") or {})
            meta["records_truncated"] = True
            meta["records_total"] = len(records)
            ft["meta"] = meta
        out["forward_tracking"] = ft
    ma = out.get("model_audit")
    if isinstance(ma, dict):
        ma = dict(ma)
        recent = ma.get("recent_records")
        if isinstance(recent, list) and len(recent) > 80:
            ma["recent_records"] = recent[:80]
        out["model_audit"] = ma
    pt = out.get("paper_trading")
    if isinstance(pt, dict):
        pt = dict(pt)
        recent = pt.get("recent")
        if isinstance(recent, list) and len(recent) > 150:
            pt["recent"] = recent[:150]
        out["paper_trading"] = pt
    return _sanitize_for_json(out)


def _ensure_analysis_background_compute() -> None:
    """Start background analysis-bundle job if not already running.

    force=True is required here, not optional — without it, compute_analysis_bundle's own
    cache-hit tiers run first even inside this "give me a fresh one" call, so as long as
    something is cached at all (any of the 3 tiers succeeding) the actual heavy compute this
    function exists to run never executes. That silent self-short-circuit is what let
    forward_tracking sit 8 weeks stale — every trigger "succeeded" by immediately re-handing
    back the same old cached value. See _forward_tracking_staleness_days's docstring.
    """
    from api.analysis_bundle_job import is_analysis_running, trigger_background_analysis

    if not is_analysis_running():
        trigger_background_analysis(lambda: compute_analysis_bundle(allow_heavy=True, force=True))


def _paper_trading_slice_stale(pt: Any) -> bool:
    """True when cached payload has aggregate stats but no trade rows (common cache bug)."""
    if not isinstance(pt, dict):
        return True
    recent = pt.get("recent")
    if isinstance(recent, list) and len(recent) > 0:
        return False
    summary = pt.get("summary")
    if isinstance(summary, dict):
        try:
            completed = int(summary.get("completed_n") or summary.get("completed") or 0)
        except (TypeError, ValueError):
            completed = 0
        if completed > 0:
            return True
    equity = pt.get("equity_curve")
    if isinstance(equity, list) and len(equity) > 0:
        return True
    return False


def _refresh_paper_trading_light(
    existing: dict,
    results: list,
    config: dict,
    data_root: Any,
) -> dict:
    """Fast paper-trading slice: read CSV + fill/mtm — no multi-minute EOD backfill."""
    from signals.paper_trade_logger import PaperTradeLogger

    pt_cfg = (config.get("paper_trading") or {}) if isinstance(config, dict) else {}
    min_done = int(pt_cfg.get("min_completed_for_summary", 60))
    min_buy = int(pt_cfg.get("min_actionable_buy_summary", 8))
    bench_sym = str(pt_cfg.get("benchmark_ticker", "SPY"))
    pt_exec_cfg = (pt_cfg.get("execution") or {}) if isinstance(pt_cfg, dict) else {}
    pt = PaperTradeLogger(data_root=data_root, execution_cfg=pt_exec_cfg)
    out = dict(existing or {})
    out["sync_targets"] = pt.sync_targets_stops_from_results(results)
    out["mtm"] = pt.mark_to_market()
    out["fill"] = pt.fill_outcomes()
    out["summary"] = pt.get_performance_summary(
        min_completed=min_done, min_actionable=min_buy, benchmark=bench_sym
    )
    out["recent"] = pt.enrich_trades_with_benchmark(pt.get_recent(limit=1000), benchmark=bench_sym)
    out["equity_curve"] = pt.get_completed_equity_curve(max_points=400)
    out["data_root"] = str(data_root)
    out.setdefault(
        "persistence_note",
        "Set env DATA_ROOT to a persistent path (e.g. volume) so paper trades and EOD survive restarts.",
    )
    return out


def _patch_stale_paper_trading(bundle: dict | None) -> dict | None:
    """Replace paper_trading in a cached bundle when summary exists but recent[] is empty."""
    if not isinstance(bundle, dict) or not _paper_trading_slice_stale(bundle.get("paper_trading")):
        return bundle
    fresh = _compute_analysis_slice("paper_trading")
    if fresh is None:
        return bundle
    out = dict(bundle)
    out["paper_trading"] = fresh
    return out


def _compute_analysis_slice(slice_key: str) -> Any | None:
    """
    Synchronous fast path for one Analysis panel (no multi-minute paper EOD backfill).
    Used when Redis slice is missing but dashboard cache is warm.
    """
    if slice_key not in ("forward_tracking", "model_audit", "paper_trading"):
        return None
    try:
        from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot

        cached = get_cached_dashboard() or get_last_dashboard_snapshot()
    except Exception:
        cached = None
    if not cached or not isinstance(cached.get("signals"), list):
        return None

    config = _load_config()
    data_root = get_data_root()
    results = list(cached["signals"])
    holdings = _holdings_from_config(config)
    watchlist = config.get("watchlist", [])
    portfolio_tickers = [h.get("ticker") if isinstance(h, dict) else h for h in holdings]

    if slice_key == "model_audit":
        try:
            from signals.signal_audit_store import build_model_audit_payload

            return build_model_audit_payload(config, data_root=data_root, resolve_outcomes=False)
        except Exception as e:
            logger.warning("[analysis-slice] model_audit sync failed: %s", e)
            return {"enabled": False, "message": str(e)}

    if slice_key == "forward_tracking":
        try:
            ft_tickers = get_forward_tracking_tickers(config, watchlist, portfolio_tickers)
            ft_params = _forward_tracking_params(config)
            return get_forward_tracking(
                data_root=data_root,
                tickers=ft_tickers,
                horizons=[5, 20, 60],
                max_pairs_per_horizon=ft_params["max_pairs_per_horizon"],
                max_records=ft_params["max_records"],
                config=config,
            )
        except Exception as e:
            logger.warning("[analysis-slice] forward_tracking sync failed: %s", e)
            return {
                "records": [],
                "summary_by_horizon": {},
                "summary_by_signal": {},
                "summary_by_gates": {},
                "message": str(e),
            }

    if slice_key == "paper_trading":
        try:
            existing = dict(cached.get("paper_trading") or {}) if isinstance(cached.get("paper_trading"), dict) else {}
            return _refresh_paper_trading_light(existing, results, config, data_root)
        except Exception as e:
            logger.warning("[analysis-slice] paper_trading sync failed: %s", e)
            return {"message": str(e)}

    return None


def _analysis_warming_response(message: str | None = None) -> dict:
    from api.dashboard_shell import empty_analysis_bundle

    warm = empty_analysis_bundle()
    warm["warming"] = True
    warm["message"] = message or (
        "Analysis sections are computing in the background (usually 1–3 minutes). "
        "This panel will update automatically."
    )
    return warm


def _analysis_slice_response(slice_key: str):
    """Return one Analysis slice from Redis, or compute synchronously for core panels."""
    from signals.cache import (
        get_analysis_bundle,
        get_analysis_slice,
        get_cached_dashboard,
        get_last_dashboard_snapshot,
        set_analysis_slice,
    )

    data = get_analysis_slice(slice_key)
    if data is None:
        bundle = get_analysis_bundle()
        if isinstance(bundle, dict):
            data = bundle.get(slice_key)

    computed = False
    if slice_key == "paper_trading" and _paper_trading_slice_stale(data):
        data = _compute_analysis_slice(slice_key)
        computed = data is not None
    elif data is None:
        data = _compute_analysis_slice(slice_key)
        computed = data is not None

    if data is not None and computed:
        try:
            dash = get_cached_dashboard() or get_last_dashboard_snapshot()
            refresh_ts = dash.get("refresh_ts") if isinstance(dash, dict) else None
            set_analysis_slice(slice_key, data, refresh_ts=refresh_ts)
            logger.info("[analysis-slice] sync compute ok: %s", slice_key)
        except Exception as e:
            logger.debug("[analysis-slice] cache write failed %s: %s", slice_key, e)

    if data is not None:
        from signals.cache import _sanitize_for_json

        return jsonable_encoder(_sanitize_for_json({slice_key: data, "analysis_deferred": False}))

    if _is_dashboard_warming():
        return jsonable_encoder(_analysis_warming_response())

    try:
        dash = get_cached_dashboard() or get_last_dashboard_snapshot()
    except Exception:
        dash = None
    if dash is None or not isinstance(dash.get("signals"), list):
        raise HTTPException(
            status_code=503,
            detail="Dashboard cache unavailable. Load the dashboard or click Refresh, then open Analysis.",
        )

    _ensure_analysis_background_compute()
    return jsonable_encoder(_analysis_warming_response())


def _dashboard_response_for_client(full: dict, *, include_full_signals: bool) -> dict:
    """
    HTTP clients get `signal_scores` + empty `signals` when Redis holds full rows (smaller payload).
    GET /api/dashboard/signals-panel returns full rows from cache. If cache write failed, inline full `signals`.
    """
    results = full.get("signals")
    if not isinstance(results, list):
        results = []
    out = dict(full)
    out["signal_scores"] = _build_signal_scores(results)
    out["signals_deferred"] = not include_full_signals
    if include_full_signals:
        out["signals"] = results
    else:
        out["signals"] = []
    return out


def _shell_while_compute_running(*, coalesced: bool = False) -> dict:
    """Best-effort shell while a full dashboard compute is already in flight."""
    from api.dashboard_shell import build_shell_from_full, build_warming_shell, enrich_shell_snapshot_meta
    from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot

    try:
        cached = get_cached_dashboard()
        if cached is not None:
            shell = build_shell_from_full(cached, include_full_signals=False)
            shell["stale"] = False
            shell["refresh_status"] = "running"
            if coalesced:
                shell["refresh_coalesced"] = True
            df = shell.get("data_freshness") or {}
            if isinstance(df, dict):
                df["snapshot_source"] = "cache"
            return enrich_shell_snapshot_meta(shell)
    except Exception as e:
        logger.debug("[dashboard] coalesced cache read: %s", e)

    try:
        stale = get_last_dashboard_snapshot()
        if stale is not None:
            shell = build_shell_from_full(stale, include_full_signals=False)
            shell["stale"] = False
            shell["refresh_status"] = "running"
            if coalesced:
                shell["refresh_coalesced"] = True
            df = shell.get("data_freshness") or {}
            if isinstance(df, dict):
                df["snapshot_source"] = "last_snapshot"
            return enrich_shell_snapshot_meta(shell)
    except Exception as e:
        logger.debug("[dashboard] coalesced snapshot read: %s", e)

    shell = build_warming_shell(_load_config())
    shell["refresh_status"] = "running"
    if coalesced:
        shell["refresh_coalesced"] = True
    return enrich_shell_snapshot_meta(shell)


@router.get("/dashboard")
async def get_dashboard(
    refresh: bool = Query(False, description="Bypass cache; recompute full dashboard (manual Refresh)."),
):
    """Serve cached snapshot instantly; stale-while-revalidate + background refresh on miss."""
    from api.dashboard_job import get_refresh_status, is_refresh_running, trigger_background_refresh
    from api.dashboard_shell import build_shell_from_full, build_warming_shell, enrich_shell_snapshot_meta
    from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot

    if refresh:
        from api.dashboard_warm import compute_signal_warm_sync

        # Manual Force refresh always allowed (including overnight); scheduled path stays gated.
        started = trigger_background_refresh(compute_signal_warm_sync)
        if not started:
            logger.info("[dashboard] refresh=true coalesced — compute already running")
            return _shell_while_compute_running(coalesced=True)
        logger.info("[dashboard] refresh=true: async signal warm started")
        cached = get_cached_dashboard() or get_last_dashboard_snapshot()
        if cached is not None:
            shell = build_shell_from_full(cached, include_full_signals=False)
            shell["stale"] = False
        else:
            shell = build_warming_shell(_load_config())
        shell["refresh_status"] = "running"
        shell["refresh_coalesced"] = False
        df = shell.get("data_freshness") or {}
        if isinstance(df, dict):
            df["snapshot_source"] = "cache" if cached else "warming"
        return enrich_shell_snapshot_meta(shell)

    try:
        cached = get_cached_dashboard()
        if cached is not None:
            logger.info("[dashboard] serving fresh Redis cache (shell payload)")
            shell = build_shell_from_full(cached, include_full_signals=False)
            shell["stale"] = False
            shell["refresh_status"] = "running" if is_refresh_running() else "idle"
            shell["refresh_coalesced"] = False
            df = shell.get("data_freshness") or {}
            if isinstance(df, dict):
                df["snapshot_source"] = "cache"
                logger.info(
                    "[dashboard] cache freshness signals=%s quotes=%s",
                    df.get("signals_updated_at"),
                    df.get("quotes_updated_at"),
                )
            return enrich_shell_snapshot_meta(shell)
    except Exception as e:
        logger.debug("[dashboard] cache check skipped: %s", e)

    stale = None
    try:
        stale = get_last_dashboard_snapshot()
    except Exception as e:
        logger.debug("[dashboard] last snapshot read failed: %s", e)

    if stale is not None:
        from alerts.market_hours import is_signal_warm_window
        from api.dashboard_warm import compute_for_background_refresh

        # Overnight / weekend: serve last good snapshot — do not re-run ~100 tickers.
        if is_signal_warm_window():
            logger.info("[dashboard] serving stale snapshot; triggering background signal warm")
            trigger_background_refresh(compute_for_background_refresh)
        else:
            logger.info(
                "[dashboard] serving post-session snapshot (no overnight signal warm) — "
                "next heavy recompute at weekday 8:30 ET"
            )
        shell = build_shell_from_full(stale, include_full_signals=False)
        shell["stale"] = False
        shell["refresh_status"] = "running" if is_refresh_running() else get_refresh_status().get("status", "idle")
        df = shell.get("data_freshness") or {}
        if isinstance(df, dict):
            df["snapshot_source"] = "last_snapshot"
            if not is_signal_warm_window():
                df["serving_post_session"] = True
        shell = enrich_shell_snapshot_meta(shell)
        df2 = shell.get("data_freshness") or {}
        if isinstance(df2, dict):
            logger.info(
                "[dashboard] last_snapshot freshness (meta overlay) signals=%s quotes=%s",
                df2.get("signals_updated_at"),
                df2.get("quotes_updated_at"),
            )
        return shell

    job_status = get_refresh_status()
    if job_status.get("status") == "error":
        raise HTTPException(
            status_code=503,
            detail=f"Dashboard compute failed: {job_status.get('error') or 'unknown error'}. Use Refresh to retry.",
        )

    if not is_refresh_running():
        from alerts.market_hours import is_signal_warm_window
        from api.dashboard_warm import compute_for_background_refresh

        if is_signal_warm_window():
            trigger_background_refresh(compute_for_background_refresh)
        else:
            logger.info("[dashboard] no cache overnight — waiting for weekday 8:30 ET warm / manual Refresh")
    logger.info("[dashboard] serving warming shell (no cache yet; compute in progress)")
    shell = build_warming_shell(_load_config())
    shell["refresh_status"] = "running" if is_refresh_running() else job_status.get("status", "running")
    return enrich_shell_snapshot_meta(shell)


@router.get("/dashboard/shell")
async def get_dashboard_shell():
    """Instant read-only shell — never runs full compute. Same as GET /dashboard without refresh."""
    from fastapi.responses import JSONResponse

    body = await get_dashboard(refresh=False)
    # get_dashboard returns a plain dict; encode so datetimes/numpy stay JSON-safe.
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(
        content=jsonable_encoder(body),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.get("/dashboard/status")
async def get_dashboard_status():
    """Background refresh job status for stale-while-revalidate polling."""
    from api.dashboard_job import get_refresh_status, is_refresh_running
    from signals.cache import get_cached_dashboard

    status = get_refresh_status()
    cache_fresh = get_cached_dashboard() is not None
    running = is_refresh_running()
    status["cache_fresh"] = cache_fresh
    status["is_running"] = running
    # Client should fetch /dashboard/shell (not ?refresh=true) when ready.
    status["ready"] = cache_fresh and not running
    return status


@router.get("/dashboard/ws-config")
async def get_dashboard_ws_config():
    """Browser WebSocket URL when HTTP /api/* is proxied through Next.js."""
    from api.dashboard_hub import ws_public_url

    url = ws_public_url()
    return {"enabled": bool(url), "url": url}


@router.websocket("/dashboard/ws")
async def dashboard_websocket(websocket: WebSocket):
    from api.dashboard_hub import handle_websocket

    await handle_websocket(websocket)


def _compute_full_dashboard_sync() -> dict:
    """Full pipeline (signals, portfolio, macro). Used by refresh + background job."""
    dashboard_start = time.perf_counter()
    logger.info("[dashboard] START loading dashboard")
    t0 = time.perf_counter()
    logger.info("[dashboard] section: config + last_run...")
    config = _load_config()
    last_run_prev = load_last_run()  # Load BEFORE save so what_changed compares old vs new
    logger.info("[dashboard] section: config + last_run DONE (%.0f ms)", (time.perf_counter() - t0) * 1000)

    # Build holdings list first (needed for portfolio tickers and for report)
    holdings = _holdings_from_config(config)

    # Consolidate tickers for single FMP batch quote (signals + portfolio + opportunity universe) to stay under API limit
    watchlist = config.get("watchlist", [])
    signal_universe = get_dashboard_signal_universe(config)
    portfolio_tickers = [h.get("ticker") if isinstance(h, dict) else h for h in holdings]
    opportunity_universe = config.get("opportunity_universe") or []
    all_quote_tickers = list(dict.fromkeys([t for t in signal_universe + portfolio_tickers + opportunity_universe if t]))
    # Alert-only audit cohort (~100): batch quotes on Refresh so cohort band checks use fresh prices
    _alert_cfg = config.get("alerts") or {}
    if _alert_cfg.get("include_audit_cohort_on_refresh", True) is not False:
        try:
            from config_loader import get_audit_cohort_tickers

            all_quote_tickers = list(
                dict.fromkeys([t for t in all_quote_tickers + get_audit_cohort_tickers(config) if t])
            )
        except Exception as e:
            logger.debug("audit cohort quote expansion: %s", e)
    prices_by_ticker = None
    prices_from_fmp_batch = False
    has_fmp_key = bool(get_fmp_api_key(config))
    global _fmp_batch_quote_disabled_until
    _circuit_open = time.monotonic() < _fmp_batch_quote_disabled_until
    use_fmp_batch_quote = (
        config.get("data", {}).get("use_fmp_batch_quote", True)
        and has_fmp_key
        and not _circuit_open
    )
    if _circuit_open:
        remaining = int((_fmp_batch_quote_disabled_until - time.monotonic()) / 60)
        logger.info("[dashboard] FMP batch-quote circuit open (402 cooldown, %d min remaining) — using yfinance batch", remaining)
    logger.info("[dashboard] Batch quote check: use_fmp_batch_quote=%s, all_quote_tickers=%d", use_fmp_batch_quote, len(all_quote_tickers))
    if use_fmp_batch_quote and all_quote_tickers:
        logger.info("[dashboard] FMP batch quote: requesting %d symbols...", len(all_quote_tickers))
        batch_quotes, batch_err = fetch_batch_quote(config, all_quote_tickers)
        if batch_err:
            logger.warning("[dashboard] FMP batch quote error: %s (falling back to yfinance batch)", batch_err)
            if "402" in str(batch_err) or "Payment" in str(batch_err):
                _fmp_batch_quote_disabled_until = time.monotonic() + 7200  # 2-hour cooldown
                logger.warning(
                    "[dashboard] FMP batch-quote 402: requires Premium plan. "
                    "Circuit breaker engaged for 2 hours. Set use_fmp_batch_quote: false in config.yaml to suppress."
                )
        elif batch_quotes:
            prices_by_ticker = {}
            for sym, row in batch_quotes.items():
                p = row.get("price")
                if p is not None:
                    try:
                        prices_by_ticker[sym] = float(p)
                    except (TypeError, ValueError):
                        pass
            if prices_by_ticker:
                logger.info("[dashboard] FMP batch quote: received %d prices (1 API call)", len(prices_by_ticker))
                prices_from_fmp_batch = True
            else:
                logger.warning("[dashboard] FMP batch quote: no valid prices returned")
        else:
            logger.warning("[dashboard] FMP batch quote: empty response")
    elif all_quote_tickers:
        # Use yfinance (delayed) live quotes until FMP batch quote is available on paid plan
        prices_by_ticker = fetch_yfinance_latest_prices(all_quote_tickers)
        if prices_by_ticker:
            logger.info("[dashboard] yfinance latest: %d prices (delayed quote)", len(prices_by_ticker))

    # Optional: replace FMP batch marks for index ETFs with Yahoo (same vendor as OHLCV). Off via config if undesired.
    use_yahoo_overlay = config.get("data", {}).get("yahoo_overlay_index_etf_quotes", True)
    if use_yahoo_overlay and prices_from_fmp_batch and prices_by_ticker:
        idx = [t for t in all_quote_tickers if t and str(t).strip().upper() in MAJOR_INDEX_ETFS]
        if idx:
            yf_idx = fetch_yfinance_latest_prices(idx)
            if yf_idx:
                prices_by_ticker = dict(prices_by_ticker)
                for t in idx:
                    if t in yf_idx:
                        prices_by_ticker[t] = yf_idx[t]
                logger.info(
                    "[dashboard] Yahoo spot overlay for index ETFs (aligned with band OHLCV): %s",
                    [t for t in idx if t in yf_idx],
                )

    # Paper trading container (populated after run_signals)
    paper_trading: dict = {"summary": None, "recent": [], "log": None, "fill": None}

    # Forward tracking (before run_signals) for hit-rate gate: suppress BUY/ADD when ADD hit rate < VIX threshold
    hit_rate_context = None
    try:
        ft = get_forward_tracking(
            data_root=get_data_root(),
            tickers=["SPY", "QQQ"],
            horizons=[20],
        )
        sb = ft.get("summary_by_signal") or {}
        add_info = sb.get("HOLD/ADD")
        if add_info and isinstance(add_info, dict) and add_info.get("hit_rate_pct") is not None:
            hit_rate_context = {"add_hit_rate_pct": float(add_info["hit_rate_pct"])}
    except Exception as e:
        logger.debug("Forward tracking for hit-rate gate: %s", e)

    t0 = time.perf_counter()
    logger.info("[dashboard] section: run_signals (watchlist + portfolio, %d tickers)...", len(signal_universe))
    results = run_signals(
        config,
        prices_by_ticker=prices_by_ticker,
        hit_rate_context=hit_rate_context,
        tickers=signal_universe,
    )
    logger.info("[dashboard] section: run_signals DONE (%d tickers, %.0f ms)", len(results) if results else 0, (time.perf_counter() - t0) * 1000)

    market_reversal_overlay = None
    for r in results or []:
        if isinstance(r, dict) and r.get("market_overlay"):
            if market_reversal_overlay is None:
                market_reversal_overlay = r.get("market_overlay")
            r.pop("market_overlay", None)

    # Live quotes for UI display (indicators still computed from OHLCV series above).
    if prices_by_ticker:
        from signals.live_quotes import apply_live_quotes_to_results

        _quote_src = "fmp_batch" if prices_from_fmp_batch else "yfinance_latest"
        apply_live_quotes_to_results(results, prices_by_ticker, source=_quote_src)

    # Paper trading + signal audit log (idempotent by date+ticker)
    try:
        from datetime import datetime as _dt

        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo  # type: ignore

        paper_trade_date = _dt.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        from signals.signal_audit_store import persist_daily_signal_logs

        log_result = persist_daily_signal_logs(
            results,
            config,
            date_str=paper_trade_date,
            run_source="dashboard",
            data_root=get_data_root(),
        )
        paper_log = log_result.get("paper_trades") or {}
        logger.info("[dashboard] paper trades logged: %s", paper_log)
        logger.info("[dashboard] signal audit logged: %s", log_result.get("signal_audit"))
        paper_trading["log"] = paper_log
        paper_trading["signal_audit"] = log_result.get("signal_audit")
    except Exception as e:
        logger.debug("Paper trading / signal audit log failed: %s", e)

    # Update price-target accuracy report (same results, no extra fetch) so GET /api/accuracy is always current
    try:
        acc_path = run_accuracy_and_save(results, config)
        if acc_path:
            logger.info("[dashboard] section: accuracy report saved to %s", acc_path.name)
    except Exception as e:
        logger.warning("[dashboard] accuracy report save skipped: %s", e)

    t0 = time.perf_counter()
    logger.info("[dashboard] section: portfolio_report (holdings + doctor)...")
    portfolios_cfg = config.get("portfolios") or {}
    portfolio_names = ["All"] + ([k for k in portfolios_cfg.keys() if isinstance(portfolios_cfg.get(k), list)] if isinstance(portfolios_cfg, dict) else [])
    # Group holdings by account for per-portfolio reports
    holdings_by_account: dict[str, list] = {}
    for h in holdings:
        acc = (h.get("account") if isinstance(h, dict) else None) or "Default"
        holdings_by_account.setdefault(acc, []).append(dict(h) if isinstance(h, dict) else {"ticker": h, "quantity": 1})
    if not holdings_by_account and holdings:
        holdings_by_account["All"] = list(holdings)

    # 7-layer confidence for holdings (used by Portfolio Doctor) — run in parallel
    confidence_by_ticker: dict = {}
    holdings_tickers = list(dict.fromkeys(h.get("ticker") if isinstance(h, dict) else h for h in holdings))
    if holdings_tickers:
        def _confidence_one(ticker: str):
            try:
                conf = run_confidence(ticker, config=config)
                return (ticker, conf) if conf.get("confidence") is not None else (ticker, None)
            except Exception as e:
                logger.debug("Confidence for %s: %s", ticker, e)
                return (ticker, None)
        try:
            t0_conf = time.perf_counter()
            from signals.process_memory import dashboard_parallel_max_workers

            with ThreadPoolExecutor(max_workers=min(4, dashboard_parallel_max_workers())) as ex:
                futures = [ex.submit(_confidence_one, t) for t in holdings_tickers]
                for fut in as_completed(futures):
                    ticker, conf = fut.result()
                    if conf is not None:
                        confidence_by_ticker[ticker] = conf
            logger.info("[dashboard] confidence for %d holdings tickers (parallel, %.0f ms)", len(confidence_by_ticker), (time.perf_counter() - t0_conf) * 1000)
        except Exception as e:
            logger.debug("Confidence fetch failed: %s", e)

    from signals.alert_provenance import attach_trim_provenance_to_holdings

    sell_max_trim = float((config.get("score") or {}).get("sell_max", 35))
    trim_cfg = config.get("trim_gates") or {}
    signals_by_ticker = {
        str(r["ticker"]).upper(): r for r in results if isinstance(r, dict) and r.get("ticker") and not r.get("error")
    }
    portfolios_out: dict[str, dict] = {}
    for name in portfolio_names:
        if name == "All":
            subset = holdings
        else:
            subset = holdings_by_account.get(name, [])
        if not subset:
            continue
        rep = portfolio_report(
            holdings=subset,
            results=results,
            watchlist=config.get("watchlist", []),
            score_cfg=config.get("score", {}),
            concentration_threshold_pct=config.get("concentration_alert_pct", 20),
            cash_deploy_min_score=config.get("cash_deploy_min_score", 70),
            confidence_by_ticker=confidence_by_ticker,
            model_rules=config.get("model_rules"),
        )
        if prices_by_ticker:
            total_value = rep.get("total_value") or 0.0
            filled_value = 0.0
            recalc_total = False
            for h in rep.get("per_holding", []):
                t = str(h.get("ticker") or "").upper()
                if t not in prices_by_ticker:
                    continue
                try:
                    price = float(prices_by_ticker[t])
                except (TypeError, ValueError):
                    continue
                qty = h.get("quantity") or 1
                old_val = h.get("value")
                h["price"] = price
                h["value"] = qty * price
                h["live_price_source"] = "fmp_batch" if prices_from_fmp_batch else "yfinance_latest"
                if old_val != h["value"]:
                    recalc_total = True
                if h.get("price") is None:
                    filled_value += h["value"] or 0
            if recalc_total or filled_value > 0:
                total_value = sum(
                    float(x.get("value") or 0) for x in rep.get("per_holding", []) if x.get("value") is not None
                )
                rep["total_value"] = total_value
                for h in rep.get("per_holding", []):
                    if h.get("value") is not None and total_value > 0:
                        h["pct"] = round(100 * h["value"] / total_value, 1)
        attach_trim_provenance_to_holdings(
            rep.get("per_holding") or [],
            sell_max=sell_max_trim,
            signals_by_ticker=signals_by_ticker,
            trim_cfg=trim_cfg,
        )
        portfolios_out[name] = rep
    report = portfolios_out.get("All") or (portfolios_out[portfolio_names[1]] if len(portfolio_names) > 1 else {})
    logger.info("[dashboard] section: portfolio_report DONE (%.0f ms)", (time.perf_counter() - t0) * 1000)

    # Load independent sections in parallel to reduce total time and timeout risk
    crypto_tickers = config.get("crypto_watchlist") or ["BTC-USD", "ETH-USD"]
    cross_asset_tickers = config.get("cross_asset_tickers") or ["^VIX", "DX-Y.NYB", "GLD", "USO", "UNG"]
    watchlist_tickers_for_insider = list(dict.fromkeys([r.get("ticker") for r in results if r.get("ticker")]))[:15]
    data_root = get_data_root()
    period_long = config.get("data", {}).get("period_long", "13y")

    def _task_crypto():
        try:
            return ("crypto_signals", run_crypto_signals(crypto_tickers, config))
        except Exception as e:
            logger.debug("crypto_signals failed: %s", e)
            return ("crypto_signals", [])

    def _task_cross_asset():
        try:
            cross = run_cross_asset_daily(cross_asset_tickers)
            rate_10y = None
            try:
                rates, _ = fetch_treasury_rates(config)
                rate_10y = get_10y_rate(rates)
            except Exception:
                pass
            if rate_10y is not None:
                cross = list(cross) + [{"ticker": "10Y", "label": "10Y Treasury", "close": rate_10y, "pct_change": None}]
            return ("cross_asset", cross)
        except Exception as e:
            logger.debug("cross_asset failed: %s", e)
            return ("cross_asset", [])

    def _task_economic_calendar():
        try:
            from signals.cache import cached_economic_calendar
            def _fetch_cal():
                ev, _ = fetch_economic_calendar(config, 7)
                return [e for e in (ev or [])[:30] if isinstance(e, dict)] if ev else []
            cal = cached_economic_calendar(7, _fetch_cal) or []
            return ("economic_calendar", cal)
        except Exception:
            try:
                events, _ = fetch_economic_calendar(config, 7)
                cal = [e for e in events[:30] if isinstance(e, dict)] if events and isinstance(events, list) else []
                return ("economic_calendar", cal)
            except Exception as e:
                logger.debug("economic_calendar failed: %s", e)
                return ("economic_calendar", [])

    def _task_real_yield():
        try:
            return ("real_yield", get_real_yield_proxy(config))
        except Exception:
            return ("real_yield", None)

    def _task_cot():
        try:
            return ("cot_extremes", get_cot_extremes_for_guidelines())
        except Exception:
            return ("cot_extremes", [])

    # Pre-market is lazy-loaded: PreMarketPanel fetches /api/pre-market when Markets tab is shown; skip here to speed initial load.
    # def _task_pre_market(): ...

    def _task_eod_redis():
        # Live Redis ∪ disk index — never deserialize full multi‑MB blobs here.
        eod_snapshots_out: list = []
        try:
            from signals.cache import build_eod_snapshot_index

            eod_snapshots_out = build_eod_snapshot_index()
        except Exception as e:
            logger.debug("EOD snapshot list failed: %s", e)
        redis_status_out = {"configured": False, "connected": False}
        try:
            from signals.cache import redis_status as _redis_status

            redis_status_out = _redis_status()
        except Exception:
            pass
        return ("eod_redis", (eod_snapshots_out, redis_status_out))

    def _task_insider():
        try:
            from signals.edgar_insider import run_insider_flow
            from signals.cache import cached_edgar_insider_flow
            if watchlist_tickers_for_insider:
                out = cached_edgar_insider_flow(
                    watchlist_tickers_for_insider,
                    lambda: run_insider_flow(watchlist_tickers_for_insider, max_form4_per_ticker=5, days_lookback=90),
                )
                return ("insider_flow", out if isinstance(out, dict) else {"insider_buys": [], "insider_sells": [], "ticker_activities": [], "message": "No data"})
            return ("insider_flow", {"insider_buys": [], "insider_sells": [], "ticker_activities": [], "message": None})
        except Exception as e:
            logger.debug("Insider flow failed: %s", e)
            return ("insider_flow", {"insider_buys": [], "insider_sells": [], "ticker_activities": [], "message": str(e)})

    def _task_fmp_plan():
        try:
            return ("fmp_plan_status", run_fmp_plan_check(config))
        except Exception:
            return ("fmp_plan_status", {"has_key": False, "available": [], "unavailable": []})

    def _task_forward_tracking():
        try:
            ft_tickers = get_forward_tracking_tickers(config, watchlist, portfolio_tickers)
            ft_params = _forward_tracking_params(config)
            return ("forward_tracking", get_forward_tracking(
                data_root=data_root,
                tickers=ft_tickers,
                horizons=[5, 20, 60],
                max_pairs_per_horizon=ft_params["max_pairs_per_horizon"],
                max_records=ft_params["max_records"],
                config=config,
            ))
        except Exception as e:
            ft = {"records": [], "summary_by_horizon": {}, "summary_by_signal": {}, "summary_by_gates": {}, "message": str(e)}
            return ("forward_tracking", ft)

    def _task_confidence_calibration():
        try:
            from signals.confidence_calibration import build_calibration_report, calibration_report_to_dict
            report = build_calibration_report(data_root)
            return ("confidence_calibration", calibration_report_to_dict(report))
        except Exception as e:
            logger.debug("Confidence calibration failed: %s", e)
            return ("confidence_calibration", {"buckets": [], "note": str(e)})

    def _task_regime_validation():
        """
        Full market-level regime validation (Issues 1-6).
        Uses SPY/QQQ signals from the current run + EOD persistence history.
        Runs in parallel — safe because it only reads EOD snapshots (no writes).
        """
        try:
            from signals.regime_consensus import compute_regime_consensus
            from signals.regime_persistence import compute_regime_persistence
            from signals.regime_validation import build_regime_validation

            # Extract SPY HMM bull probability from current run results
            spy_row = next(
                (r for r in results if isinstance(r, dict) and str(r.get("ticker") or "").upper() == "SPY"),
                None,
            )
            hmm_bull_prob: float | None = None
            hmm_data_spy: dict | None = None
            if spy_row:
                conf = spy_row.get("confidence") or {}
                if isinstance(conf, dict):
                    hmm_data_spy = conf.get("hmm")
                    if isinstance(hmm_data_spy, dict):
                        try:
                            hmm_bull_prob = float(hmm_data_spy.get("bull_probability") or 0)
                        except (TypeError, ValueError):
                            pass

            # MA regime: prefer resolved regime from HMM validation payload
            ma_regime: str | None = None
            if isinstance(hmm_data_spy, dict):
                ma_regime = hmm_data_spy.get("ma_regime") or hmm_data_spy.get("resolved_regime")
            if not ma_regime and market_regime_data:
                # Fall back to global market regime label from run_signals
                ma_regime = next(
                    (r.get("_global_market_regime") for r in results
                     if isinstance(r, dict) and r.get("_global_market_regime")),
                    None,
                )

            # Composite regime from average composite_buy of SPY/QQQ
            composite_regime: str | None = None
            try:
                from signals.regime import get_regime
                spy_score = float((spy_row or {}).get("composite_buy") or 50)
                composite_regime = get_regime(spy_score)
            except Exception:
                pass

            # Breadth RS tech leadership from market_regime_data (already computed above)
            tech_leadership: str | None = (market_regime_data or {}).get("tech_leadership")

            consensus = compute_regime_consensus(
                hmm_bull_prob=hmm_bull_prob,
                ma_regime=ma_regime,
                composite_regime=composite_regime,
                macro_regime=macro_regime,
                tech_leadership=tech_leadership,
            )

            # Persistence: track current consensus direction in EOD history
            persistence = compute_regime_persistence(
                current_regime=consensus["consensus_direction"],
                data_root=data_root,
            )

            validation = build_regime_validation(
                consensus=consensus,
                persistence=persistence,
                hmm_data=hmm_data_spy,
                data_root=data_root,
            )
            return ("regime_validation", validation)
        except Exception as exc:
            logger.debug("regime_validation task failed: %s", exc)
            return ("regime_validation", {"validated": None, "summary": str(exc), "error": True})

    # Pre-market full: lazy-loaded with pre_market above (PreMarketPanel fetches /api/pre-market).

    def _task_paper_trading_async():
        try:
            from config_loader import get_dashboard_signal_universe
            from signals.paper_trade_logger import PaperTradeLogger
            pt_cfg = (config.get("paper_trading") or {}) if isinstance(config, dict) else {}
            min_done = int(pt_cfg.get("min_completed_for_summary", 60))
            min_buy = int(pt_cfg.get("min_actionable_buy_summary", 8))
            bench_sym = str(pt_cfg.get("benchmark_ticker", "SPY"))
            backfill_days = int(pt_cfg.get("backfill_from_eod_days", 90))
            horizon_days = int(pt_cfg.get("horizon_trading_days", 20))
            pt_exec_cfg = (pt_cfg.get("execution") or {}) if isinstance(pt_cfg, dict) else {}
            pt = PaperTradeLogger(data_root=data_root, execution_cfg=pt_exec_cfg)
            paper_universe = set(get_dashboard_signal_universe(config))
            backfill = pt.backfill_from_eod_snapshots(
                allowed_tickers=paper_universe,
                max_days=backfill_days,
                horizon_trading_days=horizon_days,
                config=config,
            )
            sync = pt.sync_targets_stops_from_results(results)
            mtm = pt.mark_to_market()
            mtm_history_sync = pt.sync_mtm_history_from_eod(max_days=backfill_days)
            mtm_history_log = pt.append_mtm_history()
            fill = pt.fill_outcomes()
            summary = pt.get_performance_summary(
                min_completed=min_done,
                min_actionable=min_buy,
                benchmark=bench_sym,
            )
            recent = pt.get_recent(limit=1000)
            recent = pt.enrich_trades_with_benchmark(recent, benchmark=bench_sym)
            mtm_history = pt.get_mtm_history_map(recent or [], limit_per_trade=30)
            equity_curve = pt.get_completed_equity_curve(max_points=400)
            return ("paper_trading_async", {
                "backfill": backfill,
                "sync_targets": sync, "mtm": mtm,
                "mtm_history_sync": mtm_history_sync,
                "mtm_history_log": mtm_history_log,
                "fill": fill, "summary": summary, "recent": recent, "mtm_history": mtm_history,
                "equity_curve": equity_curve,
            })
        except Exception as e:
            logger.debug("Paper trading summary failed: %s", e)
            return ("paper_trading_async", None)

    def _timed_parallel_task(name: str, fn):
        t0 = time.perf_counter()
        try:
            key, value = fn()
            logger.info("[dashboard] section: %s took %.0f ms", name, (time.perf_counter() - t0) * 1000)
            return key, value
        except Exception as e:
            logger.info("[dashboard] section: %s failed after %.0f ms: %s", name, (time.perf_counter() - t0) * 1000, e)
            raise

    parallel_task_specs_core = [
        ("crypto_signals", _task_crypto),
        ("cross_asset", _task_cross_asset),
        ("economic_calendar", _task_economic_calendar),
        ("real_yield", _task_real_yield),
        ("cot_extremes", _task_cot),
        ("eod_redis", _task_eod_redis),
    ]
    # Analysis-tab sections: lazy via GET /api/dashboard/analysis-bundle
    parallel_task_specs_deferred = [
        ("insider_flow", _task_insider),
        ("fmp_plan_status", _task_fmp_plan),
        ("forward_tracking", _task_forward_tracking),
        ("paper_trading_async", _task_paper_trading_async),
        ("regime_validation", _task_regime_validation),
        ("confidence_calibration", _task_confidence_calibration),
    ]
    parallel_task_specs = parallel_task_specs_core
    parallel_results: dict = {}
    t_parallel = time.perf_counter()
    logger.info("[dashboard] section: parallel load (%d tasks)...", len(parallel_task_specs))
    from signals.process_memory import dashboard_parallel_max_workers

    _par = dashboard_parallel_max_workers()
    with ThreadPoolExecutor(max_workers=min(_par, len(parallel_task_specs))) as ex:
        futures = [ex.submit(_timed_parallel_task, name, fn) for name, fn in parallel_task_specs]
        for fut in as_completed(futures):
            try:
                key, value = fut.result()
                parallel_results[key] = value
            except Exception as e:
                logger.debug("Parallel task failed: %s", e)
    logger.info("[dashboard] section: parallel load DONE (wall %.0f ms)", (time.perf_counter() - t_parallel) * 1000)

    crypto_signals = parallel_results.get("crypto_signals", [])
    cross_asset = parallel_results.get("cross_asset", [])
    economic_calendar = parallel_results.get("economic_calendar", [])
    real_yield = parallel_results.get("real_yield")
    cot_extremes = parallel_results.get("cot_extremes", [])
    # Pre-market: lazy-loaded by PreMarketPanel when user opens Markets tab
    pre_market = {}
    pre_market_full = None
    eod_redis = parallel_results.get("eod_redis", ([], {"configured": False, "connected": False}))
    eod_snapshots = eod_redis[0] if isinstance(eod_redis, tuple) else []
    redis_status_out = eod_redis[1] if isinstance(eod_redis, tuple) and len(eod_redis) > 1 else {"configured": False, "connected": False}
    insider_flow = parallel_results.get("insider_flow", {"insider_buys": [], "insider_sells": [], "ticker_activities": [], "message": None})
    fmp_plan_status = parallel_results.get("fmp_plan_status", {})
    forward_tracking = parallel_results.get("forward_tracking", {"records": [], "summary_by_horizon": {}, "summary_by_signal": {}, "summary_by_gates": {}, "message": None})
    regime_validation = parallel_results.get("regime_validation", {"validated": None, "summary": "Not computed"})
    confidence_calibration = parallel_results.get("confidence_calibration", {"buckets": [], "note": "Not computed"})
    paper_async = parallel_results.get("paper_trading_async")
    if paper_async:
        paper_trading["sync_targets"] = paper_async.get("sync_targets")
        paper_trading["mtm"] = paper_async.get("mtm")
        paper_trading["mtm_history_sync"] = paper_async.get("mtm_history_sync")
        paper_trading["mtm_history_log"] = paper_async.get("mtm_history_log")
        paper_trading["backfill"] = paper_async.get("backfill")
        paper_trading["fill"] = paper_async.get("fill")
        paper_trading["summary"] = paper_async.get("summary")
        paper_trading["recent"] = paper_async.get("recent")
        paper_trading["mtm_history"] = paper_async.get("mtm_history") or paper_async.get("mtm_history_map")
        paper_trading["equity_curve"] = paper_async.get("equity_curve") or []
    try:
        paper_trading["data_root"] = str(get_data_root())
        paper_trading["persistence_note"] = "Set env DATA_ROOT to a persistent path (e.g. volume) so paper trades and EOD survive restarts."
    except Exception:
        pass

    # Market scenarios (what-if): upcoming events + historical reaction stats (13y)
    t0 = time.perf_counter()
    market_scenarios = []
    try:
        market_scenarios = get_upcoming_event_scenarios(economic_calendar, period_long=period_long, symbol="SPY")
    except Exception as e:
        logger.debug("Market scenarios failed: %s", e)
    logger.info("[dashboard] section: market_scenarios %.0f ms", (time.perf_counter() - t0) * 1000)

    # Cross-asset guidelines (macro + calendar + real yield + COT) — uses parallel-loaded data
    t0 = time.perf_counter()
    guidelines = compute_cross_asset_guidelines(
        cross_asset, economic_calendar,
        real_yield=real_yield,
        cot_extremes=cot_extremes,
    )
    logger.info("[dashboard] section: cross_asset_guidelines %.0f ms", (time.perf_counter() - t0) * 1000)

    # COT by ticker for table (GLD, SLV, USO)
    cot_by_ticker = {}
    for item in cot_extremes:
        if not isinstance(item, dict) or not item.get("extreme"):
            continue
        label = (item.get("label") or "").strip()
        extreme = item.get("extreme")
        ticker_map = {"Gold": "GLD", "Silver": "SLV", "Crude oil": "USO"}
        t = ticker_map.get(label)
        if t:
            cot_by_ticker[t] = f"Crowded {'Long' if extreme == 'long' else 'Short'}"

    # Macro regime: simple Risk-On / Neutral / Risk-Off for banner
    vix_val = None
    for c in cross_asset or []:
        if isinstance(c, dict) and (c.get("label") == "VIX" or c.get("ticker") == "^VIX"):
            vix_val = normalize_vix_close_price(c.get("close"))
            break
    if real_yield is not None and real_yield > 2.0:
        macro_regime = "Risk-Off"
    elif vix_val is not None and vix_val > 20:
        macro_regime = "Risk-Off"
    elif real_yield is not None and real_yield < 1.0 and (vix_val is None or vix_val < 15):
        macro_regime = "Risk-On"
    else:
        macro_regime = "Neutral"

    t0 = time.perf_counter()
    macro_regime_bundle: dict = {}
    try:
        mr_cfg = config.get("macro_regime") or {}
        if mr_cfg.get("enabled", True):
            from signals.macro_regime import build_macro_regime_bundle

            hmm_bear_pct = None
            if mr_cfg.get("combine_with_hmm", True):
                try:
                    from signals.hmm_regime import get_hmm_regime

                    # Reuse SPY close+volume from run_signals pre-fetch (already in cache as "5y")
                    # Pass volume so _build_features always uses 3 features — consistent with
                    # price_targets.py / confidence_engine.py which also pass volume.
                    # Inconsistent volume presence across call sites caused a 2 vs 3 dim mismatch.
                    from signals.fetcher import fetch_ohlcv_with_volume as _fwv
                    close_spy_hmm, vol_spy_hmm = _fwv("SPY", "2y")
                    if close_spy_hmm is not None and len(close_spy_hmm) >= 252:
                        hmm = get_hmm_regime("SPY", close_spy_hmm, volume=vol_spy_hmm, vix=vix_val)
                        if hmm and hmm.get("bear_probability") is not None:
                            hmm_bear_pct = float(hmm["bear_probability"]) * 100.0
                except Exception as e:
                    logger.debug("macro+HMM: %s", e)
            macro_regime_bundle = build_macro_regime_bundle(
                config,
                vix=vix_val,
                hmm_bear_pct=hmm_bear_pct,
                hmm_weight=float(mr_cfg.get("hmm_weight", 0.40)),
                macro_weight=float(mr_cfg.get("macro_weight", 0.60)),
            )
    except Exception as e:
        logger.debug("macro_regime_bundle: %s", e)
    logger.info("[dashboard] section: macro_regime_bundle %.0f ms", (time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    portfolio_risk_metrics: dict = {}
    try:
        pr_cfg = config.get("portfolio_risk") or {}
        if pr_cfg.get("enabled", True) and holdings:
            from signals.portfolio_risk_model import (
                compute_correlation_matrix,
                compute_portfolio_beta_metrics,
                compute_var_cvar,
                correlation_adjusted_sizing,
            )

            raw_tickers = []
            for h in holdings:
                t = h.get("ticker") if isinstance(h, dict) else h
                if t:
                    raw_tickers.append(str(t).upper().split("-")[0])
            tickers_pr = list(dict.fromkeys(raw_tickers))[: int(pr_cfg.get("max_tickers", 20))]

            first_report = next(iter(portfolios_out.values()), None) if portfolios_out else None
            per_holding_ph = (first_report or {}).get("per_holding") or []
            sector_alloc = (first_report or {}).get("sector_allocation") or []

            if per_holding_ph:
                try:
                    portfolio_risk_metrics["beta"] = compute_portfolio_beta_metrics(
                        per_holding_ph,
                        sector_allocation=sector_alloc,
                    )
                except Exception as be:
                    logger.debug("portfolio beta metrics: %s", be)

            if len(tickers_pr) >= 2:
                # portfolio_risk_model uses "5y" — same period as run_signals above.
                # All holdings tickers are already in the in-process OHLCV cache; no extra
                # network calls needed here.
                n = len(tickers_pr)
                eq_w = {t: 1.0 / n for t in tickers_pr}
                corr_df, c_err = compute_correlation_matrix(tickers_pr)
                if corr_df is not None:
                    portfolio_risk_metrics["correlation_matrix"] = corr_df.round(3).to_dict()
                portfolio_risk_metrics["correlation_error"] = c_err
                portfolio_risk_metrics["var_cvar"] = compute_var_cvar(tickers_pr, eq_w)
                base_kelly = {t: float(pr_cfg.get("base_kelly_fraction", 0.25)) for t in tickers_pr}
                portfolio_risk_metrics["correlation_adjusted_sizes"] = correlation_adjusted_sizing(
                    tickers_pr,
                    base_kelly,
                    max_portfolio=float(pr_cfg.get("max_portfolio", 0.65)),
                )
                portfolio_risk_metrics["note"] = (
                    "Equal-weight illustrative VaR; use correlation_adjusted_sizes with your own base fractions."
                )
    except Exception as e:
        logger.debug("portfolio_risk_metrics: %s", e)
    logger.info("[dashboard] section: portfolio_risk_metrics %.0f ms", (time.perf_counter() - t0) * 1000)

    # ── Portfolio Doctor v2: health score, MCTR, stress tests, earnings cal, priority queue ──
    t0 = time.perf_counter()
    portfolio_doctor_v2: dict = {}
    try:
        if holdings and portfolios_out:
            first_report = next(iter(portfolios_out.values()), None)
            if first_report:
                _pd_ph = first_report.get("per_holding") or []
                _pd_tv = first_report.get("total_value") or 0

                # Health score
                from portfolio.health_score import compute_health_score
                health = compute_health_score(
                    _pd_ph, _pd_tv,
                    correlation_matrix=portfolio_risk_metrics.get("correlation_matrix"),
                    var_cvar=portfolio_risk_metrics.get("var_cvar"),
                    sector_allocation=first_report.get("sector_allocation"),
                    stress_scenarios=None,
                )

                # MCTR
                from portfolio.mctr import compute_mctr
                mctr = compute_mctr(_pd_ph, _pd_tv)

                # Stress tests
                from portfolio.stress_test import compute_stress_tests
                sector_map_for_stress = {}
                for sa in (first_report.get("sector_allocation") or []):
                    pass
                stress = compute_stress_tests(_pd_ph, _pd_tv)

                # Update health with stress data
                if stress:
                    health_with_stress = compute_health_score(
                        _pd_ph, _pd_tv,
                        correlation_matrix=portfolio_risk_metrics.get("correlation_matrix"),
                        var_cvar=portfolio_risk_metrics.get("var_cvar"),
                        sector_allocation=first_report.get("sector_allocation"),
                        stress_scenarios=stress,
                    )
                    health = health_with_stress

                # Earnings calendar
                from portfolio.priority_actions import build_earnings_calendar_portfolio
                earnings_cal = build_earnings_calendar_portfolio(_pd_ph, _pd_tv, config)

                # Priority actions
                from portfolio.priority_actions import build_priority_actions
                first_rec = next(iter(portfolio_doctor_recommendations.values()), None) or {}
                priority = build_priority_actions(
                    _pd_ph, _pd_tv,
                    trim_list=first_rec.get("trim"),
                    add_list=first_rec.get("add"),
                    correlation_alerts=first_report.get("correlation_alerts"),
                    earnings_calendar=earnings_cal.get("items"),
                    mctr=mctr,
                )

                # Performance attribution
                attribution = {}
                try:
                    from portfolio.attribution import compute_attribution
                    attribution = compute_attribution(_pd_ph, _pd_tv)
                except Exception as e:
                    logger.debug("attribution: %s", e)

                # Liquidity scores
                liquidity = {}
                try:
                    from portfolio.liquidity import compute_liquidity_scores
                    liquidity = compute_liquidity_scores(_pd_ph)
                except Exception as e:
                    logger.debug("liquidity: %s", e)

                # Factor exposure
                factor_exposure = {}
                try:
                    from portfolio.factor_exposure import compute_factor_exposure
                    factor_exposure = compute_factor_exposure(_pd_ph, _pd_tv, config)
                except Exception as e:
                    logger.debug("factor_exposure: %s", e)

                portfolio_doctor_v2 = {
                    "health": health,
                    "mctr": mctr,
                    "stress_tests": stress,
                    "earnings_calendar": earnings_cal,
                    "priority_actions": priority,
                    "portfolio_beta": mctr.get("portfolio_beta") if mctr else None,
                    "attribution": attribution,
                    "liquidity": liquidity,
                    "factor_exposure": factor_exposure,
                }
    except Exception as e:
        logger.debug("portfolio_doctor_v2: %s", e)
    logger.info("[dashboard] section: portfolio_doctor_v2 %.0f ms", (time.perf_counter() - t0) * 1000)

    # Macro analog: historical one-liner when VIX + real yield match current state
    macro_analog = None
    try:
        macro_analog = get_macro_analog(vix_val, real_yield, config, period=config.get("data", {}).get("period_long", "13y"))
    except Exception as e:
        logger.debug("Macro analog failed: %s", e)

    market_forecast = None
    try:
        market_forecast = build_market_forecast_brief(
            config,
            macro_regime=macro_regime,
            real_yield=real_yield,
            vix=vix_val,
            cross_asset=cross_asset,
            economic_calendar=economic_calendar,
        )
    except Exception as e:
        logger.debug("Market forecast brief failed: %s", e)

    # Market/sector regime (breadth proxy, tech leadership, rotation risk) and rotation step-down for tech
    try:
        market_regime_data = get_market_regime(period="6mo", vix=vix_val, real_yield=real_yield)
        results = apply_rotation_step_down(results, market_regime_data)
    except Exception:
        market_regime_data = {}

    # Next-day outlook and typical move (SPY, QQQ, GLD, SLV)
    next_day_outlook = []
    typical_move = []
    try:
        from signals.cache import cached_next_day_backtest
        backtest_cache = {}
        for sym in ["SPY", "QQQ", "GLD", "SLV"]:
            try:
                backtest_cache[sym] = cached_next_day_backtest(sym, lambda s=sym: run_next_day_backtest(s, period="5y"))
            except Exception:
                pass
        next_day_outlook = next_day_outlook_for_symbols(["SPY", "QQQ", "GLD", "SLV"], backtest_cache)
    except Exception:
        next_day_outlook = next_day_outlook_for_symbols(["SPY", "QQQ", "GLD", "SLV"])
    try:
        typical_move = typical_move_for_symbols(["SPY", "QQQ", "GLD", "SLV"])
    except Exception:
        typical_move = []

    # Indicator validation: our next-day bias vs external (Yahoo analyst consensus)
    indicator_validation = []
    try:
        indicator_validation = validate_indicators_vs_external(next_day_outlook)
    except Exception as e:
        logger.debug("Indicator validation failed: %s", e)

    # Indicator comparison: close, RSI, bias vs Alpha Vantage, Polygon, Finnhub (margin of error)
    indicator_comparisons = []
    try:
        compare_tickers = ["SPY", "QQQ", "GLD", "SLV"]
        our_by_ticker = {
            r["ticker"]: {
                "close": r.get("close"),
                "rsi": r.get("rsi"),
                "ma20": r.get("ma20"),
                "ma50": r.get("ma50"),
                "macd_hist": r.get("macd_hist"),
            }
            for r in results
            if not r.get("error") and r.get("ticker") in compare_tickers
        }
        indicator_comparisons = run_indicator_comparison(config, our_by_ticker, next_day_outlook, tickers=compare_tickers)
    except Exception as e:
        logger.debug("Indicator comparison failed: %s", e)

    # (forward_tracking, paper_trading sync, pre_market, pre_market_full, eod_snapshots, redis_status, insider_flow, fmp_plan_status loaded in parallel above)

    # Opportunities scan: lazy via GET /api/dashboard/opportunities-bundle when enabled.
    opp_bundle_on = _opportunities_bundle_enabled(config)
    opportunities: list = []

    # Watchlist 7-layer confidence: lazy (roadmaps / ticker detail / opportunities-bundle). Holdings only above.
    for r in results:
        if r.get("error"):
            continue
        t = r.get("ticker")
        co = confidence_by_ticker.get(t) if t else None
        if isinstance(co, dict):
            r["plan_action"] = co.get("action")
            r["plan_confidence"] = co.get("confidence")
        else:
            r["plan_action"] = None
            r["plan_confidence"] = None

    # Align horizon suggestion strings with 7-layer plan when plan says de-risk (matches roadmap tone)
    for r in results:
        if r.get("error"):
            continue
        pa = (r.get("plan_action") or "").upper()
        if "AVOID" in pa:
            for k in ("short_suggestion", "medium_suggestion", "long_suggestion"):
                r[k] = "HOLD"
        elif "REDUCE" in pa:
            for k in ("short_suggestion", "medium_suggestion", "long_suggestion"):
                v = r.get(k)
                if isinstance(v, str) and "ADD" in v.upper():
                    r[k] = "HOLD"

    # Retail status tokens for frontend (gates, rsi_status, gate_cleared) — after plan_action/confidence
    try:
        from signals.retail_action_payload import enrich_dashboard_signal_row

        _hmm_bear = macro_regime_bundle.get("hmm_bear_pct_used") if isinstance(macro_regime_bundle, dict) else None
        _regime_bull_global = (100.0 - float(_hmm_bear)) if _hmm_bear is not None else None
        for r in results:
            if r.get("error"):
                continue
            # Prefer this ticker's own HMM bull % (set in run_daily._process_single_ticker);
            # the market-wide proxy is a fallback only, not an override — otherwise every
            # ticker's regime gate collapses to the same market-wide number.
            _rb = r.get("regime_bull_pct")
            enrich_dashboard_signal_row(r, regime_bull_pct=_rb if _rb is not None else _regime_bull_global)
        try:
            from signals.readiness_score import compute_readiness

            for r in results:
                if r.get("error"):
                    continue
                r.update(compute_readiness(r))
        except Exception as e:
            logger.debug("readiness recompute after enrich: %s", e)
    except Exception as e:
        logger.debug("retail_status enrich: %s", e)

    # Portfolio Doctor trim/add $ recommendations.
    if opp_bundle_on:
        portfolio_doctor_recommendations: dict = {}
        opportunities_deferred = True
        logger.info("[dashboard] portfolio_doctor recommendations deferred (opportunities-bundle)")
    else:
        portfolio_doctor_recommendations = _doctor_recommendations_for_portfolios(
            config, portfolios_out, results, [], confidence_by_ticker
        )
        opportunities_deferred = False
        logger.info("[dashboard] portfolio_doctor trim-only (opportunities bundle disabled)")

    # Performance vs benchmark (portfolio vs SPY/QQQ over 1m, 3m, 6m, 1y)
    performance_vs_benchmark = {"periods": [], "as_of": None, "message": None}
    t0_perf = time.perf_counter()
    if holdings and (portfolios_cfg or config.get("portfolio")):
        try:
            merged_prices = dict(prices_by_ticker) if prices_by_ticker else {}
            for r in results:
                if not r.get("error") and r.get("close") is not None:
                    merged_prices[r["ticker"]] = float(r["close"])
            if "SPY" not in merged_prices or "QQQ" not in merged_prices:
                yf_prices = fetch_yfinance_latest_prices(["SPY", "QQQ"])
                if yf_prices:
                    merged_prices.update(yf_prices)
            performance_vs_benchmark = compute_performance_vs_benchmark(
                holdings=holdings,
                prices_by_ticker=merged_prices,
                fetcher=fetch_ohlcv_safe,
            )
            if performance_vs_benchmark.get("periods"):
                logger.info("[dashboard] section: performance_vs_benchmark DONE (%d periods, %.0f ms)", len(performance_vs_benchmark["periods"]), (time.perf_counter() - t0_perf) * 1000)
            else:
                performance_vs_benchmark["message"] = performance_vs_benchmark.get("message") or "Insufficient history"
                logger.info("[dashboard] section: performance_vs_benchmark DONE (no periods, %.0f ms)", (time.perf_counter() - t0_perf) * 1000)
        except Exception as e:
            logger.debug("Performance vs benchmark failed: %s", e)
            performance_vs_benchmark["message"] = str(e)
            logger.info("[dashboard] section: performance_vs_benchmark failed (%.0f ms)", (time.perf_counter() - t0_perf) * 1000)
    else:
        performance_vs_benchmark["message"] = "Add portfolios in config to see performance vs benchmark"

    t0 = time.perf_counter()
    logger.info("[dashboard] section: thesis_check + what_changed...")
    theses = load_theses()
    story_changes = [r for r in results if r.get("story_change")]

    thesis_check = []
    for r in results:
        if r.get("error"):
            continue
        t = theses.get(r["ticker"])
        if not t:
            continue
        prev_row = last_run_prev.get(r["ticker"]) if last_run_prev else None
        nudge = get_nudge(
            r["ticker"],
            r.get("regime", ""),
            r.get("composite_buy"),
            theses,
            prev_regime=(prev_row or {}).get("regime") if prev_row else None,
            prev_score=(prev_row or {}).get("composite_buy") if prev_row else None,
        )
        thesis_check.append({
            "ticker": r["ticker"],
            "thesis": t.get("thesis", ""),
            "exit_condition": t.get("exit_condition", ""),
            "nudge": nudge,
        })

    from signals.alert_provenance import build_trim_candidates_from_holdings

    trim_candidates = build_trim_candidates_from_holdings(
        report.get("per_holding") or [],
        sell_max=sell_max_trim,
        signals_by_ticker=signals_by_ticker,
        trim_cfg=trim_cfg,
    )

    # Tax-aware exit optimizer: positions approaching 1-year LTCG threshold (federal + SC state)
    tax_aware_exits_out: dict = {"items": [], "message": None}
    try:
        from portfolio.tax_aware_exit import tax_aware_exits as _tax_aware_exits
        tax_cfg = config.get("tax_aware_exit") or {}
        tax_aware_exits_out = _tax_aware_exits(
            report.get("per_holding") or [],
            results,
            config=config,
            taxable_accounts=tax_cfg.get("taxable_accounts"),
        )
    except Exception as e:
        logger.debug("Tax-aware exits failed: %s", e)

    # What changed: compare new results vs previous run (before we overwrite)
    what_changed_list = []
    for r in results:
        if r.get("error"):
            continue
        prev = last_run_prev.get(r["ticker"]) if last_run_prev else None
        if not prev:
            continue
        diffs, summary = what_changed(prev, r)
        if diffs:
            what_changed_list.append({"ticker": r["ticker"], "changes": diffs, "summary": summary})
    logger.info("[dashboard] section: thesis_check + what_changed DONE (%d changed, %.0f ms)", len(what_changed_list), (time.perf_counter() - t0) * 1000)

    # Earnings risk count (holdings with earnings in next 7 days)
    earnings_warn_days = config.get("earnings", {}).get("days_warning", 14)
    earnings_caution_days = min(7, earnings_warn_days)
    earnings_risk_count = 0
    results_by_ticker = {r["ticker"]: r for r in results if not r.get("error")}
    portfolio_ticker_set = {h.get("ticker") if isinstance(h, dict) else h for h in holdings}
    for t in portfolio_ticker_set:
        r = results_by_ticker.get(t)
        if not r or not r.get("earnings_note"):
            continue
        # Parse "Earnings in X days"
        import re as _re
        m = _re.search(r"Earnings in (\d+) days", r.get("earnings_note", "") or "")
        if m and 0 <= int(m.group(1)) <= earnings_caution_days:
            earnings_risk_count += 1

    # Risk sizing for signals
    t0 = time.perf_counter()
    logger.info("[dashboard] section: risk_sizing + save_last_run...")
    risk_cfg = config.get("risk_sizing", {}) or {}
    risk_pct = risk_cfg.get("risk_pct", 1)
    stop_pct = risk_cfg.get("default_stop_pct", 10)
    total_value = report.get("total_value", 0) or 0
    for r in results:
        if r.get("error") or r.get("close") is None or total_value <= 0:
            r["risk_sizing"] = None
            continue
        try:
            risk_budget_dollars = total_value * (risk_pct / 100.0)
            size_dollars = total_value * (risk_pct / 100) / (stop_pct / 100)
            shares = max(0, int(size_dollars / float(r["close"])))
            # Max shares for 1% portfolio risk (retail preset)
            size_1pct = total_value * 0.01 / (stop_pct / 100.0)
            shares_1pct = max(0, int(size_1pct / float(r["close"])))
            r["risk_sizing"] = {
                "size_dollars": round(size_dollars, 0),
                "shares": shares,
                "shares_1pct_risk": shares_1pct,
                "stop_pct": stop_pct,
                "risk_budget_dollars": round(risk_budget_dollars, 2),
                "risk_pct": risk_pct,
            }
        except (TypeError, ZeroDivisionError):
            r["risk_sizing"] = None

    try:
        from signals.portfolio_stress import enrich_signal_uncertainty

        for r in results:
            if not r.get("error"):
                enrich_signal_uncertainty(r)
    except Exception as e:
        logger.debug("enrich_signal_uncertainty: %s", e)

    try:
        from signals.earnings_quality_batch import enrich_results_earnings_quality

        enrich_results_earnings_quality(config, results)
    except Exception as e:
        logger.debug("enrich_results_earnings_quality: %s", e)

    try:
        from portfolio.liquidity import enrich_results_liquidity

        enrich_results_liquidity(results)
    except Exception as e:
        logger.debug("enrich_results_liquidity: %s", e)

    try:
        from signals.catalyst_batch import enrich_results_catalysts

        enrich_results_catalysts(config, results)
    except Exception as e:
        logger.debug("enrich_results_catalysts: %s", e)

    _vix_level = None
    for item in cross_asset or []:
        if isinstance(item, dict) and str(item.get("label") or item.get("ticker") or "").upper() in ("VIX", "^VIX"):
            try:
                _vix_level = float(item.get("close") or item.get("value") or item.get("last"))
            except (TypeError, ValueError):
                pass
            break

    try:
        from signals.signal_event_modifiers import enrich_results_event_modifiers

        enrich_results_event_modifiers(results, config, vix=_vix_level)
    except Exception as e:
        logger.debug("enrich_results_event_modifiers: %s", e)

    retail_alerts_refresh = None
    try:
        from scanner.horizon_levels import sync_horizon_levels_from_signal_results

        _nhl = sync_horizon_levels_from_signal_results(get_data_root(), results)
        logger.info("[dashboard] scanner horizon_levels synced (%d tickers with bands/ML)", _nhl)
    except Exception as e:
        logger.debug("horizon_levels sync: %s", e)

    try:
        from scanner.dashboard_alerts import run_retail_alerts_from_dashboard_refresh

        retail_alerts_refresh = run_retail_alerts_from_dashboard_refresh(
            results,
            config,
            get_data_root(),
            prices_by_ticker=prices_by_ticker,
            vix=_vix_level,
        )
    except Exception as e:
        logger.warning("[dashboard] retail alerts after refresh failed: %s", e)

    save_last_run(results)  # Save AFTER building what_changed
    try:
        eod_auto = maybe_save_eod_from_last_run()
        if eod_auto and not eod_auto.get("skipped"):
            logger.info(
                "[dashboard] auto EOD snapshot %s (%s tickers)",
                eod_auto.get("snapshot_date"),
                eod_auto.get("tickers_count"),
            )
        elif eod_auto and eod_auto.get("reason") in (
            "dashboard_only_universe",
            "dashboard_fallback",
        ):
            logger.info(
                "[dashboard] refresh is dashboard-only (%s/%s tickers) reason=%s — "
                "full cohort runs at 8pm ET (EOD scheduler) or POST /api/eod/run",
                eod_auto.get("tickers_count"),
                eod_auto.get("expected_min"),
                eod_auto.get("reason"),
            )
            try:
                from api.eod_job import trigger_full_eod_background_if_missing

                if trigger_full_eod_background_if_missing(min_hour_et=20):
                    logger.info("[dashboard] queued background full EOD (missing after 8pm ET)")
            except Exception as eod_exc:
                logger.debug("[dashboard] full EOD safety-net skipped: %s", eod_exc)
    except Exception as e:
        logger.debug("Auto EOD snapshot skipped: %s", e)
    logger.info("[dashboard] section: risk_sizing + save_last_run DONE (%.0f ms)", (time.perf_counter() - t0) * 1000)

    # Tier 1 risk features (position sizing, drawdown, exits, earnings, concentration)
    tier1_payload = {}
    if generate_tier1_payload and report.get("per_holding") and report.get("total_value"):
        try:
            holdings_for_tier1 = [
                {"ticker": h["ticker"], "value": float(h.get("value") or 0), "cost_basis": h.get("cost_basis")}
                for h in report["per_holding"]
                if h.get("value") is not None and (h.get("value") or 0) > 0
            ]
            signals_for_tier1 = [
                {
                    "ticker": r["ticker"],
                    "score": float(r.get("composite_buy") or 50),
                    "confidence": (
                        float(confidence_by_ticker.get(r["ticker"], {}).get("confidence"))
                        if isinstance(confidence_by_ticker.get(r["ticker"]), dict) and confidence_by_ticker.get(r["ticker"], {}).get("confidence") is not None
                        else min(1.0, max(0, (r.get("composite_buy") or 50) / 100))
                    ),
                    # Let Tier1 engine derive win rate dynamically (avoids hardcoded 60%)
                    "win_rate": None,
                    "avg_win_pct": 7.0,
                    "avg_loss_pct": 4.0,
                }
                for r in results
                if not r.get("error") and r.get("ticker")
            ]
            portfolio_value_t1 = float(report.get("total_value") or 100_000)
            regime_t1 = next(
                (r.get("_global_market_regime") for r in results if not r.get("error") and r.get("_global_market_regime")),
                "BULL",
            )
            # Limit tickers to avoid long yfinance fetches
            all_tickers = list(dict.fromkeys([h["ticker"] for h in holdings_for_tier1] + [s["ticker"] for s in signals_for_tier1]))[:15]
            holdings_for_tier1 = [h for h in holdings_for_tier1 if h["ticker"] in all_tickers]
            signals_for_tier1 = [s for s in signals_for_tier1 if s["ticker"] in all_tickers]
            if holdings_for_tier1 or signals_for_tier1:
                tier1_payload = generate_tier1_payload(
                    holdings=holdings_for_tier1,
                    signals=signals_for_tier1,
                    portfolio_value=portfolio_value_t1,
                    regime=regime_t1,
                    risk_tolerance=RiskTolerance(get_risk_profile(config)),
                    horizon="medium",
                )
                logger.info("[dashboard] Tier 1 risk payload: sizing=%d drawdown=%d exits=%d earnings=%d",
                    len(tier1_payload.get("position_sizing", [])),
                    len(tier1_payload.get("drawdown_sim", [])),
                    len(tier1_payload.get("exit_levels", [])),
                    len(tier1_payload.get("earnings_impacts", [])),
                )
        except Exception as e:
            logger.warning("[dashboard] Tier 1 risk engine failed: %s", e)

    if not tier1_payload.get("position_sizing") and report.get("per_holding") and report.get("total_value"):
        try:
            tier1_payload = _tier1_lightweight_fallback(
                report,
                results,
                portfolio_value=float(report.get("total_value") or 0),
                risk_profile=get_risk_profile(config),
            )
            if tier1_payload:
                logger.info(
                    "[dashboard] Tier 1 lightweight fallback: sizing=%d drawdown=%d earnings=%d",
                    len(tier1_payload.get("position_sizing", [])),
                    len(tier1_payload.get("drawdown_sim", [])),
                    len(tier1_payload.get("earnings_impacts", [])),
                )
        except Exception as e:
            logger.debug("[dashboard] Tier 1 fallback failed: %s", e)

    from signals.time_et import format_et_display, now_iso_et

    as_of_date = now_iso_et()
    as_of_et = format_et_display()

    ohlcv_dates: list[str] = []
    for r in results or []:
        if isinstance(r, dict) and r.get("ohlcv_last_date"):
            ohlcv_dates.append(str(r["ohlcv_last_date"])[:10])
    price_last_bar_date = max(ohlcv_dates) if ohlcv_dates else None
    eod_latest_date = None
    eod_saved_at = None
    if eod_snapshots and isinstance(eod_snapshots, list) and len(eod_snapshots) > 0:
        e0 = eod_snapshots[0]
        if isinstance(e0, dict):
            eod_latest_date = e0.get("date")
            eod_saved_at = e0.get("run_date") or e0.get("saved_at")

    data_freshness = {
        "as_of_et": as_of_et,
        "snapshot_updated_at": as_of_date,
        "snapshot_updated_et": as_of_et,
        "signals_updated_at": as_of_date,
        "quotes_updated_at": as_of_date,
        "eod_snapshot_saved_at": eod_saved_at,
        "prices": "Daily adjusted close from the data pipeline (typically prior session close vs. run time).",
        "fundamentals": "FMP / estimates can lag filings; not point-in-time perfect for backtests.",
        "macro": "FRED / cross-asset as of last observation before this run.",
        "disclaimer": "Signals are model output, not investment advice.",
        "price_last_bar_date": price_last_bar_date,
        "eod_snapshot_latest_date": eod_latest_date,
        "precision_note": (
            "Targets and stops are model ranges and thresholds, not guaranteed prices."
        ),
    }
    try:
        from signals.data_degraded import build_degraded_sources, degraded_mode_active

        degraded_sources = build_degraded_sources(config)
        data_freshness["degraded_sources"] = degraded_sources
        data_freshness["degraded_mode"] = degraded_mode_active(degraded_sources)
    except Exception as deg_err:
        logger.debug("degraded_sources: %s", deg_err)

    paper_vs_backtest_drift = None
    try:
        from signals.paper_vs_backtest_drift import build_paper_vs_backtest_drift

        paper_vs_backtest_drift = build_paper_vs_backtest_drift(forward_tracking, data_root)
    except Exception as e:
        logger.debug("paper_vs_backtest_drift: %s", e)

    portfolio_stress: dict = {}
    try:
        from signals.portfolio_stress import build_portfolio_stress_scenarios

        portfolio_stress = build_portfolio_stress_scenarios(report)
    except Exception as e:
        logger.debug("portfolio_stress: %s", e)

    # Retail value-add: daily briefing, portfolio heat, one-line actions, badges, nudges
    retail_briefing = {}
    try:
        from retail_briefing import build_retail_briefing

        plan_actions_for_retail = {
            t: c.get("action")
            for t, c in confidence_by_ticker.items()
            if isinstance(c, dict) and c.get("action")
        }
        retail_briefing = build_retail_briefing(
            results=results,
            report=report,
            data_root=data_root,
            opportunities=opportunities,
            tax_aware_exits=tax_aware_exits_out,
            earnings_risk_count=earnings_risk_count,
            macro_regime=macro_regime,
            risk_pct=risk_pct,
            stop_pct=stop_pct,
            paper_trading=paper_trading,
            thesis_check=thesis_check,
            config=config,
            plan_actions=plan_actions_for_retail,
        )
    except Exception as e:
        logger.debug("Retail briefing failed: %s", e)

    _pm_report: dict | None = None
    try:
        import json as _json

        _pm_path = data_root / "pre_market_latest.json"
        if _pm_path.exists():
            _pm_report = _json.loads(_pm_path.read_text())
            if isinstance(_pm_report, dict):
                _pm_report = _premarket_with_catalysts(_pm_report)
    except Exception:
        pass

    retail_market_decisions = None
    try:
        from signals.market_flip_stats import load_market_flip_stats
        from signals.retail_market_decisions import build_retail_market_decisions

        _pm_catalysts = None
        try:
            if _pm_report and isinstance(_pm_report, dict):
                _pm_catalysts = _pm_report.get("market_catalysts")
        except Exception:
            pass
        _global_regime = next(
            (r.get("_global_market_regime") for r in results if not r.get("error") and r.get("_global_market_regime")),
            None,
        )
        retail_market_decisions = build_retail_market_decisions(
            config=config,
            macro_regime=macro_regime,
            global_market_regime=_global_regime,
            macro_regime_bundle=macro_regime_bundle,
            market_regime=market_regime_data,
            market_catalysts=_pm_catalysts,
            portfolio_doctor_v2=portfolio_doctor_v2,
            retail_briefing=retail_briefing,
            per_holding=report.get("per_holding") if isinstance(report, dict) else None,
            avg_portfolio_score=report.get("avg_score") if isinstance(report, dict) else None,
            flip_stats=load_market_flip_stats(),
            cross_asset=cross_asset,
            premarket=_pm_report if isinstance(_pm_report, dict) else None,
            data_root=data_root,
        )
    except Exception as e:
        logger.debug("retail_market_decisions: %s", e)

    morning_newsletter = None
    try:
        from signals.morning_newsletter import build_morning_newsletter

        _rmd = retail_market_decisions if isinstance(retail_market_decisions, dict) else {}
        morning_newsletter = build_morning_newsletter(
            as_of_date=as_of_date,
            macro_regime=macro_regime,
            macro_analog=macro_analog,
            market_regime=market_regime_data,
            retail_briefing=retail_briefing,
            earnings_risk_count=earnings_risk_count or 0,
            forward_tracking=forward_tracking,
            results=results,
            model_rules=config.get("model_rules"),
            trim_candidates=trim_candidates,
            regime_validation=regime_validation,
            premarket_report=_pm_report,
            market_context=_rmd.get("market_context"),
            hold_vs_trade=_rmd.get("hold_vs_trade"),
            trigger_levels=_rmd.get("trigger_levels"),
        )
    except Exception as e:
        logger.debug("Morning newsletter failed: %s", e)

    model_health: dict = {}
    try:
        model_health = build_model_health(
            data_root,
            config,
            forward_tracking,
            eod_snapshots,
        )
    except Exception as e:
        logger.debug("model_health failed: %s", e)

    raw_kl = config.get("known_limits")
    if isinstance(raw_kl, list) and len(raw_kl) > 0:
        known_limits_list = [str(x).strip() for x in raw_kl if str(x).strip()]
    else:
        known_limits_list = list(DEFAULT_KNOWN_LIMITS)

    if retail_market_decisions:
        try:
            _global_regime = next(
                (r.get("_global_market_regime") for r in results if not r.get("error") and r.get("_global_market_regime")),
                None,
            )
            market_forecast = build_market_forecast_brief(
                config,
                macro_regime=macro_regime,
                real_yield=real_yield,
                vix=vix_val,
                cross_asset=cross_asset,
                economic_calendar=economic_calendar,
                market_context=(retail_market_decisions or {}).get("market_context"),
                global_market_regime=_global_regime,
            )
        except Exception as e:
            logger.debug("Market forecast reconcile: %s", e)

    try:
        from signals.pre_ipo import build_pre_ipo_panel

        pre_ipo_results = {
            str(r["ticker"]).upper(): r
            for r in results
            if isinstance(r, dict) and r.get("ticker") and not r.get("error")
        }
        pre_ipo_panel = build_pre_ipo_panel(config, results_by_ticker=pre_ipo_results)
    except Exception as pre_ipo_err:
        logger.debug("pre_ipo panel failed: %s", pre_ipo_err)
        pre_ipo_panel = {"enabled": False, "items": []}

    out = {
        "as_of_date": as_of_date,
        "data_freshness": data_freshness,
        "portfolio_stress": portfolio_stress,
        "known_limits": known_limits_list,
        "signals": results,
        "retail_briefing": retail_briefing,
        "retail_market_decisions": retail_market_decisions,
        "crypto": crypto_signals,
        "pre_ipo": pre_ipo_panel,
        "cross_asset": cross_asset,
        "economic_calendar": economic_calendar,
        "market_scenarios": market_scenarios,
        "macro_analog": macro_analog,
        "market_forecast": market_forecast,
        "guidelines": guidelines,
        "macro_regime": macro_regime,
        "macro_regime_bundle": macro_regime_bundle,
        "portfolio_risk_metrics": portfolio_risk_metrics,
        "portfolio_doctor_v2": portfolio_doctor_v2,
        "market_reversal_overlay": market_reversal_overlay,
        "market_regime": market_regime_data,
        "global_market_regime": next(
            (r.get("_global_market_regime") for r in results if not r.get("error") and r.get("_global_market_regime")),
            None,
        ),
        "next_day_outlook": next_day_outlook,
        "typical_move": typical_move,
        "indicator_validation": indicator_validation,
        "indicator_comparisons": indicator_comparisons,
        "forward_tracking": forward_tracking,
        "regime_validation": regime_validation,
        "confidence_calibration": confidence_calibration,
        "paper_vs_backtest_drift": paper_vs_backtest_drift,
        "paper_trading": paper_trading,
        "pre_market": pre_market,
        "pre_market_full": pre_market_full,
        "eod_snapshots": eod_snapshots,
        "data_root": str(data_root),
        "redis_status": redis_status_out,
        "insider_flow": insider_flow,
        "cot_by_ticker": cot_by_ticker,
        "fmp_plan_status": fmp_plan_status,
        "story_changes": story_changes,
        "portfolio": report,
        "portfolios": portfolios_out,
        "portfolio_names": portfolio_names,
        "portfolio_doctor_recommendations": portfolio_doctor_recommendations,
        "risk_profile": get_risk_profile(config),
        "performance_vs_benchmark": performance_vs_benchmark,
        "tax_aware_exits": tax_aware_exits_out,
        "trim_candidates": trim_candidates,
        "opportunities": opportunities,
        "opportunities_bundle_enabled": opp_bundle_on,
        "opportunities_deferred": opportunities_deferred,
        "analysis_deferred": True,
        "watchlist": watchlist,
        "signal_universe": signal_universe,
        "universe_meta": get_universe_meta(config),
        "signal_scores": _build_signal_scores(results),
        "thesis_check": thesis_check,
        "what_changed": what_changed_list,
        "earnings_risk_count": earnings_risk_count,
        "morning_newsletter": morning_newsletter,
        "model_health": model_health,
        "tactical_breakouts": _build_tactical_breakouts(results, config),
        "event_risk_strip": _build_event_risk_strip(results, config),
        "hunter_panel": _build_hunter_panel_payload(
            results,
            config,
            signal_universe=signal_universe,
            as_of=as_of_date,
        ),
        "retail_alerts_refresh": retail_alerts_refresh,
        "config": {
            "watchlist": config.get("watchlist", []),
            "score": config.get("score", {}),
            "regime": config.get("regime", {}),
            "risk_sizing": {"risk_pct": risk_pct, "stop_pct": stop_pct},
            "concentration_alert_pct": config.get("concentration_alert_pct", 20),
            "model_rules": config.get("model_rules") or {"add_min_confidence": 70, "trim_max_confidence": 30, "add_min_regime": "UP"},
            "horizons": {
                "short_term": "~1 month (2–4 weeks)",
                "medium_term": "~3–6 months",
                "long_term": "1–2 years",
            },
            "regime_plain_english": {
                "UP": "Trend and momentum support the position; favor holding or adding on pullbacks.",
                "NEUTRAL": "Mixed signals; hold, avoid large new adds until clarity.",
                "DOWN": "Weak trend or momentum; consider trimming or avoiding new buys.",
            },
        },
    }
    out.update(tier1_payload)
    try:
        from behavior.push_digest import maybe_broadcast_retail_push

        trim_ts = [h["ticker"] for h in trim_candidates if h.get("ticker")]
        push_out = maybe_broadcast_retail_push(
            config,
            story_changes=story_changes,
            trim_tickers=trim_ts,
        )
        if push_out.get("sent"):
            logger.info("[dashboard] web push digest sent (%s)", push_out.get("fingerprint"))
    except Exception as e:
        logger.debug("[dashboard] web push digest skipped: %s", e)
    cache_ok = False
    # Stamp a per-refresh ISO timestamp + signal count so the frontend can detect new runs on
    # the same day (as_of_date alone is a date string — unchanged between same-day refreshes).
    import time as _time
    out["refresh_ts"] = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
    out["signals_count"] = len(results)
    df = out.get("data_freshness")
    if isinstance(df, dict):
        df["snapshot_updated_at"] = out["refresh_ts"]
    try:
        from signals.overnight_delta import save_overnight_baseline, snapshot_for_baseline

        save_overnight_baseline(data_root, snapshot_for_baseline(cross_asset, macro_regime_bundle))
    except Exception as e:
        logger.debug("[dashboard] overnight baseline: %s", e)
    try:
        from signals.cache import set_cached_dashboard
        cache_ok = bool(set_cached_dashboard(out))
    except Exception as e:
        logger.debug("[dashboard] cache set skipped: %s", e)

    # Write dedicated per-panel Redis keys — separate from the large dashboard payload.
    # More reliable on memory-constrained Redis; survives TTL expiry of the main cache.
    try:
        from signals.cache import set_universe_signals, set_signals_panel
        from config_loader import get_eod_signal_universe

        universe_rows, universe_source = _resolve_universe_cache_rows(config, results)
        eod_uni_n = len(get_eod_signal_universe(config))
        ok_uni = set_universe_signals(universe_rows, as_of=as_of_date)
        try:
            from signals.cache import set_eod_universe_panel

            shaped_uni = _shape_universe_rows(universe_rows, as_of_date)
            shaped_uni["source"] = universe_source
            set_eod_universe_panel(shaped_uni)
        except Exception as e:
            logger.debug("[dashboard] eod_universe_panel cache: %s", e)
        ok_sig = set_signals_panel(results, as_of=as_of_date)
        logger.info(
            "[dashboard] panel caches: universe_signals=%s (%d rows, source=%s, eod_universe=%d), "
            "signals_panel=%s (%d rows, source=dashboard)",
            "ok" if ok_uni else "FAILED",
            len(universe_rows),
            universe_source,
            eod_uni_n,
            "ok" if ok_sig else "FAILED",
            len(results),
        )
        if universe_source == "dashboard" and len(universe_rows) < eod_uni_n:
            logger.info(
                "[dashboard] universe_signals is dashboard-only (%d/%d) — run EOD scheduler (8pm ET) "
                "or POST /api/eod/run?force=true to populate full cohort",
                len(universe_rows),
                eod_uni_n,
            )
    except Exception as e:
        logger.warning("[dashboard] panel cache error: %s", e)

    try:
        _ensure_analysis_background_compute()
    except Exception as e:
        logger.debug("[dashboard] analysis background trigger skipped: %s", e)

    logger.info("[dashboard] END loading dashboard - total %.0f ms", (time.perf_counter() - dashboard_start) * 1000)
    return out



@router.get("/dashboard/opportunities-bundle")
async def get_dashboard_opportunities_bundle():
    """Lazy load: opportunity scan + Portfolio Doctor add-side (uses cached dashboard signals)."""
    try:
        out = compute_opportunities_bundle()
    except Exception as e:
        logger.exception("opportunities-bundle compute failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    if out is None:
        if _is_dashboard_warming():
            warm = _empty_opportunities_bundle(enabled=False)
            warm["warming"] = True
            return jsonable_encoder(warm)
        raise HTTPException(
            status_code=503,
            detail="Dashboard cache unavailable. Load the dashboard or click Refresh, then try again.",
        )
    return jsonable_encoder(out)


@router.get("/dashboard/analysis-bundle/job-status")
async def get_analysis_bundle_job_status():
    """
    Diagnostic: is the background analysis-bundle recompute idle/running/done/error, and when
    did it last finish? Added because there was previously no way to tell from outside the
    process whether a stale Analysis tab (e.g. forward-tracking stuck weeks behind the live
    EOD snapshot dates) meant "never triggered," "stuck running," or "failing every attempt" —
    _ensure_analysis_background_compute() only fires when the cache-only read misses, so a
    STALE-BUT-PRESENT cached bundle (the actual observed symptom) never re-triggers a compute
    at all; this at least surfaces whether the last attempt (if any) succeeded or why not.
    """
    from api.analysis_bundle_job import get_analysis_job_status

    return get_analysis_job_status()


@router.get("/dashboard/analysis-bundle")
async def get_dashboard_analysis_bundle():
    """Lazy load: Analysis tab sections (paper trading, forward tracking, insider, validation)."""
    try:
        out = compute_analysis_bundle(allow_heavy=False)
    except Exception as e:
        logger.exception("analysis-bundle compute failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

    if out is not None:
        return jsonable_encoder(_slim_analysis_for_http(out))

    if _is_dashboard_warming():
        return jsonable_encoder(_analysis_warming_response())

    try:
        from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot

        cached = get_cached_dashboard() or get_last_dashboard_snapshot()
    except Exception:
        cached = None
    if cached is None or not isinstance(cached.get("signals"), list):
        raise HTTPException(
            status_code=503,
            detail="Dashboard cache unavailable. Load the dashboard or click Refresh, then open Analysis.",
        )

    _ensure_analysis_background_compute()
    logger.info("[analysis-bundle] returning warming shell (background compute triggered or running)")
    return jsonable_encoder(_analysis_warming_response())


@router.get("/dashboard/analysis/forward-tracking")
async def get_analysis_forward_tracking():
    """Forward outcomes panel — small dedicated cache (avoids monolithic bundle 502)."""
    return _analysis_slice_response("forward_tracking")


@router.get("/dashboard/analysis/model-audit")
async def get_analysis_model_audit():
    """100-ticker gate audit panel — small dedicated cache."""
    return _analysis_slice_response("model_audit")


@router.get("/dashboard/analysis/paper-trading")
async def get_analysis_paper_trading():
    """Paper trading panel — small dedicated cache."""
    return _analysis_slice_response("paper_trading")


@router.get("/dashboard/signals-panel")
async def get_dashboard_signals_panel():
    """Per-ticker signal rows for the Signals table (strips heavy investor_summary to keep response lean)."""
    # Fields only needed in TickerDetailModal — strip them here to avoid 502 on large payloads.
    _HEAVY_KEYS = frozenset({"investor_summary", "horizons_detail", "valuation_deck"})

    def _slim(rows: list) -> list:
        out = []
        for row in rows:
            if not isinstance(row, dict):
                out.append(row)
                continue
            out.append({k: v for k, v in row.items() if k not in _HEAVY_KEYS})
        return out

    try:
        from signals.cache import get_signals_panel, get_universe_signals

        # Priority 1: dedicated signals-panel key (already stripped; survives Redis pressure)
        sp = get_signals_panel()
        if sp and isinstance(sp.get("signals"), list) and len(sp["signals"]) > 0:
            logger.info("[signals-panel] signals_panel key hit: %d rows", len(sp["signals"]))
            return {"signals": sp["signals"]}

        # Priority 2: compact universe_signals — never deserialize the full dashboard blob
        # (multi‑MB JSON under memory pressure hangs the single worker for minutes).
        logger.info("[signals-panel] signals_panel miss — trying universe_signals")
        try:
            uni = get_universe_signals()
            if uni and isinstance(uni.get("rows"), list) and len(uni["rows"]) > 0:
                slim = _slim(uni["rows"])
                logger.info("[signals-panel] universe_signals hit: %d rows", len(slim))
                return {"signals": slim}
        except Exception as e:
            logger.warning("[signals-panel] universe_signals fallback error: %s", e)

        if _is_dashboard_warming():
            logger.info("[signals-panel] warming — compact caches empty")
            return {"signals": [], "warming": True}

        logger.warning("[signals-panel] compact caches empty; dashboard may need a full Refresh")
        return {
            "signals": [],
            "warming": False,
            "message": "No signals found. Click Refresh to populate.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("signals-panel: %s", e)
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/reports/monthly-signal-buckets")
async def get_monthly_signal_buckets():
    """
    Monthly rollup: score buckets (HOLD/ADD, HOLD, CONSIDER TRIM) vs forward returns at EOD horizons 5 and 20.
    Uses stored EOD snapshots under data/eod/. Horizons are snapshot-step counts (see forward_tracking).
    """
    try:
        from signals.monthly_signal_report import build_monthly_signal_report

        return build_monthly_signal_report(data_root=get_data_root())
    except Exception as e:
        logger.warning("monthly_signal_buckets: %s", e)
        return {"months": [], "overall_by_bucket": {}, "message": str(e), "n_records_used": 0}


@router.get("/signals")
async def get_signals():
    """Signals only - faster than full dashboard."""
    config = _load_config()
    results = run_signals(config)
    save_last_run(results)
    return {"signals": results}


def _parse_refresh(raw: Any) -> bool:
    """Accept true / 1 / yes from query string (some clients stringify booleans)."""
    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    s = str(raw).strip().lower()
    return s in ("true", "1", "yes", "on")


@router.get("/backtest")
async def get_backtest(
    tickers: str = "SPY",
    years: int = 2,
    refresh: Any = False,
):
    """
    Backtest results - may take ~1 min per ticker.
    tickers: comma-separated (e.g. SPY,QQQ,GLD), default SPY
    years: 2, 5, or 10, default 2
    refresh: if true, bypass Redis and re-run (use after code/deploy changes; otherwise cached 24h).
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        ticker_list = ["SPY"]
    years = max(2, min(10, years))
    period = f"{years}y"
    force_refresh = _parse_refresh(refresh)
    from scripts.backtest_simple import run_backtest as _run_backtest, walk_forward_backtest
    from signals.backtest_validation import validate_backtest_result
    cfg = _load_config()
    wf_cfg = (cfg.get("backtest") or {}).get("walk_forward") or {}
    wf_enabled = bool(wf_cfg.get("enabled"))
    txn_cost = float(cfg.get("backtest_transaction_cost", 0.003))
    out = []
    from signals.cache import cached_backtest
    for t in ticker_list[:6]:
        def _fetch_backtest(ticker=t, per=period):
            res = _run_backtest(ticker, per, transaction_cost=txn_cost)
            if wf_enabled and res and "error" not in res:
                try:
                    res["walk_forward"] = walk_forward_backtest(
                        ticker,
                        per,
                        train_years=int(wf_cfg.get("train_years", 3)),
                        test_months=int(wf_cfg.get("test_months", 6)),
                        buy_threshold=float(wf_cfg.get("buy_threshold", 70)),
                        transaction_cost=txn_cost,
                    )
                except Exception as e:
                    res["walk_forward"] = {"error": str(e)}
            return res

        result = cached_backtest(t, period, _fetch_backtest, force_refresh=force_refresh)
        if result and "error" not in result:
            result["validation"] = validate_backtest_result(result)
            try:
                from signals.backtest_tiers import build_primary_kpis

                result["primary_kpis"] = build_primary_kpis(result)
            except Exception:
                pass
        out.append(result)
    return {
        "backtest": out,
        "backtest_years": years,
        "backtest_period": period,
        "bypass_cache": force_refresh,
    }


@router.get("/backtest/gates/status")
async def get_gate_backtest_status():
    """
    Status/result of the background gate-cohort walk-forward backtest
    (scripts/backtest_gates.py logic, same computation, run via POST /backtest/gates/run
    instead of a shell). Poll this after starting a run — running=false + last_result
    populated means it finished; last_error populated means it failed.
    """
    from api.gate_backtest_job import gate_backtest_job_state

    return gate_backtest_job_state()


@router.post("/backtest/gates/run")
async def run_gate_backtest(
    tickers: str = "",
    source: str = "eod",
    period: str = "5y",
    step: int = 0,
    eod_days: int = 90,
    horizons: str = "",
    min_gates: int = 4,
    predict_ml: bool = False,
    authorization: str | None = Header(None),
):
    """
    Kick off the gate-cohort backtest (does gates ≥N/4 actually beat raw score
    alone?) in a background thread — mirrors `python scripts/backtest_gates.py`,
    but runs off the request thread so it doesn't block/timeout the caller, and
    doesn't need shell access to the backend service.

    source="eod" (default) uses real frozen daily gate snapshots from data/eod/
    — "production-like fidelity" per the walk-forward UI panel's own guidance,
    since that panel's regime gate falls back to a SPY-vs-SMA proxy rather than
    real per-ticker HMM history. Needs a real EOD history (production has one;
    local dev mostly doesn't) — fails fast with a clear error if <3 snapshot
    days are found. source="walkforward" rebuilds from live OHLCV instead.

    Still real, sustained CPU + live-network work (multi-year OHLCV fetch per
    ticker for forward returns, either source) in the same process as the live
    API — keep `tickers` modest and avoid kicking off a large cohort run during
    high-traffic periods. Single-flight: returns started=false if already running.

    Query params:
      tickers — comma-separated (default: watchlist from config.yaml). Capped at 120.
      source — "eod" (default) or "walkforward".
      period — history window for walkforward source, default 5y.
      step — bar sampling stride for walkforward source; 0 = config default (~5).
      eod_days — max recent EOD snapshot days to use for eod source, default 90.
      horizons — comma-separated trading-day horizons, default from config (21,63,126).
      min_gates — gate count threshold for the "gates_ge_min" cohort (1-4, default 4).
      predict_ml — walkforward source only; run real ML inference per bar instead of
                   leaving the ML gate defaulted to fail. Meaningfully slower.

    If env EOD_RUN_SECRET is set, require header: Authorization: Bearer <secret>
    (same admin-trigger gate as /eod/run — this is comparably expensive).
    Poll GET /backtest/gates/status for progress/result.
    """
    secret = os.environ.get("EOD_RUN_SECRET", "").strip()
    if secret and (authorization or "").strip() != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    from api.gate_backtest_job import start_gate_backtest_job

    config = _load_config()
    ev = config.get("evaluation") or {}

    if tickers.strip():
        ticker_list = sorted({t.strip().upper() for t in tickers.split(",") if t.strip()})
    else:
        ticker_list = [str(t).upper() for t in (config.get("watchlist") or []) if t]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="No tickers: pass ?tickers=... or set watchlist in config.yaml")
    if len(ticker_list) > 120:
        raise HTTPException(status_code=400, detail=f"{len(ticker_list)} tickers requested — capped at 120 to bound run time/resource use.")

    horizons_list = ev.get("horizons_trading_days") or [21, 63, 126]
    if horizons.strip():
        horizons_list = [int(x.strip()) for x in horizons.split(",") if x.strip()]

    started = start_gate_backtest_job(
        tickers=ticker_list,
        source=source,
        period=period,
        step=step,
        eod_days=eod_days,
        horizons=tuple(int(h) for h in horizons_list),
        min_gates_passed=min_gates,
        predict_ml=predict_ml,
    )
    if not started:
        return {
            "started": False,
            "message": "A gate backtest is already running — poll GET /backtest/gates/status.",
        }
    return {
        "started": True,
        "tickers_count": len(ticker_list),
        "source": source,
        "period": period,
        "horizons": horizons_list,
        "message": "Running in background — poll GET /backtest/gates/status for progress/result.",
    }


@router.get("/theses")
async def get_theses():
    """Load thesis storage."""
    return {"theses": load_theses()}


@router.get("/config")
async def get_config():
    """Current config."""
    return _load_config()


@router.get("/behavior/cooldown/{ticker}")
async def get_trim_cooldown(ticker: str):
    """Check whether re-add is blocked after a logged trim."""
    from behavior.trade_discipline import check_add_allowed

    config = _load_config()
    return check_add_allowed(ticker.upper(), config)


@router.post("/behavior/trim-cooldown")
async def post_trim_cooldown(body: dict):
    """Log a trim and start re-add cooldown (default 14 days from config.behavior)."""
    from behavior.trade_discipline import record_trim_cooldown

    ticker = (body.get("ticker") or "").strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    config = _load_config()
    return record_trim_cooldown(ticker, config, note=body.get("note"))


@router.get("/behavior/journal")
async def get_trade_journal(
    limit: int = Query(30, ge=1, le=200),
    ticker: str | None = Query(None, description="Filter by ticker"),
    action: str | None = Query(None, description="Filter by action (add|trim)"),
    q: str | None = Query(None, description="Search note/ticker/action"),
):
    from behavior.trade_discipline import list_journal

    return {
        "entries": list_journal(
            limit,
            ticker=ticker,
            action=action,
            q=q,
        )
    }


@router.post("/behavior/journal")
async def post_trade_journal(body: dict):
    from behavior.trade_discipline import append_journal

    ticker = (body.get("ticker") or "").strip().upper()
    note = (body.get("note") or "").strip()
    action = (body.get("action") or "add").strip().lower()
    if not ticker or not note:
        raise HTTPException(status_code=400, detail="ticker and note required")
    config = _load_config()
    return append_journal(ticker, action, note, config)


@router.post("/tickers")
async def add_ticker_api(body: dict):
    """Add ticker to watchlist (persists in user_overrides, no config edit needed)."""
    from behavior.trade_discipline import append_journal, check_add_allowed

    ticker = body.get("ticker", "").strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    config = _load_config()
    journal_note = (body.get("journal_note") or body.get("note") or "").strip()
    thesis_override = bool(body.get("thesis_override"))
    cd = check_add_allowed(ticker, config, thesis_override=thesis_override)
    if not cd.get("allowed"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"{ticker} on trim cooldown ({cd.get('days_left')} days left). Log a thesis update to override.",
                "cooldown": cd,
            },
        )
    if _add_ticker(ticker):
        if journal_note:
            append_journal(ticker, "add", journal_note, config)
        return {"ok": True, "ticker": ticker}
    return {"ok": False, "ticker": ticker, "message": "Already in watchlist"}


@router.delete("/tickers/{ticker}")
async def remove_ticker_api(ticker: str):
    """Remove ticker from user-added list (only affects additions, not config watchlist)."""
    if _remove_ticker(ticker):
        return {"ok": True, "ticker": ticker.upper()}
    return {"ok": False, "message": "Ticker not in additional list"}


@router.post("/portfolio/risk-profile")
async def set_risk_profile_api(body: dict):
    """Persist the user's risk profile — drives portfolio doctor sizing + Tier1 position sizing."""
    profile = str(body.get("profile") or "").strip().lower()
    if not set_risk_profile(profile):
        raise HTTPException(
            status_code=400, detail="profile must be conservative, moderate, or aggressive"
        )
    return {"ok": True, "profile": profile}


@router.post("/portfolio/upload")
async def upload_portfolio(
    file: UploadFile = File(...),
    portfolio_name: str = Form("Uploaded"),
):
    """
    Upload portfolio from Excel. Expected columns: ticker, quantity (optional: cost_basis).
    portfolio_name: name for this portfolio (e.g. 'IRA', 'Taxable').
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Excel file (.xlsx, .xls) required")
    try:
        import io
        import pandas as pd
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "ticker" not in df.columns and "symbol" not in df.columns:
            raise HTTPException(status_code=400, detail="Excel must have 'ticker' or 'symbol' column")
        ticker_col = "ticker" if "ticker" in df.columns else "symbol"
        holdings = []
        for _, row in df.iterrows():
            t = str(row.get(ticker_col, "")).strip().upper()
            if not t or t == "NAN":
                continue
            qty = 1
            if "quantity" in df.columns or "qty" in df.columns:
                qcol = "quantity" if "quantity" in df.columns else "qty"
                try:
                    qty = int(float(row.get(qcol, 1)))
                except (ValueError, TypeError):
                    pass
            h = {"ticker": t, "quantity": max(1, qty)}
            if "cost_basis" in df.columns or "cost" in df.columns:
                ccol = "cost_basis" if "cost_basis" in df.columns else "cost"
                try:
                    cb = float(row.get(ccol))
                    if not pd.isna(cb):
                        h["cost_basis"] = round(cb, 2)
                except (ValueError, TypeError):
                    pass
            for date_col in ("purchase_date", "acquisition_date", "date", "purchase"):
                if date_col in df.columns:
                    raw = row.get(date_col)
                    if pd.notna(raw) and str(raw).strip():
                        h["purchase_date"] = str(raw).strip()[:10]
                        break
            holdings.append(h)
        if not holdings:
            raise HTTPException(status_code=400, detail="No valid tickers found in Excel")
        add_uploaded_portfolio(portfolio_name.strip() or "Uploaded", holdings)
        return {"ok": True, "portfolio": portfolio_name, "holdings_count": len(holdings)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _is_premarket_hours_et() -> bool:
    """True if current time is US pre-market (weekday 4:00–9:30 AM ET)."""
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    now = _dt.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    hour, minute = now.hour, now.minute
    if hour < 4:
        return False
    if hour < 9:
        return True
    return hour == 9 and minute < 30


def _premarket_file_is_from_today(data: dict) -> bool:
    """Return True if the cached pre-market snapshot's timestamp is from today (ET)."""
    ts = data.get("timestamp", "")
    if not ts:
        return False
    try:
        from datetime import datetime as _dt
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo  # type: ignore
        et = ZoneInfo("America/New_York")
        # Accept ISO-8601 with or without timezone suffix
        file_dt = _dt.fromisoformat(ts.replace("Z", "+00:00"))
        file_date = file_dt.astimezone(et).date()
        today = _dt.now(et).date()
        return file_date == today
    except Exception:
        return False  # If we can't parse, treat as stale


@router.get("/after-hours/snapshot")
async def get_after_hours_snapshot(refresh: bool = Query(False)):
    """
    After-hours earnings marks (portfolio ∪ watchlist names reporting today).
    refresh=true runs a live pass; default reads file / dashboard cache.
    """
    if refresh:
        try:
            from signals.after_hours_earnings import run_after_hours_earnings_snapshot

            out = run_after_hours_earnings_snapshot(slot="manual")
            return jsonable_encoder(out)
        except Exception as e:
            logger.exception("after-hours refresh failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e)) from e
    try:
        from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot
        from signals.after_hours_earnings import load_after_hours_snapshot

        cached = get_cached_dashboard() or get_last_dashboard_snapshot()
        if cached and isinstance(cached.get("after_hours_earnings"), dict):
            return jsonable_encoder(cached["after_hours_earnings"])
        file_snap = load_after_hours_snapshot()
        if file_snap:
            return jsonable_encoder(file_snap)
    except Exception as e:
        logger.debug("after-hours read: %s", e)
    raise HTTPException(
        status_code=503,
        detail="No after-hours snapshot yet. Runs at 4:30 PM and 6:00 PM ET on earnings days (portfolio ∪ watchlist).",
    )


def _premarket_with_catalysts(data: dict) -> dict:
    """Attach P0 market catalyst board (calendar, tensions, FOMC stats) to pre-market payload."""
    try:
        from signals.market_catalysts import attach_catalysts_to_premarket

        return attach_catalysts_to_premarket(data, _load_config())
    except Exception as e:
        logger.debug("premarket catalysts attach failed: %s", e)
        return data


@router.get("/pre-market")
async def get_pre_market(refresh: bool = Query(False)):
    """
    Pre-market signal engine (6 categories, 15 sources).

    Priority order:
      1. Cached file from TODAY  → return immediately (fresh)
      2. In pre-market hours     → run engine live, save file, return
      3. Cached file from a PREVIOUS day → return with stale=True flag so the
         UI can show a "last updated yesterday" warning instead of hiding the data
      4. Nothing + outside pre-market → 503
    """
    pre_market_file = get_data_root() / "pre_market_latest.json"
    cached: dict | None = None

    try:
        if pre_market_file.exists():
            with open(pre_market_file) as f:
                cached = json.load(f)
            if not (cached.get("composite_score") is not None and cached.get("bias") and cached.get("signals") is not None):
                cached = None  # Malformed — discard
    except Exception as e:
        logger.debug("Pre-market file read failed: %s", e)
        cached = None

    # ── Explicit refresh: re-attach catalysts + intraday (P2) without re-running engine ──
    if refresh and cached:
        return _premarket_with_catalysts(cached)

    # ── Case 1: fresh file from today ──────────────────────────────────────
    if cached and _premarket_file_is_from_today(cached):
        cached.pop("stale", None)
        return _premarket_with_catalysts(cached)

    # ── Case 2: in pre-market hours → run engine live ─────────────────────
    if _is_premarket_hours_et():
        try:
            from signals.premarket_engine import PreMarketEngine
            from scripts.pre_market_scheduler import report_to_dict
            engine = PreMarketEngine()
            report = engine.run(verbose=False)
            data = report_to_dict(report)
            pre_market_file.parent.mkdir(parents=True, exist_ok=True)
            with open(pre_market_file, "w") as f:
                json.dump(data, f, indent=2)
            try:
                from scripts.pre_market_scheduler import archive_premarket_snapshot

                archive_premarket_snapshot(data)
            except Exception:
                pass
            return _premarket_with_catalysts(data)
        except Exception as e:
            logger.exception("Pre-market engine failed: %s", e)
            # Fall through to serve stale cache if available

    # ── Case 3: stale cached file from a previous day ─────────────────────
    if cached:
        ts = cached.get("timestamp", "")
        try:
            from datetime import datetime as _dt
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                from backports.zoneinfo import ZoneInfo  # type: ignore
            et = ZoneInfo("America/New_York")
            file_dt = _dt.fromisoformat(ts.replace("Z", "+00:00"))
            date_str = file_dt.astimezone(et).strftime("%b %d")
        except Exception:
            date_str = "a previous day"
        cached["stale"] = True
        cached["stale_message"] = f"Showing pre-market data from {date_str} — refreshes at 4:00 AM ET on trading days"
        return _premarket_with_catalysts(cached)

    # ── Case 4: no data at all ─────────────────────────────────────────────
    raise HTTPException(
        status_code=503,
        detail="Pre-market data is only generated before the open (4:00–9:30 AM ET, weekdays). "
               "Run scripts/pre_market_scheduler.py during that window, or use the last cached snapshot.",
    )


@router.get("/market-state")
async def get_market_state():
    """
    P3: Unified market state — macro, pre-market + catalysts, next-day outlook, typical move, intraday.
    Used by Overview MarketStatePanel; optional lazy load separate from full dashboard bundle.
    """
    try:
        from signals.market_state import build_market_state

        return jsonable_encoder(build_market_state(_load_config()))
    except Exception as e:
        logger.exception("market-state failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ticker/{ticker}")
async def get_ticker_detail(ticker: str):
    """Ticker detail: thesis, earnings, sector, peers, benchmark vs SPY/industry/peers."""
    from starlette.concurrency import run_in_threadpool

    from api.ticker_detail import get_ticker_detail as _get

    config = _load_config()
    t0 = time.perf_counter()
    try:
        out = await run_in_threadpool(_get, ticker, config)
        logger.info("[ticker-detail] %s done in %.0fms", (ticker or "").upper(), (time.perf_counter() - t0) * 1000)
        return out
    except Exception as e:
        logger.exception("ticker-detail failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/live-prices")
async def get_live_prices(tickers: str = Query(..., description="Comma-separated list of tickers")):
    """
    Return latest delayed prices for a set of tickers in one call.
    yfinance batch (free, ~15-min delay). Used by the frontend 1-min price polling loop.
    Response: { prices: {TICKER: price}, as_of: ISO, source: "yfinance_latest" }
    """
    from starlette.concurrency import run_in_threadpool

    syms = [t.strip().upper() for t in (tickers or "").split(",") if t.strip()]
    if not syms:
        return {"prices": {}, "as_of": None, "source": None}
    syms = syms[:150]  # cap to avoid abuse

    def _fetch():
        config = _load_config()
        from signals.live_quotes import fetch_live_quotes
        prices, source = fetch_live_quotes(config, syms)
        return prices, source

    try:
        prices, source = await run_in_threadpool(_fetch)
    except Exception as e:
        logger.warning("[live-prices] fetch failed: %s", e)
        prices, source = {}, None

    return {
        "prices": prices,
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "count": len(prices),
    }


_SECTOR_MAP_ETFS: list[tuple[str, str]] = [
    ("XLK", "Tech"),
    ("XLC", "Comm"),
    ("XLY", "Discretionary"),
    ("XLF", "Financials"),
    ("XLV", "Health"),
    ("XLE", "Energy"),
    ("XLI", "Industrials"),
    ("XLP", "Staples"),
    ("XLU", "Utilities"),
    ("XLB", "Materials"),
    ("XLRE", "Real estate"),
]
_SECTOR_MAP_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_SECTOR_MAP_TTL_S = 600


@router.get("/sector-map")
async def get_sector_map():
    """
    Today tab "Market map": SPY + SPDR sector ETFs, % change of the latest daily bar vs the
    prior close (yfinance, ~15-min delayed during RTH). Cached in-process for 10 minutes.
    Response: { spy: {ticker, change_pct}, sectors: [{ticker, name, change_pct}], as_of }
    """
    from starlette.concurrency import run_in_threadpool

    now = time.time()
    cached = _SECTOR_MAP_CACHE.get("data")
    if cached and now - float(_SECTOR_MAP_CACHE.get("at") or 0) < _SECTOR_MAP_TTL_S:
        return cached

    def _fetch() -> dict:
        import yfinance as yf

        syms = ["SPY"] + [s for s, _ in _SECTOR_MAP_ETFS]
        df = yf.download(syms, period="5d", interval="1d", progress=False, auto_adjust=False, threads=True)
        closes = df["Close"] if "Close" in df else df
        changes: dict[str, float | None] = {}
        for s in syms:
            try:
                series = closes[s].dropna()
                if len(series) >= 2 and float(series.iloc[-2]) > 0:
                    changes[s] = round((float(series.iloc[-1]) / float(series.iloc[-2]) - 1.0) * 100.0, 2)
                else:
                    changes[s] = None
            except Exception:
                changes[s] = None
        return {
            "spy": {"ticker": "SPY", "change_pct": changes.get("SPY")},
            "sectors": [{"ticker": s, "name": n, "change_pct": changes.get(s)} for s, n in _SECTOR_MAP_ETFS],
            "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "yfinance_daily",
        }

    try:
        data = await run_in_threadpool(_fetch)
    except Exception as e:
        logger.warning("[sector-map] fetch failed: %s", e)
        if cached:
            return cached
        return {"spy": None, "sectors": [], "as_of": None, "source": None, "error": "sector data unavailable"}

    _SECTOR_MAP_CACHE["at"] = now
    _SECTOR_MAP_CACHE["data"] = data
    return data


@router.get("/ticker/{ticker}/intraday")
async def get_ticker_intraday(
    ticker: str,
    period: str = Query("1mo", description="1d | 5d | 1mo"),
    interval: str = Query("", description="auto-selected per period if blank"),
):
    """
    Intraday / recent OHLCV bars for the price chart in ticker detail.

    period=1d  → interval=1m   (today only, ~390 bars)
    period=5d  → interval=15m  (~130 bars)
    period=1mo → interval=1h   (~195 bars)

    Data via yfinance (free, 15-min delayed). Returns:
      { ticker, period, interval, bars: [{t, o, h, l, c, v}], last_price, as_of }
    """
    from starlette.concurrency import run_in_threadpool

    def _fetch() -> dict:
        sym = (ticker or "").upper().strip()
        if not sym:
            return {"error": "ticker required", "bars": []}

        # Auto-select interval per period
        period_map = {"1d": "1m", "5d": "15m", "1mo": "1h"}
        resolved_interval = interval.strip() if interval.strip() else period_map.get(period, "1h")

        try:
            from signals.fetcher import _download_with_crumb_retry

            t0_fetch = time.perf_counter()
            df = _download_with_crumb_retry(
                sym,
                period=period,
                interval=resolved_interval,
                threads=False,
            )
            logger.info(
                "[intraday] %s period=%s interval=%s rows=%d in %.0fms",
                sym, period, resolved_interval, len(df) if df is not None else 0,
                (time.perf_counter() - t0_fetch) * 1000,
            )
        except Exception as e:
            logger.warning("[intraday] yfinance failed %s: %s", sym, e)
            return {"error": str(e), "bars": [], "ticker": sym}

        if df is None or df.empty:
            return {"ticker": sym, "period": period, "interval": resolved_interval, "bars": [], "error": "No data"}

        # Flatten MultiIndex columns if present (yfinance 0.2.x)
        if hasattr(df.columns, "levels"):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        bars = []
        for ts, row in df.iterrows():
            try:
                t_iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                o = float(row.get("Open") or row.get("open") or 0)
                h = float(row.get("High") or row.get("high") or 0)
                lo = float(row.get("Low") or row.get("low") or 0)
                c = float(row.get("Close") or row.get("close") or 0)
                v = int(row.get("Volume") or row.get("volume") or 0)
                if c > 0:
                    bars.append({"t": t_iso, "o": round(o, 4), "h": round(h, 4), "l": round(lo, 4), "c": round(c, 4), "v": v})
            except Exception:
                continue

        last_price = bars[-1]["c"] if bars else None
        as_of = bars[-1]["t"] if bars else None

        return {
            "ticker": sym,
            "period": period,
            "interval": resolved_interval,
            "bars": bars,
            "last_price": last_price,
            "as_of": as_of,
            "delayed_note": "Prices delayed ~15 min (yfinance). Not for execution.",
        }

    try:
        result = await run_in_threadpool(_fetch)
        return result
    except Exception as e:
        logger.exception("[intraday] unexpected error %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/roadmaps")
async def get_roadmaps(tickers: str = ""):
    """
    Lightweight roadmaps for multiple tickers (dashboard Roadmaps tab).
    Query: ?tickers=NVDA,GLD,SPY (comma-separated, max 12).
    Returns: { roadmaps: [ { ticker, one_answer, trade_roadmap } ] }.
    Each ticker uses full get_ticker_detail; we strip to one_answer + trade_roadmap only.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from api.ticker_detail import get_ticker_detail as _get

    config = _load_config()
    raw = [t.strip().upper() for t in tickers.split(",") if t.strip()][:12]
    if not raw:
        return {"roadmaps": [], "message": "Provide ?tickers=NVDA,GLD,SPY"}

    def _one(t: str) -> dict:
        try:
            detail = _get(t, config)
            inv = detail.get("investor_summary") or {}
            return {
                "ticker": t,
                "one_answer": inv.get("one_answer"),
                "trade_roadmap": inv.get("trade_roadmap"),
            }
        except Exception as e:
            logger.warning("Roadmap skip %s: %s", t, e)
            return {"ticker": t, "one_answer": None, "trade_roadmap": None}

    by_ticker: dict[str, dict] = {}
    workers = min(4, len(raw))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, t): t for t in raw}
        for fut in as_completed(futures):
            t = futures[fut]
            by_ticker[t] = fut.result()
    out = [by_ticker[t] for t in raw if t in by_ticker]
    return {"roadmaps": out}


@router.get("/ticker/{ticker}/track-record")
async def get_ticker_track_record(ticker: str):
    """
    Per-ticker signal-accuracy summary — has our own model been right on THIS ticker?

    Reads already-cached watchlist-wide forward-tracking data and filters it to one ticker
    in-memory. Deliberately does NOT call get_forward_tracking() fresh here — that call's
    cost is dominated by EOD snapshot I/O, not ticker count, so a "single ticker" call is
    not meaningfully cheaper than the full-watchlist one. Stays a cheap Redis read; never
    triggers a live recompute.

    Was reading only the dedicated per-key slice (analysis:slice:forward_tracking), which
    has its own 6h TTL independent of the other core slices (model_audit, paper_trading) —
    confirmed live that this key can be empty/expired while GET /api/dashboard/analysis-bundle
    still serves full forward_tracking data (500 records) via its dedicated-bundle or
    dashboard-cache fallback tiers, because that endpoint tries three cache sources and this
    one only tried the first. Reuses compute_analysis_bundle(allow_heavy=False) — the exact
    same cache-only fallback chain — instead of duplicating it, so this endpoint can't go
    stale independently of the tab it's summarizing data from.
    """
    from signals.forward_tracking_metrics import (
        build_ticker_track_record,
        build_ticker_track_record_all_horizons,
    )
    from signals.model_version import MODEL_VERSION

    sym = ticker.upper().strip()
    try:
        bundle = compute_analysis_bundle(allow_heavy=False)
    except Exception:
        bundle = None
    ft = bundle.get("forward_tracking") if isinstance(bundle, dict) else None
    if not isinstance(ft, dict):
        return {"available": False, "ticker": sym, "reason": "forward-tracking data not cached yet"}

    records = ft.get("records") or []
    out = build_ticker_track_record(records, sym, current_model_version=MODEL_VERSION)
    # Additive, backward-compatible: the 20d fields above stay the headline number once a
    # version is mature, but a just-launched version has zero chance of a resolved 20d
    # outcome for weeks (20 *trading* days must elapse first) — by_horizon lets the UI show
    # an early 1d/5d read under the current version instead of only "not enough data yet".
    try:
        out["by_horizon"] = build_ticker_track_record_all_horizons(
            records, sym, current_model_version=MODEL_VERSION
        ).get("by_horizon")
    except Exception:
        out["by_horizon"] = None

    # Per-trade daily table (signal price, fill, target/stop, outcome, P&L) — the aggregate
    # win-rate fields above answer "was the model right overall"; this answers "show me",
    # row by row, what it would have actually traded on this ticker.
    try:
        from signals.paper_trade_logger import PaperTradeLogger, build_ticker_trade_table

        pt = PaperTradeLogger(data_root=get_data_root())
        out["daily_trades"] = build_ticker_trade_table(pt.get_trades_for_ticker(sym, limit=60))
    except Exception:
        out["daily_trades"] = []
    return out


@router.get("/ticker/{ticker}/correlation-to-holdings")
async def get_ticker_correlation_to_holdings(ticker: str, tickers: str = ""):
    """
    Pre-trade check: how correlated is this candidate to the portfolio's current top
    holdings (by value)? `tickers` is a comma-separated list of holding tickers the caller
    already knows from the loaded dashboard's per_holding (no portfolio/config lookup here)
    — capped at 5 to keep this a bounded, one-time fetch.
    """
    from signals.portfolio_risk_model import correlation_to_holdings

    holding_syms = [t for t in tickers.split(",") if t.strip()][:5]
    return correlation_to_holdings(ticker, holding_syms)


@router.get("/ticker/{ticker}/narrative")
async def get_ticker_narrative(
    ticker: str,
    mode: str = Query("scout", description="scout | swing | owner"),
):
    """
    Validated action-contract narrative for one persona (narrative_waterfall.py).

    Layers 0-2 (canonical packet + validation, deterministic BUY/WAIT/HOLD
    action contract, templated gate explanations + catalysts) are always
    computed, free, from data already in the ticker-detail/confidence/
    price-targets responses. Layer 3 (a short guarded LLM narrative paragraph,
    Anthropic Haiku) only runs when ANTHROPIC_API_KEY is configured — otherwise
    `narrative_status` comes back "skipped" and the deterministic action/why/
    catalysts still populate. Redis-cached per ticker+mode+decision-state so
    repeat views (and unchanged tickers across restarts) don't re-call the LLM.
    """
    from starlette.concurrency import run_in_threadpool

    mode_norm = (mode or "scout").lower().strip()
    if mode_norm not in ("scout", "swing", "owner"):
        mode_norm = "scout"
    sym = ticker.upper().strip()

    def _build() -> dict:
        import os

        from api.ticker_detail import get_ticker_detail as _get
        from signals.narrative_packet_mapper import to_packet
        from signals.narrative_waterfall import build_summary_tiered, make_anthropic_client

        config = _load_config()
        detail = _get(sym, config)

        scenarios_raw: list = []
        try:
            from signals.cache import cached_price_target_scenarios
            from signals.price_targets import run_price_targets
            inv = detail.get("investor_summary") or {}
            rb = inv.get("regime_bull_pct") or 0
            regime = "UP" if rb >= 60 else "DOWN" if rb <= 40 else "NEUTRAL"
            fair_value = inv.get("fair_value")
            pt = cached_price_target_scenarios(
                sym, regime,
                lambda: run_price_targets(sym, market_regime=regime, config=config, fair_value=fair_value),
            )
            scenarios_raw = (pt or {}).get("scenarios") or []
        except Exception as e:
            logger.warning("[narrative] scenarios unavailable for %s: %s", sym, e)

        pkt = to_packet(detail, mode_norm, scenarios_raw=scenarios_raw)

        api_key = os.getenv("ANTHROPIC_API_KEY") or config.get("data", {}).get("anthropic_api_key")
        llm = make_anthropic_client() if api_key else None

        summary = build_summary_tiered(pkt, llm=llm, on_view=True)
        if summary.get("status") == "blocked":
            errs = summary.get("errors") or []
            logger.warning("[narrative] %s (%s) blocked: %s", sym, mode_norm, errs)
            return {
                "status": "blocked",
                "ticker": sym,
                "mode": mode_norm,
                "errors": errs,
            }
        return summary

    try:
        return await run_in_threadpool(_build)
    except Exception as e:
        logger.exception("[narrative] failed for %s (%s): %s", sym, mode_norm, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ticker/{ticker}/catalyst-notes")
async def get_ticker_catalyst_notes(
    ticker: str,
    mode: str = Query("scout", description="scout | swing | owner"),
):
    """On-view LLM wrap of Phase-1 news catalyst cards.

    Deterministic cards always return. Haiku wrap runs only when
    ANTHROPIC_API_KEY is set; number-guarded against packet + headline facts;
    cached on ticker+mode+asof+headline hash. Never mutates bands or gates.
    """
    from starlette.concurrency import run_in_threadpool

    mode_norm = (mode or "scout").lower().strip()
    if mode_norm not in ("scout", "swing", "owner"):
        mode_norm = "scout"
    sym = ticker.upper().strip()

    def _build() -> dict:
        import os

        from api.ticker_detail import get_ticker_detail as _get
        from signals.catalyst_detector import build_catalyst_note_cards
        from signals.catalyst_llm_wrap import wrap_catalyst_cards
        from signals.narrative_packet_mapper import to_packet
        from signals.narrative_waterfall import make_anthropic_client
        from signals.time_et import today_est

        config = _load_config()
        detail = _get(sym, config) or {}
        inv = detail.get("investor_summary") or {}
        layer = ((inv.get("trade_roadmap") or {}).get("news_sentiment_layer") or {})
        cards = layer.get("catalyst_cards") or []
        if not cards:
            cards = build_catalyst_note_cards(layer.get("headlines") or [], ticker=sym)

        packet = None
        try:
            packet = to_packet(detail, mode_norm, scenarios_raw=[])
        except Exception as e:
            logger.warning("[catalyst_notes] packet unavailable for %s: %s", sym, e)

        asof = getattr(packet, "asof", None) or today_est()
        api_key = os.getenv("ANTHROPIC_API_KEY") or config.get("data", {}).get("anthropic_api_key")
        llm = make_anthropic_client() if api_key else None
        return wrap_catalyst_cards(
            cards, ticker=sym, asof=asof, mode=mode_norm,
            packet=packet, llm=llm, on_view=True,
        )

    try:
        return await run_in_threadpool(_build)
    except Exception as e:
        logger.exception("[catalyst_notes] failed for %s (%s): %s", sym, mode_norm, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/confidence/{ticker}")
async def get_confidence(ticker: str):
    """
    7-layer ConfidenceEngine breakdown for a single ticker.
    Returns: confidence (0-1), action, breakdown per layer, disqualifiers, risk_factors, watch_levels,
    penalty_audit (layer blend vs HMM/insider multipliers), pre_flight, ml_horizons, nlp, etc.
    Layers: HMM regime, pattern+technical, LightGBM prob, options sentiment, insider, fundamentals, NLP.
    Gracefully degrades — missing layers are redistributed. Safe to call any time.
    """
    ticker = ticker.upper().strip()
    try:
        from signals.cache import cached_run_confidence
        from signals.confidence_engine import run_confidence
        config = _load_config()
        period = config.get("data", {}).get("period", "2y") or "2y"
        result = cached_run_confidence(
            ticker,
            period,
            lambda: run_confidence(ticker, period=period, config=config),
        )
        return result
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Confidence engine unavailable: {e}")
    except Exception as e:
        logger.exception("Confidence engine error for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights/{ticker}")
async def get_insights(ticker: str):
    """
    Institutional proxies (Yahoo 13F-derived ownership, SEC EDGAR 13F changes, optional FMP insider/short)
    and earnings-quality heuristics. Optional in config: insights.enabled.
    """
    from starlette.concurrency import run_in_threadpool

    ticker_u = (ticker or "").upper().strip()
    if not ticker_u:
        raise HTTPException(status_code=400, detail="Ticker required")
    config = _load_config()
    ins_cfg = config.get("insights") or {}
    if not ins_cfg.get("enabled", True):
        return {"disabled": True, "message": "insights.disabled in config"}
    t0 = time.perf_counter()
    try:
        from signals.cache import cached_earnings_quality, cached_institutional_bundle
        from signals.earnings_quality import analyze_earnings_quality
        from signals.institutional_signals import build_institutional_bundle

        def _build() -> dict[str, Any]:
            return {
                "ticker": ticker_u,
                "institutional": cached_institutional_bundle(
                    ticker_u, lambda: build_institutional_bundle(config, ticker_u)
                ),
                "earnings_quality": cached_earnings_quality(
                    ticker_u, lambda: analyze_earnings_quality(config, ticker_u)
                ),
            }

        payload = await run_in_threadpool(_build)
        logger.info("[insights] %s done in %.0fms", ticker_u, (time.perf_counter() - t0) * 1000)
        return payload
    except Exception as e:
        logger.exception("insights error for %s: %s", ticker_u, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unified-signal/{ticker}")
async def get_unified_signal(ticker: str):
    """
    Unified Signal Engine: 3-layer confluence (regime + pattern + momentum) with regime gating.
    Returns: regime, pattern_score, momentum_score, confluence, action, Kelly multiplier, narrative.
    Runs in ~1-2s (fetches 2y OHLCV, no ML training required).
    When pattern_score is 0 (no OHLCV pattern), we use composite_score as fallback and set
    pattern_score_source so the UI can label "Confluence (pattern n/a)" to avoid 48 vs 0 confusion.
    """
    ticker = ticker.upper().strip()
    try:
        from signals.unified_signal_engine import run_unified_signal
        from signals.fetcher import fetch_ohlcv_safe
        from signals.regime import get_global_market_regime
        # Resolve global market regime so we never return UNKNOWN
        market_regime = "NEUTRAL"
        vix = None
        try:
            close_spy = fetch_ohlcv_safe("SPY", "2y")
            if close_spy is not None and len(close_spy) >= 60:
                market_regime = get_global_market_regime(close_spy, min_days_confirm=3)
        except Exception:
            pass
        result = run_unified_signal(ticker, period="2y", composite_score=None, market_regime=market_regime, vix=vix)
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        if result.get("pattern_score", 0) == 0 and result.get("composite_score") is not None:
            result["pattern_score"] = result["composite_score"]
            result["pattern_score_source"] = "confluence_fallback"
        return result
    except HTTPException:
        raise
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Unified signal engine unavailable: {e}")
    except Exception as e:
        logger.exception("Unified signal error for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-targets/{ticker}")
async def get_price_targets(
    ticker: str,
    regime: str = "NEUTRAL",
    fair_value: float | None = Query(None, description="Model fair value from ticker detail — aligns scenario caps"),
):
    """
    Consolidated buy/sell zones, expected returns, and scenario analysis for a ticker.

    Returns per-horizon (short/medium/long):
      - Entry zone anchored to MA50/MA200/52w-low
      - Base / bull / bear price targets
      - Expected return (probability-weighted)
      - Stop loss and risk/reward ratio

    Plus 5-6 scenarios (3 universal + up to 3 asset-specific):
      - Fed rate cuts, earnings beat/miss, momentum squeeze, geopolitical events, etc.
    """
    ticker = ticker.upper().strip()
    try:
        from signals.price_targets import run_price_targets
        config = _load_config()
        result = run_price_targets(
            ticker,
            market_regime=regime.upper(),
            config=config,
            fair_value=fair_value,
        )
        return result
    except Exception as e:
        logger.exception("Price targets error for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/classify/{ticker}")
async def get_classify(ticker: str):
    """
    Pre-flight asset classification for a single ticker.
    Returns asset type, weight profile, pre-flight flags, and scoreability.
    Uses curated registry, then JSON cache, then live FMP/yfinance profile inference.
    """
    ticker = ticker.upper().strip()
    try:
        from signals.pre_flight import classify_asset
        result = classify_asset(ticker)
        return result.to_dict()
    except Exception as e:
        logger.exception("Asset classify error for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-suite")
async def run_test_suite(body: dict):
    """
    Batch pre-flight classification + optional confidence for a list of tickers.
    Used by the Signal Test Suite tab to verify model behavior across asset types.

    Request body:
      { "tickers": ["NVDA", "GLD", ...], "include_confidence": false }

    Returns list of results per ticker, each with:
      - classification (asset_type, weight_profile, flags, is_scoreable)
      - confidence (full 7-layer breakdown) if include_confidence=True
      - timing stats
    """
    from signals.pre_flight import classify_asset, get_registered_tickers
    import time

    tickers = [t.upper().strip() for t in (body.get("tickers") or get_registered_tickers())]
    include_confidence = bool(body.get("include_confidence", False))
    results = []

    for ticker in tickers:
        t0 = time.perf_counter()
        row: dict = {"ticker": ticker, "classification": None, "confidence": None, "error": None, "elapsed_ms": 0}
        try:
            cls = classify_asset(ticker)
            row["classification"] = cls.to_dict()
        except Exception as e:
            row["error"] = f"classify failed: {e}"
            results.append(row)
            continue

        if include_confidence:
            try:
                from signals.confidence_engine import run_confidence
                row["confidence"] = run_confidence(ticker)
            except Exception as e:
                row["confidence"] = {"error": str(e)}

        row["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        results.append(row)

    scoreable   = sum(1 for r in results if r.get("classification", {}) and r["classification"].get("is_scoreable"))
    incompat    = sum(1 for r in results if r.get("classification", {}) and not r["classification"].get("is_scoreable"))
    total_flags = sum(len(r["classification"].get("flags", [])) for r in results if r.get("classification"))
    bonus_count = sum(
        1 for r in results
        if r.get("confidence") and r["confidence"].get("pre_flight", {}).get("transition_bonus", {}) and
           r["confidence"]["pre_flight"]["transition_bonus"].get("bonus_active")
    )

    return {
        "tickers":     tickers,
        "total":       len(results),
        "scoreable":   scoreable,
        "incompatible": incompat,
        "total_flags": total_flags,
        "bonus_active": bonus_count,
        "results":     results,
    }


@router.get("/registry")
async def get_registry():
    """Return all tickers in the pre-flight asset registry grouped by asset type."""
    from signals.pre_flight import get_registered_tickers, get_tickers_by_type
    from signals.pre_flight.constants import AssetType
    registry: dict = {}
    for at in AssetType:
        tickers = get_tickers_by_type(at)
        if tickers:
            registry[at.value] = tickers
    return {
        "total": sum(len(v) for v in registry.values()),
        "by_type": registry,
    }


@router.get("/last-run")
async def get_last_run():
    """Last run state for comparison."""
    data = load_last_run()
    if data is None:
        return {"run_results": []}
    path = get_data_root() / "last_run.json"
    if not path.exists():
        return {"run_results": []}
    with open(path) as f:
        return json.load(f)


@router.post("/eod/save-from-last-run")
def eod_save_from_last_run(snapshot_date: str | None = None):
    """
    Save current last_run.json to data/eod/YYYY-MM-DD.json (fast, no recompute).
    Use after loading the dashboard: last run is already on disk; this copies it to the EOD directory.
    snapshot_date: optional YYYY-MM-DD; if omitted, uses today EST.
    Skips if a snapshot for that date already exists. Does not include next_day_outlook/typical_move.
    """
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    today_est = _dt.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    date_str = snapshot_date.strip() if isinstance(snapshot_date, str) and snapshot_date.strip() else today_est
    last_run_path = get_data_root() / "last_run.json"
    eod_path = get_data_root() / "eod" / f"{date_str}.json"
    if eod_path.exists():
        logger.info("[eod/save-from-last-run] Snapshot already exists for %s, skipping", date_str)
        return {
            "ok": True,
            "skipped": True,
            "message": f"EOD snapshot already exists for {date_str}",
            "snapshot_date": date_str,
            "snapshot_path": str(eod_path),
        }
    if not last_run_path.exists():
        raise HTTPException(
            status_code=400,
            detail="No last run found. Load the dashboard or run POST /api/eod/run first.",
        )
    with open(last_run_path) as f:
        payload = json.load(f)
    run_results = payload.get("run_results") or []
    if not run_results:
        raise HTTPException(
            status_code=400,
            detail="last_run.json has no run_results. Load the dashboard or run POST /api/eod/run first.",
        )
    eod_path.parent.mkdir(parents=True, exist_ok=True)
    payload["snapshot_date"] = date_str
    with open(eod_path, "w") as f:
        json.dump(payload, f, indent=2)
    try:
        from signals.cache import set_eod_snapshot_redis
        set_eod_snapshot_redis(date_str, payload)
    except Exception:
        pass
    logger.info("[eod/save-from-last-run] Saved %s from last_run (%d tickers)", date_str, len(run_results))
    return {
        "ok": True,
        "skipped": False,
        "snapshot_date": date_str,
        "snapshot_path": str(eod_path),
        "tickers_count": len(run_results),
    }


@router.get("/eod/status")
def eod_status():
    """
    Quick EOD snapshot status: latest file/Redis date, whether today's EST snapshot exists,
    and configured signal universe sizes (dashboard vs EOD/audit).
    """
    from datetime import datetime as _dt

    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore

    today_est = _dt.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    config = _load_config()
    from config_loader import get_dashboard_signal_universe, get_eod_signal_universe

    dashboard_uni = get_dashboard_signal_universe(config)
    eod_uni = get_eod_signal_universe(config)
    dates: list[str] = []
    try:
        from signals.cache import build_eod_snapshot_index

        # Union Redis + disk (never Redis-only — that hid newer files on disk).
        dates = [s["date"] for s in build_eod_snapshot_index() if s.get("date")]
    except Exception:
        try:
            from signals.cache import list_eod_dates_redis

            dates = list(list_eod_dates_redis() or [])
        except Exception:
            dates = []
        eod_dir = get_data_root() / "eod"
        if eod_dir.exists():
            for p in eod_dir.glob("*.json"):
                if p.stem[:4].isdigit() and p.stem not in dates:
                    dates.append(p.stem)
    latest = max(dates) if dates else None
    today_path = get_data_root() / "eod" / f"{today_est}.json"
    scheduler: dict = {}
    try:
        from api.eod_scheduler import scheduler_status

        scheduler = scheduler_status()
    except Exception as e:
        scheduler = {"enabled": False, "running": False, "off_reason": str(e)}

    job_state: dict = {}
    safety_net_queued = False
    try:
        from api.eod_job import eod_job_state, trigger_full_eod_background_if_missing

        job_state = eod_job_state()
        # Lightweight kick: if full cohort missing after 8pm, queue background job (with cooldown).
        safety_net_queued = bool(trigger_full_eod_background_if_missing(min_hour_et=20))
    except Exception as e:
        job_state = {"error": str(e)}

    gap_days = None
    if latest:
        try:
            gap_days = (
                _dt.strptime(today_est, "%Y-%m-%d").date()
                - _dt.strptime(str(latest)[:10], "%Y-%m-%d").date()
            ).days
        except Exception:
            gap_days = None

    return {
        "today_est": today_est,
        "latest_snapshot_date": latest,
        "snapshot_count": len(dates),
        "days_since_latest": gap_days,
        "today_snapshot_exists": today_path.exists() or today_est in dates,
        "today_snapshot_path": str(today_path) if today_path.exists() else None,
        "dashboard_universe_count": len(dashboard_uni),
        "eod_universe_count": len(eod_uni),
        "dashboard_universe_sample": dashboard_uni[:8],
        "scheduler": scheduler,
        "eod_job": job_state,
        "safety_net_queued": safety_net_queued,
        "stale_warning": (
            f"Latest EOD in Redis/disk is {latest} ({gap_days}d behind {today_est}). "
            "Dashboard signals can still be fresh while this badge stays old — "
            "POST /api/eod/run?force=true&refresh_dashboard=true&universe=eod to catch up."
            if latest and gap_days is not None and gap_days >= 2
            else None
        ),
        "manual_run_hint": (
            "POST /api/eod/run?force=true&refresh_dashboard=true&universe=eod re-runs today's snapshot "
            "and refreshes the dashboard cache (use after 8pm scheduler if you want a fresh pass)."
        ),
    }


@router.get("/eod/snapshots")
def eod_snapshots_list():
    """Live Redis ∪ disk EOD file index (no blob loads). Used by the Analysis panel."""
    from config_loader import get_data_root
    from signals.cache import build_eod_snapshot_index

    snaps = build_eod_snapshot_index()
    latest = snaps[0]["date"] if snaps else None
    return {
        "latest_date": latest,
        "count": len(snaps),
        "snapshots": snaps,
        "data_root": str(get_data_root()),
    }


@router.get("/eod/snapshots/{snapshot_date}")
def eod_snapshot_get(snapshot_date: str):
    """
    Return one full EOD snapshot JSON (Redis first, then DATA_ROOT/eod).

    Used for local audits / fill walkthroughs against prod Railway data.
    ``snapshot_date`` must be YYYY-MM-DD.
    """
    import re

    date_str = (snapshot_date or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        raise HTTPException(status_code=400, detail="snapshot_date must be YYYY-MM-DD")

    snap: dict | None = None
    source = None
    try:
        from signals.cache import get_eod_snapshot_redis

        snap = get_eod_snapshot_redis(date_str)
        if snap:
            source = "redis"
    except Exception:
        snap = None

    if not snap:
        path = get_data_root() / "eod" / f"{date_str}.json"
        if path.is_file():
            try:
                snap = json.loads(path.read_text(encoding="utf-8"))
                source = "disk"
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to read {path.name}: {e}") from e

    if not snap or not isinstance(snap, dict):
        raise HTTPException(status_code=404, detail=f"No EOD snapshot for {date_str}")

    # Keep payload lean for clients that only need run_results + meta.
    out = dict(snap)
    out["_meta"] = {
        "snapshot_date": date_str,
        "source": source,
        "tickers": len(out.get("run_results") or []),
    }
    return out


@router.post("/eod/run")
def run_eod_now(
    snapshot_date: str | None = None,
    force: bool = False,
    refresh_dashboard: bool = False,
    universe: str = "eod",
    authorization: str | None = Header(None),
):
    """
    Run EOD snapshot ad-hoc: compute signals and save data/eod/YYYY-MM-DD.json (+ Redis).

    Query params:
      snapshot_date — optional YYYY-MM-DD (EST market date); default today EST.
      force — when true, overwrite an existing snapshot for that date (default skips if file exists).
      refresh_dashboard — when true, trigger background full dashboard recompute after a successful run.
      universe — ticker set: ``eod`` (watchlist+portfolio+audit cohort, same as 8pm scheduler) or
                 ``dashboard`` (watchlist+portfolio only, matches dashboard signal panels).

    May take 1–2 minutes. If env EOD_RUN_SECRET is set, require header: Authorization: Bearer <secret>.
    """
    secret = os.environ.get("EOD_RUN_SECRET", "").strip()
    if secret and (authorization or "").strip() != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    from datetime import datetime as _dt

    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore

    today_est = _dt.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    date_str = snapshot_date.strip() if isinstance(snapshot_date, str) and snapshot_date.strip() else today_est
    eod_path = get_data_root() / "eod" / f"{date_str}.json"
    uni_key = (universe or "eod").strip().lower()
    if uni_key not in ("eod", "dashboard"):
        raise HTTPException(status_code=400, detail="universe must be 'eod' or 'dashboard'")

    if eod_path.exists() and not force:
        logger.info("[eod/run] Snapshot already exists for %s, skipping (use force=true to overwrite)", date_str)
        return {
            "ok": True,
            "skipped": True,
            "forced": False,
            "message": f"EOD snapshot already exists for {date_str}. Pass force=true to re-run.",
            "snapshot_date": date_str,
            "snapshot_path": str(eod_path),
            "dashboard_refresh": None,
        }

    config = _load_config()
    from config_loader import get_dashboard_signal_universe, get_eod_signal_universe

    if uni_key == "dashboard":
        tickers = get_dashboard_signal_universe(config)
    else:
        tickers = get_eod_signal_universe(config)

    logger.info(
        "[eod/run] Starting EOD snapshot run date=%s universe=%s tickers=%d force=%s",
        date_str,
        uni_key,
        len(tickers),
        force,
    )
    result = run_eod_snapshot_only(
        config, snapshot_date=date_str, tickers=tickers, allow_non_trading_day=bool(force)
    )
    if result.get("skipped") and result.get("reason") == "non_trading_day":
        return {
            "ok": True,
            "skipped": True,
            "forced": bool(force),
            "message": (
                f"No EOD run for {date_str}: US market closed (weekend). "
                "Pass force=true to snapshot anyway (stale Friday close)."
            ),
            "snapshot_date": date_str,
            "dashboard_refresh": None,
        }
    if result.get("error"):
        logger.warning("[eod/run] EOD snapshot failed: %s", result["error"])
        raise HTTPException(status_code=500, detail=result["error"])
    logger.info("[eod/run] EOD snapshot saved: %s", result.get("snapshot_path"))

    dash_refresh: dict[str, Any] | None = None
    if refresh_dashboard:
        from api.dashboard_job import is_refresh_running, trigger_background_refresh

        started = trigger_background_refresh(_compute_full_dashboard_sync)
        dash_refresh = {
            "triggered": started,
            "already_running": (not started) and is_refresh_running(),
            "poll_status_url": "/api/dashboard/status",
            "reload_hint": "Poll /api/dashboard/status until idle, then reload dashboard or GET /api/dashboard/shell",
        }
    else:
        # Prefer light post-EOD merge from last_run; skip overnight to avoid OOM after the EOD write.
        try:
            from alerts.market_hours import is_signal_warm_window
            from api.dashboard_warm import trigger_post_eod_dashboard_sync

            if is_signal_warm_window():
                started = trigger_post_eod_dashboard_sync()
                dash_refresh = {
                    "triggered": started,
                    "mode": "post_eod_cache_sync",
                    "poll_status_url": "/api/dashboard/status",
                }
            else:
                dash_refresh = {
                    "triggered": False,
                    "mode": "deferred_until_warm_window",
                    "hint": "EOD/audit saved; dashboard cache sync waits until weekday 8:30 ET (or Force refresh).",
                }
                logger.info("[eod/run] deferred post-EOD dashboard sync until next warm window")
        except Exception as e:
            logger.debug("[eod/run] post-EOD cache sync queue failed: %s", e)

    return {
        "ok": True,
        "skipped": False,
        "forced": bool(force),
        "snapshot_date": result.get("snapshot_date"),
        "snapshot_path": result.get("snapshot_path"),
        "tickers_count": result.get("tickers_count", 0),
        "pruned": result.get("pruned", 0),
        "universe": uni_key,
        "universe_count": len(tickers),
        "signal_audit": result.get("signal_audit"),
        "paper_trades": result.get("paper_trades"),
        "signal_audit_outcomes": result.get("signal_audit_outcomes"),
        "dashboard_refresh": dash_refresh,
    }


@router.post("/audit/resolve")
def audit_resolve_outcomes(authorization: str | None = Header(None)):
    """
    Phase 2: resolve WIN/LOSS/NEUTRAL outcomes for cohort signals with enough EOD history.
    Same as scripts/resolve_signal_outcomes.py. Optional Bearer if EOD_RUN_SECRET is set.
    """
    secret = os.environ.get("EOD_RUN_SECRET", "").strip()
    if secret and (authorization or "").strip() != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    from signals.signal_audit_outcomes import resolve_signal_audit_outcomes

    config = _load_config()
    result = resolve_signal_audit_outcomes(config, data_root=get_data_root())
    return {"ok": True, **result}


@router.get("/audit/summary")
def audit_summary(
    cohort: str | None = Query(None),
    days: int | None = Query(None, ge=1, le=365),
):
    """Headline cohort audit stats including outcome win rates when resolved."""
    from signals.signal_audit_report import build_audit_report

    config = _load_config()
    if days:
        report = build_audit_report(config, data_root=get_data_root(), cohort_tag=cohort, days=days, write_files=False)
        return report
    from signals.signal_audit_store import build_model_audit_payload

    return build_model_audit_payload(config, data_root=get_data_root())


@router.get("/audit/report")
def audit_report(
    days: int | None = Query(None, ge=1, le=365),
    write: bool = Query(True, description="Persist audit_summary.json + CSV under DATA_ROOT/reports"),
):
    """Build (and optionally write) full audit report JSON."""
    from signals.signal_audit_report import build_audit_report

    config = _load_config()
    return build_audit_report(config, data_root=get_data_root(), days=days, write_files=write)


@router.get("/audit/cohort")
def audit_cohort():
    """Fixed audit cohort definition + category tags."""
    from signals.signal_audit_report import audit_cohort_payload

    return audit_cohort_payload(_load_config())


@router.get("/audit/breakdown")
def audit_breakdown(
    by: str = Query("gates_passed", description="gates_passed|go_no_go|market_cap_bucket|ml_signal|regime_label"),
    days: int | None = Query(None, ge=1, le=365),
):
    from config_loader import get_audit_cohort_tag
    from signals.signal_audit_report import _since_date
    from signals.signal_audit_store import SignalAuditStore

    config = _load_config()
    tag = get_audit_cohort_tag(config)
    since = _since_date(days)
    store = SignalAuditStore(data_root=get_data_root())
    col_map = {
        "gates": "gates_passed",
        "gates_passed": "gates_passed",
        "go_no_go": "go_no_go",
        "go": "go_no_go",
        "category": "market_cap_bucket",
        "sector": "market_cap_bucket",
        "market_cap_bucket": "market_cap_bucket",
        "signal": "ml_signal",
        "ml_signal": "ml_signal",
        "regime": "regime_label",
        "regime_label": "regime_label",
    }
    group_col = col_map.get(by.strip().lower(), by)
    rows = store.breakdown_rows(tag, group_col, since_date=since)
    return {"cohort_tag": tag, "by": group_col, "since_date": since, "rows": rows}


@router.get("/audit/records")
def audit_records(
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    days: int | None = Query(None, ge=1, le=365),
    ticker: str | None = Query(None),
):
    """Paginated audit rows with outcomes (JSON)."""
    from signals.signal_audit_report import _since_date, list_audit_records

    since = _since_date(days)
    return list_audit_records(
        _load_config(),
        data_root=get_data_root(),
        since_date=since,
        limit=limit,
        offset=offset,
        ticker=ticker,
    )


@router.get("/audit/export")
def audit_export_csv(
    days: int | None = Query(None, ge=1, le=365),
    limit: int = Query(10000, ge=1, le=50000),
):
    """Download CSV matching spreadsheet columns (signal + outcome fields)."""
    from signals.signal_audit_report import _since_date, export_records_csv

    since = _since_date(days)
    csv_text = export_records_csv(
        _load_config(),
        data_root=get_data_root(),
        since_date=since,
        limit=limit,
    )
    filename = "signal_audit_export.csv"
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/eod/upload")
async def eod_upload(
    file: UploadFile = File(...),
    snapshot_date: str | None = Form(None),
):
    """
    Upload an EOD snapshot JSON file. Saved to configured EOD directory (data/eod/).
    snapshot_date: optional YYYY-MM-DD; if omitted, inferred from payload run_date/snapshot_date or filename.
    """
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="JSON file required")
    try:
        content = await file.read()
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    if not data.get("run_results") and not data.get("run_date"):
        raise HTTPException(
            status_code=400,
            detail="File must look like an EOD snapshot (run_results or run_date).",
        )
    date_str = None
    if snapshot_date and isinstance(snapshot_date, str):
        s = snapshot_date.strip()
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            date_str = s
    if not date_str and data.get("run_date"):
        rd = data["run_date"]
        if isinstance(rd, str) and len(rd) >= 10:
            date_str = rd[:10]
    if not date_str and data.get("snapshot_date"):
        sd = data["snapshot_date"]
        if isinstance(sd, str) and len(sd) >= 10:
            date_str = sd[:10]
    if not date_str and file.filename:
        import re
        m = re.match(r"^(\d{4}-\d{2}-\d{2})", file.filename.replace(".json", ""))
        if m:
            date_str = m.group(1)
    if not date_str:
        from datetime import datetime as _dt
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo  # type: ignore
        date_str = _dt.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    eod_dir = get_data_root() / "eod"
    eod_dir.mkdir(parents=True, exist_ok=True)
    eod_path = eod_dir / f"{date_str}.json"
    with open(eod_path, "w") as f:
        json.dump(data, f, indent=2)
    try:
        from signals.cache import set_eod_snapshot_redis
        set_eod_snapshot_redis(date_str, data)
    except Exception:
        pass
    logger.info("[eod/upload] Saved %s (%d bytes, %d tickers)", date_str, len(content), len(data.get("run_results") or []))
    return {
        "ok": True,
        "snapshot_date": date_str,
        "snapshot_path": str(eod_path),
        "tickers_count": len(data.get("run_results") or []),
    }


def _accuracy_interpretation(config: dict) -> dict:
    """Build interpretation thresholds and notes from config.accuracy for dashboard/API."""
    acc = (config or {}).get("accuracy") or {}
    return {
        "thresholds": {
            "st_target_err_acceptable_pct": acc.get("st_target_err_acceptable_pct", 5),
            "support_err_acceptable_pct": acc.get("support_err_acceptable_pct", 5),
            "st_target_mape_tweak_above": acc.get("st_target_mape_tweak_above", 8),
            "support_mape_tweak_above": acc.get("support_mape_tweak_above", 15),
        },
        "notes": acc.get("notes") or [
            "ST target err% = |close − short-term target| / close. Low = price near our ST target.",
            "Support err% = |close − MA20| / close. MA20 lags; some error is normal in fast moves.",
            "MAPE = mean absolute % error across tickers. Lower = model tracks close better.",
            "Acceptable: ST target err ≤ 5% per ticker, MAPE ≤ 5–8%. No tweak needed.",
            "Consider tweak: ST target MAPE > 8% or many tickers with err > 10%.",
        ],
    }


@router.get("/accuracy")
async def get_accuracy():
    """
    Price target accuracy report: model levels vs today's close.
    Reads data/accuracy_price_targets.json (generated when dashboard/daily run executes).
    interpretation: from config.accuracy (thresholds + notes for when err% is acceptable vs when to tweak).
    """
    config = _load_config()
    interpretation = _accuracy_interpretation(config)

    path = ROOT / "data" / "accuracy_price_targets.json"
    if not path.exists():
        return {
            "ok": False,
            "message": "Report not generated. Refresh the dashboard or run: cd backend && python scripts/accuracy_price_targets.py",
            "per_ticker": [],
            "summary": {},
            "recommendations": [],
            "amber_tickers": [],
            "tweak_tickers": [],
            "as_of": None,
            "interpretation": interpretation,
        }
    try:
        with open(path) as f:
            data = json.load(f)
        return {
            "ok": True,
            "message": None,
            "per_ticker": data.get("per_ticker", []),
            "summary": data.get("summary", {}),
            "recommendations": data.get("recommendations", []),
            "amber_tickers": data.get("amber_tickers", []),
            "tweak_tickers": data.get("tweak_tickers", []),
            "as_of": data.get("as_of"),
            "interpretation": interpretation,
        }
    except Exception as e:
        logger.warning("Failed to load accuracy report: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/paper-trading/purge-velocity")
async def purge_velocity_paper_trades(dry_run: bool = Query(True)):
    """
    One-time migration: remove contaminated velocity-track rows from paper_trades.csv.
    These were logged with inverted target logic and dedup bugs (fixed Jun 2026).
    Accumulate-track rows are NOT touched.

    Call with ?dry_run=false to actually purge. Default is dry_run=true (safe preview).
    """
    try:
        from signals.paper_trade_logger import PaperTradeLogger
        from config_loader import get_config
        config = get_config()
        data_root = config.get("data_root") or "data"
        pt = PaperTradeLogger(data_root=data_root)
        result = pt.purge_velocity_track(dry_run=dry_run)
        logger.info("[paper-trading] purge-velocity: %s", result)
        return result
    except Exception as e:
        logger.warning("purge-velocity failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/eod-universe")
async def get_eod_universe(date: str = Query("latest")):
    """
    Return compact Signal Universe rows for the EOD Universe table.
    Fast path: shaped Redis cache → universe_signals → signals_panel → dashboard cache → EOD scan.
    """
    try:
        from signals.cache import (
            get_cached_dashboard,
            get_eod_universe_panel,
            get_last_dashboard_snapshot,
            get_signals_panel,
            get_universe_signals,
            set_eod_universe_panel,
        )

        cached_panel = get_eod_universe_panel()
        if cached_panel and isinstance(cached_panel.get("rows"), list) and cached_panel["rows"]:
            logger.info("[eod-universe] panel cache hit (%d rows)", len(cached_panel["rows"]))
            return cached_panel

        config = _load_config()

        def _finish(shaped: dict, source: str) -> dict:
            shaped = dict(shaped)
            shaped["source"] = source
            try:
                set_eod_universe_panel(shaped)
            except Exception:
                pass
            return shaped

        if date != "latest":
            rows, as_of, source = _pick_best_eod_snapshot(config, date=date, allow_thin=True)
            if rows:
                return _finish(_shape_universe_rows(rows, as_of), source)
            return {
                "rows": [],
                "as_of": None,
                "total": 0,
                "message": f"No EOD snapshot for {date}.",
            }

        uni = get_universe_signals()
        if uni and isinstance(uni.get("rows"), list) and uni["rows"]:
            logger.info("[eod-universe] universe_signals hit (%d rows)", len(uni["rows"]))
            return _finish(_shape_universe_rows(uni["rows"], uni.get("as_of")), "universe_signals")

        sp = get_signals_panel()
        if sp and isinstance(sp.get("signals"), list) and sp["signals"]:
            logger.info("[eod-universe] signals_panel hit (%d rows)", len(sp["signals"]))
            return _finish(_shape_universe_rows(sp["signals"], sp.get("as_of")), "signals_panel")

        dash = get_cached_dashboard() or get_last_dashboard_snapshot()
        if dash and isinstance(dash.get("signals"), list) and dash["signals"]:
            as_of = dash.get("as_of_date") or dash.get("run_date")
            logger.info("[eod-universe] dashboard cache hit (%d rows)", len(dash["signals"]))
            return _finish(_shape_universe_rows(dash["signals"], as_of), "dashboard_cache")

        rows, as_of, source = _pick_best_eod_snapshot(config, date=date, allow_thin=True)
        if rows:
            min_full = _min_full_eod_rows(config)
            logger.info("[eod-universe] EOD scan %d rows from %s", len(rows), source)
            shaped = _shape_universe_rows(rows, as_of)
            if len(rows) < min_full:
                shaped["message"] = (
                    f"Dashboard-only snapshot ({len(rows)} tickers). "
                    f"Full EOD cohort is ~{min_full}+ — refresh on a trading day or run POST /api/eod/run?force=true."
                )
            return _finish(shaped, source)

        if dash is None:
            try:
                from api.dashboard_job import is_refresh_running, trigger_background_refresh

                if not is_refresh_running():
                    trigger_background_refresh(_compute_full_dashboard_sync)
            except Exception:
                pass

        return {
            "rows": [],
            "as_of": None,
            "total": 0,
            "message": "Refresh in progress — data will appear shortly. Click Refresh if not populated in 5 min.",
        }

    except Exception as e:
        logger.warning("eod-universe failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _shape_universe_rows(raw_rows: list, as_of: str | None) -> dict:
    """Shape raw EOD signal rows into compact universe table rows."""
    from signals.tracking_gate import gate_snapshot_from_row

    out = []
    for r in raw_rows:
        if not isinstance(r, dict) or not r.get("ticker"):
            continue
        ticker = str(r.get("ticker", "")).upper()
        if not ticker or r.get("error"):
            continue

        # Already panel-shaped row (from eod_universe_panel cache)
        if (
            r.get("gates_passed") is not None
            and r.get("score") is not None
            and r.get("composite_buy") is None
            and r.get("composite_score") is None
        ):
            out.append({
                "ticker": ticker,
                "close": r.get("close"),
                "change_pct": r.get("change_pct"),
                "score": r.get("score"),
                "regime": str(r.get("regime") or "NEUTRAL").upper(),
                "rsi": r.get("rsi"),
                "signal": str(r.get("signal") or "HOLD").upper(),
                "entry_mode": r.get("entry_mode"),
                "gates_passed": int(r.get("gates_passed") or 0),
                "gates_total": int(r.get("gates_total") or 4),
                "confidence": r.get("confidence"),
                "sector": str(r.get("sector") or ""),
                "market_cap_bucket": str(r.get("market_cap_bucket") or ""),
            })
            continue

        rs = r.get("retail_status") if isinstance(r.get("retail_status"), dict) else {}
        snap = gate_snapshot_from_row(r)
        gates_passed = int(snap.get("gates_passed") or 0)
        gates_total = int(snap.get("gates_total") or 4)

        entry_mode = rs.get("entry_mode") or r.get("entry_mode") or r.get("go_no_go")
        if entry_mode == "go":
            entry_mode = "full_go"
        elif entry_mode == "no_go":
            entry_mode = "hard_lock" if gates_passed == 0 else "starter_only"
        elif entry_mode in ("GO", "NO_GO"):
            entry_mode = "full_go" if entry_mode == "GO" else ("hard_lock" if gates_passed == 0 else "starter_only")

        conf = r.get("model_confidence_pct") or r.get("confidence_mid")
        if conf is None:
            conf_block = r.get("confidence")
            if isinstance(conf_block, dict):
                conf = conf_block.get("confidence_pct") or conf_block.get("confidence")
        try:
            conf = round(float(conf), 1) if conf is not None else None
        except (TypeError, ValueError):
            conf = None

        try:
            score = round(float(r.get("composite_buy") or r.get("composite_score") or 0), 1)
        except (TypeError, ValueError):
            score = None

        try:
            rsi = round(float(r.get("rsi") or r.get("rsi14") or 0), 1)
        except (TypeError, ValueError):
            rsi = None

        try:
            close = round(float(r.get("close") or 0), 2) or None
        except (TypeError, ValueError):
            close = None

        try:
            change_pct = round(float(r.get("change_pct") or r.get("price_change_pct") or 0), 2)
        except (TypeError, ValueError):
            change_pct = None

        out.append({
            "ticker": ticker,
            "close": close,
            "change_pct": change_pct,
            "score": score,
            "regime": str(r.get("regime") or "NEUTRAL").upper(),
            "rsi": rsi,
            "signal": str(r.get("signal") or r.get("suggestion") or "HOLD").upper(),
            "entry_mode": entry_mode,
            "gates_passed": gates_passed,
            "gates_total": gates_total,
            "confidence": conf,
            "sector": str(r.get("sector") or ""),
            "market_cap_bucket": str(r.get("market_cap_bucket") or ""),
        })

    out.sort(key=lambda x: (
        {"full_go": 0, "starter_only": 1, "hard_lock": 2}.get(str(x.get("entry_mode") or ""), 3),
        -(x.get("score") or 0),
    ))
    return {"rows": out, "as_of": as_of, "total": len(out)}
