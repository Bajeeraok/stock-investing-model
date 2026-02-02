"""
Dashboard API - exposes all model features as JSON.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

logger = logging.getLogger("api.dashboard")

ROOT = Path(__file__).resolve().parent.parent.parent
sys_path = list(__import__("sys").path)
if str(ROOT) not in sys_path:
    __import__("sys").path.insert(0, str(ROOT))

import yaml
from behavior.thesis import load_theses, get_nudge
from behavior.what_changed import what_changed
from opportunity.scanner import run_opportunity_scan
from portfolio.doctor import portfolio_report
from config_loader import add_ticker as _add_ticker, add_uploaded_portfolio, load_config, remove_ticker as _remove_ticker
from scripts.run_daily import (
    load_last_run,
    run_signals,
    save_last_run,
)
from signals.cross_asset import run_crypto_signals, run_cross_asset_daily, compute_cross_asset_guidelines
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

try:
    from best_picks import get_best_picks_2026
except ImportError:
    get_best_picks_2026 = None

router = APIRouter()


def _load_config():
    return load_config()


@router.get("/dashboard")
async def get_dashboard():
    """Full dashboard data - runs signals, portfolio, opportunities. May take 1-2 min."""
    logger.info("[dashboard] START loading dashboard")
    logger.info("[dashboard] section: config + last_run...")
    config = _load_config()
    last_run_prev = load_last_run()  # Load BEFORE save so what_changed compares old vs new
    logger.info("[dashboard] section: config + last_run DONE")

    # Build holdings list first (needed for portfolio tickers and for report)
    holdings = []
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

    # Consolidate tickers for single FMP batch quote (signals + portfolio + opportunities) to stay under API limit
    watchlist = config.get("watchlist", [])
    portfolio_tickers = [h.get("ticker") if isinstance(h, dict) else h for h in holdings]
    opportunity_universe = config.get("opportunity_universe") or []
    all_quote_tickers = list(dict.fromkeys([t for t in watchlist + portfolio_tickers + opportunity_universe if t]))
    prices_by_ticker = None
    use_fmp_batch_quote = config.get("data", {}).get("use_fmp_batch_quote", True) and get_fmp_api_key(config)
    if use_fmp_batch_quote and all_quote_tickers:
        batch_quotes, batch_err = fetch_batch_quote(config, all_quote_tickers)
        if not batch_err and batch_quotes:
            prices_by_ticker = {}
            for sym, row in batch_quotes.items():
                p = row.get("price")
                if p is not None:
                    try:
                        prices_by_ticker[sym] = float(p)
                    except (TypeError, ValueError):
                        pass
            if prices_by_ticker:
                logger.info("[dashboard] FMP batch quote: %d symbols, 1 request", len(prices_by_ticker))

    logger.info("[dashboard] section: run_signals (watchlist + indicators)...")
    results = run_signals(config, prices_by_ticker=prices_by_ticker)
    logger.info("[dashboard] section: run_signals DONE (%d tickers)", len(results) if results else 0)

    logger.info("[dashboard] section: portfolio_report (holdings + doctor)...")
    report = portfolio_report(
        holdings=holdings,
        results=results,
        watchlist=config.get("watchlist", []),
        score_cfg=config.get("score", {}),
        concentration_threshold_pct=config.get("concentration_alert_pct", 20),
        cash_deploy_min_score=config.get("cash_deploy_min_score", 70),
    )
    # Fill prices for holdings not in watchlist (no signal) from batch quote when available
    if prices_by_ticker:
        total_value = report.get("total_value") or 0.0
        filled_value = 0.0
        for h in report.get("per_holding", []):
            if h.get("price") is None and h.get("ticker") in prices_by_ticker:
                price = prices_by_ticker[h["ticker"]]
                qty = h.get("quantity") or 1
                value = qty * price
                h["price"] = price
                h["value"] = value
                filled_value += value
        if filled_value > 0:
            total_value += filled_value
            report["total_value"] = total_value
            for h in report.get("per_holding", []):
                if h.get("value") is not None and total_value > 0:
                    h["pct"] = round(100 * h["value"] / total_value, 1)
    logger.info("[dashboard] section: portfolio_report DONE")

    # Crypto (BTC, ETH)
    logger.info("[dashboard] section: crypto_signals...")
    crypto_tickers = config.get("crypto_watchlist") or ["BTC-USD", "ETH-USD"]
    crypto_signals = run_crypto_signals(crypto_tickers, config)
    logger.info("[dashboard] section: crypto_signals DONE")

    # Cross-asset (DXY, gold, oil) daily % change
    logger.info("[dashboard] section: cross_asset...")
    cross_asset_tickers = config.get("cross_asset_tickers") or ["DX-Y.NYB", "GLD", "USO"]
    cross_asset = run_cross_asset_daily(cross_asset_tickers)

    # Treasury 10Y from FMP - add to cross-asset if available
    try:
        rates, _ = fetch_treasury_rates(config)
        rate_10y = get_10y_rate(rates)
        if rate_10y is not None:
            cross_asset = list(cross_asset) + [{"ticker": "10Y", "label": "10Y Treasury", "close": rate_10y, "pct_change": None}]
    except Exception:
        pass
    logger.info("[dashboard] section: cross_asset DONE")

    # Economic calendar (next 7 days) - FMP, cached
    economic_calendar = []
    try:
        from signals.cache import cached_economic_calendar
        def _fetch_cal():
            ev, _ = fetch_economic_calendar(config, 7)
            return [e for e in (ev or [])[:30] if isinstance(e, dict)] if ev else []
        economic_calendar = cached_economic_calendar(7, _fetch_cal) or []
    except Exception:
        try:
            events, _ = fetch_economic_calendar(config, 7)
            if events and isinstance(events, list):
                economic_calendar = [e for e in events[:30] if isinstance(e, dict)]
        except Exception:
            pass

    # Real yield (FRED): 10Y - inflation expectations; headwind for gold/growth when high
    real_yield = None
    try:
        real_yield = get_real_yield_proxy(config)
    except Exception:
        pass

    # CFTC COT: speculative positioning extreme (gold, silver, crude) = reversal risk
    cot_extremes = []
    try:
        cot_extremes = get_cot_extremes_for_guidelines()
    except Exception:
        pass

    # Cross-asset guidelines (macro + calendar + real yield + COT)
    guidelines = compute_cross_asset_guidelines(
        cross_asset, economic_calendar,
        real_yield=real_yield,
        cot_extremes=cot_extremes,
    )

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
            vix_val = c.get("close")
            break
    if real_yield is not None and real_yield > 2.0:
        macro_regime = "Risk-Off"
    elif vix_val is not None and vix_val > 20:
        macro_regime = "Risk-Off"
    elif real_yield is not None and real_yield < 1.0 and (vix_val is None or vix_val < 15):
        macro_regime = "Risk-On"
    else:
        macro_regime = "Neutral"

    # FMP plan status (which features work, which need upgrade)
    fmp_plan_status = {}
    try:
        fmp_plan_status = run_fmp_plan_check(config)
    except Exception:
        fmp_plan_status = {"has_key": False, "available": [], "unavailable": []}

    # 2026 best tickers (long-term picks with confidence)
    logger.info("[dashboard] section: best_2026...")
    best_2026 = []
    if get_best_picks_2026:
        try:
            best_2026 = get_best_picks_2026(config, max_results=20)
        except Exception:
            best_2026 = []
    logger.info("[dashboard] section: best_2026 DONE (%d picks)", len(best_2026))

    logger.info("[dashboard] section: opportunities...")
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
    logger.info("[dashboard] section: opportunities DONE (%d)", len(opportunities))

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
        nudge = get_nudge(r["ticker"], r.get("regime", ""), r.get("composite_buy"), theses)
        thesis_check.append({
            "ticker": r["ticker"],
            "thesis": t.get("thesis", ""),
            "exit_condition": t.get("exit_condition", ""),
            "nudge": nudge,
        })

    trim_candidates = [h for h in report["per_holding"] if h.get("score") is not None and h["score"] < 40]

    # What changed: compare new results vs previous run (before we overwrite)
    what_changed_list = []
    for r in results:
        if r.get("error"):
            continue
        prev = last_run_prev.get(r["ticker"]) if last_run_prev else None
        if not prev:
            continue
        diffs, summary = what_changed(prev, r)
        if diffs or summary:
            what_changed_list.append({"ticker": r["ticker"], "changes": diffs, "summary": summary})
    logger.info("[dashboard] section: thesis_check + what_changed DONE (%d changed)", len(what_changed_list))

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
            size_dollars = total_value * (risk_pct / 100) / (stop_pct / 100)
            shares = max(0, int(size_dollars / float(r["close"])))
            r["risk_sizing"] = {
                "size_dollars": round(size_dollars, 0),
                "shares": shares,
                "stop_pct": stop_pct,
            }
        except (TypeError, ZeroDivisionError):
            r["risk_sizing"] = None

    save_last_run(results)  # Save AFTER building what_changed
    logger.info("[dashboard] section: risk_sizing + save_last_run DONE")

    logger.info("[dashboard] END loading dashboard - returning response")
    return {
        "signals": results,
        "crypto": crypto_signals,
        "cross_asset": cross_asset,
        "economic_calendar": economic_calendar,
        "guidelines": guidelines,
        "macro_regime": macro_regime,
        "cot_by_ticker": cot_by_ticker,
        "fmp_plan_status": fmp_plan_status,
        "best_2026": best_2026,
        "story_changes": story_changes,
        "portfolio": report,
        "trim_candidates": trim_candidates,
        "opportunities": opportunities,
        "thesis_check": thesis_check,
        "what_changed": what_changed_list,
        "earnings_risk_count": earnings_risk_count,
        "config": {
            "watchlist": config.get("watchlist", []),
            "score": config.get("score", {}),
            "regime": config.get("regime", {}),
            "risk_sizing": {"risk_pct": risk_pct, "stop_pct": stop_pct},
            "horizons": {
                "short_term": "~1 month (2–4 weeks)",
                "medium_term": "~3–6 months",
                "long_term": "1–2 years",
            },
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
async def get_backtest(tickers: str = "SPY", years: int = 2):
    """
    Backtest results - may take ~1 min per ticker.
    tickers: comma-separated (e.g. SPY,QQQ,GLD), default SPY
    years: 2, 5, or 10, default 2
    """
    config = _load_config()
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        ticker_list = ["SPY"]
    years = max(2, min(10, years))
    period = f"{years}y"
    from scripts.backtest_simple import run_backtest as _run_backtest
    out = []
    from signals.cache import cached_backtest
    for t in ticker_list[:6]:
        result = cached_backtest(t, period, lambda ticker=t, per=period: _run_backtest(ticker, per))
        out.append(result)
    return {"backtest": out, "backtest_years": years, "backtest_period": period}


@router.get("/theses")
async def get_theses():
    """Load thesis storage."""
    return {"theses": load_theses()}


@router.get("/config")
async def get_config():
    """Current config."""
    return _load_config()


@router.post("/tickers")
async def add_ticker_api(body: dict):
    """Add ticker to watchlist (persists in user_overrides, no config edit needed)."""
    ticker = body.get("ticker", "").strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    if _add_ticker(ticker):
        return {"ok": True, "ticker": ticker}
    return {"ok": False, "ticker": ticker, "message": "Already in watchlist"}


@router.delete("/tickers/{ticker}")
async def remove_ticker_api(ticker: str):
    """Remove ticker from user-added list (only affects additions, not config watchlist)."""
    if _remove_ticker(ticker):
        return {"ok": True, "ticker": ticker.upper()}
    return {"ok": False, "message": "Ticker not in additional list"}


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
            holdings.append(h)
        if not holdings:
            raise HTTPException(status_code=400, detail="No valid tickers found in Excel")
        add_uploaded_portfolio(portfolio_name.strip() or "Uploaded", holdings)
        return {"ok": True, "portfolio": portfolio_name, "holdings_count": len(holdings)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ticker/{ticker}")
async def get_ticker_detail(ticker: str):
    """Ticker detail: thesis, earnings, sector, peers, benchmark vs SPY/industry/peers."""
    from api.ticker_detail import get_ticker_detail as _get
    config = _load_config()
    try:
        return _get(ticker, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
