"""
Daily run: fetch watchlist -> compute signals -> print table; optional persistence for alerts.
Run after market close (e.g. cron / Task Scheduler).
Stores EOD snapshots in data/eod/ for historical tracking.

Time cut-off: For pro-site parity, run after FMP EOD data is stable (e.g. 7–8pm ET).
Compare vs other sites at the same phase (both prior close).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

# Add project root so we can import signals
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EST = ZoneInfo("America/New_York")


def _today_est() -> str:
    """Current date in Eastern (EST/EDT) as YYYY-MM-DD for EOD snapshot filename and 'today' check."""
    return datetime.now(EST).strftime("%Y-%m-%d")

import yaml
from config_loader import load_config
from alerts.notifier import send_alert_digest
from behavior.thesis import load_theses, get_nudge
from behavior.what_changed import what_changed
from opportunity.scanner import run_opportunity_scan
from portfolio.doctor import portfolio_report
from signals.fetcher import fetch_ohlcv_safe, fetch_ohlcv_with_config, fetch_ohlcv_with_volume
from signals.indicators import multi_horizon_scores
from signals.providers import get_next_earnings
from signals.regime import (
    get_regime,
    get_regime_ma,
    get_ml_aware_signal,
    get_signal,
    _ma_regime_to_display,
    get_global_market_regime,
    get_score_label,
    get_vix_min_hit_rate,
)
from signals.target_bands import add_target_bands, compute_vol_6m, compute_swing_high_low


def load_last_run(path: Path | None = None) -> dict[str, dict] | None:
    """Load previous run: ticker -> {composite_buy, regime}."""
    if path is None:
        path = ROOT / "data" / "last_run.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return {r["ticker"]: r for r in data.get("run_results", [])}
    except Exception:
        return None


def run_signals(
    config: dict,
    prices_by_ticker: dict[str, float] | None = None,
    vix: float | None = None,
    hit_rate_context: dict | None = None,
) -> list[dict]:
    """
    Run signals for watchlist. When prices_by_ticker is provided (e.g. from FMP batch quote),
    use yfinance for historical OHLCV and overlay latest close from batch quote to save API calls.
    vix: optional VIX level for score multiplier; if None, fetches ^VIX.
    hit_rate_context: optional {add_hit_rate_pct: float} from forward_tracking for hit-rate gate.
    """
    watchlist = config.get("watchlist", [])
    period = config.get("data", {}).get("period", "5y")
    score_cfg = config.get("score", {})
    regime_cfg = config.get("regime", {})
    alert_delta = config.get("alert_score_delta", 15)

    buy_min = score_cfg.get("buy_min", 70)
    sell_max = score_cfg.get("sell_max", 30)
    up_min = regime_cfg.get("up_min", 60)
    down_max = regime_cfg.get("down_max", 40)

    last_run = load_last_run()

    earnings_cfg = config.get("earnings", {}) or {}
    days_warn = earnings_cfg.get("days_warning", 14)
    score_red = earnings_cfg.get("score_reduction", 20)

    results = []
    # Global market regime (5-level: STRONG_BULL, BULL, NEUTRAL, BEAR, STRONG_BEAR)
    global_market_regime = None
    mr_cfg = config.get("market_regime") or {}
    if mr_cfg.get("enabled", True):
        index_ticker = mr_cfg.get("index_ticker", "SPY")
        min_days = mr_cfg.get("min_days_confirm", 3)
        close_spy = fetch_ohlcv_safe(index_ticker, period)
        if close_spy is not None and len(close_spy) >= 200:
            global_market_regime = get_global_market_regime(close_spy, min_days_confirm=min_days)

    # VIX: for score multiplier and hit-rate gate; fetch if not provided
    mr_cfg_vix = (config.get("market_regime") or {}).get("use_vix_multiplier", True)
    mr_cfg_gate = (config.get("market_regime") or {}).get("use_hit_rate_gate", True)
    if vix is None and (mr_cfg_vix or mr_cfg_gate):
        try:
            vix_close = fetch_ohlcv_safe("^VIX", "1mo")
            if vix_close is not None and len(vix_close) > 0:
                vix = float(vix_close.iloc[-1])
        except Exception:
            pass

    use_fmp = bool(config.get("data", {}).get("fmp_api_key") or config.get("fmp_api_key"))
    use_batch_quote = bool(prices_by_ticker)  # when True, we use yfinance for OHLCV and overlay close
    for ticker in watchlist:
        close = None
        volume = None
        if use_batch_quote:
            # Single FMP batch quote already used; get history from yfinance to stay under API limit
            close, volume = fetch_ohlcv_with_volume(ticker, period)
            if close is None:
                close = fetch_ohlcv_safe(ticker, period)
            if close is not None and prices_by_ticker and ticker in prices_by_ticker:
                # Overlay latest close from FMP batch quote
                batch_price = prices_by_ticker.get(ticker)
                if batch_price is not None:
                    close = close.copy()
                    close.iloc[-1] = batch_price
        elif use_fmp:
            close = fetch_ohlcv_with_config(ticker, period, config)
            if close is None:
                close = fetch_ohlcv_safe(ticker, period)
        else:
            close, volume = fetch_ohlcv_with_volume(ticker, period)
            if close is None:
                close = fetch_ohlcv_safe(ticker, period)
        if close is None:
            results.append({
                "ticker": ticker,
                "error": "Insufficient data or fetch failed",
                "close": None,
                "composite_buy": None,
                "regime": None,
                "signal": None,
                "short_term": None,
                "medium_term": None,
                "long_term": None,
                "short_suggestion": None,
                "medium_suggestion": None,
                "long_suggestion": None,
                "story_change": None,
            })
            continue

        use_spec = config.get("use_spec_regime_score", False)
        sig = multi_horizon_scores(
            close, use_spec=use_spec, ticker=ticker, config=config,
            market_regime=global_market_regime,
            vix=vix if mr_cfg_vix else None,
        )
        composite_buy = sig["composite_buy"]

        # ── ML short-term probability (inference-only — never trains here) ─
        # Uses the cached LightGBM model for this ticker if it exists.
        # inference_only=True means: return None rather than trigger training
        # during dashboard load. Training runs separately on a scheduled basis.
        ml_short_prob: float | None = None
        try:
            import pandas as _pd
            from signals.ml_models import predict_probability as _ml_predict
            _df = _pd.DataFrame({"close": close})
            if volume is not None:
                _df["volume"] = volume
            ml_short_prob = _ml_predict(
                ticker, _df,
                force_retrain=False,
                horizon_key="short",
                inference_only=True,   # skip training; return None if no cached model
            )
        except Exception:
            pass  # graceful — ML column simply shows N/A
        regime = _ma_regime_to_display(sig["ma_regime"]) if sig.get("ma_regime") else get_regime(composite_buy, up_min, down_max)

        # Multi-layer signal: requires BOTH confluence AND ML to agree for BUY.
        # When ML is not yet trained, falls back to confluence-only (preserves
        # existing behaviour until models are available).
        confluence_score = sig.get("confluence_score") or composite_buy
        signal = get_ml_aware_signal(
            confluence_score,
            ml_short_prob=ml_short_prob,
            buy_min=buy_min,
            sell_max=sell_max,
        )

        # Inverted BUY in BEAR/STRONG_BEAR: never emit BUY or STRONG BUY; cap to HOLD/WATCH
        if global_market_regime in ("BEAR", "STRONG_BEAR"):
            if signal in ("BUY", "STRONG BUY"):
                signal = "HOLD"
            short_s = sig.get("short_suggestion")
            med_s = sig.get("medium_suggestion")
            long_s = sig.get("long_suggestion")
            if short_s and short_s in ("HOLD/ADD",):
                sig["short_suggestion"] = "HOLD"
            if med_s and med_s in ("HOLD/ADD",):
                sig["medium_suggestion"] = "HOLD"
            if long_s and long_s in ("HOLD/ADD",):
                sig["long_suggestion"] = "HOLD"

        # Hit rate gate: suppress BUY when historical ADD hit rate < VIX-based threshold
        add_hit_rate = (hit_rate_context or {}).get("add_hit_rate_pct")
        min_hit_rate = get_vix_min_hit_rate(vix) * 100.0 if vix else 55.0
        if mr_cfg_gate and add_hit_rate is not None and vix is not None and vix >= 20:
            if add_hit_rate < min_hit_rate:
                if signal in ("BUY", "STRONG BUY"):
                    signal = "HOLD"
                for k in ("short_suggestion", "medium_suggestion", "long_suggestion"):
                    if sig.get(k) == "HOLD/ADD":
                        sig[k] = "HOLD"

        # Earnings: reduce score or flag when within N days
        earnings_note = None
        earnings_info = get_next_earnings(ticker, config)
        if earnings_info and earnings_info.get("days_until") is not None:
            days_until = earnings_info["days_until"]
            if 0 <= days_until <= days_warn:
                earnings_note = f"Earnings in {days_until} days"
                composite_buy = max(0, composite_buy - score_red)
                regime = get_regime(composite_buy, up_min, down_max)
                # Re-derive signal with earnings-reduced score and ML
                earnings_confluence = max(0.0, (sig.get("confluence_score") or composite_buy) - score_red)
                signal = get_ml_aware_signal(
                    earnings_confluence, ml_short_prob=ml_short_prob,
                    buy_min=buy_min, sell_max=sell_max,
                )

        # Volume vs 20d average (unusual activity)
        volume_ratio = None
        volume_unusual = False
        if volume is not None and len(volume) >= 20:
            today_vol = float(volume.iloc[-1]) if len(volume) else 0
            avg_vol = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else float(volume.iloc[-20:].mean())
            if avg_vol and avg_vol > 0:
                volume_ratio = round(today_vol / avg_vol, 2)
                volume_unusual = volume_ratio >= 2.0

        # Drawdown (52w high) and ATR (14d)
        drawdown_52w = None
        atr_14 = None
        if len(close) >= 252:
            high_52w = float(close.iloc[-252:].max())
            if high_52w and high_52w > 0:
                drawdown_52w = round(100 * (float(close.iloc[-1]) - high_52w) / high_52w, 1)
        if len(close) >= 15:
            # ATR proxy: 14d std of daily returns * current price (avg $ move per day)
            returns = close.pct_change().dropna().iloc[-14:]
            if len(returns) >= 10:
                vol = float(returns.std())
                if vol > 0:
                    atr_14 = round(float(vol * close.iloc[-1]), 2)

        vol_6m = compute_vol_6m(close)
        swing_high_20d, swing_low_20d = compute_swing_high_low(close, 20)

        # FMP analyst data for LT band (cached) – optional
        eps_fwd = None
        cons_low = None
        cons_high = None
        fair_pe_low = 18
        fair_pe_high = 25
        if use_fmp:
            try:
                from signals.fmp_client import fetch_analyst_estimates, fetch_price_target_consensus, get_api_key
                from signals.cache import cached_financial_estimates, cached_price_target_consensus
                if get_api_key(config):
                    est = cached_financial_estimates(ticker, lambda: fetch_analyst_estimates(config, ticker))
                    if est and isinstance(est, dict):
                        eps_fwd = est.get("eps_fwd")
                    cons = cached_price_target_consensus(ticker, lambda: fetch_price_target_consensus(config, ticker))
                    if cons and isinstance(cons, dict):
                        cons_low = cons.get("low") or cons.get("priceWhenPosted") or cons.get("adjLow")
                        cons_high = cons.get("high") or cons.get("adjHigh")
            except Exception:
                pass

        # Story-change detection: regime flip or score drop
        story_change = None
        if last_run and ticker in last_run:
            prev = last_run[ticker]
            prev_regime = prev.get("regime")
            prev_score = prev.get("composite_buy")
            if prev_regime and prev_regime != regime:
                story_change = f"REGIME: {prev_regime} -> {regime}"
            elif prev_score is not None and composite_buy is not None:
                delta = prev_score - composite_buy
                if delta >= alert_delta:
                    story_change = f"SCORE DROP: {prev_score:.0f} -> {composite_buy:.0f} (-{delta:.0f})"

        row = {
            "ticker": ticker,
            "close": sig["close"],
            "price": sig["close"],
            "trend_score": sig["trend_score"],
            "rsi": sig["rsi"],
            "rsi_contrib": sig.get("rsi_contrib"),
            "macd_contrib": sig.get("macd_contrib"),
            "ma20": sig.get("ma20"),
            "ma50": sig.get("ma50"),
            "macd_hist": sig.get("macd_hist"),
            "composite_buy": composite_buy,
            # Confluence score — explicit 4-signal agreement (Trend+RSI+MACD+Regime)
            "confluence_score": sig.get("confluence_score"),
            "trend_signal":     sig.get("trend_signal"),
            "rsi_signal":       sig.get("rsi_signal"),
            "macd_signal":      sig.get("macd_signal"),
            # ML short-term probability — LightGBM inference from cached model (0-1)
            # None when no model trained yet; never triggers training during dashboard load
            "ml_short_prob": ml_short_prob,
            "regime": regime,
            "signal": signal,
            "earnings_note": earnings_note,
            "short_term": sig.get("short_term"),
            "medium_term": sig.get("medium_term"),
            "long_term": sig.get("long_term"),
            "short_suggestion": sig.get("short_suggestion"),
            "medium_suggestion": sig.get("medium_suggestion"),
            "long_suggestion": sig.get("long_suggestion"),
            "short_reason": sig.get("short_reason"),
            "medium_reason": sig.get("medium_reason"),
            "long_reason": sig.get("long_reason"),
            "suggested_buy_price": sig.get("suggested_buy_price"),
            "suggested_sell_price": sig.get("suggested_sell_price"),
            "support_level": sig.get("support_level"),
            "buy_target_confidence_pct": sig.get("buy_target_confidence_pct"),
            "sell_target_confidence_pct": sig.get("sell_target_confidence_pct"),
            "story_change": story_change,
            "volume_ratio": volume_ratio,
            "volume_unusual": volume_unusual,
            "drawdown_52w": drawdown_52w,
            "score_label": get_score_label(composite_buy, global_market_regime),
            "confidence_tag": "low (bear/neutral market)" if global_market_regime and global_market_regime not in ("BULL", "STRONG_BULL") else "normal",
            "_global_market_regime": global_market_regime,
            "atr_14": atr_14,
            "vol_6m": vol_6m,
            "swing_high_20d": swing_high_20d,
            "swing_low_20d": swing_low_20d,
            "eps_fwd": eps_fwd,
            "cons_low": cons_low,
            "cons_high": cons_high,
            "fair_pe_low": fair_pe_low,
            "fair_pe_high": fair_pe_high,
        }
        add_target_bands(row)
        results.append(row)
    return results


def _eod_payload(results: list[dict], include_price_targets: bool = True) -> dict:
    """Build EOD payload. include_price_targets=True adds st_band, mt_band, support_level, suggested_buy for accuracy vs close."""
    run_results = []
    for r in results:
        row = {
            "ticker": r["ticker"],
            "composite_buy": r.get("composite_buy"),
            "regime": r.get("regime"),
            "rsi": r.get("rsi"),
            "trend_score": r.get("trend_score"),
            "ma20": r.get("ma20"),
            "ma50": r.get("ma50"),
            "macd_hist": r.get("macd_hist"),
            "close": r.get("close"),
            "short_suggestion": r.get("short_suggestion"),
            "medium_suggestion": r.get("medium_suggestion"),
            "long_suggestion": r.get("long_suggestion"),
        }
        if include_price_targets:
            if r.get("st_band") is not None:
                row["st_band"] = r["st_band"]
            if r.get("mt_band") is not None:
                row["mt_band"] = r["mt_band"]
            row["support_level"] = r.get("support_level")
            row["suggested_buy_price"] = r.get("suggested_buy_price")
        run_results.append(row)
    return {
        "run_date": datetime.now().isoformat(),
        "run_results": run_results,
    }


def save_last_run(results: list[dict], path: Path | None = None) -> None:
    if path is None:
        path = ROOT / "data" / "last_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _eod_payload(results)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def save_eod_snapshot(
    results: list[dict],
    date_str: str | None = None,
    next_day_outlook: list[dict] | None = None,
    typical_move: list[dict] | None = None,
) -> Path | None:
    """Save daily EOD snapshot to data/eod/YYYY-MM-DD.json for historical tracking.
    Date is in Eastern (EST/EDT) so post-close US runs use the market date.
    Optional next_day_outlook and typical_move (SPY/QQQ) enable model validation vs actual next-day close.
    """
    date_str = date_str or _today_est()
    eod_dir = ROOT / "data" / "eod"
    eod_dir.mkdir(parents=True, exist_ok=True)
    path = eod_dir / f"{date_str}.json"
    payload = _eod_payload(results)
    payload["snapshot_date"] = date_str
    if next_day_outlook is not None:
        payload["next_day_outlook"] = next_day_outlook
    if typical_move is not None:
        payload["typical_move"] = typical_move
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path


def load_eod_snapshot(date_str: str) -> dict[str, dict] | None:
    """Load EOD snapshot for a date. Returns ticker -> {...} or None."""
    path = ROOT / "data" / "eod" / f"{date_str}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return {r["ticker"]: r for r in data.get("run_results", [])}
    except Exception:
        return None


def prune_old_eod_snapshots(retention_days: int) -> int:
    """Delete EOD snapshots older than retention_days. Returns count deleted. Uses EST for cutoff."""
    if retention_days <= 0:
        return 0
    eod_dir = ROOT / "data" / "eod"
    if not eod_dir.exists():
        return 0
    today_est = datetime.now(EST).date()
    cutoff = today_est - timedelta(days=retention_days)
    deleted = 0
    for p in eod_dir.glob("*.json"):
        try:
            # Parse YYYY-MM-DD from filename
            d = datetime.strptime(p.stem, "%Y-%m-%d").date()
            if d < cutoff:
                p.unlink()
                deleted += 1
        except ValueError:
            pass
    return deleted


def run_eod_snapshot_only(config: dict | None = None, snapshot_date: str | None = None) -> dict:
    """
    Run signals and save EOD snapshot only (no console report, no alerts).
    Used by API ad-hoc trigger and by the Python scheduler.
    snapshot_date: optional YYYY-MM-DD (e.g. 2026-02-17); if None, uses today EST.
    Returns dict with snapshot_path (str), snapshot_date (str), tickers_count (int), pruned (int), error (str or None).
    """
    if config is None:
        config = load_config()
    result = {"snapshot_path": None, "snapshot_date": None, "tickers_count": 0, "pruned": 0, "error": None}
    try:
        results = run_signals(config)
        result["tickers_count"] = len([r for r in results if not r.get("error")])
        next_day_outlook_eod = None
        typical_move_eod = None
        try:
            from signals.next_day_bias import next_day_outlook_for_symbols, run_next_day_backtest
            from signals.typical_move import typical_move_for_symbols
            backtest_cache = {}
            for sym in ["SPY", "QQQ"]:
                try:
                    backtest_cache[sym] = run_next_day_backtest(sym, period="5y")
                except Exception:
                    pass
            next_day_outlook_eod = next_day_outlook_for_symbols(["SPY", "QQQ"], backtest_cache)
            typical_move_eod = typical_move_for_symbols(["SPY", "QQQ"])
        except Exception:
            pass
        date_str = snapshot_date or _today_est()
        snapshot_path = save_eod_snapshot(
            results,
            date_str=date_str,
            next_day_outlook=next_day_outlook_eod,
            typical_move=typical_move_eod,
        )
        save_last_run(results)
        if snapshot_path:
            result["snapshot_path"] = str(snapshot_path)
            result["snapshot_date"] = snapshot_path.stem
        retention = config.get("eod_retention_days", 0)
        if retention > 0:
            result["pruned"] = prune_old_eod_snapshots(retention)
    except Exception as e:
        result["error"] = str(e)
    return result


def main() -> None:
    config = load_config()
    results = run_signals(config)

    # Story-change alerts first (trim before it goes too low)
    story_changes = [r for r in results if r.get("story_change")]
    if story_changes:
        print("=" * 60)
        print("STORY CHANGE ALERTS (review these first):")
        print("=" * 60)
        for r in story_changes:
            print(f"  {r['ticker']:6}  {r['story_change']}")
        print()

    # Main signals table
    print("Daily signals (medium-term = main):")
    print("-" * 80)
    for r in results:
        if r.get("error"):
            print(f"  {r['ticker']}: ERROR - {r['error']}")
        else:
            flag = " <-- STORY CHANGE" if r.get("story_change") else ""
            earn = f" [{r['earnings_note']}]" if r.get("earnings_note") else ""
            print(f"  {r['ticker']:6}  close={r['close']:.2f}  med={r['composite_buy']:.1f}  regime={r['regime']:8}  {r['signal']}{earn}{flag}")

    # Multi-horizon suggestions
    print()
    print("Multi-horizon suggestions (short=weeks, med=months, long=1-2yr):")
    print("-" * 80)
    for r in results:
        if r.get("error"):
            continue
        short = r.get("short_suggestion") or "-"
        med = r.get("medium_suggestion") or "-"
        long_s = r.get("long_suggestion") or "-"
        print(f"  {r['ticker']:6}  Short: {short:14}  Medium: {med:14}  Long: {long_s}")

    # Phase 3: Portfolio doctor (full report)
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

    report = portfolio_report(
        holdings=holdings,
        results=results,
        watchlist=config.get("watchlist", []),
        score_cfg=config.get("score", {}),
        concentration_threshold_pct=config.get("concentration_alert_pct", 20),
        cash_deploy_min_score=config.get("cash_deploy_min_score", 70),
    )

    print()
    print("=" * 60)
    print("PORTFOLIO HEALTH")
    print("=" * 60)
    print(f"Total value: ${report['total_value']:,.2f}")
    print(f"Average score: {report['avg_score']:.1f}")
    print(f"Regime mix: UP={report['regime_counts']['UP']}  NEUTRAL={report['regime_counts']['NEUTRAL']}  DOWN={report['regime_counts']['DOWN']}")
    if report["largest_position"]:
        lp = report["largest_position"]
        print(f"Largest position: {lp['ticker']} ({lp['pct']:.1f}%, ${lp['value']:,.2f})")
    if report["concentration_alert"]:
        print(f"Concentration alert: {', '.join(report['concentration_alert'])} exceed 20%")

    print()
    print("Per-holding:")
    print("-" * 70)
    for h in sorted(report["per_holding"], key=lambda x: -(x["value"] or 0)):
        val_str = f"${h['value']:,.2f}" if h["value"] else "N/A"
        pct_str = f"{h['pct']:.1f}%" if h["pct"] is not None else "-"
        score_str = f"{h['score']:.1f}" if h["score"] is not None else "-"
        print(f"  {h['ticker']:6}  {val_str:>12}  {pct_str:>6}  score={score_str:>5}  {h['regime'] or '-':8}  {h['suggestion']}")

    # Consider trim
    trim_candidates = [h for h in report["per_holding"] if h["score"] is not None and h["score"] < 40]
    if trim_candidates:
        print()
        print("Consider trim (score < 40, protect gains):")
        for h in sorted(trim_candidates, key=lambda x: x["score"]):
            print(f"  {h['ticker']:6}  score={h['score']:.1f}  regime={h['regime']}  {h['suggestion']}")

    # Cash deployment
    if report["cash_deployment"]:
        print()
        print("Deploy cash (watchlist, not in portfolio, score >= 70):")
        for c in report["cash_deployment"]:
            print(f"  {c['ticker']:6}  score={c['score']:.1f}  regime={c['regime']}")

    # Opportunity scan: long-term growth potential (daily discovery)
    if config.get("run_opportunity_scan", True):
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
        print()
        print("=" * 60)
        print("DAILY OPPORTUNITIES (long-term growth potential)")
        print("=" * 60)
        print("Candidates to research - not buy recommendations. Use your judgment.")
        print("-" * 70)
        if opportunities:
            for o in opportunities:
                print(f"  {o['ticker']:6}  close={o['close']:.2f}  score={o['composite_buy']:.1f}  RSI={o['rsi']:.1f}  {o['regime']:8}  {o['reason']}")
        else:
            print("  No tickers passed criteria today. Try relaxing min_score or max_rsi in config.")

    # Phase 5: Thesis check, nudges, what changed
    theses = load_theses() if config.get("run_thesis_check", True) else {}
    last_run = load_last_run()
    if config.get("run_thesis_check", True) and theses:
        print()
        print("=" * 60)
        print("THESIS CHECK")
        print("=" * 60)
        for r in results:
            if r.get("error"):
                continue
            t = theses.get(r["ticker"])
            if not t:
                continue
            nudge = get_nudge(r["ticker"], r.get("regime", ""), r.get("composite_buy"), theses)
            print(f"  {r['ticker']:6}  Why: {t.get('thesis', '-')[:60]}...")
            print(f"         Exit if: {t.get('exit_condition', '-')}")
            if nudge:
                print(f"         -> {nudge}")
            print()

    if config.get("run_what_changed", True) and last_run:
        changed = []
        for r in results:
            if r.get("error"):
                continue
            prev = last_run.get(r["ticker"])
            if not prev:
                continue
            diffs, _ = what_changed(prev, r)
            if diffs:
                changed.append((r["ticker"], diffs))
        if changed:
            print("=" * 60)
            print("WHAT CHANGED (vs last run)")
            print("=" * 60)
            for ticker, diffs in changed[:10]:  # Limit to 10 tickers
                print(f"  {ticker}: {'; '.join(diffs)}")
            print()

    if config.get("show_tooltips", False):
        import yaml as _yaml
        tt_path = ROOT / "config" / "tooltips.yaml"
        if tt_path.exists():
            with open(tt_path, "r") as f:
                tt = _yaml.safe_load(f) or {}
            print("=" * 60)
            print("INDICATOR EXPLANATIONS")
            print("=" * 60)
            for k, v in (tt or {}).items():
                if isinstance(v, str):
                    print(f"  {k}: {v}")
            print()

    # Phase 2: Send alerts (email/Telegram) when story changes
    if story_changes and config.get("alerts"):
        try:
            full_report_lines = [
                f"Portfolio avg: {report['avg_score']:.1f}",
                f"Consider trim: {[h['ticker'] for h in trim_candidates]}",
            ]
            full_report = "\n".join(full_report_lines)
            sent = send_alert_digest(story_changes, config, full_report)
            if sent:
                print("\nAlerts sent (email/Telegram).")
        except Exception as e:
            print(f"\nAlert send failed: {e}")

    # Persist for next-run alerts
    save_last_run(results)
    print("\nSaved to data/last_run.json (story-change alerts on next run).")

    # EOD snapshot for historical tracking (include next_day_outlook + typical_move for SPY/QQQ validation)
    retention = config.get("eod_retention_days", 0)
    next_day_outlook_eod = None
    typical_move_eod = None
    try:
        from signals.next_day_bias import next_day_outlook_for_symbols, run_next_day_backtest
        from signals.typical_move import typical_move_for_symbols
        backtest_cache = {}
        for sym in ["SPY", "QQQ"]:
            try:
                backtest_cache[sym] = run_next_day_backtest(sym, period="5y")
            except Exception:
                pass
        next_day_outlook_eod = next_day_outlook_for_symbols(["SPY", "QQQ"], backtest_cache)
        typical_move_eod = typical_move_for_symbols(["SPY", "QQQ"])
    except Exception as e:
        print(f"EOD validation data (next_day/typical_move) skipped: {e}")
    snapshot_path = save_eod_snapshot(
        results,
        next_day_outlook=next_day_outlook_eod,
        typical_move=typical_move_eod,
    )
    if snapshot_path:
        print(f"Saved EOD snapshot to data/eod/{snapshot_path.name}")
    if retention > 0:
        pruned = prune_old_eod_snapshots(retention)
        if pruned:
            print(f"Pruned {pruned} old EOD snapshot(s) (keeping last {retention} days).")

    # Price-target accuracy report (same results) for dashboard GET /api/accuracy
    try:
        from scripts.accuracy_price_targets import run_accuracy_and_save
        acc_path = run_accuracy_and_save(results, config)
        if acc_path:
            print(f"Saved accuracy report to data/{acc_path.name}")
    except Exception as e:
        print(f"Accuracy report save skipped: {e}")


if __name__ == "__main__":
    main()
