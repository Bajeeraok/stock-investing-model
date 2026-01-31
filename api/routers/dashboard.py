"""
Dashboard API - exposes all model features as JSON.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parent.parent.parent
sys_path = list(__import__("sys").path)
if str(ROOT) not in sys_path:
    __import__("sys").path.insert(0, str(ROOT))

import yaml
from behavior.thesis import load_theses, get_nudge
from behavior.what_changed import what_changed
from opportunity.scanner import run_opportunity_scan
from portfolio.doctor import portfolio_report
from scripts.run_daily import (
    load_config,
    load_last_run,
    run_signals,
    save_last_run,
)

router = APIRouter()


def _load_config():
    return load_config()


@router.get("/dashboard")
async def get_dashboard():
    """Full dashboard data - runs signals, portfolio, opportunities. May take 1-2 min."""
    config = _load_config()
    results = run_signals(config)
    save_last_run(results)

    portfolio = config.get("portfolio", [])
    if isinstance(portfolio, list) and portfolio and isinstance(portfolio[0], dict):
        holdings = portfolio
    else:
        holdings = [{"ticker": t, "quantity": 1} for t in config.get("watchlist", [])]

    report = portfolio_report(
        holdings=holdings,
        results=results,
        watchlist=config.get("watchlist", []),
        score_cfg=config.get("score", {}),
        concentration_threshold_pct=config.get("concentration_alert_pct", 20),
        cash_deploy_min_score=config.get("cash_deploy_min_score", 70),
    )

    opp_cfg = config.get("opportunity_criteria", {}) or {}
    universe = config.get("opportunity_universe") or []
    portfolio_tickers = [h.get("ticker") if isinstance(h, dict) else h for h in holdings]
    opportunities = run_opportunity_scan(
        universe=universe if universe else None,
        period=config.get("data", {}).get("period", "5y"),
        min_score=opp_cfg.get("min_score", 70),
        require_regime_up=opp_cfg.get("require_regime_up", True),
        max_rsi=opp_cfg.get("max_rsi", 75),
        require_price_above_ma200=True,
        min_macd_hist=opp_cfg.get("min_macd_hist", 0),
        up_min=config.get("regime", {}).get("up_min", 60),
        down_max=config.get("regime", {}).get("down_max", 40),
        exclude_from_watchlist=portfolio_tickers,
        max_results=opp_cfg.get("max_results", 25),
    )

    theses = load_theses()
    last_run = load_last_run()
    story_changes = [r for r in results if r.get("story_change")]
    what_changed_list = []
    for r in results:
        if r.get("error"):
            continue
        prev = last_run.get(r["ticker"]) if last_run else None
        if not prev:
            continue
        diffs = what_changed(prev, r)
        if diffs:
            what_changed_list.append({"ticker": r["ticker"], "changes": diffs})

    thesis_check = []
    for r in results:
        if r.get("error"):
            continue
        t = theses.get(r["ticker"])
        if not t:
            continue
        nudge = get_nudge(r["ticker"], r.get("regime", ""), r.get("composite_buy"), theses)
        thesis_check.append({
            "ticker": r["ticker"],
            "thesis": t.get("thesis", ""),
            "exit_condition": t.get("exit_condition", ""),
            "nudge": nudge,
        })

    trim_candidates = [h for h in report["per_holding"] if h.get("score") is not None and h["score"] < 40]

    return {
        "signals": results,
        "story_changes": story_changes,
        "portfolio": report,
        "trim_candidates": trim_candidates,
        "opportunities": opportunities,
        "thesis_check": thesis_check,
        "what_changed": what_changed_list,
        "config": {
            "watchlist": config.get("watchlist", []),
            "score": config.get("score", {}),
            "regime": config.get("regime", {}),
        },
    }


@router.get("/signals")
async def get_signals():
    """Signals only - faster than full dashboard."""
    config = _load_config()
    results = run_signals(config)
    save_last_run(results)
    return {"signals": results}


@router.get("/backtest")
async def get_backtest():
    """Backtest results - may take ~1 min per ticker."""
    config = _load_config()
    tickers = config.get("backtest_tickers", ["SPY", "QQQ"])
    period = config.get("data", {}).get("period", "10y") or "10y"
    from scripts.backtest_simple import run_backtest as _run_backtest
    out = []
    for t in tickers[:3]:
        result = _run_backtest(t, period)
        out.append(result)
    return {"backtest": out}


@router.get("/theses")
async def get_theses():
    """Load thesis storage."""
    return {"theses": load_theses()}


@router.get("/config")
async def get_config():
    """Current config."""
    return _load_config()


@router.get("/last-run")
async def get_last_run():
    """Last run state for comparison."""
    data = load_last_run()
    if data is None:
        return {"run_results": []}
    path = ROOT / "data" / "last_run.json"
    if not path.exists():
        return {"run_results": []}
    with open(path) as f:
        return json.load(f)
