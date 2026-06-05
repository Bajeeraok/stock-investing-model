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
from config_loader import get_data_root, get_signal_universe, load_config
from alerts.notifier import send_retail_digest
from behavior.thesis import load_theses, get_nudge
from behavior.what_changed import what_changed
from opportunity.scanner import run_opportunity_scan
from portfolio.doctor import portfolio_report
from signals.fetcher import (
    fetch_ohlcv_safe,
    fetch_ohlcv_with_volume,
    fetch_ohlcv_close_and_volume,
)
from signals.indicators import multi_horizon_scores
from signals.score_interpretation import detect_interpretation_style, effective_buy_min
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
    resolve_ml_prob_thresholds,
)
from signals.target_bands import add_target_bands, compute_vol_6m, compute_swing_high_low
from signals.market_reversal_overlay import apply_overlay_to_composite, build_market_reversal_overlay


def load_last_run(path: Path | None = None) -> dict[str, dict] | None:
    """Load previous run: ticker -> {composite_buy, regime}."""
    if path is None:
        path = get_data_root() / "last_run.json"
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
    tickers: list[str] | None = None,
) -> list[dict]:
    """
    Run signals for watchlist. When fmp_api_key is set, historical OHLCV uses FMP adjClose
    (and volume from the same response) for every ticker — including when the caller also
    passes prices_by_ticker from FMP batch quote (batch is for portfolio marks only; no last-bar
    splice into OHLCV). Without a key, uses yfinance. Falls back to yfinance if FMP fails.
    vix: optional VIX level for score multiplier; if None, fetches ^VIX.
    hit_rate_context: optional {add_hit_rate_pct: float} from forward_tracking for hit-rate gate.
    tickers: optional override list; default is get_eod_signal_universe(config).
    """
    from config_loader import get_eod_signal_universe

    watchlist = [str(t).upper() for t in tickers] if tickers else get_eod_signal_universe(config)
    period = config.get("data", {}).get("period", "5y")
    score_cfg = config.get("score", {})
    regime_cfg = config.get("regime", {})
    alert_delta = config.get("alert_score_delta", 15)

    sell_max = score_cfg.get("sell_max", 30)
    ml_strong_buy_confluence = float(score_cfg.get("ml_strong_buy_confluence", 72))
    ml_strong_buy_prob, ml_buy_prob, ml_avoid_max_prob = resolve_ml_prob_thresholds(score_cfg)
    up_min = regime_cfg.get("up_min", 60)
    down_max = regime_cfg.get("down_max", 40)

    last_run = load_last_run()

    earnings_cfg = config.get("earnings", {}) or {}
    days_warn = earnings_cfg.get("days_warning", 14)
    score_red = earnings_cfg.get("score_reduction", 20)
    caution_days = int(earnings_cfg.get("caution_days", 7))
    caution_extra = float(earnings_cfg.get("caution_extra_reduction", 5))

    results = []
    # Global market regime (5-level: STRONG_BULL, BULL, NEUTRAL, BEAR, STRONG_BEAR)
    global_market_regime = None
    close_spy = None
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

    # Market-wide stress / bounce overlay (SPY + VIX; optional ML)
    mro_cfg = config.get("market_reversal_overlay") or {}
    mro_ctx = None
    if mro_cfg.get("enabled", True):
        try:
            spy_for_mro = close_spy if close_spy is not None else fetch_ohlcv_safe(mr_cfg.get("index_ticker", "SPY"), period)
            vix_for_mro = fetch_ohlcv_safe("^VIX", "2y")
            ry_mro = None
            try:
                from signals.fred_client import get_real_yield_proxy

                ry_mro = get_real_yield_proxy(config)
            except Exception:
                pass
            mr_data_mro = {}
            try:
                from signals.breadth_rs import get_market_regime as _get_mr_overlay

                mr_data_mro = _get_mr_overlay(period="6mo", vix=vix, real_yield=ry_mro)
            except Exception:
                pass
            mro_ctx = build_market_reversal_overlay(
                config,
                vix=vix,
                real_yield=ry_mro,
                market_regime_data=mr_data_mro,
                close_spy=spy_for_mro,
                vix_series=vix_for_mro,
            )
        except Exception:
            mro_ctx = {"enabled": True, "error": "build_failed"}

    use_fmp = bool(config.get("data", {}).get("fmp_api_key") or config.get("fmp_api_key"))

    band_event_mult = 1.0
    band_event_note = None
    if use_fmp:
        try:
            from signals.band_context import macro_event_band_context
            from signals.cache import cached_economic_calendar
            from signals.fmp_client import fetch_economic_calendar

            def _cal_fetch():
                ev, _ = fetch_economic_calendar(config, 14)
                return ev or []

            cal = cached_economic_calendar(14, _cal_fetch)
            ctx = macro_event_band_context(cal)
            band_event_mult = float(ctx.get("multiplier") or 1.0)
            band_event_note = ctx.get("note")
        except Exception:
            pass

    for ticker in watchlist:
        close = None
        volume = None
        if use_fmp:
            close, volume = fetch_ohlcv_close_and_volume(ticker, period, config)
            if close is None:
                close, volume = fetch_ohlcv_with_volume(ticker, period)
            if close is None:
                close = fetch_ohlcv_safe(ticker, period)
                volume = None
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
                "story_change_source": None,
                "story_change_trigger": None,
                "story_change_horizon": None,
                "story_change_horizon_flips": None,
            })
            continue

        buy_min = effective_buy_min(ticker, score_cfg)

        use_spec = config.get("use_spec_regime_score", False)
        score_interpretation_style, score_interpretation_meta = detect_interpretation_style(
            close, volume, config, ticker=ticker,
        )
        sig = multi_horizon_scores(
            close, use_spec=use_spec, ticker=ticker, config=config,
            market_regime=global_market_regime,
            vix=vix if mr_cfg_vix else None,
            interpretation_style=score_interpretation_style,
        )
        composite_buy = sig["composite_buy"]
        confluence_adj = sig.get("confluence_score") or composite_buy
        if mro_ctx and mro_ctx.get("enabled") and mro_cfg.get("apply_score_adjustment", True):
            composite_buy, confluence_adj = apply_overlay_to_composite(
                composite_buy,
                sig.get("confluence_score"),
                mro_ctx,
                apply_adjustment=True,
            )

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
        signal = get_ml_aware_signal(
            confluence_adj,
            ml_short_prob=ml_short_prob,
            buy_min=buy_min,
            sell_max=sell_max,
            ml_strong_buy_confluence=ml_strong_buy_confluence,
            ml_strong_buy_prob=ml_strong_buy_prob,
            ml_buy_prob=ml_buy_prob,
            ml_avoid_max_prob=ml_avoid_max_prob,
            interpretation_style=score_interpretation_style,
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
        earnings_days_until = None
        earnings_caution = False
        earnings_info = get_next_earnings(ticker, config)
        if earnings_info and earnings_info.get("days_until") is not None:
            days_until = earnings_info["days_until"]
            earnings_days_until = int(days_until)
            if 0 <= days_until <= days_warn:
                total_earn_red = score_red
                if 0 <= days_until <= caution_days:
                    earnings_caution = True
                    total_earn_red = score_red + caution_extra
                    earnings_note = f"Earnings in {days_until} days — caution window (volatile)"
                else:
                    earnings_note = f"Earnings in {days_until} days"
                composite_buy = max(0, composite_buy - total_earn_red)
                regime = get_regime(composite_buy, up_min, down_max)
                # Re-derive signal with earnings-reduced score and ML
                earnings_confluence = max(0.0, confluence_adj - total_earn_red)
                signal = get_ml_aware_signal(
                    earnings_confluence, ml_short_prob=ml_short_prob,
                    buy_min=buy_min, sell_max=sell_max,
                    ml_strong_buy_confluence=ml_strong_buy_confluence,
                    ml_strong_buy_prob=ml_strong_buy_prob,
                    ml_buy_prob=ml_buy_prob,
                    ml_avoid_max_prob=ml_avoid_max_prob,
                    interpretation_style=score_interpretation_style,
                )
                confluence_adj = earnings_confluence

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
        # Proper daily ATR(14) using True Range (requires high/low/close).
        # Falls back to prior proxy only if OHLC is unavailable.
        bar_high = None
        bar_low = None
        try:
            from signals.fetcher import fetch_ohlcv_dataframe
            from signals.volatility import atr14_from_ohlcv_df
            ohlcv_df = fetch_ohlcv_dataframe(ticker, period)
            atr_14 = atr14_from_ohlcv_df(ohlcv_df)
            if ohlcv_df is not None and len(ohlcv_df) > 0:
                last = ohlcv_df.iloc[-1]
                if "High" in ohlcv_df.columns:
                    bar_high = round(float(last["High"]), 2)
                elif "high" in ohlcv_df.columns:
                    bar_high = round(float(last["high"]), 2)
                if "Low" in ohlcv_df.columns:
                    bar_low = round(float(last["Low"]), 2)
                elif "low" in ohlcv_df.columns:
                    bar_low = round(float(last["low"]), 2)
        except Exception:
            atr_14 = None
        if atr_14 is None and len(close) >= 15:
            # Fallback proxy (older behaviour): 14d std of daily returns * current price
            returns = close.pct_change().dropna().iloc[-14:]
            if len(returns) >= 10:
                vol = float(returns.std())
                if vol > 0:
                    atr_14 = round(float(vol * close.iloc[-1]), 2)

        vol_6m = compute_vol_6m(close)
        swing_high_20d, swing_low_20d = compute_swing_high_low(close, 20)

        # FMP analyst data for LT band (cached) – optional
        eps_fwd = None
        eps_dispersion = None
        consensus_median = None
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
                        eps_dispersion = est.get("eps_dispersion")
                    cons = cached_price_target_consensus(ticker, lambda: fetch_price_target_consensus(config, ticker))
                    if cons and isinstance(cons, dict):
                        cons_low = cons.get("low") or cons.get("priceWhenPosted") or cons.get("adjLow")
                        cons_high = cons.get("high") or cons.get("adjHigh")
                        consensus_median = (
                            cons.get("median")
                            or cons.get("consensus")
                            or cons.get("targetConsensus")
                            or cons.get("medianPriceTarget")
                        )
            except Exception:
                pass

        # Story-change detection (composite + optional ST/MT/LT suggestion flips)
        story_patch: dict = {}
        if last_run and ticker in last_run:
            from signals.alert_provenance import detect_story_change

            prev_row = last_run[ticker]
            _sp = detect_story_change(
                prev_row,
                regime=regime,
                composite_buy=composite_buy,
                current_row={
                    "short_suggestion": sig.get("short_suggestion"),
                    "medium_suggestion": sig.get("medium_suggestion"),
                    "long_suggestion": sig.get("long_suggestion"),
                },
                alert_delta=alert_delta,
            )
            if _sp:
                story_patch = _sp
        story_change = story_patch.get("story_change")

        daily_move_pct = None
        sparkline_closes = None
        if close is not None and len(close) >= 2:
            try:
                c0, c1 = float(close.iloc[-2]), float(close.iloc[-1])
                if c0 > 0:
                    daily_move_pct = round(100.0 * (c1 - c0) / c0, 4)
            except Exception:
                pass
            try:
                tail = close.dropna().tail(30)
                if len(tail) >= 2:
                    sparkline_closes = [round(float(v), 4) for v in tail.tolist()]
            except Exception:
                pass

        ohlcv_last_date = None
        if close is not None and len(close) > 0:
            try:
                ix = close.dropna().index
                if len(ix) > 0:
                    lix = ix[-1]
                    ohlcv_last_date = (
                        lix.strftime("%Y-%m-%d") if hasattr(lix, "strftime") else str(lix)[:10]
                    )
            except Exception:
                pass

        row = {
            "ticker": ticker,
            "close": sig["close"],
            "price": sig["close"],
            "high": bar_high,
            "low": bar_low,
            "daily_move_pct": daily_move_pct,
            "sparkline_closes": sparkline_closes,
            "trend_score": sig["trend_score"],
            "rsi": sig["rsi"],
            "rsi_contrib": sig.get("rsi_contrib"),
            "macd_contrib": sig.get("macd_contrib"),
            "ma20": sig.get("ma20"),
            "ma50": sig.get("ma50"),
            "macd_hist": sig.get("macd_hist"),
            "composite_buy": composite_buy,
            "buy_min": buy_min,
            "score_interpretation_style": score_interpretation_style,
            "score_interpretation_meta": score_interpretation_meta,
            # Confluence score — overlay + earnings adjusted (matches signal tiers)
            "confluence_score": confluence_adj,
            "trend_signal":     sig.get("trend_signal"),
            "rsi_signal":       sig.get("rsi_signal"),
            "macd_signal":      sig.get("macd_signal"),
            "market_overlay": mro_ctx,
            # ML short-term probability — LightGBM inference from cached model (0-1)
            # None when no model trained yet; never triggers training during dashboard load
            "ml_short_prob": ml_short_prob,
            "regime": regime,
            "signal": signal,
            "earnings_note": earnings_note,
            "earnings_days_until": earnings_days_until,
            "earnings_caution": earnings_caution,
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
            "story_change_source": story_patch.get("story_change_source"),
            "story_change_trigger": story_patch.get("story_change_trigger"),
            "story_change_horizon": story_patch.get("story_change_horizon"),
            "story_change_horizon_flips": story_patch.get("story_change_horizon_flips"),
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
            "eps_dispersion": eps_dispersion,
            "consensus_median": consensus_median,
            "cons_low": cons_low,
            "cons_high": cons_high,
            "fair_pe_low": fair_pe_low,
            "fair_pe_high": fair_pe_high,
            "band_event_multiplier": band_event_mult,
            "band_event_note": band_event_note,
            "ohlcv_last_date": ohlcv_last_date,
        }
        add_target_bands(row)
        try:
            from signals.velocity_engine import attach_velocity_to_row

            attach_velocity_to_row(row, close=close, volume=volume, config=config)
        except Exception:
            pass
        try:
            from signals.retail_action_payload import enrich_dashboard_signal_row

            enrich_dashboard_signal_row(row)
        except Exception:
            pass
        try:
            from signals.readiness_score import compute_readiness

            row.update(compute_readiness(row))
        except Exception:
            pass
        if row.get("model_confidence_pct") is None and row.get("composite_buy") is not None:
            try:
                row["model_confidence_pct"] = round(float(row["composite_buy"]), 1)
            except (TypeError, ValueError):
                pass
        results.append(row)
    return results


def _eod_payload(results: list[dict], include_price_targets: bool = True) -> dict:
    """Build EOD payload. include_price_targets=True adds st_band, mt_band, support_level, suggested_buy for accuracy vs close."""
    run_results = []
    for r in results:
        row = {
            "ticker": r["ticker"],
            "composite_buy": r.get("composite_buy"),
            "signal": r.get("signal"),
            "buy_min": r.get("buy_min"),
            "score_interpretation_style": r.get("score_interpretation_style"),
            "regime": r.get("regime"),
            "rsi": r.get("rsi"),
            "trend_score": r.get("trend_score"),
            "ma20": r.get("ma20"),
            "ma50": r.get("ma50"),
            "macd_hist": r.get("macd_hist"),
            "close": r.get("close"),
            "high": r.get("high"),
            "low": r.get("low"),
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
        if r.get("lt_band") is not None:
            row["lt_band"] = r.get("lt_band")
        if r.get("gate_cleared") is not None:
            row["gate_cleared"] = r.get("gate_cleared")
        rs = r.get("retail_status") if isinstance(r.get("retail_status"), dict) else {}
        if rs.get("go_no_go"):
            row["go_no_go"] = rs.get("go_no_go")
        try:
            from signals.forward_tracking_metrics import freeze_gate_fields_from_row, freeze_trim_gate_fields_from_row

            frozen = freeze_gate_fields_from_row(r)
            for k, v in frozen.items():
                if v is not None:
                    row[k] = v
            try:
                trim_frozen = freeze_trim_gate_fields_from_row(r)
                for k, v in trim_frozen.items():
                    if v is not None:
                        row[k] = v
            except Exception:
                pass
        except Exception:
            try:
                from signals.tracking_gate import gate_snapshot_from_row

                snap = gate_snapshot_from_row(r)
                if snap.get("gates_passed") is not None:
                    row["gates_passed"] = snap["gates_passed"]
                if snap.get("gates_total") is not None:
                    row["gates_total"] = snap["gates_total"]
                if row.get("go_no_go") is None and snap.get("go_no_go"):
                    row["go_no_go"] = snap["go_no_go"]
            except Exception:
                pass
        for k in (
            "velocity_triggered",
            "velocity_score",
            "track",
            "rvol",
            "bb_pct_b",
            "velocity_reasons",
            "readiness_tier",
            "readiness_score",
            "almost_ready",
            "tactical_entry",
            "tactical_t1",
            "tactical_t2",
            "tactical_stop",
            "tactical_horizon_trading_days",
            "tactical_rr",
            "tactical_expiry_note",
        ):
            if r.get(k) is not None:
                row[k] = r.get(k)
        run_results.append(row)
    return {
        "run_date": datetime.now().isoformat(),
        "run_results": run_results,
    }


def save_last_run(results: list[dict], path: Path | None = None) -> None:
    if path is None:
        path = get_data_root() / "last_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _eod_payload(results)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def maybe_save_eod_from_last_run(snapshot_date: str | None = None) -> dict:
    """
    Idempotent: archive today's last_run.json into data/eod/ + Redis when missing.
    Keeps forward tracking and paper-trade outcome chains advancing after dashboard Refresh.
    """
    date_str = snapshot_date or _today_est()
    eod_path = get_data_root() / "eod" / f"{date_str}.json"
    try:
        from signals.cache import get_eod_snapshot_redis

        if eod_path.exists() or get_eod_snapshot_redis(date_str):
            return {"ok": True, "skipped": True, "snapshot_date": date_str}
    except Exception:
        if eod_path.exists():
            return {"ok": True, "skipped": True, "snapshot_date": date_str}
    last_run_path = get_data_root() / "last_run.json"
    if not last_run_path.exists():
        return {"ok": False, "skipped": True, "snapshot_date": date_str, "reason": "no_last_run"}
    with open(last_run_path, encoding="utf-8") as f:
        payload = json.load(f)
    run_results = payload.get("run_results") or []
    if not run_results:
        return {"ok": False, "skipped": True, "snapshot_date": date_str, "reason": "empty_run_results"}
    path = save_eod_snapshot(run_results, date_str=date_str)
    return {
        "ok": True,
        "skipped": False,
        "snapshot_date": date_str,
        "snapshot_path": str(path) if path else None,
        "tickers_count": len(run_results),
    }


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
    eod_dir = get_data_root() / "eod"
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
    try:
        from signals.cache import set_eod_snapshot_redis
        set_eod_snapshot_redis(date_str, payload)
    except Exception:
        pass
    return path


def load_eod_snapshot(date_str: str) -> dict[str, dict] | None:
    """Load EOD snapshot for a date. Returns ticker -> {...} or None. Tries Redis first, then file."""
    try:
        from signals.cache import get_eod_snapshot_redis
        data = get_eod_snapshot_redis(date_str)
        if data and isinstance(data, dict):
            run_results = data.get("run_results", [])
            return {r["ticker"]: r for r in run_results}
    except Exception:
        pass
    path = get_data_root() / "eod" / f"{date_str}.json"
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
    eod_dir = get_data_root() / "eod"
    if not eod_dir.exists():
        return 0
    today_est = datetime.now(EST).date()
    cutoff = today_est - timedelta(days=retention_days)
    deleted = 0
    try:
        from signals.cache import delete_eod_snapshot_redis, list_eod_dates_redis
    except Exception:
        delete_eod_snapshot_redis = None
        list_eod_dates_redis = lambda: []
    for p in eod_dir.glob("*.json"):
        try:
            d = datetime.strptime(p.stem, "%Y-%m-%d").date()
            if d < cutoff:
                p.unlink()
                if delete_eod_snapshot_redis:
                    delete_eod_snapshot_redis(p.stem)
                deleted += 1
        except ValueError:
            pass
    for date_str in list_eod_dates_redis():
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if d < cutoff and delete_eod_snapshot_redis:
                delete_eod_snapshot_redis(date_str)
                deleted += 1
        except ValueError:
            pass
    return deleted


def run_eod_snapshot_only(
    config: dict | None = None,
    snapshot_date: str | None = None,
    tickers: list[str] | None = None,
) -> dict:
    """
    Run signals and save EOD snapshot only (no console report, no alerts).
    Used by API ad-hoc trigger and by the Python scheduler.
    snapshot_date: optional YYYY-MM-DD (e.g. 2026-02-17); if None, uses today EST.
    tickers: optional override; default is get_eod_signal_universe(config).
    Returns dict with snapshot_path (str), snapshot_date (str), tickers_count (int), pruned (int), error (str or None).
    """
    if config is None:
        config = load_config()
    result = {
        "snapshot_path": None,
        "snapshot_date": None,
        "tickers_count": 0,
        "pruned": 0,
        "error": None,
        "universe": None,
        "universe_count": 0,
    }
    try:
        results = run_signals(config, tickers=tickers)
        if tickers is not None:
            result["universe"] = "custom"
            result["universe_count"] = len(tickers)
        else:
            from config_loader import get_eod_signal_universe

            uni = get_eod_signal_universe(config)
            result["universe"] = "eod"
            result["universe_count"] = len(uni)
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
        try:
            from scanner.horizon_levels import sync_horizon_levels_from_signal_results

            sync_horizon_levels_from_signal_results(get_data_root(), results)
        except Exception:
            pass
        save_last_run(results)
        if snapshot_path:
            result["snapshot_path"] = str(snapshot_path)
            result["snapshot_date"] = snapshot_path.stem
        retention = config.get("eod_retention_days", 0)
        if retention > 0:
            result["pruned"] = prune_old_eod_snapshots(retention)
        try:
            from signals.signal_audit_store import persist_daily_signal_logs

            log_result = persist_daily_signal_logs(
                results,
                config,
                date_str=date_str,
                run_source="run_daily",
                data_root=get_data_root(),
            )
            result["signal_audit"] = log_result.get("signal_audit")
            result["paper_trades"] = log_result.get("paper_trades")
            try:
                from signals.signal_audit_outcomes import resolve_signal_audit_outcomes

                result["signal_audit_outcomes"] = resolve_signal_audit_outcomes(
                    config, data_root=get_data_root()
                )
            except Exception as e:
                result["signal_audit_outcomes"] = {"error": str(e)}
            try:
                from signals.signal_audit_report import build_audit_report

                audit_cfg = config.get("signal_audit") or {}
                if (audit_cfg.get("report") or {}).get("enabled", True):
                    result["signal_audit_report"] = build_audit_report(
                        config, data_root=get_data_root(), write_files=True
                    )
            except Exception as e:
                result["signal_audit_report"] = {"error": str(e)}
        except Exception as e:
            result["signal_audit"] = {"error": str(e)}
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
        model_rules=config.get("model_rules"),
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
            prev_r = last_run.get(r["ticker"]) if last_run else None
            nudge = get_nudge(
                r["ticker"],
                r.get("regime", ""),
                r.get("composite_buy"),
                theses,
                prev_regime=(prev_r or {}).get("regime") if prev_r else None,
                prev_score=(prev_r or {}).get("composite_buy") if prev_r else None,
            )
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

    # Phase 2: Digest alerts (email/Telegram): story changes, trim list, earnings week
    if config.get("alerts"):
        try:
            import re as _re_earn
            earnings_warn_days = config.get("earnings", {}).get("days_warning", 14)
            earnings_caution_days = min(7, earnings_warn_days)
            results_map = {r["ticker"]: r for r in results if not r.get("error")}
            earnings_tickers_list: list[str] = []
            for h in holdings:
                t = h.get("ticker") if isinstance(h, dict) else h
                row = results_map.get(t)
                if not row or not row.get("earnings_note"):
                    continue
                m = _re_earn.search(r"Earnings in (\d+) days", row.get("earnings_note", "") or "")
                if m and 0 <= int(m.group(1)) <= earnings_caution_days:
                    earnings_tickers_list.append(t)
            trim_ts = [h["ticker"] for h in trim_candidates if h.get("ticker")]
            full_report_lines = [
                f"Portfolio avg: {report['avg_score']:.1f}",
                f"Consider trim: {trim_ts}",
            ]
            full_report = "\n".join(full_report_lines)
            sent = send_retail_digest(
                config,
                story_changes=story_changes,
                trim_tickers=trim_ts,
                earnings_risk_count=len(earnings_tickers_list),
                earnings_tickers=earnings_tickers_list,
                full_report=full_report,
            )
            if sent:
                print("\nDigest sent (email/Telegram).")
        except Exception as e:
            print(f"\nAlert send failed: {e}")

    # Persist for next-run alerts + scanner price-level alerts (entry/stop/target)
    try:
        from scanner.horizon_levels import sync_horizon_levels_from_signal_results

        n_sync = sync_horizon_levels_from_signal_results(get_data_root(), results)
        print(f"\nScanner horizon_levels synced ({n_sync} tickers with bands/ML) for entry/stop/target alerts.")
    except Exception as e:
        print(f"\nHorizon levels sync skipped: {e}")
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

    try:
        from signals.signal_audit_store import persist_daily_signal_logs

        log_result = persist_daily_signal_logs(
            results,
            config,
            run_source="run_daily",
            data_root=get_data_root(),
        )
        sa = log_result.get("signal_audit") or {}
        if sa.get("enabled"):
            print(
                f"Signal audit: {sa.get('appended', 0)} new rows, "
                f"{sa.get('skipped_duplicate', 0)} duplicates, "
                f"{sa.get('missing_from_run', 0)} cohort tickers missing from run "
                f"(cohort {sa.get('cohort_size', '?')})."
            )
            if sa.get("pilot", {}).get("db_path"):
                print(f"  Audit DB: {sa['pilot']['db_path']}")
    except Exception as e:
        print(f"Signal audit log skipped: {e}")

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
