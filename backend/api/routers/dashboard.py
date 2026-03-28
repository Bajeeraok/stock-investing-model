"""
Dashboard API - exposes all model features as JSON.
Uses ThreadPoolExecutor to load independent sections in parallel and reduce timeout risk.

Lazy-loaded on frontend (not needed in initial payload; fetched when user opens tab/panel):
  - Pre-market: PreMarketPanel fetches /api/pre-market on mount (Markets tab).
  - Accuracy: AccuracyPriceTargets fetches /api/accuracy on mount (Analysis tab).
  - Backtest: BacktestStatus fetches /api/backtest on mount (Analysis tab).
  - Alerts: AlertsPanel fetches /api/scanner/alerts on mount (Overview > Alerts).
  - Ticker detail: TickerDetailModal fetches /api/ticker, /api/confidence, etc. when user opens a ticker.
  - Chat: /api/chat on user message. Test suite: /api/test-suite on run.
Pre-market is skipped in the parallel block below so the initial dashboard is faster; the UI loads it when Markets tab is shown.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from config_loader import add_ticker as _add_ticker, add_uploaded_portfolio, get_data_root, load_config, remove_ticker as _remove_ticker
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
except ImportError:
    generate_tier1_payload = None

try:
    from best_picks import get_best_picks_2026
except ImportError:
    get_best_picks_2026 = None

router = APIRouter()


def _load_config():
    return load_config()


@router.get("/dashboard")
async def get_dashboard():
    """Full dashboard data - runs signals, portfolio, opportunities. May take 1-2 min. Uses Redis cache (3 min TTL) when available."""
    try:
        from signals.cache import get_cached_dashboard
        cached = get_cached_dashboard()
        if cached is not None:
            logger.info("[dashboard] serving from Redis cache")
            return cached
    except Exception as e:
        logger.debug("[dashboard] cache check skipped: %s", e)

    dashboard_start = time.perf_counter()
    logger.info("[dashboard] START loading dashboard")
    t0 = time.perf_counter()
    logger.info("[dashboard] section: config + last_run...")
    config = _load_config()
    last_run_prev = load_last_run()  # Load BEFORE save so what_changed compares old vs new
    logger.info("[dashboard] section: config + last_run DONE (%.0f ms)", (time.perf_counter() - t0) * 1000)

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
    prices_from_fmp_batch = False
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
    logger.info("[dashboard] section: run_signals (watchlist + indicators)...")
    results = run_signals(
        config,
        prices_by_ticker=prices_by_ticker,
        hit_rate_context=hit_rate_context,
    )
    logger.info("[dashboard] section: run_signals DONE (%d tickers, %.0f ms)", len(results) if results else 0, (time.perf_counter() - t0) * 1000)

    # Paper trading log: capture today's signals (idempotent by date+ticker+signal)
    try:
        from datetime import datetime as _dt

        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo  # type: ignore

        paper_trade_date = _dt.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        from signals.paper_trade_logger import PaperTradeLogger

        pt = PaperTradeLogger(data_root=get_data_root())
        paper_log = pt.log_signals_from_results(
            results, only_actionable=False, date_str=paper_trade_date
        )
        logger.info("[dashboard] paper trades logged: %s", paper_log)
        paper_trading["log"] = paper_log
    except Exception as e:
        logger.debug("Paper trading log failed: %s", e)

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
            with ThreadPoolExecutor(max_workers=8) as ex:
                futures = [ex.submit(_confidence_one, t) for t in holdings_tickers]
                for fut in as_completed(futures):
                    ticker, conf = fut.result()
                    if conf is not None:
                        confidence_by_ticker[ticker] = conf
            logger.info("[dashboard] confidence for %d holdings tickers (parallel, %.0f ms)", len(confidence_by_ticker), (time.perf_counter() - t0_conf) * 1000)
        except Exception as e:
            logger.debug("Confidence fetch failed: %s", e)

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
        eod_snapshots_out: list = []
        try:
            from signals.cache import get_eod_snapshot_redis, list_eod_dates_redis
            seen: set = set()
            for date_str in list_eod_dates_redis():
                if date_str in seen:
                    continue
                seen.add(date_str)
                try:
                    data = get_eod_snapshot_redis(date_str)
                    size_bytes = len(json.dumps(data, default=str)) if data else 0
                    run_date = data.get("run_date") or data.get("snapshot_date") if isinstance(data, dict) else None
                    eod_snapshots_out.append({"date": date_str, "size_bytes": size_bytes, "run_date": run_date})
                except Exception:
                    pass
            eod_dir = data_root / "eod"
            if eod_dir.exists():
                for p in sorted(eod_dir.glob("*.json"), reverse=True):
                    try:
                        stem = p.stem
                        if stem in seen:
                            continue
                        if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
                            seen.add(stem)
                            size_bytes = p.stat().st_size
                            run_date = None
                            try:
                                with open(p) as _f:
                                    data = json.load(_f)
                                run_date = data.get("run_date") or data.get("snapshot_date")
                            except Exception:
                                pass
                            eod_snapshots_out.append({"date": stem, "size_bytes": size_bytes, "run_date": run_date})
                    except Exception:
                        pass
            eod_snapshots_out.sort(key=lambda x: x["date"], reverse=True)
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
                    lambda: run_insider_flow(watchlist_tickers_for_insider, max_form4_per_ticker=2, days_lookback=90),
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

    def _task_best_2026():
        if not get_best_picks_2026:
            return ("best_2026", [])
        try:
            return ("best_2026", get_best_picks_2026(config, max_results=20))
        except Exception:
            return ("best_2026", [])

    def _task_model_validation():
        try:
            recs, summary = get_validation_records(data_root=data_root, max_records=60, tickers=["SPY", "QQQ"])
            return ("model_validation", {"records": recs, "summary": summary})
        except Exception as e:
            logger.debug("Model validation failed: %s", e)
            return ("model_validation", {"records": [], "summary": {}})

    def _task_forward_tracking():
        try:
            return ("forward_tracking", get_forward_tracking(data_root=data_root, tickers=["SPY", "QQQ"], horizons=[5, 20, 60]))
        except Exception as e:
            ft = {"records": [], "summary_by_horizon": {}, "summary_by_signal": {}, "message": str(e)}
            return ("forward_tracking", ft)

    # Pre-market full: lazy-loaded with pre_market above (PreMarketPanel fetches /api/pre-market).

    def _task_paper_trading_async():
        try:
            from signals.paper_trade_logger import PaperTradeLogger
            pt = PaperTradeLogger(data_root=data_root)
            sync = pt.sync_targets_stops_from_results(results)
            mtm = pt.mark_to_market()
            mtm_history_log = pt.append_mtm_history()
            fill = pt.fill_outcomes()
            summary = pt.get_performance_summary(min_completed=60)
            recent = pt.get_recent(limit=40)
            mtm_history = pt.get_mtm_history_map(recent or [], limit_per_trade=12)
            return ("paper_trading_async", {
                "sync_targets": sync, "mtm": mtm, "mtm_history_log": mtm_history_log,
                "fill": fill, "summary": summary, "recent": recent, "mtm_history": mtm_history,
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

    parallel_task_specs = [
        ("crypto_signals", _task_crypto),
        ("cross_asset", _task_cross_asset),
        ("economic_calendar", _task_economic_calendar),
        ("real_yield", _task_real_yield),
        ("cot_extremes", _task_cot),
        ("eod_redis", _task_eod_redis),
        ("insider_flow", _task_insider),
        ("fmp_plan_status", _task_fmp_plan),
        ("best_2026", _task_best_2026),
        ("model_validation", _task_model_validation),
        ("forward_tracking", _task_forward_tracking),
        ("paper_trading_async", _task_paper_trading_async),
    ]
    parallel_results: dict = {}
    t_parallel = time.perf_counter()
    logger.info("[dashboard] section: parallel load (%d tasks)...", len(parallel_task_specs))
    with ThreadPoolExecutor(max_workers=min(14, len(parallel_task_specs))) as ex:
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
    best_2026 = parallel_results.get("best_2026", [])
    model_validation = parallel_results.get("model_validation", {"records": [], "summary": {}})
    forward_tracking = parallel_results.get("forward_tracking", {"records": [], "summary_by_horizon": {}, "summary_by_signal": {}, "message": None})
    paper_async = parallel_results.get("paper_trading_async")
    if paper_async:
        paper_trading["sync_targets"] = paper_async.get("sync_targets")
        paper_trading["mtm"] = paper_async.get("mtm")
        paper_trading["mtm_history_log"] = paper_async.get("mtm_history_log")
        paper_trading["fill"] = paper_async.get("fill")
        paper_trading["summary"] = paper_async.get("summary")
        paper_trading["recent"] = paper_async.get("recent")
        paper_trading["mtm_history"] = paper_async.get("mtm_history") or paper_async.get("mtm_history_map")
    try:
        paper_trading["data_root"] = str(get_data_root())
        paper_trading["persistence_note"] = "Set env DATA_ROOT to a persistent path (e.g. volume) so paper trades and EOD survive restarts."
    except Exception:
        pass

    # Market scenarios (what-if): upcoming events + historical reaction stats (13y)
    market_scenarios = []
    try:
        market_scenarios = get_upcoming_event_scenarios(economic_calendar, period_long=period_long, symbol="SPY")
    except Exception as e:
        logger.debug("Market scenarios failed: %s", e)

    # Cross-asset guidelines (macro + calendar + real yield + COT) — uses parallel-loaded data
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

    # (model_validation, forward_tracking, paper_trading sync, pre_market, pre_market_full, eod_snapshots, redis_status, insider_flow, fmp_plan_status, best_2026 loaded in parallel above)

    # best_2026 loaded in parallel above

    t0 = time.perf_counter()
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
    logger.info("[dashboard] section: opportunities DONE (%d, %.0f ms)", len(opportunities), (time.perf_counter() - t0) * 1000)

    # Confidence for add candidates (opportunities + best_2026)
    portfolio_tickers_set = {h.get("ticker") if isinstance(h, dict) else h for h in holdings}
    add_candidate_tickers = list(dict.fromkeys(
        [o.get("ticker") for o in opportunities if o.get("ticker") and o.get("ticker") not in portfolio_tickers_set]
        + [b.get("ticker") for b in best_2026 if b.get("ticker") and b.get("ticker") not in portfolio_tickers_set]
    ))
    t0_conf_add = time.perf_counter()
    for ticker in add_candidate_tickers:
        if ticker in confidence_by_ticker:
            continue
        try:
            conf = run_confidence(ticker, config=config)
            if conf.get("confidence") is not None:
                confidence_by_ticker[ticker] = conf
        except Exception as e:
            logger.debug("Confidence for add candidate %s: %s", ticker, e)
    if add_candidate_tickers:
        logger.info("[dashboard] confidence for %d add candidates (%.0f ms)", sum(1 for t in add_candidate_tickers if t in confidence_by_ticker), (time.perf_counter() - t0_conf_add) * 1000)

    # Portfolio Doctor: allocation recommendations (trim/add with $ and prices) per portfolio
    t0 = time.perf_counter()
    portfolio_doctor_recommendations = {}
    doctor_cfg = dict(config.get("portfolio_doctor") or {})
    doctor_cfg["model_rules"] = config.get("model_rules") or {}
    doctor_cfg["cash_deploy_min_score"] = config.get("cash_deploy_min_score", 70)
    for pname, rep in portfolios_out.items():
        try:
            rec = allocation_recommendations(
                report=rep,
                results=results,
                opportunities=opportunities,
                best_2026=best_2026,
                doctor_cfg=doctor_cfg,
                confidence_by_ticker=confidence_by_ticker,
            )
            portfolio_doctor_recommendations[pname] = rec
        except Exception as e:
            logger.debug("Portfolio Doctor for %s: %s", pname, e)
    logger.info("[dashboard] section: portfolio_doctor DONE (%.0f ms)", (time.perf_counter() - t0) * 1000)

    # Performance vs benchmark (portfolio vs SPY/QQQ over 1m, 3m, 6m, 1y)
    performance_vs_benchmark = {"periods": [], "as_of": None, "message": None}
    t0_perf = time.perf_counter()
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
        nudge = get_nudge(r["ticker"], r.get("regime", ""), r.get("composite_buy"), theses)
        thesis_check.append({
            "ticker": r["ticker"],
            "thesis": t.get("thesis", ""),
            "exit_condition": t.get("exit_condition", ""),
            "nudge": nudge,
        })

    trim_candidates = [h for h in report["per_holding"] if h.get("score") is not None and h["score"] < 40]

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
        if diffs or summary:
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
            }
        except (TypeError, ZeroDivisionError):
            r["risk_sizing"] = None

    save_last_run(results)  # Save AFTER building what_changed
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

    from datetime import datetime as _dt
    as_of_date = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Retail value-add: daily briefing, portfolio heat, one-line actions, badges, nudges
    retail_briefing = {}
    try:
        from retail_briefing import build_retail_briefing
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
        )
    except Exception as e:
        logger.debug("Retail briefing failed: %s", e)

    morning_newsletter = None
    try:
        from signals.morning_newsletter import build_morning_newsletter
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
            model_validation=model_validation,
        )
    except Exception as e:
        logger.debug("model_health failed: %s", e)

    out = {
        "as_of_date": as_of_date,
        "signals": results,
        "retail_briefing": retail_briefing,
        "crypto": crypto_signals,
        "cross_asset": cross_asset,
        "economic_calendar": economic_calendar,
        "market_scenarios": market_scenarios,
        "macro_analog": macro_analog,
        "market_forecast": market_forecast,
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
        "paper_trading": paper_trading,
        "pre_market": pre_market,
        "pre_market_full": pre_market_full,
        "eod_snapshots": eod_snapshots,
        "redis_status": redis_status_out,
        "insider_flow": insider_flow,
        "cot_by_ticker": cot_by_ticker,
        "fmp_plan_status": fmp_plan_status,
        "best_2026": best_2026,
        "story_changes": story_changes,
        "portfolio": report,
        "portfolios": portfolios_out,
        "portfolio_names": portfolio_names,
        "portfolio_doctor_recommendations": portfolio_doctor_recommendations,
        "performance_vs_benchmark": performance_vs_benchmark,
        "tax_aware_exits": tax_aware_exits_out,
        "trim_candidates": trim_candidates,
        "opportunities": opportunities,
        "thesis_check": thesis_check,
        "what_changed": what_changed_list,
        "earnings_risk_count": earnings_risk_count,
        "morning_newsletter": morning_newsletter,
        "model_health": model_health,
        "config": {
            "watchlist": config.get("watchlist", []),
            "score": config.get("score", {}),
            "regime": config.get("regime", {}),
            "risk_sizing": {"risk_pct": risk_pct, "stop_pct": stop_pct},
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
        from signals.cache import set_cached_dashboard
        set_cached_dashboard(out)
    except Exception as e:
        logger.debug("[dashboard] cache set skipped: %s", e)
    logger.info("[dashboard] END loading dashboard - total %.0f ms", (time.perf_counter() - dashboard_start) * 1000)
    return out


@router.get("/signals")
async def get_signals():
    """Signals only - faster than full dashboard."""
    config = _load_config()
    results = run_signals(config)
    save_last_run(results)
    return {"signals": results}


@router.get("/backtest")
async def get_backtest(
    tickers: str = "SPY",
    years: int = 2,
    refresh: bool = False,
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
    from scripts.backtest_simple import run_backtest as _run_backtest
    from signals.backtest_validation import validate_backtest_result
    out = []
    from signals.cache import cached_backtest
    for t in ticker_list[:6]:
        result = cached_backtest(
            t,
            period,
            lambda ticker=t, per=period: _run_backtest(ticker, per),
            force_refresh=refresh,
        )
        if result and "error" not in result:
            result["validation"] = validate_backtest_result(result)
        out.append(result)
    return {
        "backtest": out,
        "backtest_years": years,
        "backtest_period": period,
        "bypass_cache": refresh,
    }


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


@router.get("/pre-market")
async def get_pre_market():
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

    # ── Case 1: fresh file from today ──────────────────────────────────────
    if cached and _premarket_file_is_from_today(cached):
        cached.pop("stale", None)  # Clean up stale flag if somehow present
        return cached

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
            return data
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
        return cached

    # ── Case 4: no data at all ─────────────────────────────────────────────
    raise HTTPException(
        status_code=503,
        detail="Pre-market data is only generated before the open (4:00–9:30 AM ET, weekdays). "
               "Run scripts/pre_market_scheduler.py during that window, or use the last cached snapshot.",
    )


@router.get("/ticker/{ticker}")
async def get_ticker_detail(ticker: str):
    """Ticker detail: thesis, earnings, sector, peers, benchmark vs SPY/industry/peers."""
    from api.ticker_detail import get_ticker_detail as _get
    config = _load_config()
    try:
        return _get(ticker, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roadmaps")
async def get_roadmaps(tickers: str = ""):
    """
    Lightweight roadmaps for multiple tickers (dashboard Roadmaps tab).
    Query: ?tickers=NVDA,GLD,SPY (comma-separated, max 12).
    Returns: { roadmaps: [ { ticker, one_answer, trade_roadmap } ] }.
    Each ticker uses full get_ticker_detail; we strip to one_answer + trade_roadmap only.
    """
    from api.ticker_detail import get_ticker_detail as _get
    config = _load_config()
    raw = [t.strip().upper() for t in tickers.split(",") if t.strip()][:12]
    if not raw:
        return {"roadmaps": [], "message": "Provide ?tickers=NVDA,GLD,SPY"}
    out = []
    for t in raw:
        try:
            detail = _get(t, config)
            inv = detail.get("investor_summary") or {}
            out.append({
                "ticker": t,
                "one_answer": inv.get("one_answer"),
                "trade_roadmap": inv.get("trade_roadmap"),
            })
        except Exception as e:
            logger.warning("Roadmap skip %s: %s", t, e)
            out.append({"ticker": t, "one_answer": None, "trade_roadmap": None})
    return {"roadmaps": out}


@router.get("/confidence/{ticker}")
async def get_confidence(ticker: str):
    """
    7-layer ConfidenceEngine breakdown for a single ticker.
    Returns: confidence (0-1), action, breakdown per layer, disqualifiers, risk_factors, watch_levels.
    Layers: HMM regime, pattern+technical, LightGBM prob, options sentiment, insider, fundamentals, NLP.
    Gracefully degrades — missing layers are redistributed. Safe to call any time.
    """
    ticker = ticker.upper().strip()
    try:
        from signals.confidence_engine import run_confidence
        config = _load_config()
        result = run_confidence(ticker, config=config)
        return result
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Confidence engine unavailable: {e}")
    except Exception as e:
        logger.exception("Confidence engine error for %s: %s", ticker, e)
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
async def get_price_targets(ticker: str, regime: str = "NEUTRAL"):
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
        result = run_price_targets(ticker, market_regime=regime.upper(), config=config)
        return result
    except Exception as e:
        logger.exception("Price targets error for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/classify/{ticker}")
async def get_classify(ticker: str):
    """
    Pre-flight asset classification for a single ticker.
    Returns asset type, weight profile, pre-flight flags, and scoreability.
    Fast — no data fetching, just registry lookup + flag generation.
    Call this when user types a new ticker to show asset type badge and warnings immediately.
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
    eod_path = get_data_root() / "eod" / f"{date_str}.json"
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
