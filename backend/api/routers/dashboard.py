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
from portfolio.doctor import portfolio_report, allocation_recommendations
from portfolio.performance import compute_performance_vs_benchmark
from config_loader import add_ticker as _add_ticker, add_uploaded_portfolio, load_config, remove_ticker as _remove_ticker
from scripts.run_daily import (
    load_last_run,
    run_eod_snapshot_only,
    run_signals,
    save_last_run,
)
from scripts.accuracy_price_targets import run_accuracy_and_save
from signals.cross_asset import run_crypto_signals, run_cross_asset_daily, compute_cross_asset_guidelines
from signals.breadth_rs import get_market_regime, apply_rotation_step_down
from signals.typical_move import typical_move_for_symbols
from signals.next_day_bias import next_day_outlook_for_symbols, run_next_day_backtest
from signals.premarket import run_premarket_snapshot
from signals.indicator_validation import validate_indicators_vs_external
from signals.indicator_comparison import run_indicator_comparison
from signals.validation import get_validation_records
from signals.forward_tracking import get_forward_tracking
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
from signals.event_scenarios import get_upcoming_event_scenarios
from signals.macro_analog import get_macro_analog

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
    has_fmp_key = bool(get_fmp_api_key(config))
    use_fmp_batch_quote = config.get("data", {}).get("use_fmp_batch_quote", True) and has_fmp_key
    logger.info("[dashboard] Batch quote check: use_fmp_batch_quote=%s, all_quote_tickers=%d", use_fmp_batch_quote, len(all_quote_tickers))
    if use_fmp_batch_quote and all_quote_tickers:
        logger.info("[dashboard] FMP batch quote: requesting %d symbols...", len(all_quote_tickers))
        batch_quotes, batch_err = fetch_batch_quote(config, all_quote_tickers)
        if batch_err:
            logger.warning("[dashboard] FMP batch quote error: %s (falling back to per-ticker data)", batch_err)
            if "402" in str(batch_err) or "Payment" in str(batch_err):
                logger.warning("[dashboard] FMP batch-quote may require a paid plan; using yfinance/FMP historical per ticker")
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
            else:
                logger.warning("[dashboard] FMP batch quote: no valid prices returned")
        else:
            logger.warning("[dashboard] FMP batch quote: empty response")
    elif all_quote_tickers:
        # Use yfinance (delayed) live quotes until FMP batch quote is available on paid plan
        prices_by_ticker = fetch_yfinance_latest_prices(all_quote_tickers)
        if prices_by_ticker:
            logger.info("[dashboard] yfinance latest: %d prices (delayed quote)", len(prices_by_ticker))

    # Forward tracking (before run_signals) for hit-rate gate: suppress BUY/ADD when ADD hit rate < VIX threshold
    hit_rate_context = None
    try:
        ft = get_forward_tracking(
            data_root=ROOT / "data",
            tickers=["SPY", "QQQ"],
            horizons=[20],
        )
        sb = ft.get("summary_by_signal") or {}
        add_info = sb.get("HOLD/ADD")
        if add_info and isinstance(add_info, dict) and add_info.get("hit_rate_pct") is not None:
            hit_rate_context = {"add_hit_rate_pct": float(add_info["hit_rate_pct"])}
    except Exception as e:
        logger.debug("Forward tracking for hit-rate gate: %s", e)

    logger.info("[dashboard] section: run_signals (watchlist + indicators)...")
    results = run_signals(
        config,
        prices_by_ticker=prices_by_ticker,
        hit_rate_context=hit_rate_context,
    )
    logger.info("[dashboard] section: run_signals DONE (%d tickers)", len(results) if results else 0)

    # Update price-target accuracy report (same results, no extra fetch) so GET /api/accuracy is always current
    try:
        acc_path = run_accuracy_and_save(results, config)
        if acc_path:
            logger.info("[dashboard] section: accuracy report saved to %s", acc_path.name)
    except Exception as e:
        logger.warning("[dashboard] accuracy report save skipped: %s", e)

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
        )
        if prices_by_ticker:
            total_value = rep.get("total_value") or 0.0
            filled_value = 0.0
            for h in rep.get("per_holding", []):
                if h.get("price") is None and h.get("ticker") in prices_by_ticker:
                    price = prices_by_ticker[h["ticker"]]
                    qty = h.get("quantity") or 1
                    value = qty * price
                    h["price"] = price
                    h["value"] = value
                    filled_value += value
            if filled_value > 0:
                total_value += filled_value
                rep["total_value"] = total_value
                for h in rep.get("per_holding", []):
                    if h.get("value") is not None and total_value > 0:
                        h["pct"] = round(100 * h["value"] / total_value, 1)
        portfolios_out[name] = rep
    report = portfolios_out.get("All") or (portfolios_out[portfolio_names[1]] if len(portfolio_names) > 1 else {})
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

    # Market scenarios (what-if): upcoming events + historical reaction stats (13y)
    market_scenarios = []
    period_long = config.get("data", {}).get("period_long", "13y")
    try:
        market_scenarios = get_upcoming_event_scenarios(economic_calendar, period_long=period_long, symbol="SPY")
    except Exception as e:
        logger.debug("Market scenarios failed: %s", e)

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

    # Macro analog: historical one-liner when VIX + real yield match current state
    macro_analog = None
    try:
        macro_analog = get_macro_analog(vix_val, real_yield, config, period=config.get("data", {}).get("period_long", "13y"))
    except Exception as e:
        logger.debug("Macro analog failed: %s", e)

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

    # Model validation: predicted vs actual close (SPY/QQQ) from EOD snapshots
    model_validation = {"records": [], "summary": {}}
    try:
        model_validation_records, model_validation_summary = get_validation_records(
            data_root=ROOT / "data",
            max_records=60,
            tickers=["SPY", "QQQ"],
        )
        model_validation = {"records": model_validation_records, "summary": model_validation_summary}
    except Exception as e:
        logger.debug("Model validation failed: %s", e)

    # Forward tracking: multi-horizon (5d, 20d, 60d) returns, signal accuracy
    forward_tracking: dict = {"records": [], "summary_by_horizon": {}, "summary_by_signal": {}, "message": None}
    try:
        forward_tracking = get_forward_tracking(
            data_root=ROOT / "data",
            tickers=["SPY", "QQQ"],
            horizons=[5, 20, 60],
        )
    except Exception as e:
        logger.debug("Forward tracking failed: %s", e)
        forward_tracking["message"] = str(e)

    # Pre-market snapshot (futures + basket; can be slow)
    pre_market = None
    try:
        pre_market = run_premarket_snapshot()
    except Exception:
        pre_market = {}

    # Pre-market full (6 classes, 15 sources) — from scheduler-written file if present
    pre_market_full = None
    try:
        pre_market_file = ROOT / "data" / "pre_market_latest.json"
        if pre_market_file.exists():
            with open(pre_market_file) as _f:
                pre_market_full = json.load(_f)
    except Exception:
        pre_market_full = None

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
    logger.info("[dashboard] section: opportunities DONE (%d)", len(opportunities))

    # Portfolio Doctor: allocation recommendations (trim/add with $ and prices) per portfolio
    portfolio_doctor_recommendations = {}
    doctor_cfg = config.get("portfolio_doctor") or {}
    for pname, rep in portfolios_out.items():
        try:
            rec = allocation_recommendations(
                report=rep,
                results=results,
                opportunities=opportunities,
                best_2026=best_2026,
                doctor_cfg=doctor_cfg,
            )
            portfolio_doctor_recommendations[pname] = rec
        except Exception as e:
            logger.debug("Portfolio Doctor for %s: %s", pname, e)
    logger.info("[dashboard] section: portfolio_doctor DONE")

    # Performance vs benchmark (portfolio vs SPY/QQQ over 1m, 3m, 6m, 1y)
    performance_vs_benchmark = {"periods": [], "as_of": None, "message": None}
    if holdings and (portfolios or config.get("portfolio")):
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
                logger.info("[dashboard] section: performance_vs_benchmark DONE (%d periods)", len(performance_vs_benchmark["periods"]))
            else:
                performance_vs_benchmark["message"] = performance_vs_benchmark.get("message") or "Insufficient history"
        except Exception as e:
            logger.debug("Performance vs benchmark failed: %s", e)
            performance_vs_benchmark["message"] = str(e)
    else:
        performance_vs_benchmark["message"] = "Add portfolios in config to see performance vs benchmark"

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

    from datetime import datetime as _dt
    as_of_date = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info("[dashboard] END loading dashboard - returning response")
    return {
        "as_of_date": as_of_date,
        "signals": results,
        "crypto": crypto_signals,
        "cross_asset": cross_asset,
        "economic_calendar": economic_calendar,
        "market_scenarios": market_scenarios,
        "macro_analog": macro_analog,
        "guidelines": guidelines,
        "macro_regime": macro_regime,
        "market_regime": market_regime_data,
        "global_market_regime": next(
            (r.get("_global_market_regime") for r in results if not r.get("error") and r.get("_global_market_regime")),
            None,
        ),
        "next_day_outlook": next_day_outlook,
        "typical_move": typical_move,
        "indicator_validation": indicator_validation,
        "indicator_comparisons": indicator_comparisons,
        "model_validation": model_validation,
        "forward_tracking": forward_tracking,
        "pre_market": pre_market,
        "pre_market_full": pre_market_full,
        "cot_by_ticker": cot_by_ticker,
        "fmp_plan_status": fmp_plan_status,
        "best_2026": best_2026,
        "story_changes": story_changes,
        "portfolio": report,
        "portfolios": portfolios_out,
        "portfolio_names": portfolio_names,
        "portfolio_doctor_recommendations": portfolio_doctor_recommendations,
        "performance_vs_benchmark": performance_vs_benchmark,
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
            "regime_plain_english": {
                "UP": "Trend and momentum support the position; favor holding or adding on pullbacks.",
                "NEUTRAL": "Mixed signals; hold, avoid large new adds until clarity.",
                "DOWN": "Weak trend or momentum; consider trimming or avoiding new buys.",
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
    from signals.backtest_validation import validate_backtest_result
    out = []
    from signals.cache import cached_backtest
    for t in ticker_list[:6]:
        result = cached_backtest(t, period, lambda ticker=t, per=period: _run_backtest(ticker, per))
        if result and "error" not in result:
            result["validation"] = validate_backtest_result(result)
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


@router.get("/pre-market")
async def get_pre_market():
    """
    Pre-market signal engine (6 categories, 15 sources). Reads from data/pre_market_latest.json
    if present (written by scripts/pre_market_scheduler.py); otherwise runs engine once and returns.
    """
    pre_market_file = ROOT / "data" / "pre_market_latest.json"
    try:
        if pre_market_file.exists():
            with open(pre_market_file) as f:
                data = json.load(f)
            if data.get("composite_score") is not None and data.get("bias") and data.get("signals") is not None:
                return data
    except Exception as e:
        logger.debug("Pre-market file read failed: %s", e)
    try:
        from signals.premarket_engine import PreMarketEngine
        from scripts.pre_market_scheduler import report_to_dict
        engine = PreMarketEngine()
        report = engine.run(verbose=False)
        data = report_to_dict(report)
        pre_market_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pre_market_file, "w") as f:
            json.dump(data, f, indent=2)
        return data
    except Exception as e:
        logger.exception("Pre-market engine failed: %s", e)
        raise HTTPException(status_code=503, detail=f"Pre-market data unavailable: {e}")


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
    last_run_path = ROOT / "data" / "last_run.json"
    eod_path = ROOT / "data" / "eod" / f"{date_str}.json"
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
    logger.info("[eod/save-from-last-run] Saved %s from last_run (%d tickers)", date_str, len(run_results))
    return {
        "ok": True,
        "skipped": False,
        "snapshot_date": date_str,
        "snapshot_path": str(eod_path),
        "tickers_count": len(run_results),
    }


@router.post("/eod/run")
def run_eod_now(snapshot_date: str | None = None):
    """
    Run EOD snapshot ad-hoc: compute signals and save data/eod/YYYY-MM-DD.json.
    snapshot_date: optional query param (YYYY-MM-DD, e.g. 2026-02-17) to save for that EST date; if omitted, uses today EST.
    Skips if a snapshot for that date already exists (idempotent once per day when no date given).
    May take 1-2 minutes when run. Use for manual trigger or to backfill a day.
    """
    from datetime import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    today_est = _dt.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    date_str = snapshot_date.strip() if isinstance(snapshot_date, str) and snapshot_date.strip() else today_est
    eod_path = ROOT / "data" / "eod" / f"{date_str}.json"
    if eod_path.exists():
        logger.info("[eod/run] Snapshot already exists for %s, skipping", date_str)
        return {
            "ok": True,
            "skipped": True,
            "message": f"EOD snapshot already exists for {date_str}",
            "snapshot_date": date_str,
            "snapshot_path": str(eod_path),
        }
    config = _load_config()
    logger.info("[eod/run] Starting EOD snapshot run for date=%s", date_str)
    result = run_eod_snapshot_only(config, snapshot_date=date_str)
    if result.get("error"):
        logger.warning("[eod/run] EOD snapshot failed: %s", result["error"])
        raise HTTPException(status_code=500, detail=result["error"])
    logger.info("[eod/run] EOD snapshot saved: %s", result.get("snapshot_path"))
    return {
        "ok": True,
        "skipped": False,
        "snapshot_date": result.get("snapshot_date"),
        "snapshot_path": result.get("snapshot_path"),
        "tickers_count": result.get("tickers_count", 0),
        "pruned": result.get("pruned", 0),
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
