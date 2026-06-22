"""
Retail Phase 1: lightweight quote tick (~5 min) + signal warm (~30 min).

Quote tick patches live prices into the cached dashboard snapshot.
Signal warm runs run_signals on the EOD universe and merges signal/portfolio
sections — skips accuracy, paper backfill, performance vs benchmark, analysis bundle.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger("api.dashboard_warm")

_fmp_batch_quote_disabled_until: float = 0.0


def get_retail_quote_tickers(config: dict, holdings: list) -> list[str]:
    """EOD signal universe ∪ portfolio ∪ watchlist (deduped, uppercase)."""
    from config_loader import get_eod_signal_universe

    merged = list(get_eod_signal_universe(config))
    seen = {str(t).upper() for t in merged if t}
    for src in (
        config.get("watchlist") or [],
        [h.get("ticker") if isinstance(h, dict) else h for h in holdings],
    ):
        for t in src:
            sym = str(t or "").upper().strip()
            if sym and sym not in seen:
                merged.append(sym)
                seen.add(sym)
    return merged


def fetch_live_prices(config: dict, tickers: list[str]) -> tuple[dict[str, float] | None, bool]:
    """
    Batch live quotes (FMP batch when available, else yfinance).
    Returns (prices_by_ticker, used_fmp_batch).
    """
    global _fmp_batch_quote_disabled_until

    if not tickers:
        return None, False

    from signals.fmp_client import fetch_batch_quote, get_fmp_api_key
    from signals.fetcher import fetch_yfinance_latest_prices
    from signals.providers import MAJOR_INDEX_ETFS

    has_fmp_key = bool(get_fmp_api_key(config))
    circuit_open = time.monotonic() < _fmp_batch_quote_disabled_until
    use_fmp = (
        config.get("data", {}).get("use_fmp_batch_quote", True)
        and has_fmp_key
        and not circuit_open
    )
    prices_by_ticker: dict[str, float] | None = None
    prices_from_fmp = False

    if use_fmp:
        batch_quotes, batch_err = fetch_batch_quote(config, tickers)
        if batch_err:
            if "402" in str(batch_err) or "Payment" in str(batch_err):
                _fmp_batch_quote_disabled_until = time.monotonic() + 7200
                logger.warning("[dashboard-warm] FMP batch-quote 402 — 2h cooldown")
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
                prices_from_fmp = True

    if not prices_by_ticker:
        prices_by_ticker = fetch_yfinance_latest_prices(tickers)

    if not prices_by_ticker:
        return None, False

    use_yahoo_overlay = config.get("data", {}).get("yahoo_overlay_index_etf_quotes", True)
    if use_yahoo_overlay and prices_from_fmp:
        idx = [t for t in tickers if t and str(t).strip().upper() in MAJOR_INDEX_ETFS]
        if idx:
            yf_idx = fetch_yfinance_latest_prices(idx)
            if yf_idx:
                prices_by_ticker = dict(prices_by_ticker)
                for t in idx:
                    if t in yf_idx:
                        prices_by_ticker[t] = yf_idx[t]

    return prices_by_ticker, prices_from_fmp


def _iso_utc_now() -> str:
    import time as _time

    return _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())


def _patch_portfolios_with_prices(
    portfolios_out: dict[str, dict],
    prices_by_ticker: dict[str, float],
    *,
    fmp_batch: bool,
) -> None:
    src = "fmp_batch" if fmp_batch else "yfinance_latest"
    for rep in portfolios_out.values():
        if not isinstance(rep, dict):
            continue
        total_value = rep.get("total_value") or 0.0
        recalc_total = False
        for h in rep.get("per_holding") or []:
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
            h["live_price_source"] = src
            if old_val != h["value"]:
                recalc_total = True
        if recalc_total:
            total_value = sum(
                float(x.get("value") or 0) for x in rep.get("per_holding", []) if x.get("value") is not None
            )
            rep["total_value"] = total_value
            for h in rep.get("per_holding", []):
                if h.get("value") is not None and total_value > 0:
                    h["pct"] = round(100 * h["value"] / total_value, 1)


def compute_quote_tick_sync() -> dict | None:
    """Patch cached dashboard with fresh batch quotes. No-op when signal warm is running."""
    from api.dashboard_job import is_refresh_running
    from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot, merge_dashboard_cache_updates

    if is_refresh_running():
        logger.info("[dashboard-warm] quote tick skipped — refresh in progress")
        return None

    cached = get_cached_dashboard() or get_last_dashboard_snapshot()
    if not cached:
        logger.info("[dashboard-warm] quote tick skipped — no dashboard cache")
        return None

    from api.routers.dashboard import _build_signal_scores, _holdings_from_config, _load_config

    config = _load_config()
    holdings = _holdings_from_config(config)
    tickers = get_retail_quote_tickers(config, holdings)
    prices, fmp_batch = fetch_live_prices(config, tickers)
    if not prices:
        logger.warning("[dashboard-warm] quote tick — no prices returned")
        return None

    results = list(cached.get("signals") or [])
    if results:
        from signals.live_quotes import apply_live_quotes_to_results

        apply_live_quotes_to_results(
            results,
            prices,
            source="fmp_batch" if fmp_batch else "yfinance_latest",
        )

    portfolios_out = dict(cached.get("portfolios") or {})
    if portfolios_out:
        _patch_portfolios_with_prices(portfolios_out, prices, fmp_batch=fmp_batch)
    portfolio = portfolios_out.get("All") or cached.get("portfolio") or {}

    ts = _iso_utc_now()
    df = dict(cached.get("data_freshness") or {})
    df["quotes_updated_at"] = ts

    updates: dict[str, Any] = {
        "signals": results,
        "signal_scores": _build_signal_scores(results),
        "portfolios": portfolios_out,
        "portfolio": portfolio,
        "data_freshness": df,
    }
    ok = merge_dashboard_cache_updates(updates)
    logger.info(
        "[dashboard-warm] quote tick %s — %d prices, %d signal rows",
        "ok" if ok else "FAILED",
        len(prices),
        len(results),
    )
    try:
        from signals.process_memory import release_process_caches

        release_process_caches(aggressive=False)
    except Exception:
        pass
    return updates if ok else None


def _write_panel_caches(config: dict, results: list[dict], as_of_date: str | None) -> None:
    from api.routers.dashboard import _resolve_universe_cache_rows, _shape_universe_rows
    from config_loader import get_eod_signal_universe
    from signals.cache import set_eod_universe_panel, set_signals_panel, set_universe_signals

    universe_rows, universe_source = _resolve_universe_cache_rows(config, results)
    eod_uni_n = len(get_eod_signal_universe(config))
    ok_uni = set_universe_signals(universe_rows, as_of=as_of_date)
    try:
        shaped = _shape_universe_rows(universe_rows, as_of_date)
        shaped["source"] = universe_source
        set_eod_universe_panel(shaped)
    except Exception as e:
        logger.debug("[dashboard-warm] eod_universe_panel: %s", e)
    ok_sig = set_signals_panel(results, as_of=as_of_date)
    logger.info(
        "[dashboard-warm] panel caches universe=%s (%d/%d) signals=%s (%d rows)",
        "ok" if ok_uni else "FAIL",
        len(universe_rows),
        eod_uni_n,
        "ok" if ok_sig else "FAIL",
        len(results),
    )


def compute_signal_warm_sync() -> dict:
    """Signal warm: EOD universe signals + portfolio; merge into cached macro snapshot."""
    from api.routers.dashboard import (
        _build_event_risk_strip,
        _build_hunter_panel_payload,
        _build_signal_scores,
        _build_tactical_breakouts,
        _doctor_recommendations_for_portfolios,
        _holdings_from_config,
        _load_config,
        _opportunities_bundle_enabled,
    )
    from behavior.thesis import get_nudge, load_theses
    from behavior.what_changed import what_changed
    from config_loader import get_eod_signal_universe
    from portfolio.doctor import portfolio_report
    from scripts.run_daily import load_last_run, save_last_run
    from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot, set_cached_dashboard
    from signals.confidence_engine import run_confidence
    from signals.forward_tracking import get_forward_tracking
    from signals.time_et import format_et_display, now_iso_et

    t0_all = time.perf_counter()
    config = _load_config()
    cached = get_cached_dashboard() or get_last_dashboard_snapshot()

    if not cached:
        logger.info("[dashboard-warm] no cache — falling back to full dashboard compute")
        from api.routers.dashboard import _compute_full_dashboard_sync

        return _compute_full_dashboard_sync()

    last_run_prev = load_last_run()
    holdings = _holdings_from_config(config)
    signal_universe = get_eod_signal_universe(config)
    quote_tickers = get_retail_quote_tickers(config, holdings)

    prices, fmp_batch = fetch_live_prices(config, quote_tickers)
    from config_loader import get_data_root

    hit_rate_context = None
    try:
        ft = get_forward_tracking(
            data_root=get_data_root(),
            tickers=["SPY", "QQQ"],
            horizons=[20],
        )
        add_info = (ft.get("summary_by_signal") or {}).get("HOLD/ADD")
        if isinstance(add_info, dict) and add_info.get("hit_rate_pct") is not None:
            hit_rate_context = {"add_hit_rate_pct": float(add_info["hit_rate_pct"])}
    except Exception as e:
        logger.debug("[dashboard-warm] hit-rate gate: %s", e)

    from scripts.run_daily import run_signals

    logger.info("[dashboard-warm] run_signals EOD universe (%d tickers)...", len(signal_universe))
    t0 = time.perf_counter()
    results = run_signals(
        config,
        prices_by_ticker=prices,
        hit_rate_context=hit_rate_context,
        tickers=signal_universe,
    )
    logger.info("[dashboard-warm] run_signals DONE (%d rows, %.0f ms)", len(results or []), (time.perf_counter() - t0) * 1000)

    market_reversal_overlay = cached.get("market_reversal_overlay")
    for r in results or []:
        if isinstance(r, dict) and r.get("market_overlay"):
            market_reversal_overlay = r.get("market_overlay")
            r.pop("market_overlay", None)

    if prices:
        from signals.live_quotes import apply_live_quotes_to_results

        apply_live_quotes_to_results(
            results,
            prices,
            source="fmp_batch" if fmp_batch else "yfinance_latest",
        )

    confidence_by_ticker: dict = {}
    holdings_tickers = list(dict.fromkeys(h.get("ticker") if isinstance(h, dict) else h for h in holdings))

    def _confidence_one(ticker: str):
        try:
            conf = run_confidence(ticker, config=config)
            return (ticker, conf) if conf.get("confidence") is not None else (ticker, None)
        except Exception as e:
            logger.debug("[dashboard-warm] confidence %s: %s", ticker, e)
            return (ticker, None)

    if holdings_tickers:
        t0_conf = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(_confidence_one, t) for t in holdings_tickers]
            for fut in as_completed(futures):
                ticker, conf = fut.result()
                if conf is not None:
                    confidence_by_ticker[ticker] = conf
        logger.info(
            "[dashboard-warm] confidence %d holdings (%.0f ms)",
            len(confidence_by_ticker),
            (time.perf_counter() - t0_conf) * 1000,
        )

    from signals.alert_provenance import attach_trim_provenance_to_holdings

    sell_max_trim = float((config.get("score") or {}).get("sell_max", 35))
    trim_cfg = config.get("trim_gates") or {}
    signals_by_ticker = {
        str(r["ticker"]).upper(): r
        for r in results
        if isinstance(r, dict) and r.get("ticker") and not r.get("error")
    }

    portfolios_cfg = config.get("portfolios") or {}
    portfolio_names = ["All"] + (
        [k for k in portfolios_cfg.keys() if isinstance(portfolios_cfg.get(k), list)]
        if isinstance(portfolios_cfg, dict)
        else []
    )
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
            confidence_by_ticker=confidence_by_ticker,
            model_rules=config.get("model_rules"),
        )
        attach_trim_provenance_to_holdings(
            rep.get("per_holding") or [],
            sell_max=sell_max_trim,
            signals_by_ticker=signals_by_ticker,
            trim_cfg=trim_cfg,
        )
        portfolios_out[name] = rep

    if prices and portfolios_out:
        _patch_portfolios_with_prices(portfolios_out, prices, fmp_batch=fmp_batch)

    report = portfolios_out.get("All") or {}

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

    macro_regime_bundle = cached.get("macro_regime_bundle") if isinstance(cached.get("macro_regime_bundle"), dict) else {}
    try:
        from signals.retail_action_payload import enrich_dashboard_signal_row

        _hmm_bear = macro_regime_bundle.get("hmm_bear_pct_used")
        _regime_bull_global = (100.0 - float(_hmm_bear)) if _hmm_bear is not None else None
        for r in results:
            if r.get("error"):
                continue
            enrich_dashboard_signal_row(r, regime_bull_pct=_regime_bull_global)
        try:
            from signals.readiness_score import compute_readiness

            for r in results:
                if r.get("error"):
                    continue
                r.update(compute_readiness(r))
        except Exception as e:
            logger.debug("[dashboard-warm] readiness: %s", e)
    except Exception as e:
        logger.debug("[dashboard-warm] retail enrich: %s", e)

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

    earnings_warn_days = config.get("earnings", {}).get("days_warning", 14)
    earnings_caution_days = min(7, earnings_warn_days)
    earnings_risk_count = 0
    results_by_ticker = {r["ticker"]: r for r in results if not r.get("error")}
    portfolio_ticker_set = {h.get("ticker") if isinstance(h, dict) else h for h in holdings}
    import re as _re

    for t in portfolio_ticker_set:
        r = results_by_ticker.get(t)
        if not r or not r.get("earnings_note"):
            continue
        m = _re.search(r"Earnings in (\d+) days", r.get("earnings_note", "") or "")
        if m and 0 <= int(m.group(1)) <= earnings_caution_days:
            earnings_risk_count += 1

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

    cross_asset = cached.get("cross_asset") or []
    _vix_level = None
    for item in cross_asset or []:
        if isinstance(item, dict) and str(item.get("label") or item.get("ticker") or "").upper() in ("VIX", "^VIX"):
            try:
                _vix_level = float(item.get("close") or item.get("value") or item.get("last"))
            except (TypeError, ValueError):
                pass
            break

    try:
        from signals.portfolio_stress import enrich_signal_uncertainty

        for r in results:
            if not r.get("error"):
                enrich_signal_uncertainty(r)
    except Exception as e:
        logger.debug("[dashboard-warm] signal uncertainty: %s", e)

    try:
        from signals.signal_event_modifiers import enrich_results_event_modifiers

        enrich_results_event_modifiers(results, config, vix=_vix_level)
    except Exception as e:
        logger.debug("[dashboard-warm] event modifiers: %s", e)

    retail_alerts_refresh = None
    try:
        from scanner.horizon_levels import sync_horizon_levels_from_signal_results

        sync_horizon_levels_from_signal_results(get_data_root(), results)
    except Exception as e:
        logger.debug("[dashboard-warm] horizon_levels: %s", e)

    try:
        from scanner.dashboard_alerts import run_retail_alerts_from_dashboard_refresh

        retail_alerts_refresh = run_retail_alerts_from_dashboard_refresh(
            results,
            config,
            get_data_root(),
            prices_by_ticker=prices,
            vix=_vix_level,
        )
    except Exception as e:
        logger.debug("[dashboard-warm] retail alerts: %s", e)

    save_last_run(results)

    opp_bundle_on = _opportunities_bundle_enabled(config)
    if opp_bundle_on:
        portfolio_doctor_recommendations: dict = {}
    else:
        portfolio_doctor_recommendations = _doctor_recommendations_for_portfolios(
            config, portfolios_out, results, [], confidence_by_ticker
        )

    as_of_date = now_iso_et()
    as_of_et = format_et_display()
    ts = _iso_utc_now()

    ohlcv_dates = [str(r["ohlcv_last_date"])[:10] for r in results if isinstance(r, dict) and r.get("ohlcv_last_date")]
    price_last_bar_date = max(ohlcv_dates) if ohlcv_dates else (cached.get("data_freshness") or {}).get("price_last_bar_date")

    df = dict(cached.get("data_freshness") or {})
    df.update({
        "as_of_et": as_of_et,
        "snapshot_updated_at": as_of_date,
        "snapshot_updated_et": as_of_et,
        "signals_updated_at": ts,
        "quotes_updated_at": ts,
        "price_last_bar_date": price_last_bar_date,
    })

    retail_briefing = cached.get("retail_briefing")
    try:
        from retail_briefing import build_retail_briefing

        plan_actions = {
            t: c.get("action")
            for t, c in confidence_by_ticker.items()
            if isinstance(c, dict) and c.get("action")
        }
        retail_briefing = build_retail_briefing(
            results=results,
            report=report,
            data_root=get_data_root(),
            opportunities=cached.get("opportunities") or [],
            tax_aware_exits=cached.get("tax_aware_exits"),
            earnings_risk_count=earnings_risk_count,
            macro_regime=cached.get("macro_regime"),
            risk_pct=risk_pct,
            stop_pct=stop_pct,
            paper_trading=cached.get("paper_trading"),
            thesis_check=thesis_check,
            config=config,
            plan_actions=plan_actions,
        )
    except Exception as e:
        logger.debug("[dashboard-warm] retail_briefing: %s", e)

    merged = dict(cached)
    merged.update({
        "signals": results,
        "signal_scores": _build_signal_scores(results),
        "portfolio": report,
        "portfolios": portfolios_out,
        "portfolio_names": portfolio_names,
        "portfolio_doctor_recommendations": portfolio_doctor_recommendations,
        "story_changes": story_changes,
        "trim_candidates": trim_candidates,
        "thesis_check": thesis_check,
        "what_changed": what_changed_list,
        "earnings_risk_count": earnings_risk_count,
        "retail_briefing": retail_briefing,
        "retail_alerts_refresh": retail_alerts_refresh,
        "market_reversal_overlay": market_reversal_overlay,
        "global_market_regime": next(
            (r.get("_global_market_regime") for r in results if not r.get("error") and r.get("_global_market_regime")),
            cached.get("global_market_regime"),
        ),
        "signal_universe": signal_universe,
        "hunter_panel": _build_hunter_panel_payload(
            results,
            config,
            signal_universe=signal_universe,
            as_of=as_of_date,
        ),
        "tactical_breakouts": _build_tactical_breakouts(results, config),
        "event_risk_strip": _build_event_risk_strip(results, config),
        "as_of_date": as_of_date,
        "refresh_ts": ts,
        "signals_count": len(results),
        "data_freshness": df,
        "warm_kind": "signal_warm",
    })

    set_cached_dashboard(merged)
    _write_panel_caches(config, results, as_of_date)

    try:
        from signals.process_memory import release_process_caches

        release_process_caches(aggressive=True)
    except Exception:
        pass

    logger.info("[dashboard-warm] signal warm DONE (%.0f ms)", (time.perf_counter() - t0_all) * 1000)
    return merged


def compute_for_background_refresh() -> dict:
    """Background job: signal warm when cache exists, else full pipeline."""
    from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot

    if get_cached_dashboard() or get_last_dashboard_snapshot():
        return compute_signal_warm_sync()
    from api.routers.dashboard import _compute_full_dashboard_sync

    return _compute_full_dashboard_sync()
