"""
Ticker detail: thesis, earnings, benchmarks (SPY, industry ETF, peers), model accuracy.
Uses parallel fetches and 5-min cache to reduce timeout risk.
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behavior.thesis import load_theses
from signals.fetcher import fetch_ohlcv_safe, fetch_ohlcv_with_volume
from signals.providers import MAJOR_INDEX_ETFS
from signals.indicators import multi_horizon_scores
from signals.providers import get_next_earnings, get_sector_and_industry, get_peers

try:
    import pandas as pd
except ImportError:
    pd = None

_MAX_PEERS_RETURNS = 2  # Fewer peer fetches = faster (was 4)


def _returns_over_periods(close: pd.Series, periods_days: dict) -> dict:
    """Compute % return from last date over each period. {label: pct_return}."""
    if close is None or close.empty or pd is None:
        return {}
    last = float(close.iloc[-1])
    if last <= 0:
        return {}
    out = {}
    for label, days in periods_days.items():
        if len(close) < days + 5:
            continue
        past_price = float(close.iloc[-1 - days])
        if past_price and past_price > 0:
            out[label] = round(100 * (last - past_price) / past_price, 2)
    return out


def get_ticker_detail(ticker: str, config: dict) -> dict:
    """
    Full ticker detail: thesis, earnings, sector, peers, benchmark comparison.
    Uses 5-min cache (Redis) and parallel fetches to reduce timeout risk.
    """
    period = config.get("data", {}).get("period", "2y") or "2y"
    config_hash = period
    try:
        from signals.cache import cached_ticker_detail
        return cached_ticker_detail(
            ticker.upper(),
            config_hash,
            lambda: _fetch_ticker_detail_impl(ticker, config),
        )
    except Exception:
        return _fetch_ticker_detail_impl(ticker, config)


def _fetch_ticker_detail_impl(ticker: str, config: dict) -> dict:
    """Inner implementation (called with or without cache)."""
    ticker = ticker.upper()
    theses = load_theses()
    thesis_data = theses.get(ticker, {})
    period = config.get("data", {}).get("period", "2y") or "2y"
    periods = {"1m": 21, "3m": 63, "6m": 126, "1y": 252}

    # Phase 1: sector, peers, earnings, ticker OHLCV, SPY OHLCV in parallel
    sector_info: dict = {}
    peers_raw: list = []
    earnings = None
    close_ticker = None
    volume = None
    close_spy = None

    def _sector():
        return get_sector_and_industry(ticker, config) or {}

    def _peers():
        return get_peers(ticker, config) or []

    def _earn():
        return get_next_earnings(ticker, config)

    def _ticker_ohlcv():
        c, v = fetch_ohlcv_with_volume(ticker, period)
        if c is None:
            c = fetch_ohlcv_safe(ticker, period)
        return c, v

    def _spy():
        return fetch_ohlcv_safe("SPY", period)

    with ThreadPoolExecutor(max_workers=5) as ex:
        f_sector = ex.submit(_sector)
        f_peers = ex.submit(_peers)
        f_earn = ex.submit(_earn)
        f_ticker = ex.submit(_ticker_ohlcv)
        f_spy = ex.submit(_spy)
        for f in as_completed([f_sector, f_peers, f_earn, f_ticker, f_spy]):
            try:
                r = f.result()
                if f is f_sector:
                    sector_info = r
                elif f is f_peers:
                    peers_raw = r
                elif f is f_earn:
                    earnings = r
                elif f is f_ticker:
                    close_ticker, volume = r or (None, None)
                elif f is f_spy:
                    close_spy = r
            except Exception:
                pass

    sector_etf = sector_info.get("sector_etf", "SPY")
    peers = [str(p).upper() for p in peers_raw if str(p).upper() not in ("SPY", "QQQ", "GLD", "SLV")][:6]

    # Phase 2: sector ETF (if != SPY) and peer OHLCV in parallel
    close_sector = close_spy
    peer_returns = []

    def _sector_ohlcv():
        return ("sector", fetch_ohlcv_safe(sector_etf, period) if sector_etf != "SPY" else None)

    def _peer_ohlcv(peer_sym: str):
        # Fix 2: Explicit peer symbol per call so cache/closure never reuse wrong ticker.
        c = fetch_ohlcv_safe(peer_sym, period)
        ret = _returns_over_periods(c, periods) if c is not None else None
        return ("peer", peer_sym, ret)

    seen_peer_signatures: dict = {}  # (1m, 3m, 6m, 1y) -> ticker for deduplication detection
    with ThreadPoolExecutor(max_workers=1 + _MAX_PEERS_RETURNS) as ex:
        tasks = [ex.submit(_sector_ohlcv)]
        for p in peers[:_MAX_PEERS_RETURNS]:
            tasks.append(ex.submit(_peer_ohlcv, p))
        for f in as_completed(tasks):
            try:
                r = f.result()
                if r[0] == "sector" and r[1] is not None:
                    close_sector = r[1]
                elif r[0] == "peer" and r[2]:
                    pr_ticker, pr_returns = r[1], r[2]
                    sig = tuple(pr_returns.get(lbl) for lbl in ["1m", "3m", "6m", "1y"])
                    if sig in seen_peer_signatures and sig != (None, None, None, None):
                        # Flag duplicate data (e.g. API returning same series for different tickers).
                        peer_returns.append({
                            "ticker": pr_ticker,
                            "returns": pr_returns,
                            "data_quality_warning": f"Same returns as {seen_peer_signatures[sig]}",
                        })
                    else:
                        seen_peer_signatures[sig] = pr_ticker
                        peer_returns.append({"ticker": pr_ticker, "returns": pr_returns})
            except Exception:
                pass

    if close_sector is None:
        close_sector = close_spy
    if close_ticker is None:
        close_ticker, volume = fetch_ohlcv_with_volume(ticker, period), None
        if close_ticker is None:
            close_ticker = fetch_ohlcv_safe(ticker, period)

    # Fix 1: Compute benchmark from explicitly separate series so ticker and SPY never share data.
    ret_ticker = _returns_over_periods(close_ticker, periods) if close_ticker is not None else {}
    ret_spy = _returns_over_periods(close_spy, periods) if close_spy is not None else {}
    ret_sector = _returns_over_periods(close_sector, periods) if close_sector is not None else {}

    # Sanity: if ticker and SPY returns are identical in all periods, refetch SPY once (breaks cache/confusion).
    if ret_ticker and ret_spy and set(ret_ticker.keys()) == set(ret_spy.keys()):
        all_same = all(ret_ticker.get(k) == ret_spy.get(k) for k in ret_ticker)
        if all_same and ticker.upper() != "SPY":
            close_spy = fetch_ohlcv_safe("SPY", period)
            ret_spy = _returns_over_periods(close_spy, periods) if close_spy is not None else ret_spy

    # Current price = last bar of the same close series used for bands (index ETFs: Ticker.history path in fetcher)
    current_price = float(close_ticker.iloc[-1]) if close_ticker is not None and not close_ticker.empty else None

    # Volume vs 20d avg, drawdown 52w
    volume_ratio = None
    volume_unusual = False
    if volume is not None and len(volume) >= 20:
        today_vol = float(volume.iloc[-1])
        avg_vol = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else float(volume.iloc[-20:].mean())
        if avg_vol and avg_vol > 0:
            volume_ratio = round(today_vol / avg_vol, 2)
            volume_unusual = volume_ratio >= 2.0

    # 52-week range and drawdown from price history (252 trading days)
    range_low = range_high = high_52w = low_52w = drawdown_52w = None
    if close_ticker is not None and len(close_ticker) >= 252 and current_price:
        last_252 = close_ticker.iloc[-252:]
        range_high = round(float(last_252.max()), 2)
        range_low = round(float(last_252.min()), 2)
        if range_high and range_high > 0:
            drawdown_52w = round(100 * (current_price - range_high) / range_high, 1)

    # Sanity checks for 52w range and drawdown
    sanity_errors: list[str] = []
    if range_low is not None and range_low < 0:
        sanity_errors.append("range_negative")
    if range_low is not None and range_high is not None and current_price is not None:
        if not (range_low <= current_price <= max(range_high * 1.05, range_high + 0.01)):
            sanity_errors.append("range_drawdown")
    if drawdown_52w is not None and abs(drawdown_52w) > 80:
        sanity_errors.append("drawdown_extreme")

    # Single fused confidence pass for this request (price_reasoning + investor_summary + news layer)
    conf_snapshot_for_request: dict | None = None
    try:
        from signals.confidence_engine import run_confidence

        conf_snapshot_for_request = run_confidence(ticker, config=config)
    except Exception:
        pass

    # Signal reasoning (HOLD/BUY/SELL with brief why)
    signal_data = {}
    price_reasoning: dict[str, str] = {}
    if close_ticker is not None and not close_ticker.empty and pd is not None:
        try:
            from signals.score_interpretation import detect_interpretation_style

            _sty, _meta = detect_interpretation_style(close_ticker, volume, config, ticker=ticker)
            sig = multi_horizon_scores(close_ticker, interpretation_style=_sty)
            buy_p = sig.get("suggested_buy_price")
            sell_p = sig.get("suggested_sell_price")
            supp = sig.get("support_level")
            rsi = sig.get("rsi")
            score = sig.get("composite_buy")
            buy_conf = sig.get("buy_target_confidence_pct")
            sell_conf = sig.get("sell_target_confidence_pct")
            model_confidence_pct = None
            if conf_snapshot_for_request and conf_snapshot_for_request.get("confidence") is not None:
                model_confidence_pct = int(round(float(conf_snapshot_for_request["confidence"]) * 100))

            signal_data = {
                "score_interpretation_style": _sty,
                "score_interpretation_meta": _meta,
                "short_suggestion": sig.get("short_suggestion"),
                "medium_suggestion": sig.get("medium_suggestion"),
                "long_suggestion": sig.get("long_suggestion"),
                "short_reason": sig.get("short_reason"),
                "medium_reason": sig.get("medium_reason"),
                "long_reason": sig.get("long_reason"),
                "suggested_buy_price": buy_p,
                "suggested_sell_price": sell_p,
                "support_level": supp,
                "rsi": sig.get("rsi"),
                "buy_target_confidence_pct": buy_conf,
                "sell_target_confidence_pct": sell_conf,
                "model_confidence_pct": model_confidence_pct,
                "ma20": sig.get("ma20"),
                "ma50": sig.get("ma50"),
                "ma200": sig.get("ma200"),
                "score_breakdown": {
                    "trend": sig.get("trend_score"),
                    "rsi": sig.get("rsi_contrib"),
                    "macd": sig.get("macd_contrib"),
                    "composite": sig.get("composite_buy"),
                },
            }
            # Human-readable reasoning — distinguish model (7-layer) vs technical composite (rule-based)
            if buy_p is not None:
                tech_b = int(buy_conf) if buy_conf is not None else None
                parts_buy: list[str] = [
                    f"Technical entry level ~${buy_p:.2f} (MA50/200 support zone).",
                ]
                if model_confidence_pct is not None:
                    parts_buy.append(
                        f"Model confidence {model_confidence_pct}% (7-layer fused) — use this as the primary action gauge; "
                        "wait for regime confirmation before sizing new adds mainly on this level."
                    )
                if tech_b is not None:
                    parts_buy.append(
                        f"Technical setup strength ~{tech_b}% (momentum/RSI/MACD composite only — not the same measure as model confidence)."
                    )
                price_reasoning["buy"] = " ".join(parts_buy)
            else:
                price_reasoning["buy"] = "Buy: – (no add level; price below MA50 or insufficient data)"

            if sell_p is not None:
                tech_s = int(sell_conf) if sell_conf is not None else None
                parts_sell: list[str] = [f"Technical trim/exit zone ~${sell_p:.2f}."]
                if model_confidence_pct is not None:
                    parts_sell.append(f"Model confidence {model_confidence_pct}% reflects the full thesis, not this rule-based exit flag alone.")
                if tech_s is not None:
                    parts_sell.append(f"Technical exit signal strength ~{tech_s}% (rule-based).")
                price_reasoning["sell"] = " ".join(parts_sell)
            else:
                rsi_s = f"RSI {rsi:.0f}" if rsi is not None else "RSI n/a"
                score_s = f"score {score:.0f}" if score is not None else "score n/a"
                price_reasoning["sell"] = f"Sell: – (no sell signal; {rsi_s}, {score_s})"

            supp_primary = sig.get("support_primary")
            supp_secondary = sig.get("support_secondary")
            if supp_primary is not None and supp_secondary is not None:
                price_reasoning["support"] = f"Support: primary ~${supp_primary:.2f} (MA50), secondary ~${supp_secondary:.2f} (MA200)"
            elif supp is not None:
                price_reasoning["support"] = f"Support: ~${supp:.2f}; break below suggests caution"
            else:
                price_reasoning["support"] = "Support: – (price below MA50 or no data)"
        except Exception:
            pass

    extra = _get_extra_info(ticker, config)
    high_52w = extra.get("high_52w") if extra.get("high_52w") is not None else (round(range_high, 2) if range_high is not None else None)
    low_52w = extra.get("low_52w") if extra.get("low_52w") is not None else (round(range_low, 2) if range_low is not None else None)
    if extra.get("dividend_yield_error"):
        sanity_errors.append("yield")
    dividend_explanation = (
        "Gold ETFs usually have ~0% dividend; they track gold price, not income."
        if ticker in _GOLD_ETFS
        else "Dividend yield = last 12-month dividends / current price."
    )
    lhr = None
    period_long_risk = config.get("data", {}).get("period_long_risk", "13y") or "13y"
    try:
        from signals.long_horizon_risk import compute_long_horizon_risk
        from signals.cache import cached_long_horizon_risk
        lhr = cached_long_horizon_risk(ticker, period_long_risk, lambda: compute_long_horizon_risk(ticker, period_long_risk))
    except Exception:
        pass
    fmp_data = _get_fmp_data(ticker, config, current_price, signal_data, close_ticker, range_low=range_low, range_high=range_high, long_horizon_risk=lhr)
    if fmp_data.get("lt_scenarios"):
        lt = fmp_data["lt_scenarios"]
        bear, base, bull = lt.get("bear"), lt.get("base"), lt.get("bull")
        if bear is not None and base is not None and bull is not None and not (bear < base < bull):
            sanity_errors.append("bb_band_order")

    # Build response dict first so we can pass it to investor summary
    response = {
        "fundamentals_snapshot": {
            "point_in_time": False,
            "short_label": "Current snapshot (not PIT)",
            "detail": (
                "PE, EPS estimates, and key metrics from FMP/yfinance reflect the latest vendor snapshot "
                "at load time — not restated point-in-time historical fundamentals. "
                "Backtests that use price only avoid lookahead; valuation ratios on the card are descriptive, not causal history."
            ),
        },
        "ticker": ticker,
        "thesis": thesis_data.get("thesis", ""),
        "exit_condition": thesis_data.get("exit_condition", ""),
        "earnings": earnings,
        "sector": sector_info.get("sector"),
        "industry": sector_info.get("industry"),
        "sector_etf": sector_etf,
        "sector_etf_name": sector_info.get("sector_etf_name", sector_etf),
        "peers": peers,
        "current_price": current_price,
        "returns": ret_ticker or {},
        "benchmark_spy": ret_spy or {},
        "benchmark_industry": ret_sector or {},
        "peer_returns": peer_returns or [],
        "earnings_history": _get_earnings_history(ticker),
        "sector_specific": _get_sector_specific_metrics(ticker, sector_info.get("sector")),
        "rate_sensitivity": _get_rate_sensitivity(ticker, close_ticker),
        "seasonal_note": _seasonal_note(ticker),
        "price_reasoning": price_reasoning,
        "volume_ratio": volume_ratio,
        "volume_unusual": volume_unusual,
        "drawdown_52w": drawdown_52w,
        "high_52w": round(high_52w, 2) if high_52w is not None else None,
        "low_52w": round(low_52w, 2) if low_52w is not None else None,
        "dividend_yield_explanation": dividend_explanation,
        "sanity_errors": sanity_errors,
        "long_horizon_risk": lhr or fmp_data.get("long_horizon_risk"),
        **extra,
        **signal_data,
        **fmp_data,
    }
    response["investor_summary"] = _build_investor_summary(
        ticker,
        config,
        response,
        close_ticker=close_ticker,
        signal_data=signal_data,
        conf_snapshot=conf_snapshot_for_request,
    )
    # Ensure 52w range is always 2 decimals (yfinance/merge can leave raw floats)
    if response.get("high_52w") is not None:
        response["high_52w"] = round(float(response["high_52w"]), 2)
    if response.get("low_52w") is not None:
        response["low_52w"] = round(float(response["low_52w"]), 2)
    return response


def _build_news_sentiment_layer_for_ui(conf: dict | None, config: dict | None = None) -> dict | None:
    """
    Sanitized news/NLP payload for the roadmap UI — same run_confidence() pass as ML/HMM/pattern inputs.
    Includes booleans fmp_key_configured / alpha_vantage_key_configured (no secrets) for deploy debugging.
    """
    cfg = config or {}
    try:
        from signals.fmp_client import get_api_key as _fmp_key
        from signals.alpha_vantage_client import get_api_key as _av_key

        fmp_key_configured = bool(_fmp_key(cfg))
        alpha_vantage_key_configured = bool(_av_key(cfg))
    except Exception:
        fmp_key_configured = False
        alpha_vantage_key_configured = False

    if not conf:
        return {
            "pipeline_note": (
                "Headlines feed the news sentiment layer in the same confidence run as ML/HMM/pattern. "
                "Confidence response was empty — cannot show NLP details."
            ),
            "fmp_key_configured": fmp_key_configured,
            "alpha_vantage_key_configured": alpha_vantage_key_configured,
            "message": (
                "Confidence engine did not return a payload for this ticker (check backend logs). "
                "Keys only matter once the engine runs: set FMP_API_KEY / ALPHA_VANTAGE_API_KEY on the host or "
                "data.fmp_api_key / data.alpha_vantage_api_key in config."
            ),
        }
    nlp = conf.get("nlp")
    bd = conf.get("breakdown") or {}
    news_b = bd.get("nlp_sentiment") if isinstance(bd.get("nlp_sentiment"), dict) else {}
    if not news_b and isinstance(bd.get("news"), dict):
        news_b = bd["news"]
    weight = news_b.get("weight")
    available = news_b.get("available")
    label_bd = news_b.get("label")

    headlines_out: list[dict[str, Any]] = []
    if isinstance(nlp, dict):
        for h in (nlp.get("headlines") or [])[:10]:
            if isinstance(h, dict):
                headlines_out.append(
                    {
                        "title": str(h.get("title") or "")[:220],
                        "score": h.get("score"),
                        "label": h.get("label"),
                    }
                )
            elif isinstance(h, str):
                headlines_out.append({"title": h[:220], "score": None, "label": None})

    has_score = isinstance(nlp, dict) and nlp.get("score") is not None

    if has_score:
        msg = None
    elif available is False and (weight == 0 or weight is None):
        msg = (
            "News layer weight is 0 for this asset class (e.g. commodity ETFs) — not a missing API key. "
            "Headlines are shown for transparency; other layers drive the roadmap."
        )
    elif not fmp_key_configured and not alpha_vantage_key_configured:
        msg = (
            "No FMP or Alpha Vantage API key is loaded in this process. "
            "Set environment variables FMP_API_KEY and/or ALPHA_VANTAGE_API_KEY on Railway (or fill "
            "data.fmp_api_key / data.alpha_vantage_api_key in config). "
            "Subscription alone does not inject keys — they must be configured where the API runs."
        )
    elif fmp_key_configured and not isinstance(nlp, dict):
        msg = (
            "FMP key is configured, but NLP did not attach headline data this run — often rate limit, "
            "transient FMP error, or Yahoo Finance fallback in use. Check server logs for "
            "'News sentiment' / 'fetch_stock_news'."
        )
    else:
        msg = (
            "No scored news sentiment this run (empty headlines, rate limit, or lexicon miss). "
            "Other layers still drive the roadmap; weights may be redistributed."
        )

    return {
        "pipeline_note": (
            "Headlines feed the news sentiment layer in the same confidence run that supplies "
            "ML horizons, HMM regime, and pattern scores for this roadmap — not a separate price engine."
        ),
        "fmp_key_configured": fmp_key_configured,
        "alpha_vantage_key_configured": alpha_vantage_key_configured,
        "score_0_1": nlp.get("score") if isinstance(nlp, dict) else None,
        "raw_score_neg1_to_1": nlp.get("raw_score") if isinstance(nlp, dict) else None,
        "summary_label": (nlp.get("label") if isinstance(nlp, dict) else None) or label_bd,
        "sentiment_label": nlp.get("sentiment_label") if isinstance(nlp, dict) else None,
        "headline_count": nlp.get("headline_count") if isinstance(nlp, dict) else None,
        "source": nlp.get("source") if isinstance(nlp, dict) else None,
        "method": nlp.get("method") if isinstance(nlp, dict) else None,
        "headlines": headlines_out,
        "layer_weight": weight,
        "layer_available": available,
        "message": msg,
        "fmp_request_error": (nlp.get("fmp_request_error") if isinstance(nlp, dict) else None),
    }


def _build_investor_summary(
    ticker: str,
    config: dict,
    response: dict,
    *,
    close_ticker=None,
    signal_data: dict | None = None,
    conf_snapshot: dict | None = None,
) -> dict | None:
    """
    Build Investor Decision Summary (horizon entry tiers + verdicts) for the ticker detail modal.
    Uses horizon_entry_calculator with data from response + run_confidence for ML probs.
    Trade roadmap produces the canonical scenario_target; medium horizon target is overwritten to match
    so UI and copy stay consistent (one source of truth).
    Returns None if required inputs are missing.
    """
    signal_data = signal_data or {}
    try:
        from signals.horizon_entry_calculator import build_all_horizons_payload
        from signals.fair_value_estimator import (
            FairValueResult,
            compute_index_fair_value,
            estimate_fair_value as estimate_fair_value_full,
        )
    except Exception:
        return None

    current_price = response.get("current_price")
    if current_price is None or current_price <= 0:
        return None
    ma50 = _safe_float(response.get("ma50"))
    ma200 = _safe_float(response.get("ma200"))
    low_52w = _safe_float(response.get("low_52w"))
    high_52w = _safe_float(response.get("high_52w"))
    if ma50 is None or ma200 is None or low_52w is None:
        return None

    # ML probs and regime from confidence engine (full `conf` kept for roadmap news transparency)
    st_ml_prob = mt_ml_prob = lt_ml_prob = 25.0
    regime_bull_pct = 50.0
    pattern_score = 50.0
    regime_hmm_label: str | None = None
    model_confidence_pct_summary: int | None = None
    if response.get("score_breakdown") and response["score_breakdown"].get("composite") is not None:
        pattern_score = float(response["score_breakdown"]["composite"])
    if conf_snapshot is None:
        try:
            from signals.confidence_engine import run_confidence

            conf_snapshot = run_confidence(ticker, config=config)
        except Exception:
            conf_snapshot = None
    try:
        if conf_snapshot:
            mh = conf_snapshot.get("ml_horizons") or {}
            st_ml_prob = float(mh.get("short", {}).get("prob") or 0.25) * 100.0
            mt_ml_prob = float(mh.get("medium", {}).get("prob") or 0.25) * 100.0
            lt_ml_prob = float(mh.get("long", {}).get("prob") or 0.25) * 100.0
            hmm = conf_snapshot.get("hmm") or {}
            regime_bull_pct = float(hmm.get("bull_probability") or 0.5) * 100.0
            if conf_snapshot.get("confidence") is not None:
                model_confidence_pct_summary = int(round(float(conf_snapshot["confidence"]) * 100))
            b = conf_snapshot.get("breakdown") or {}
            pl = b.get("pattern") or b.get("pattern_technical")
            if isinstance(pl, dict) and pl.get("score") is not None:
                pattern_score = float(pl["score"]) * 100.0
            rh = b.get("regime_hmm")
            if isinstance(rh, dict) and rh.get("label"):
                regime_hmm_label = str(rh["label"])
    except Exception:
        pass

    rsi = _safe_float(response.get("rsi")) or 50.0
    atr = _safe_float(response.get("atr14"))
    if atr is None or atr <= 0:
        atr = current_price * 0.02
    support_level = _safe_float(response.get("support_level")) or (low_52w or current_price * 0.95)
    resistance_level = high_52w or current_price * 1.05
    # Do not anchor short-horizon targets to 52w high alone for index ETFs — can sit far above spot
    # and distorts entry/target copy when Yahoo spot and FMP profile 52w disagree.
    if ticker.upper() in MAJOR_INDEX_ETFS:
        resistance_level = min(float(resistance_level), current_price * 1.12)
    vwap = current_price
    volume_ratio = _safe_float(response.get("volume_ratio")) or 1.0

    # Fair value: prefer multi-method estimator (value/growth/high-growth) so "X% undervalued"
    # reflects fundamental valuation, not analyst consensus high. Fall back to LT band high if
    # estimator cannot run (e.g. missing PE/margin data).
    fair_value: float | None = None
    fv_result = None
    sector_specific = response.get("sector_specific") or {}
    ttm_pe_used: float | None = None
    forward_pe_used: float | None = None
    forward_pe_discarded = False  # set True when fwd << ttm and we exclude from FV
    analyst_target_yahoo: float | None = None  # yfinance targetMeanPrice — exposed vs model FV for verification
    try:
        import yfinance as yf
        from signals.fmp_client import fetch_key_metrics_ttm

        t = yf.Ticker(ticker)
        info = getattr(t, "info", None) or {}
        # Resolve TTM PE with priority: FMP > computed (price/trailingEps) > yfinance trailingPE
        ttm_pe = None
        forward_pe = None
        fmp_km, _ = fetch_key_metrics_ttm(config, ticker)
        if fmp_km and isinstance(fmp_km, dict):
            ttm_pe = _safe_float(
                fmp_km.get("peRatioTTM") or fmp_km.get("peRatio") or fmp_km.get("trailingPE") or fmp_km.get("priceEarningsRatio")
            )
            forward_pe = _safe_float(fmp_km.get("forwardPE"))

        if ttm_pe is None and current_price:
            eps = _safe_float(info.get("trailingEps"))
            if eps and eps > 0:
                ttm_pe = round(current_price / eps, 2)
        if ttm_pe is None:
            ttm_pe = _safe_float(info.get("trailingPE"))
        if forward_pe is None:
            forward_pe = _safe_float(info.get("forwardPE"))

        # Sanity: known high-PE growth names (e.g. NVDA 35–40x TTM) — if source returns
        # suspiciously low TTM PE (e.g. 17.3 from split/adjustment error), recompute from
        # current price / trailingEps so fair value and fundamentals are not built on bad inputs.
        _HIGH_PE_GROWTH = frozenset({"NVDA", "AVGO", "META", "AMD", "TSLA", "CRM", "NOW", "SNOW", "PLTR", "NET", "DDOG", "MDB", "CRWD", "PANW"})
        if (
            ticker.upper() in _HIGH_PE_GROWTH
            and current_price
            and ttm_pe is not None
            and 0 < ttm_pe < 25
        ):
            trailing_eps = _safe_float(info.get("trailingEps"))
            if trailing_eps and trailing_eps > 0:
                ttm_pe_recomputed = round(current_price / trailing_eps, 2)
                if 25 <= ttm_pe_recomputed <= 100:
                    ttm_pe = ttm_pe_recomputed

        # Sanity: forward PE much lower than TTM (e.g. NVDA 17x fwd vs 38x TTM) often indicates
        # split-adjustment or GAAP/non-GAAP mismatch. Cross-check with yfinance forwardEps.
        if (
            ttm_pe is not None
            and ttm_pe > 0
            and forward_pe is not None
            and forward_pe > 0
            and forward_pe < ttm_pe * 0.65
            and current_price
        ):
            forward_eps_yf = _safe_float(info.get("forwardEps"))
            if forward_eps_yf and forward_eps_yf > 0:
                forward_pe_yf = round(current_price / forward_eps_yf, 2)
                # If yfinance forward PE is in a more plausible range (e.g. 20–50), prefer it
                if 18 <= forward_pe_yf <= 60:
                    forward_pe = forward_pe_yf
                else:
                    forward_pe = None  # exclude from fair value; use TTM only
                    forward_pe_discarded = True
            else:
                forward_pe = None  # exclude suspicious FMP forward PE from fair value
                forward_pe_discarded = True

        revenue_growth = _safe_float(info.get("revenueGrowth"))
        if revenue_growth is not None and revenue_growth < 1 and revenue_growth > 0:
            revenue_growth = revenue_growth * 100
        earnings_growth = _safe_float(info.get("earningsGrowth"))
        if earnings_growth is not None and earnings_growth < 1 and earnings_growth > 0:
            earnings_growth = earnings_growth * 100
        margin = _safe_float(info.get("profitMargins"))
        if margin is not None and margin < 1:
            margin = margin * 100
        de = _safe_float(info.get("debtToEquity"))
        sector_pe = 28.0
        sector_forward_pe = 25.0
        analyst_target = _safe_float(info.get("targetMeanPrice"))
        analyst_target_yahoo = analyst_target
        fcf = _safe_float(info.get("freeCashflow"))
        shares = _safe_float(info.get("sharesOutstanding"))
        fcf_per_share = (fcf / shares) if (fcf and shares and shares > 0) else None

        # SPY: earnings-yield model (rf + ERP) on ETF EPS — avoids PE-relative growth logic on an index
        use_spy_yield = (config.get("fair_value") or {}).get("use_earnings_yield_for_spy", True)
        if ticker.upper() == "SPY" and use_spy_yield:
            fv_cfg = config.get("fair_value") or {}
            rf = float(fv_cfg.get("risk_free_rate", 0.043))
            erp = float(fv_cfg.get("equity_risk_premium", 0.045))
            forward_eps = _safe_float(info.get("forwardEps"))
            if forward_eps is None or forward_eps <= 0:
                if forward_pe and forward_pe > 0 and current_price:
                    forward_eps = current_price / forward_pe
                else:
                    te = _safe_float(info.get("trailingEps"))
                    if te and te > 0:
                        forward_eps = te
            if forward_eps and forward_eps > 0:
                fv_sp = compute_index_fair_value(forward_eps, rf, erp, index_level_eps=False)
                disc = round((fv_sp - current_price) / current_price * 100, 1) if current_price else 0.0
                fv_result = FairValueResult(
                    fair_value=fv_sp,
                    stock_type="index_etf",
                    method_used="earnings_yield_sp500_etf",
                    confidence="Medium",
                    discount_pct=disc,
                    analyst_target=analyst_target,
                    notes=[
                        "SPY FV uses earnings-yield (1/(rf+ERP)×EPS per SPY share). "
                        "Tune fair_value.risk_free_rate and equity_risk_premium; not comparable to single-name DCF."
                    ],
                    bear_case=round(fv_sp * 0.85, 2) if fv_sp > 0 else None,
                    methodology_summary=f"SPY index ETF: EPS×(1/(rf+ERP)); rf={rf:.1%}, ERP={erp:.1%}",
                )
                fair_value = fv_sp

        pe = ttm_pe or forward_pe
        if ttm_pe is not None and ttm_pe > 0:
            ttm_pe_used = ttm_pe
        if forward_pe is not None and forward_pe > 0:
            forward_pe_used = forward_pe
        if fv_result is None and pe and pe > 0 and margin is not None:
            _fv_gr = (config.get("fair_value") or {}).get("guardrails")
            fv_result = estimate_fair_value_full(
                current_price=current_price,
                ttm_pe=ttm_pe if (ttm_pe is not None and ttm_pe > 0) else (forward_pe or pe),
                sector_pe=sector_pe,
                revenue_growth_pct=revenue_growth or 10.0,
                earnings_growth_pct=earnings_growth if earnings_growth is not None else (revenue_growth or 10.0),
                net_margin_pct=margin or 15.0,
                de_ratio=de or 0.5,
                forward_pe=forward_pe,
                sector_forward_pe=sector_forward_pe,
                fcf_per_share=fcf_per_share,
                analyst_target=analyst_target,
                guardrails=dict(_fv_gr) if isinstance(_fv_gr, dict) else None,
            )
            if fv_result and fv_result.fair_value and fv_result.fair_value > 0:
                fair_value = fv_result.fair_value
    except Exception:
        pass
    # Fallback: LT band high (blends model + analyst consensus)
    if fair_value is None or fair_value <= 0:
        fair_value = _safe_float(response.get("lt_band", {}).get("high")) if isinstance(response.get("lt_band"), dict) else None
    if fair_value is None or fair_value <= 0:
        fair_value = current_price * 1.15

    days_to_earnings = None
    if response.get("earnings") and isinstance(response["earnings"], dict):
        days_to_earnings = response["earnings"].get("days_until")

    options_sentiment_score = 50.0
    insider_activity_score = 50.0
    fundamentals_score = 50.0
    if response.get("breakdown"):
        b = response["breakdown"]
        for layer, key in [("options_sentiment", "options_sentiment"), ("insider_signal", "insider_signal"), ("fundamental_score", "fundamental_score")]:
            s = (b.get(layer) or b.get(key)) or {}
            sc = s.get("score") if isinstance(s, dict) else None
            if sc is not None:
                v = float(sc) * 100 if float(sc) <= 1 else float(sc)
                if layer == "options_sentiment":
                    options_sentiment_score = v
                elif layer == "insider_signal":
                    insider_activity_score = v
                else:
                    fundamentals_score = v
    # Prefer confidence breakdown if we have it from a prior run (we don't pass it in response; keep defaults)

    h_cfg = config.get("horizons") or {}
    tier2_mos_by_class = h_cfg.get("tier2_mos_pct")
    tier2_mos_pct_by_ticker = h_cfg.get("tier2_mos_pct_by_ticker")

    try:
        payload = build_all_horizons_payload(
            current_price=current_price,
            rsi=rsi,
            atr=atr,
            vwap=vwap,
            support_level=support_level,
            resistance_level=resistance_level,
            ma50=ma50,
            ma200=ma200,
            week52_low=low_52w,
            volume_ratio=volume_ratio,
            st_ml_prob=st_ml_prob,
            mt_ml_prob=mt_ml_prob,
            lt_ml_prob=lt_ml_prob,
            regime_bull_pct=regime_bull_pct,
            pattern_score=pattern_score,
            fair_value=fair_value,
            options_sentiment_score=options_sentiment_score,
            insider_activity_score=insider_activity_score,
            fundamentals_score=fundamentals_score,
            days_to_earnings=days_to_earnings,
            ticker=ticker,
            tier2_mos_by_class=tier2_mos_by_class,
            tier2_mos_pct_by_ticker=tier2_mos_pct_by_ticker,
            model_confidence_pct=float(model_confidence_pct_summary)
            if model_confidence_pct_summary is not None
            else None,
        )
    except Exception:
        return None

    verdicts = [payload["short"].get("verdict"), payload["medium"].get("verdict"), payload["long"].get("verdict")]
    overall = "STRONG BUY" if "STRONG BUY" in verdicts else "BUY" if "BUY" in verdicts else "WATCH" if "WATCH" in verdicts else "WAIT"

    # When regime/ML say REDUCE or AVOID but long-term MOS says "entry justified", avoid contradiction
    display_verdict = (response.get("short_suggestion") or response.get("medium_suggestion") or response.get("long_suggestion")) or ""
    if display_verdict.upper() in ("REDUCE", "AVOID"):
        long_h = payload.get("long") or {}
        et = long_h.get("entry_tiers") or {}
        ca = et.get("current_assessment") or {}
        label = ca.get("label") or ""
        if "entry justified" in label.lower():
            payload["long"] = dict(long_h)
            payload["long"]["entry_tiers"] = dict(et)
            payload["long"]["entry_tiers"]["current_assessment"] = dict(ca)
            payload["long"]["entry_tiers"]["current_assessment"]["label"] = (
                f"Valuation supports entry — but regime/ML say {display_verdict.upper()}."
            )

    out: dict = {
        "fair_value": round(fair_value, 2),
        "overall_verdict": overall,
        "horizons": payload,
        "pattern_score": round(pattern_score, 1) if pattern_score is not None else None,
        "regime_bull_pct": round(regime_bull_pct, 1),
        "regime_hmm_label": regime_hmm_label,
        "model_confidence_pct": model_confidence_pct_summary,
    }

    def _fv_pct_vs_ref(model: float, ref: float | None) -> float | None:
        if ref is None or ref <= 0:
            return None
        return round(100.0 * (model - ref) / ref, 1)

    fmp_lo = _safe_float(response.get("cons_low"))
    fmp_hi = _safe_float(response.get("cons_high"))
    fmp_med = _safe_float(response.get("consensus_median"))
    fmp_median_is_range_midpoint = False
    if fmp_med is None and fmp_lo is not None and fmp_hi is not None and fmp_lo > 0 and fmp_hi > 0:
        fmp_med = (fmp_lo + fmp_hi) / 2.0
        fmp_median_is_range_midpoint = True
    fv_ext: dict = {
        "yahoo_12m_mean_usd": round(analyst_target_yahoo, 2) if analyst_target_yahoo else None,
        "pct_model_vs_yahoo_mean": _fv_pct_vs_ref(fair_value, analyst_target_yahoo),
        "fmp_consensus_low_usd": round(fmp_lo, 2) if fmp_lo is not None else None,
        "fmp_consensus_high_usd": round(fmp_hi, 2) if fmp_hi is not None else None,
        "fmp_consensus_median_usd": round(fmp_med, 2) if fmp_med is not None else None,
        "fmp_median_is_range_midpoint": fmp_median_is_range_midpoint,
        "pct_model_vs_fmp_median": _fv_pct_vs_ref(fair_value, fmp_med),
        "note": (
            "Model FV vs Yahoo mean (yfinance targetMeanPrice) and vs FMP analyst consensus when configured. "
            "Yahoo mean is also used to cap FV at +10% in the estimator; large gaps often mean stale consensus or method mismatch."
        ),
    }
    out["fair_value_vs_external"] = fv_ext

    if ttm_pe_used is not None:
        out["ttm_pe_used"] = round(ttm_pe_used, 2)
    if forward_pe_used is not None:
        out["forward_pe_used"] = round(forward_pe_used, 2)
    if fv_result is not None:
        fv_meta: dict = {
            "bear_case": getattr(fv_result, "bear_case", None),
            "method_used": fv_result.method_used,
            "methodology_summary": getattr(fv_result, "methodology_summary", None),
            "notes": list(getattr(fv_result, "notes", []) or []),
        }
        fv_meta["notes"] = list(fv_meta.get("notes") or [])
        if forward_pe_used is not None and forward_pe_used < 22.0:
            fv_meta["notes"].append(
                "Forward PE below typical sector range — verify earnings estimate source (FMP/yfinance)."
            )
        if forward_pe_discarded:
            fv_meta["notes"].append(
                "Forward PE discarded (implied earnings vs TTM looked inconsistent); fair value uses TTM only."
            )
        out["fair_value_metadata"] = fv_meta

    # Commodity ETFs: no P/E; fair value from band/consensus — add clarity so users compare to spot
    _COMMODITY_ETFS = _GOLD_ETFS | frozenset({"SLV", "USO", "GDX", "GDXJ", "SIL", "PSLV"})
    if ticker.upper() in _COMMODITY_ETFS:
        fv_meta = out.get("fair_value_metadata") or {"notes": []}
        fv_meta["notes"] = list(fv_meta.get("notes") or [])
        fv_meta["notes"].append(
            "Commodity ETF — no P/E. Fair value from band/consensus; compare to spot (e.g. gold ~$2,900/oz, GLD ≈ 1/10)."
        )
        out["fair_value_metadata"] = fv_meta

    # Trade roadmap first: canonical scenario_target (post RC-1 alignment) is single source of truth.
    retail_cfg = (config.get("retail") or {})
    roadmap_cfg = {
        "apply_auto_fixes": True,
        "enable_signal_regime_on_detail": True,
        **(retail_cfg.get("roadmap") or {}),
    }
    regime_signal_note = (retail_cfg.get("regime_signals") or {}).get(
        "precedence_note",
        "Score bucket thresholds use score.interpretation (ACF) when enabled in config; "
        "Hurst on trade_roadmap is supplementary context.",
    )
    out["trade_roadmap"] = _build_trade_roadmap(
        ticker,
        out,
        response,
        current_price,
        close_series=close_ticker,
        interpretation_style=signal_data.get("score_interpretation_style"),
        interpretation_meta=signal_data.get("score_interpretation_meta"),
        roadmap_cfg=roadmap_cfg,
        regime_signal_precedence_note=regime_signal_note,
        conf_snapshot=conf_snapshot_for_request,
    )
    news_layer = _build_news_sentiment_layer_for_ui(conf_snapshot, config)
    if news_layer and isinstance(out.get("trade_roadmap"), dict):
        out["trade_roadmap"] = {**out["trade_roadmap"], "news_sentiment_layer": news_layer}
    out["scenario_target"] = (out.get("trade_roadmap") or {}).get("scenario_target")

    # One Answer + Trader / Investor roadmaps (horizons.medium.target already synced in _build_trade_roadmap)
    out["one_answer"], out["trader_roadmap"], out["investor_roadmap"] = _build_one_answer_roadmaps(
        ticker, out, response, current_price
    )

    # Cache ST/MT/LT entry/stop/target and ML prob for scanner retail alerts
    try:
        from config_loader import get_data_root
        from scanner.horizon_levels import merge_horizon_band_for_ticker, merge_ml_prob_for_ticker
        data_root = get_data_root()
        for band_key, label in (
            ("short", "Short-term"),
            ("medium", "Medium-term"),
            ("long", "Long-term"),
        ):
            h = payload.get(band_key) or {}
            ez = h.get("entry_zone") or {}
            el = _safe_float(ez.get("low"))
            eh = _safe_float(ez.get("high"))
            stop = _safe_float(h.get("stop_loss"))
            tgt = _safe_float(h.get("target"))
            if el is not None and eh is not None and stop is not None and tgt is not None:
                merge_horizon_band_for_ticker(
                    data_root,
                    ticker,
                    band_key,
                    entry_low=el,
                    entry_high=eh,
                    stop_loss=stop,
                    target=tgt,
                    horizon_label=label,
                )
        merge_ml_prob_for_ticker(data_root, ticker, st_ml_prob)
    except Exception:
        pass

    return out


def _roadmap_core_zone_3_to_6(
    current_price: float,
    ma200: float | None,
    t1_lo: float | None,
    t1_hi: float | None,
    t2_lo: float | None,
    t2_hi: float | None,
    low_52w: float | None,
) -> tuple[float | None, float | None, str, str]:
    """
    When spot is below the MA200 (Tier 1) band, do not show a 'core' zone entirely above spot
    (implies buying higher toward MA200). Prefer MOS tier or a dip band at/under spot.
    """
    core_lo = round(t1_lo, 2) if t1_lo else (round(ma200 * 0.95, 2) if ma200 else None)
    core_hi = round(t1_hi, 2) if t1_hi else (round(ma200 * 1.05, 2) if ma200 else None)
    when = "Core position"
    cond = "Full regime confirmation + ML >60%"
    if not ma200 or core_lo is None or current_price >= core_lo:
        return core_lo, core_hi, when, cond

    when = "Wait for MA200 reclaim or add on weakness"
    if t2_lo is not None and t2_hi is not None:
        if t2_hi <= current_price * 1.02:
            return (
                round(t2_lo, 2),
                round(t2_hi, 2),
                "Core (MOS tier) on weakness",
                "25% MOS band — MA200 is overhead until reclaimed",
            )
        if t2_lo < current_price:
            return (
                round(t2_lo, 2),
                round(min(t2_hi, current_price * 1.01), 2),
                "Core (MOS) below spot",
                "Partial MOS; add only below spot or after reclaim of MA200 zone",
            )
    lo = max(low_52w * 1.02, current_price * 0.88) if low_52w else current_price * 0.90
    hi = min(current_price * 0.995, ma200 * 0.92) if ma200 else current_price * 0.995
    if hi <= lo:
        hi = round(lo * 1.02, 2)
    return (
        round(lo, 2),
        round(hi, 2),
        when,
        f"MA200 ~${ma200:.0f} overhead — no core adds above spot until reclaim; dip adds only",
    )


def _roadmap_scenario_probabilities(
    *,
    regime_bull_pct: float,
    st_ml: float,
    mt_ml: float,
    lt_ml: float,
    pattern_score: float,
    risk_off: bool | None = None,
    vix: float | None = None,
) -> dict:
    """
    Rough scenario weights (sum ≈ 100%) from ML horizons + HMM + pattern — not a forecast, a blend for UX.
    When ``risk_off`` (from VIX / ATR / HMM) is true, shifts mass toward bear vs a pure ML blend.
    """
    def _c(x: float) -> float:
        return max(0.05, min(0.95, x))

    rb = _c(regime_bull_pct / 100.0)
    s = _c(st_ml / 100.0)
    m = _c(mt_ml / 100.0)
    l = _c(lt_ml / 100.0)
    p = _c(pattern_score / 100.0)
    w_bull = 0.28 * rb + 0.22 * s + 0.18 * m + 0.12 * l + 0.20 * p
    w_bear = 0.35 * (1.0 - rb) + 0.25 * (1.0 - s) + 0.15 * max(0.0, 0.55 - p)
    w_base = max(0.08, 1.0 - w_bull - w_bear)
    ssum = w_bull + w_base + w_bear
    b_pct = w_bull / ssum
    be_pct = w_bear / ssum
    ba_pct = w_base / ssum

    method_bits = ["HMM bull %", "short/med/long ML P(hit)", "pattern score"]
    if risk_off:
        freed = b_pct * 0.14
        b_pct *= 0.86
        be_pct += freed * 0.62 + 0.02
        ba_pct += freed * 0.36
        method_bits.append("risk-off gate (VIX/ATR/HMM)")
    try:
        vix_n = float(vix) if vix is not None else None
        if vix_n is not None and vix_n == vix_n and vix_n >= 26.0:
            b_pct *= 0.94
            be_pct += 0.04
            method_bits.append("elevated VIX")
    except (TypeError, ValueError):
        pass

    tot = b_pct + be_pct + ba_pct
    if tot > 1e-12:
        b_pct /= tot
        be_pct /= tot
        ba_pct /= tot

    bull = round(100.0 * b_pct, 0)
    base = round(100.0 * ba_pct, 0)
    bear = 100.0 - bull - base
    bear = max(0.0, bear)
    return {
        "bull_pct": bull,
        "base_pct": base,
        "bear_pct": round(bear, 0),
        "method": "weighted blend of " + ", ".join(method_bits) + " — illustrative",
    }


def _roadmap_market_regime_layer(
    *,
    vix: float | None,
    atr: float | None,
    current_price: float,
    regime_bull_pct: float,
) -> dict:
    atr_pct = (float(atr) / float(current_price)) if (atr and current_price and current_price > 0) else None
    try:
        vix_n = float(vix) if vix is not None else None
        if vix_n is not None and (vix_n != vix_n):  # NaN
            vix_n = None
    except (TypeError, ValueError):
        vix_n = None
    risk_off = False
    if vix_n is not None and vix_n >= 22.0:
        risk_off = True
    if regime_bull_pct < 42.0:
        risk_off = True
    if atr_pct is not None and atr_pct >= 0.035:
        risk_off = True

    if vix_n is None:
        vol_bucket = "unknown"
    elif vix_n >= 28:
        vol_bucket = "high"
    elif vix_n >= 18:
        vol_bucket = "elevated"
    else:
        vol_bucket = "low"

    parts = []
    if risk_off:
        parts.append("Risk-off")
    else:
        parts.append("Risk-on / neutral")
    parts.append(f"vol regime: {vol_bucket}")
    if vix_n is not None:
        parts.append(f"VIX ~{vix_n:.1f}")
    if atr_pct is not None:
        parts.append(f"ATR/price ~{atr_pct * 100:.1f}%")

    return {
        "vix": round(vix_n, 2) if vix_n is not None else None,
        "atr_pct_of_price": round(atr_pct * 100, 2) if atr_pct is not None else None,
        "risk_off": risk_off,
        "vol_bucket": vol_bucket,
        "label": " · ".join(parts),
    }


def _roadmap_resolve_near_term_conflict(buy_stages: list[dict]) -> None:
    """If Today and Days 1–10 share the same price band but differ in action, make dominance explicit."""
    today = next((s for s in buy_stages if s.get("timeline_key") == "today"), None)
    d110 = next((s for s in buy_stages if s.get("timeline_key") == "days_1_10"), None)
    if not today or not d110:
        return
    zt = (
        round(float(today.get("price_zone_low") or 0), 2),
        round(float(today.get("price_zone_high") or 0), 2),
    )
    zd = (
        round(float(d110.get("price_zone_low") or 0), 2),
        round(float(d110.get("price_zone_high") or 0), 2),
    )
    if zt[0] <= 0 or zd[0] <= 0:
        return
    if zt != zd:
        return
    dom = (today.get("when_to_act") or "").strip()
    d110["when_to_act"] = "Patience — no new buy yet"
    d110["condition"] = (
        f"Dominant near-term action is “{dom}” (Today row). Same price band — Days 1–10 means "
        "hold any starter only; do not scale until a later row confirms (not a conflicting entry)."
    )
    d110["priority_note"] = "Subordinate to Today — time discipline, not a second trigger."
    today["priority_note"] = "Governs near-term buys; next row is wait-only in the same band."


def _roadmap_you_are_here(buy_stages: list[dict], price: float) -> dict | None:
    for s in buy_stages:
        lo = s.get("price_zone_low")
        hi = s.get("price_zone_high")
        if lo is None or hi is None:
            continue
        try:
            if float(lo) <= price <= float(hi):
                return {
                    "timeline_key": s.get("timeline_key"),
                    "label": s.get("label"),
                    "within_zone": True,
                }
        except (TypeError, ValueError):
            continue
    return {"timeline_key": None, "label": None, "within_zone": False, "note": "Price between staged bands — see nearest rows."}


def _roadmap_buy_row_risk_reward(
    *,
    horizon_key: str,
    zone_lo: float | None,
    zone_hi: float | None,
    current_price: float,
    fair_value: float,
    ma50: float | None,
    ma200: float | None,
    stop_52w: float,
) -> dict:
    if zone_lo is None or zone_hi is None:
        return {}
    mid = (float(zone_lo) + float(zone_hi)) / 2.0
    if mid <= 0:
        return {}
    upside_pct = max(0.0, (float(fair_value) - mid) / mid * 100.0) if fair_value else None
    if horizon_key in ("today", "days_1_10", "week_2_4"):
        ref_stop = float(ma50) * 0.97 if ma50 else stop_52w
        stop_kind = "technical (≈ MA50×0.97)"
    elif horizon_key in ("1_3_months", "3_6_months"):
        ref_stop = float(ma200) * 0.97 if ma200 else stop_52w
        stop_kind = "technical (≈ MA200×0.97)"
    else:
        ref_stop = float(stop_52w)
        stop_kind = "tail / structural (52w-based)"
    downside_pct = max(0.0, (mid - ref_stop) / mid * 100.0) if ref_stop < mid else 0.0
    rr = None
    if downside_pct > 0.05 and upside_pct is not None:
        rr = round(upside_pct / downside_pct, 2)
    return {
        "upside_to_model_fv_pct": round(upside_pct, 1) if upside_pct is not None else None,
        "downside_to_ref_stop_pct": round(downside_pct, 1),
        "risk_reward": rr,
        "ref_stop_level": round(ref_stop, 2),
        "ref_stop_kind": stop_kind,
    }


def _build_trade_roadmap(
    ticker: str,
    investor_out: dict,
    response: dict,
    current_price: float,
    close_series=None,
    interpretation_style: str | None = None,
    interpretation_meta: dict | None = None,
    roadmap_cfg: dict | None = None,
    regime_signal_precedence_note: str | None = None,
    conf_snapshot: dict | None = None,
) -> dict:
    """
    Build complete Trade Roadmap: buy stages (Today → 6–12 mo) and sell stages (stop → full target),
    plus regime label and trader-type one-liners. See GLD sample in RETAIL_ONE_ANSWER_DESIGN / user spec.
    """
    roadmap_cfg = {
        "apply_auto_fixes": True,
        "enable_signal_regime_on_detail": True,
        **(roadmap_cfg or {}),
    }
    horizons = investor_out.get("horizons") or {}
    short = horizons.get("short") or {}
    medium = horizons.get("medium") or {}
    long_h = horizons.get("long") or {}
    fair_value = investor_out.get("fair_value") or current_price * 1.1
    regime_bull_pct = investor_out.get("regime_bull_pct") or 50.0
    pattern_score = investor_out.get("pattern_score") or 50.0

    vix_cc: float | None = None
    model_confidence_pct: int | None = None
    try:
        if conf_snapshot:
            vx = conf_snapshot.get("vix")
            if vx is not None:
                vix_cc = float(vx)
            if conf_snapshot.get("confidence") is not None:
                model_confidence_pct = int(round(float(conf_snapshot["confidence"]) * 100))
    except (TypeError, ValueError):
        pass

    display_verdict = (
        (response.get("short_suggestion") or response.get("medium_suggestion") or response.get("long_suggestion"))
        or ""
    ).strip().upper()
    overall = investor_out.get("overall_verdict") or "WATCH"
    if display_verdict not in ("REDUCE", "AVOID"):
        display_verdict = overall

    high_52w = _safe_float(response.get("high_52w"))
    low_52w = _safe_float(response.get("low_52w"))
    ma50 = _safe_float(response.get("ma50"))
    ma200 = _safe_float(response.get("ma200"))

    def _ez(d: dict) -> tuple[float | None, float | None]:
        ez = d.get("entry_zone") or {}
        return _safe_float(ez.get("low")), _safe_float(ez.get("high"))

    s_lo, s_hi = _ez(short)
    m_lo, m_hi = _ez(medium)
    st_ml = (short.get("ml_prob") or 0) * 100 if isinstance(short.get("ml_prob"), (int, float)) else (short.get("ml_prob") or 25)
    mt_ml = (medium.get("ml_prob") or 0) * 100 if isinstance(medium.get("ml_prob"), (int, float)) else (medium.get("ml_prob") or 25)
    lt_ml = (long_h.get("ml_prob") or 0) * 100 if isinstance(long_h.get("ml_prob"), (int, float)) else (long_h.get("ml_prob") or 25)

    tiers = (long_h.get("entry_tiers") or {}).get("tiers") or []
    t1_lo = t1_hi = t2_lo = t2_hi = t3_lo = t3_hi = None
    if len(tiers) >= 1:
        t1_lo, t1_hi = _safe_float(tiers[0].get("low")), _safe_float(tiers[0].get("high"))
    if len(tiers) >= 2:
        t2_lo, t2_hi = _safe_float(tiers[1].get("low")), _safe_float(tiers[1].get("high"))
    if len(tiers) >= 3:
        t3_lo, t3_hi = _safe_float(tiers[2].get("low")), _safe_float(tiers[2].get("high"))

    stop_52w = round((low_52w or current_price * 0.8) * 0.97, 2)
    regime_label = (
        investor_out.get("regime_hmm_label")
        or (
            f"Bull {regime_bull_pct:.0f}%"
            if regime_bull_pct >= 50
            else f"Bear {100 - regime_bull_pct:.0f}%"
        )
    )

    # Core / MA200 tier (3–6m) — compute first so near-term rows can match the same entry ladder.
    c6_lo, c6_hi, c6_when, c6_cond = _roadmap_core_zone_3_to_6(
        current_price, ma200, t1_lo, t1_hi, t2_lo, t2_hi, low_52w
    )
    # Same story as long-horizon investor copy: pullbacks toward MA200 when spot is not meaningfully below MA200.
    lt_pullback_toward_ma200 = bool(
        ma200 and ma200 > 0 and current_price >= ma200 * 0.985
    )
    extended_above_core_zone = bool(
        c6_lo is not None and c6_hi is not None and current_price > float(c6_hi) * 1.002
    )
    align_buy_rows_to_core = bool(
        lt_pullback_toward_ma200
        and extended_above_core_zone
        and display_verdict not in ("REDUCE", "AVOID")
    )

    zone_core_lo = round(c6_lo, 2) if c6_lo is not None else None
    zone_core_hi = round(c6_hi, 2) if c6_hi is not None else None
    core_zone_fmt = (
        f"${zone_core_lo:.2f}–${zone_core_hi:.2f}"
        if (zone_core_lo is not None and zone_core_hi is not None)
        else "core zone"
    )

    # ── Buy roadmap stages ───────────────────────────────────────────────────
    buy_stages = []

    # Today — when extended above MA200/core, do not show a competing ST band as the primary entry.
    if display_verdict in ("REDUCE", "AVOID"):
        when = "Do not buy"
        cond = f"Regime {regime_label} — {display_verdict} today"
        conv = "None"
        pos = 0
    elif align_buy_rows_to_core:
        when = "Watch only"
        cond = (
            f"Spot is above preferred adds at {core_zone_fmt} (MA200 / core tier — same ladder as summary). "
            f"Wait for pullback; short-term band is not the plan entry."
        )
        conv = "None"
        pos = 0
    else:
        when = "Start small" if s_lo and current_price <= (s_hi or current_price) else "Watch only"
        in_st_band = bool(s_lo and s_hi and s_lo <= current_price <= s_hi)
        st_conv = (short.get("conviction") or "").strip()
        st_conv_l = st_conv.lower()
        if not in_st_band:
            cond = "Wait for pullback"
        elif st_conv_l in ("medium", "high"):
            cond = "In entry zone"
        else:
            cond = "Inside short-term band (low conviction — starter size only)"
        if when == "Start small":
            conv = st_conv if st_conv else "Low-Medium"
        else:
            conv = "None"
        pos = 25 if when == "Start small" else 0
    if align_buy_rows_to_core:
        today_lo = zone_core_lo
        today_hi = zone_core_hi
    else:
        today_lo = round(s_lo, 2) if s_lo else round(current_price, 2)
        today_hi = round(s_hi, 2) if s_hi else round(current_price, 2)

    # Cumulative % is staged deployment (legacy: 25 → 25 → 60 → 85 → 100), not a raw sum of rows.
    if align_buy_rows_to_core:
        cum_today, cum_days, cum_week, cum_13, cum_36, cum_612 = 0, 0, 0, 35, 60, 100
    else:
        cum_today = cum_days = pos
        cum_week = 25
        cum_13, cum_36, cum_612 = 60, 85, 100

    buy_stages.append({
        "timeline_key": "today",
        "label": "Today",
        "when_to_act": when,
        "price_zone_low": today_lo,
        "price_zone_high": today_hi,
        "condition": cond,
        "conviction": conv,
        "position_pct": pos,
        "cumulative_pct": cum_today,
    })

    # Days 1–10 — use the same price ladder as Today (ST band or core zone). A raw ±2% envelope
    # around spot used to dip below the ST low, so "Watch only" looked like a better fill than
    # "Start small" on the row above (confusing).
    if align_buy_rows_to_core:
        days_lo = zone_core_lo if zone_core_lo is not None else today_lo
        days_hi = zone_core_hi if zone_core_hi is not None else today_hi
        days_cond = (
            f"Near-term chop — hold any starter; do not add until price is in {core_zone_fmt} "
            "or you get a clear regime-shift confirmation (same zone as Today / summary)."
        )
    else:
        days_lo = round(s_lo, 2) if s_lo else (round((current_price * 0.98), 2) if current_price else None)
        days_hi = round(s_hi, 2) if s_hi else (round((current_price * 1.02), 2) if current_price else None)
        days_cond = (
            "Near-term tape — keep Today’s starter only; wait for regime shift before scaling "
            "(same ST band as Today — not a separate ‘cheaper’ dip zone below it)."
        )
    buy_stages.append({
        "timeline_key": "days_1_10",
        "label": "Days 1–10",
        "when_to_act": "Watch only",
        "price_zone_low": days_lo,
        "price_zone_high": days_hi,
        "condition": days_cond,
        "conviction": "None",
        "position_pct": 0,
        "cumulative_pct": cum_days,
    })

    # Week 2–4 (short entry) — align zone to core ladder when extended (no separate ST band as entry).
    if align_buy_rows_to_core:
        w_pos = 0
        w_when = "Watch only"
        w_cond = f"Same preferred zone {core_zone_fmt} — wait for price into band (aligned with 3–6 mo row)."
        w_lo, w_hi = zone_core_lo, zone_core_hi
    else:
        w_pos = 25
        w_when = "Start small"
        w_cond = f"Price touches MA50 + ML crosses 25%"
        w_lo = round(s_lo, 2) if s_lo else None
        w_hi = round(s_hi, 2) if s_hi else None
    buy_stages.append({
        "timeline_key": "week_2_4",
        "label": "Week 2–4",
        "when_to_act": w_when,
        "price_zone_low": w_lo,
        "price_zone_high": w_hi,
        "condition": w_cond,
        "conviction": "None" if align_buy_rows_to_core else "Low-Medium",
        "position_pct": w_pos,
        "cumulative_pct": cum_week,
    })

    # 1–3 months (medium zone) — same core zone when aligning so entry bands do not disagree.
    if align_buy_rows_to_core:
        m13_lo, m13_hi = zone_core_lo, zone_core_hi
        m13_cond = (
            f"Adds when price reaches {core_zone_fmt} over this window (MA50/HMM context). "
            f"Same entry ladder as Today / Week 2–4 / 3–6 mo — not a different price story."
        )
    else:
        m13_lo = round(m_lo, 2) if m_lo else None
        m13_hi = round(m_hi, 2) if m_hi else None
        m13_cond = f"MA50 holds + HMM transitions + Pattern >50%"
    pos_13 = 35
    buy_stages.append({
        "timeline_key": "1_3_months",
        "label": "1–3 months",
        "when_to_act": "Add position",
        "price_zone_low": m13_lo,
        "price_zone_high": m13_hi,
        "condition": m13_cond,
        "conviction": "Medium",
        "position_pct": pos_13,
        "cumulative_pct": cum_13,
    })

    # 3–6 months (long-term core)
    pos_36 = 25
    buy_stages.append({
        "timeline_key": "3_6_months",
        "label": "3–6 months",
        "when_to_act": c6_when,
        "price_zone_low": c6_lo,
        "price_zone_high": c6_hi,
        "condition": c6_cond,
        "conviction": "High",
        "position_pct": pos_36,
        "cumulative_pct": cum_36,
    })

    # 6–12 months (T3 52w stress) — when early tranches were 0, complete 100% with a larger tail slice.
    pos_612 = 40 if align_buy_rows_to_core else 15
    tail_extra = (
        " Remaining slice completes the 100% plan after waiting for core zone (early rows were 0%)."
        if align_buy_rows_to_core
        else ""
    )
    tail_weekly_trigger = round((low_52w or current_price * 0.75) * 0.98, 2)
    buy_stages.append({
        "timeline_key": "6_12_months",
        "label": "6–12 months (tail risk)",
        "when_to_act": "Tail risk / black swan zone only",
        "price_zone_low": round(t3_lo, 2) if t3_lo else (round((low_52w or current_price * 0.75) * 1.05, 2) if low_52w else None),
        "price_zone_high": round(t3_hi, 2) if t3_hi else (round((low_52w or current_price * 0.75) * 1.15, 2) if low_52w else None),
        "condition": (
            f"Execution trigger: weekly close below ~${tail_weekly_trigger:,.2f} (52w stress) OR acute liquidity stress "
            f"(e.g. VIX spike + sustained breadth washout). Not a base-case dip-buy." + tail_extra
        ),
        "conviction": "Stress / rare",
        "position_pct": pos_612,
        "cumulative_pct": cum_612,
    })

    _roadmap_resolve_near_term_conflict(buy_stages)
    atr_for_notes = _safe_float(response.get("atr14"))
    if atr_for_notes is None or atr_for_notes <= 0:
        atr_for_notes = current_price * 0.02
    ext_ma200_pct = ((current_price / float(ma200)) - 1.0) * 100.0 if ma200 and ma200 > 0 else 0.0
    atr_pct_s = (atr_for_notes / current_price * 100.0) if current_price else 0.0
    tranche_policy = ((long_h.get("entry_tiers") or {}).get("tranche_policy")) or None
    _road_note_fn = None
    try:
        from signals.tranche_heuristic import (
            compute_long_horizon_tier_percentages,
            roadmap_allocation_note_for_timeline,
        )

        _road_note_fn = roadmap_allocation_note_for_timeline
        if tranche_policy is None:
            tranche_policy = compute_long_horizon_tier_percentages(
                current_price=float(current_price),
                ma200=float(ma200) if ma200 else None,
                atr=atr_for_notes,
                model_confidence_pct=float(model_confidence_pct) if model_confidence_pct is not None else None,
            )
    except Exception:
        tranche_policy = None
        _road_note_fn = None

    for s in buy_stages:
        tk = str(s.get("timeline_key") or "")
        s["risk_reward_context"] = _roadmap_buy_row_risk_reward(
            horizon_key=tk,
            zone_lo=s.get("price_zone_low"),
            zone_hi=s.get("price_zone_high"),
            current_price=float(current_price),
            fair_value=float(fair_value),
            ma50=ma50,
            ma200=ma200,
            stop_52w=float(stop_52w),
        )
        if tranche_policy and _road_note_fn:
            note = _road_note_fn(tk, tranche_policy)
            s["allocation_note"] = note or (
                f"Heuristic: {ext_ma200_pct:+.1f}% vs MA200; ATR/price {atr_pct_s:.1f}% — staged ladder."
            )
        elif model_confidence_pct is not None:
            s["allocation_note"] = (
                f"Tranche scale heuristic: model confidence {model_confidence_pct}%; "
                f"{ext_ma200_pct:+.1f}% vs MA200; ATR/price {atr_pct_s:.1f}%. "
                "Nearer support / lower vol → larger slice; extended / high vol → smaller starter."
            )
        else:
            s["allocation_note"] = (
                f"Heuristic: {ext_ma200_pct:+.1f}% vs MA200; ATR/price {atr_pct_s:.1f}% — "
                "staged ladder (not equal conviction in every row)."
            )

    # ── Sell roadmap stages ───────────────────────────────────────────────────
    sell_stages = []
    sell_stages.append({
        "timeline_key": "immediate",
        "label": "Immediate",
        "when_to_sell": "Hard stop",
        "price_zone_low": None,
        "price_zone_high": round(stop_52w, 2),
        "condition": "Weekly close below structural invalidation — thesis broken (price / technical)",
        "action": "Exit 100%",
        "reason": "Invalidation",
        "exit_category": "technical_structure",
    })
    near_high = round((high_52w or current_price * 1.1) * 0.98, 2) if high_52w else None
    high_val = round(high_52w, 2) if high_52w else None
    sell_stages.append({
        "timeline_key": "short_term",
        "label": "Short-term",
        "when_to_sell": "Trim",
        "price_zone_low": near_high,
        "price_zone_high": high_val,
        "condition": "Technical: near 52w high + RSI extended + weak volume confirmation",
        "action": "Trim 25%",
        "reason": "Extended, poor R/R",
        "exit_category": "technical_momentum",
    })
    fv_82 = round(fair_value * 0.82, 2)
    fv_88 = round(fair_value * 0.88, 2)
    sell_stages.append({
        "timeline_key": "1_3_months",
        "label": "1–3 months",
        "when_to_sell": "Partial exit",
        "price_zone_low": fv_82,
        "price_zone_high": round(fair_value * 0.85, 2),
        "condition": "Macro scenario: policy / Fed path hits your pre-defined trim band (tracked separately from pure price)",
        "action": "Trim 35%",
        "reason": "Scenario target reached",
        "exit_category": "macro_scenario",
    })
    sell_stages.append({
        "timeline_key": "3_6_months",
        "label": "3–6 months",
        "when_to_sell": "Major trim",
        "price_zone_low": round(fair_value * 0.87, 2),
        "price_zone_high": round(fair_value * 0.92, 2),
        "condition": "Valuation: price enters fair-value band — reduce into strength",
        "action": "Sell 50%",
        "reason": "Near fair value",
        "exit_category": "valuation_fair_value",
    })
    sell_stages.append({
        "timeline_key": "6_12_months",
        "label": "6–12 months",
        "when_to_sell": "Full target",
        "price_zone_low": round(fair_value * 0.93, 2),
        "price_zone_high": round(fair_value, 2),
        "condition": f"Valuation: approaches model fair value ${fair_value:.2f}",
        "action": "Sell 75–100%",
        "reason": "Fair value achieved",
        "exit_category": "valuation_fair_value",
    })
    sell_stages.append({
        "timeline_key": "anytime",
        "label": "Anytime",
        "when_to_sell": "Regime flip",
        "price_zone_low": None,
        "price_zone_high": None,
        "condition": "Model regime: HMM bear probability >80% after sustained bull read",
        "action": "Exit 50% immediately",
        "reason": "Regime invalidates thesis",
        "exit_category": "model_regime",
    })

    _apply_sell_roadmap_band_alignment(
        sell_stages,
        current_price=current_price,
        fair_value=fair_value,
        high_52w=high_52w,
        short_h=short,
        medium_h=medium,
        long_h=long_h,
        st_band=response.get("st_band") if isinstance(response.get("st_band"), dict) else None,
        mt_band=response.get("mt_band") if isinstance(response.get("mt_band"), dict) else None,
        lt_band=response.get("lt_band") if isinstance(response.get("lt_band"), dict) else None,
    )

    from signals.scenario_target import compute_initial_scenario_target, sync_medium_horizon_target

    scenario_target = compute_initial_scenario_target(medium, long_h, float(fair_value))
    atr_rm = _safe_float(response.get("atr14"))
    if atr_rm is None or atr_rm <= 0:
        atr_rm = current_price * 0.02
    w52_lo = float(low_52w) if low_52w is not None else current_price * 0.85
    w52_hi = float(high_52w) if high_52w is not None else current_price * 1.15
    ma50_f = float(ma50) if ma50 is not None else current_price
    ma200_f = float(ma200) if ma200 is not None else current_price

    try:
        from signals.roadmap_validator import apply_roadmap_consistency

        roadmap_validation = apply_roadmap_consistency(
            ticker,
            buy_stages,
            sell_stages,
            current_price=float(current_price),
            fair_value=float(fair_value),
            regime_bull_pct=float(regime_bull_pct),
            ma50=ma50_f,
            ma200=ma200_f,
            week52_low=w52_lo,
            week52_high=w52_hi,
            atr=float(atr_rm),
            scenario_target=float(scenario_target),
            apply_fixes=bool(roadmap_cfg.get("apply_auto_fixes", True)),
        )
        scenario_target = roadmap_validation["scenario_target"]
    except Exception:
        roadmap_validation = {
            "issues": [],
            "issues_before_fix": [],
            "fixes_applied": False,
            "roadmap_auto_adjusted": False,
            "scenario_target": round(scenario_target, 2),
            "scenario_target_aligned": True,
        }

    _patch_immediate_sell_stage_copy(sell_stages, low_52w)

    # Single source of truth: medium horizon target matches canonical scenario_target before any trader copy.
    try:
        st = float(scenario_target)
        if st > 0:
            sync_medium_horizon_target(horizons, st)
            medium = horizons.get("medium") or {}
    except Exception:
        pass

    signal_regime = None
    if roadmap_cfg.get("enable_signal_regime_on_detail", True) and close_series is not None and pd is not None:
        try:
            s = close_series.dropna()
            if len(s) >= 120:
                from signals.signal_inversion import (
                    classify_regime,
                    compute_hurst_exponent,
                    get_regime_weights,
                )

                h = compute_hurst_exponent(s)
                reg = classify_regime(h)
                w = get_regime_weights(reg)
                signal_regime = {
                    "hurst_exponent": round(h, 4),
                    "asset_regime": reg.value,
                    "regime_weights": w.as_dict(),
                    "acf_interpretation_style": interpretation_style or "TRENDING",
                    "precedence_note": regime_signal_precedence_note
                    or (
                        "Score bucket thresholds use score.interpretation (ACF) when enabled; "
                        "Hurst here is supplementary."
                    ),
                    "note": (
                        "Bucket inversion detection needs labeled backtest stats; "
                        "use POST /api/signal-diagnostics/{ticker} with bucket_stats, or "
                        "run run_inversion_diagnostic() in scripts."
                    ),
                }
        except Exception:
            signal_regime = None

    consistency_notes: list[str] = []
    for issue in roadmap_validation.get("issues") or []:
        if isinstance(issue, dict) and issue.get("severity") == "HIGH":
            consistency_notes.append(
                "Roadmap still reports HIGH-severity consistency checks after auto-fix; "
                "confirm price zones before trading."
            )
            break
    if (
        signal_regime
        and (interpretation_style or "").upper() == "TRENDING"
        and signal_regime.get("asset_regime") == "mean_reverting"
    ):
        consistency_notes.append(
            "ACF score interpretation is trending-style but Hurst classifies mean-reverting tape; "
            "threshold flips follow config score.interpretation, not Hurst alone."
        )

    nest_note = _sell_major_trim_inside_short_trim_note(sell_stages)
    if nest_note:
        consistency_notes.append(nest_note)

    # Trader-type one-liners — derived from the same Today-row logic as the buy roadmap (when/pos/align_buy_rows_to_core).
    short_stop = _safe_float(short.get("stop_loss"))
    short_tgt = _safe_float(short.get("target"))
    short_zone = f"${s_lo:.2f}–${s_hi:.2f}" if (s_lo and s_hi) else f"${current_price:.2f}"
    medium_zone = f"${m_lo:.2f}–${m_hi:.2f}" if (m_lo and m_hi) else "entry zone"
    ma50_str = f"${ma50:.2f}" if ma50 else "MA50"
    ma200_str = f"${ma200:.2f}" if ma200 else "MA200"
    full_by = (t1_hi or ma200 or current_price)
    exit_line = _long_horizon_structural_exit_phrase(sell_stages, low_52w)

    if display_verdict in ("REDUCE", "AVOID"):
        trader_summary_short = (
            f"No new buys today — model read {display_verdict} ({regime_label}). "
            f"Matches the Today row in the buy roadmap."
        ).strip()
    elif align_buy_rows_to_core:
        trader_summary_short = (
            f"Short-term ({ticker}): watch only — spot is extended above preferred adds at {core_zone_fmt} "
            f"(same as the Today row). Wait for pullback into that ladder; do not treat current print as the primary entry."
        ).strip()
    elif when == "Start small":
        parts_ts = [
            f"Short-term ({ticker}): Today row allows a starter ({pos}% tranche) in/near {short_zone} "
            f"(starter only — see Today condition). ",
        ]
        if short_stop and short_tgt:
            parts_ts.append(f"Stop ${short_stop:.2f}, target ${short_tgt:.2f}. ")
        if high_52w:
            parts_ts.append(f"Tactical trim consideration near 52w high ${high_52w:.2f}. ")
        trader_summary_short = "".join(parts_ts).strip()
    else:
        parts_tw = [
            f"Short-term ({ticker}): Today row is watch only — prefer pullback toward {short_zone} before sizing. ",
        ]
        if short_stop and short_tgt:
            parts_tw.append(f"If band is tested: stop ${short_stop:.2f}, target ${short_tgt:.2f}. ")
        trader_summary_short = "".join(parts_tw).strip()

    if align_buy_rows_to_core:
        trader_summary_medium = (
            f"Swing: same staged ladder as the table — adds concentrate on {core_zone_fmt} over the next weeks/months "
            f"(see 1–3 mo and 3–6 mo rows), not a separate medium-term price story."
        )
        if medium.get("target"):
            trader_summary_medium += f" Scenario target ~${_safe_float(medium.get('target')):.2f}."
        if medium.get("stop_loss"):
            trader_summary_medium += f" Stop context: ${_safe_float(medium.get('stop_loss')):.2f}."
        trader_summary_medium = trader_summary_medium.strip()
    else:
        trader_summary_medium = (
            f"Wait for MA50 test + regime stabilization. Build toward {medium_zone} per roadmap. "
            + (f"Target ${_safe_float(medium.get('target')):.2f} (scenario). " if medium.get("target") else "")
            + (f"Stop: ${_safe_float(medium.get('stop_loss')):.2f}." if medium.get("stop_loss") else "Stop: below MA50.")
        ).strip()

    # MA200 is support when price is above it; when below, it is overhead — do not frame as "accumulate toward" a higher level
    if ma200 and current_price < ma200 * 0.985:
        tier_txt = (
            f"MA200 tier ${t1_lo:.2f}–${t1_hi:.2f} is overhead until reclaim — not a zone to average up into from here. "
            if (t1_lo and t1_hi)
            else ""
        )
        trader_summary_long = (
            f"Investor: price is below MA200 ({ma200_str}) — overhead until reclaimed. "
            f"Stage adds near {ma50_str} and long-term tiers on weakness; {tier_txt}"
            f"Fair value ~${fair_value:.2f} over 12–18m. "
            + exit_line
        ).strip()
    elif align_buy_rows_to_core:
        trader_summary_long = (
            f"Investor: structural adds on pullbacks toward MA200 / core around {core_zone_fmt} — "
            f"aligned with the 3–6 mo row (full core ~${full_by:.2f} when the tier fills). "
            f"Fair value ~${fair_value:.2f} over 12–18m. "
            + exit_line
        ).strip()
    elif when == "Start small":
        trader_summary_long = (
            f"Investor: accumulate on pullbacks toward MA200 support ({ma200_str}). "
            f"Optional tactical starter in {short_zone} matches the Today row; larger core builds on planned dips. "
            f"Full core by ~${full_by:.2f} when tier fills. Fair value ~${fair_value:.2f} over 12–18m. "
            + exit_line
        ).strip()
    else:
        trader_summary_long = (
            f"Investor: accumulate on pullbacks toward MA200 support ({ma200_str}). Full core by ~${full_by:.2f} when tier fills. "
            + f"Fair value ~${fair_value:.2f} over 12–18m. "
            + exit_line
        ).strip()

    trader_summary_horizon_note = (
        "Each view emphasizes a different horizon; the buy roadmap table is the full staged plan. "
        "If a line here and a table row disagree, use the table row for that timeline."
    )

    atr_rm_layer = _safe_float(response.get("atr14"))
    if atr_rm_layer is None or atr_rm_layer <= 0:
        atr_rm_layer = current_price * 0.02
    market_regime_layer = _roadmap_market_regime_layer(
        vix=vix_cc,
        atr=atr_rm_layer,
        current_price=float(current_price),
        regime_bull_pct=regime_bull_pct,
    )
    scenario_outlook = _roadmap_scenario_probabilities(
        regime_bull_pct=regime_bull_pct,
        st_ml=float(st_ml) if st_ml is not None else 25.0,
        mt_ml=float(mt_ml) if mt_ml is not None else 25.0,
        lt_ml=float(lt_ml) if lt_ml is not None else 25.0,
        pattern_score=pattern_score,
        risk_off=bool(market_regime_layer.get("risk_off")),
        vix=market_regime_layer.get("vix"),
    )
    try:
        if ticker.upper() in MAJOR_INDEX_ETFS and ma200 and low_52w:
            key_inv = max(float(ma200) * 0.97, float(low_52w) * 0.97)
        else:
            key_inv = float(stop_52w)
    except (TypeError, ValueError):
        key_inv = float(stop_52w)

    dom_action = buy_stages[0].get("when_to_act") if buy_stages else None
    tldr = {
        "bias": (
            (
                "Constructive"
                if display_verdict in ("BUY", "STRONG BUY")
                else "Defensive"
                if display_verdict in ("REDUCE", "AVOID")
                else "Neutral / selective"
            )
            + f" · {regime_label}"
        ),
        "strategy": (
            "Wait for pullback into core / MA200 zones before scaling"
            if align_buy_rows_to_core
            else "Staged adds on planned dips (per rows below)"
        ),
        "key_level": round(key_inv, 2),
        "key_level_label": "Structural invalidation / support reference (see watch levels in confidence)",
        "model_confidence_pct": model_confidence_pct,
        "dominant_near_term_action": dom_action,
    }
    you_are_here = _roadmap_you_are_here(buy_stages, float(current_price))
    action_glossary = {
        "Start small": "Starter tranche only — first slice of your planned position (not full size).",
        "Watch only": "Do not add shares; observe. Any existing starter is held, not enlarged here.",
        "Patience — no new buy yet": "Subordinate row: defers to Today — hold only, no scale in the same band.",
        "Add position": "Scale toward your target allocation once this row’s conditions are met.",
        "Tail risk / black swan zone only": "Reserved slice for extreme stress — not ordinary dips.",
        "Do not buy": "Model verdict blocks new purchases in this zone.",
    }
    probabilistic_framing = (
        f"Illustrative scenario mix: Bull ~{scenario_outlook['bull_pct']:.0f}%, "
        f"Base ~{scenario_outlook['base_pct']:.0f}%, Bear ~{scenario_outlook['bear_pct']:.0f}% "
        f"({scenario_outlook.get('method', '')})."
    )

    return {
        "current_price": round(current_price, 2),
        "fair_value": round(fair_value, 2),
        "scenario_target": round(scenario_target, 2),
        "high_52w": round(high_52w, 2) if high_52w is not None else None,
        "low_52w": round(low_52w, 2) if low_52w is not None else None,
        "regime_label": regime_label,
        "display_verdict": display_verdict,
        "buy_roadmap": buy_stages,
        "sell_roadmap": sell_stages,
        "roadmap_validation": roadmap_validation,
        "signal_regime": signal_regime,
        "consistency_notes": consistency_notes,
        "score_interpretation_style": (interpretation_style or "TRENDING"),
        "score_interpretation_meta": interpretation_meta if isinstance(interpretation_meta, dict) else {},
        "trader_summary": {
            "short_term": trader_summary_short,
            "medium_term": trader_summary_medium,
            "long_term": trader_summary_long,
            "horizon_note": trader_summary_horizon_note,
        },
        "tldr": tldr,
        "you_are_here": you_are_here,
        "scenario_outlook": scenario_outlook,
        "market_regime_layer": market_regime_layer,
        "action_glossary": action_glossary,
        "probabilistic_framing": probabilistic_framing,
    }


def _hold_vs_trade_guidance(
    *,
    display_verdict: str,
    overall: str,
    regime_bull_pct: float | None,
) -> dict[str, str]:
    """
    Retail education: reconcile "take profits vs buy the dip" with "hold 5–10 years."
    Not personalized advice — dashboard copy only.
    """
    rb = float(regime_bull_pct) if regime_bull_pct is not None else 50.0

    long_term = (
        "For a 5–10 year plan, the usual approach is to stay invested through normal pullbacks "
        "when the business (or index) thesis is intact, and to add on planned dips — not to sell "
        "everything trying to time a lower re-entry. Taxes, whipsaw, and missing recovery days "
        "often hurt retail returns more than a simple hold-and-rebalance discipline."
    )
    short_term = (
        "For trading or 1–6 month horizons, taking profit near short and medium targets "
        "(and the sell roadmap stages) is appropriate — then redeploy in buy zones on the "
        "next pullback or rotate to a stronger name. The same holding can be split: a core long-term "
        "slice and a tactical trim slice with different rules."
    )

    if display_verdict in ("REDUCE", "AVOID"):
        bridge = (
            f"Today’s model read leans {display_verdict} (regime/ML vs valuation). "
            "That often means trim size or pause new buys, not necessarily abandoning a multi-year "
            "thesis — many investors reduce tactical exposure while keeping a smaller core."
        )
    elif overall in ("STRONG BUY", "BUY") and rb >= 50:
        bridge = (
            f"Today’s model is constructive ({overall}, bull regime ~{rb:.0f}%). "
            "Routine volatility alone is usually not a reason to exit a 5–10 year position; "
            "prefer rebalancing and adds on drawdowns toward your plan."
        )
    elif overall in ("WAIT", "WATCH"):
        bridge = (
            "Signals are mixed. Match action to time horizon: use trader and sell roadmap "
            "for trims, and long-term tiers plus fair value for adds — they answer different questions."
        )
    else:
        bridge = (
            "Use horizon cards as intended: short and medium for tactical entries and exits; "
            "long-term tiers for strategic allocation. This dashboard separates those on purpose."
        )

    return {
        "title": "Hold for years vs take profits — how to use this app",
        "long_term": long_term,
        "short_term": short_term,
        "signal_bridge": bridge,
        "disclaimer": "Educational only — not personalized financial advice.",
    }


def _build_one_answer_roadmaps(
    ticker: str,
    investor_out: dict,
    response: dict,
    current_price: float,
) -> tuple[dict, dict, dict]:
    """
    Build One Answer headline + Trader roadmap + Investor roadmap for retail.
    See RETAIL_ONE_ANSWER_DESIGN.md. All derived from existing investor_summary + response.
    """
    horizons = investor_out.get("horizons") or {}
    short = horizons.get("short") or {}
    medium = horizons.get("medium") or {}
    long_h = horizons.get("long") or {}
    fair_value = investor_out.get("fair_value") or current_price * 1.1
    overall = investor_out.get("overall_verdict") or "WATCH"

    display_verdict = (
        (response.get("short_suggestion") or response.get("medium_suggestion") or response.get("long_suggestion"))
        or ""
    ).strip().upper()
    if display_verdict not in ("REDUCE", "AVOID"):
        display_verdict = overall

    def _ez(d: dict) -> tuple[float | None, float | None]:
        ez = d.get("entry_zone") or {}
        return _safe_float(ez.get("low")), _safe_float(ez.get("high"))

    def _action_today(verdict: str, in_zone: bool) -> str:
        if verdict in ("REDUCE", "AVOID"):
            return "trim" if verdict == "REDUCE" else "no_new_position"
        if verdict in ("STRONG BUY", "BUY") and in_zone:
            return "enter_now"
        if verdict in ("STRONG BUY", "BUY"):
            return "wait_for_pullback"
        return "hold"

    # Short/medium entry zones and in-zone check (trader)
    s_lo, s_hi = _ez(short)
    m_lo, m_hi = _ez(medium)
    in_short = s_lo is not None and s_hi is not None and s_lo <= current_price <= s_hi
    in_medium = m_lo is not None and m_hi is not None and m_lo <= current_price <= m_hi
    in_zone = in_short or in_medium
    action_today = _action_today(display_verdict, in_zone)

    # Headline: one sentence
    verdict_label = display_verdict or overall
    stop_s = _safe_float(short.get("stop_loss"))
    tgt_s = _safe_float(short.get("target"))
    headline_parts = []
    if display_verdict in ("REDUCE", "AVOID"):
        headline_parts.append(f"{verdict_label}: Valuation may support entry but regime/ML say {verdict_label}.")
        if long_h:
            lt_tiers = (long_h.get("entry_tiers") or {}).get("tiers") or []
            if lt_tiers:
                t1 = lt_tiers[0]
                lo, hi = _safe_float(t1.get("low")), _safe_float(t1.get("high"))
                if lo is not None and hi is not None:
                    headline_parts.append(f" Trim into strength; add only below ${hi:.2f}.")
        subline = "Consider trimming; add only on pullback to long-term entry tiers."
    else:
        if action_today == "enter_now":
            z = f"${s_lo:.2f}–${s_hi:.2f}" if (s_lo and s_hi) else "current zone"
            headline_parts.append(f"{verdict_label}: Enter in the zone {z}.")
        elif action_today == "wait_for_pullback":
            z = f"${s_lo:.2f}–${s_hi:.2f}" if (s_lo and s_hi) else (f"${m_lo:.2f}–${m_hi:.2f}" if (m_lo and m_hi) else "entry zone")
            headline_parts.append(f"{verdict_label}: Wait for pullback. Buy at {z}.")
        else:
            headline_parts.append(f"{verdict_label}: Hold. No new position here.")
        if stop_s and tgt_s:
            headline_parts.append(f" Stop ${stop_s:.2f}, target ${tgt_s:.2f} (~1 mo).")
        subline = None
    headline = "".join(headline_parts).strip() or f"{verdict_label}: See trader/investor roadmaps below."

    regime_bull_pct = investor_out.get("regime_bull_pct")
    one_answer = {
        "headline": headline,
        "subline": subline if display_verdict in ("REDUCE", "AVOID") else None,
        "verdict": verdict_label,
        "action_today": action_today,
        "hold_vs_trade": _hold_vs_trade_guidance(
            display_verdict=verdict_label,
            overall=overall,
            regime_bull_pct=regime_bull_pct if isinstance(regime_bull_pct, (int, float)) else None,
        ),
    }

    # Trader roadmap (short + medium)
    short_entry = {"low": round(s_lo, 2), "high": round(s_hi, 2)} if (s_lo is not None and s_hi is not None) else None
    medium_entry = {"low": round(m_lo, 2), "high": round(m_hi, 2)} if (m_lo is not None and m_hi is not None) else None
    trader_roadmap = {
        "verdict": verdict_label,
        "action_today": action_today,
        "short": {
            "entry_zone": short_entry,
            "stop": round(stop_s, 2) if stop_s is not None else None,
            "target": round(tgt_s, 2) if tgt_s is not None else None,
            "target_pct": round(short.get("target_pct"), 1) if short.get("target_pct") is not None else None,
            "timeframe": "~1 month",
            "trigger": (short.get("trigger_buy") or "").strip() or "On pullback; ML confirmation.",
        },
        "medium": {
            "entry_zone": medium_entry,
            "stop": round(_safe_float(medium.get("stop_loss")), 2) if medium.get("stop_loss") is not None else None,
            "target": round(_safe_float(medium.get("target")), 2) if medium.get("target") is not None else None,
            "timeframe": "3–6 months",
            "trigger": (medium.get("trigger_buy") or "").strip() or "Add on dip to MA50.",
        },
    }

    # Investor roadmap (long tiers + fair value)
    add_tiers = []
    for t in (long_h.get("entry_tiers") or {}).get("tiers") or []:
        add_tiers.append({
            "id": t.get("id"),
            "label": t.get("label"),
            "low": _safe_float(t.get("low")),
            "high": _safe_float(t.get("high")),
            "allocation_pct": t.get("allocation_pct"),
        })
    investor_roadmap = {
        "verdict": overall,
        "action_today": "hold" if action_today in ("hold", "no_new_position", "trim") else ("add" if overall in ("STRONG BUY", "BUY") else "hold"),
        "add_tiers": add_tiers,
        "trim_near": round(fair_value, 2),
        "hold_thesis": (long_h.get("rationale") or long_h.get("trigger_buy") or "").strip()
        or f"Hold 6–18 mo toward fair value ${fair_value:.2f}; add on dips to entry tiers.",
    }

    return one_answer, trader_roadmap, investor_roadmap


def _seasonal_note(ticker: str) -> str | None:
    """Brief seasonal/events note - placeholder for future enhancement."""
    # Could add: earnings season patterns, sector rotation notes
    return None


# Fix 5: Earnings history (last 4Q actual vs estimate, beat/miss)
def _get_earnings_history(ticker: str) -> dict:
    """
    Last 4 quarters EPS: actual, estimate, beat/miss.
    Uses earnings_dates (current yfinance API) — quarterly_earnings and
    Ticker.earnings were deprecated and now return 401 from Yahoo Finance.
    """
    if ticker in _ETFS_SKIP_YAHOO_INFO:
        return {}
    try:
        import warnings
        import yfinance as yf
        t = yf.Ticker(ticker)

        # earnings_dates: index=datetime, cols=['EPS Estimate','Reported EPS','Surprise(%)']
        # Only past rows (Reported EPS not NaN) are actual quarters.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # suppress yfinance deprecation noise
            ed = getattr(t, "earnings_dates", None)

        if ed is None or (hasattr(ed, "empty") and ed.empty):
            return {}

        import pandas as pd
        # Keep only past quarters that have a reported EPS
        reported_col = next((c for c in ed.columns if "reported" in c.lower()), None)
        estimate_col = next((c for c in ed.columns if "estimate" in c.lower()), None)
        surprise_col = next((c for c in ed.columns if "surprise" in c.lower()), None)

        if reported_col is None:
            return {}

        past = ed[ed[reported_col].notna()].head(4)
        if past.empty:
            return {}

        history = []
        for dt, row in past.iterrows():
            actual   = _safe_float(row.get(reported_col))
            estimate = _safe_float(row.get(estimate_col)) if estimate_col else None
            surprise = _safe_float(row.get(surprise_col)) if surprise_col else None

            if actual is not None and estimate is not None and estimate != 0:
                beat_pct = surprise if surprise is not None else round(
                    (actual - estimate) / abs(estimate) * 100, 1
                )
                status = "Beat" if (beat_pct or 0) > 0 else "Missed"
            else:
                beat_pct, status = None, "N/A"

            # Format date as "Q1 2025" style when possible
            try:
                quarter_label = pd.Timestamp(dt).strftime("%b %Y")
            except Exception:
                quarter_label = str(dt)[:10]

            history.append({
                "quarter":  quarter_label,
                "actual":   round(actual, 2) if actual is not None else None,
                "estimate": round(estimate, 2) if estimate is not None else None,
                "beat_pct": round(beat_pct, 1) if beat_pct is not None else None,
                "status":   status,
            })

        beats = [h for h in history if h["status"] == "Beat"]
        beat_rate = round(len(beats) / len(history) * 100) if history else 0
        return {
            "history":   history,
            "beat_rate": beat_rate,
            "summary":   f"Beat estimates {len(beats)}/{len(history)} of last quarters ({beat_rate}%)",
        }
    except Exception:
        return {}


def _safe_float(v) -> float | None:
    """Return float or None; handles NaN/None/strings gracefully."""
    try:
        import math
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _immediate_stop_floor_from_52w(low_52w: float | None) -> float | None:
    """~3% cushion under raw 52w low — matches initial stop_52w before horizon max()."""
    if low_52w is None:
        return None
    return round(float(low_52w) * 0.97, 2)


def _patch_immediate_sell_stage_copy(sell_stages: list[dict], low_52w: float | None) -> None:
    """
    Immediate row may be raised to short-horizon stop (max vs 52w-based floor).
    Condition text must match that price; do not say only '52w low' when horizon binds.
    """
    if not sell_stages or sell_stages[0].get("timeline_key") != "immediate":
        return
    s0 = sell_stages[0]
    hi = _safe_float(s0.get("price_zone_high"))
    lo = _safe_float(s0.get("price_zone_low"))
    if hi is None:
        return
    floor_52 = _immediate_stop_floor_from_52w(low_52w)
    tol = max(1.0, 0.005 * hi)
    if floor_52 is not None and hi > floor_52 + tol and low_52w is not None:
        s0["condition"] = (
            f"Closes below ~${hi:.2f} — nearer-term invalidation (horizon stop; "
            f"52w low ${float(low_52w):.2f} is farther down)"
        )
        return
    if low_52w is not None:
        if lo is not None and abs(lo - hi) > 0.02:
            band = f"${lo:.2f}–${hi:.2f}"
        else:
            band = f"~${hi:.2f}"
        s0["condition"] = (
            f"Closes below {band} (~3% cushion under 52w low ${float(low_52w):.2f}) — thesis dead"
        )


def _long_horizon_structural_exit_phrase(sell_stages: list[dict], low_52w: float | None) -> str:
    """One line for trader_summary long_term: matches Immediate sell row after alignment + validator."""
    if not sell_stages or sell_stages[0].get("timeline_key") != "immediate":
        return (
            f"Only exit if 52w low ${float(low_52w):.2f} breaks."
            if low_52w is not None
            else "Only exit on thesis break."
        )
    s0 = sell_stages[0]
    hi = _safe_float(s0.get("price_zone_high"))
    lo = _safe_float(s0.get("price_zone_low"))
    if hi is None:
        return (
            f"Only exit if 52w low ${float(low_52w):.2f} breaks."
            if low_52w is not None
            else "Only exit on thesis break."
        )
    floor_52 = _immediate_stop_floor_from_52w(low_52w)
    tol = max(1.0, 0.005 * hi)
    if lo is not None and abs(lo - hi) > 0.02:
        zone = f"${lo:.2f}–${hi:.2f}"
    else:
        zone = f"~${hi:.2f}"
    if floor_52 is not None and hi > floor_52 + tol and low_52w is not None:
        return (
            f"Only exit long-term thesis if spot closes below {zone} "
            f"(nearer-term invalidation; 52w low ${float(low_52w):.2f} is farther support)."
        )
    if low_52w is not None:
        return (
            f"Only exit long-term thesis if spot closes below {zone} "
            f"(~3% cushion under 52w low ${float(low_52w):.2f})."
        )
    return f"Only exit long-term thesis if spot closes below {zone}."


def _band_edges(b: dict | None) -> tuple[float | None, float | None]:
    if not isinstance(b, dict):
        return None, None
    return _safe_float(b.get("low")), _safe_float(b.get("high"))


def _sell_roadmap_config() -> dict[str, float]:
    """Defaults merged with config retail.sell_roadmap (see config.yaml)."""
    defaults: dict[str, float] = {
        "pad_min_pct_of_spot": 0.01,
        "pad_floor": 0.05,
        "short_no_52w_cap_mult": 1.15,
        "short_target_hi_mult": 1.04,
        "short_st_hi_mult": 0.995,
        "short_target_lo_mult": 0.97,
        "st_fallback_band_lo_mult": 0.96,
        "st_fallback_52w_mult": 0.97,
        "medium_lo_mult": 0.91,
        "medium_hi_mult": 0.995,
        "medium_mt_hi_mult": 0.92,
        "medium_mt_cap_mult": 1.06,
        "major_medium_lo_mult": 0.98,
        "major_fv_low_mult": 0.82,
        "major_fv_hi_mult": 0.92,
        "full_long_lo_mult": 0.93,
        "full_fv_lo_mult": 0.93,
    }
    try:
        from config_loader import load_config
        raw = (load_config().get("retail") or {}).get("sell_roadmap")
        if not isinstance(raw, dict):
            return defaults
        for k, v in raw.items():
            if k in defaults and v is not None:
                try:
                    defaults[k] = float(v)
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    return defaults


def _sell_major_trim_inside_short_trim_note(sell_stages: list) -> str | None:
    """
    When the 3–6 month trim band lies inside the short-term trim window (targets can align that way),
    explain that later legs size remaining position — not a separate gate that only fires if ST was skipped.
    """
    if len(sell_stages) < 4:
        return None
    try:
        st = sell_stages[1]
        mj = sell_stages[3]
        sl, sh = st.get("price_zone_low"), st.get("price_zone_high")
        ml, mh = mj.get("price_zone_low"), mj.get("price_zone_high")
        if None in (sl, sh, ml, mh):
            return None
        slf, shf = float(sl), float(sh)
        mlf, mhf = float(ml), float(mh)
        if mlf >= slf and mhf <= shf:
            return (
                "Sell roadmap: the 3–6 month trim band can sit inside the short-term trim window when targets align — "
                "later rows apply to size remaining after earlier trims (or a larger move through the band), "
                "not a separate trigger that only runs if you skipped the short-term leg."
            )
    except (TypeError, ValueError):
        return None
    return None


def _apply_sell_roadmap_band_alignment(
    sell_stages: list[dict],
    *,
    current_price: float,
    fair_value: float,
    high_52w: float | None,
    short_h: dict,
    medium_h: dict,
    long_h: dict,
    st_band: dict | None,
    mt_band: dict | None,
    lt_band: dict | None,
) -> None:
    """
    Align sell roadmap price zones with horizon targets/stops and ST/MT/LT model bands.
    Buy roadmap already uses horizon entry zones; sell side previously used only 52w + FV multiples.
    Mutates sell_stages in place (indices: 0 hard stop, 1 short trim, 2 partial, 3 major, 4 full).
    """
    if len(sell_stages) < 5 or current_price <= 0:
        return

    short_stop = _safe_float(short_h.get("stop_loss"))
    short_tgt = _safe_float(short_h.get("target"))
    medium_tgt = _safe_float(medium_h.get("target"))
    long_tgt = _safe_float(long_h.get("target")) or (fair_value if fair_value > 0 else None)

    _st_lo, st_hi = _band_edges(st_band)
    _mt_lo, mt_hi = _band_edges(mt_band)
    _lt_lo, lt_hi = _band_edges(lt_band)

    if not short_stop and not short_tgt and not medium_tgt and not st_hi and not mt_hi and not lt_hi:
        return

    cfg = _sell_roadmap_config()
    pad = max(cfg["pad_min_pct_of_spot"] * current_price, cfg["pad_floor"])

    # 0 — Hard stop: stricter (higher) invalidation when short horizon stop is tighter than 52w-based
    if sell_stages[0].get("price_zone_high") is not None and short_stop:
        try:
            ph = float(sell_stages[0]["price_zone_high"])
            sell_stages[0]["price_zone_high"] = round(max(ph, short_stop), 2)
            c = sell_stages[0].get("condition") or ""
            if "horizon" not in c.lower():
                sell_stages[0]["condition"] = c + " — max(52w-based, short-term horizon stop)"
        except (TypeError, ValueError):
            pass

    # 1 — Short-term trim: horizon target + optional ST band / 52w cap
    if short_tgt:
        cap = high_52w if high_52w else short_tgt * cfg["short_no_52w_cap_mult"]
        hi = min(cap, short_tgt * cfg["short_target_hi_mult"])
        if st_hi:
            hi = min(cap, max(hi, st_hi * cfg["short_st_hi_mult"]))
        lo = short_tgt * cfg["short_target_lo_mult"]
        if lo >= hi - 1e-6:
            lo = hi - pad * 2
        sell_stages[1]["price_zone_low"] = round(max(lo, current_price * 0.5), 2)
        sell_stages[1]["price_zone_high"] = round(max(hi, float(sell_stages[1]["price_zone_low"]) + pad), 2)
        c = sell_stages[1].get("condition") or ""
        if "horizon" not in c.lower():
            sell_stages[1]["condition"] = c + " — short-term target + ST band"
    elif st_hi and high_52w:
        sell_stages[1]["price_zone_low"] = round(
            min(st_hi * cfg["st_fallback_band_lo_mult"], high_52w * cfg["st_fallback_52w_mult"]), 2
        )
        sell_stages[1]["price_zone_high"] = round(high_52w, 2)
        sell_stages[1]["condition"] = (sell_stages[1].get("condition") or "") + " — ST band / 52w"

    # 2 — 1–3 months partial: medium horizon target + MT band
    if medium_tgt:
        lo = medium_tgt * cfg["medium_lo_mult"]
        hi = medium_tgt * cfg["medium_hi_mult"]
        if mt_hi:
            hi = min(max(hi, mt_hi * cfg["medium_mt_hi_mult"]), medium_tgt * cfg["medium_mt_cap_mult"])
        if hi <= lo:
            hi = lo + pad * 2
        sell_stages[2]["price_zone_low"] = round(lo, 2)
        sell_stages[2]["price_zone_high"] = round(hi, 2)
        c = sell_stages[2].get("condition") or ""
        if "horizon" not in c.lower():
            sell_stages[2]["condition"] = c + " — medium-term target + MT band"

    # 3 — 3–6 months: between medium scenario and fair value
    if medium_tgt and fair_value > 0:
        lo = max(medium_tgt * cfg["major_medium_lo_mult"], fair_value * cfg["major_fv_low_mult"])
        hi = fair_value * cfg["major_fv_hi_mult"]
        if hi <= lo:
            hi = lo + pad * 3
        sell_stages[3]["price_zone_low"] = round(lo, 2)
        sell_stages[3]["price_zone_high"] = round(hi, 2)
        sell_stages[3]["condition"] = (sell_stages[3].get("condition") or "") + " — medium→FV ladder"

    # 4 — Full target: long horizon / LT band high
    if fair_value > 0 and long_tgt:
        fv_cap = min(fair_value, lt_hi) if lt_hi else fair_value
        lo = max(long_tgt * cfg["full_long_lo_mult"], fair_value * cfg["full_fv_lo_mult"])
        sell_stages[4]["price_zone_low"] = round(lo, 2)
        sell_stages[4]["price_zone_high"] = round(max(fv_cap, lo + pad), 2)
        c = sell_stages[4].get("condition") or ""
        if "horizon" not in c.lower():
            sell_stages[4]["condition"] = c + " — fair value / LT band"

    # Profit-taking ladder: each stage floor should not sit below the prior stage ceiling
    prev_hi: float | None = None
    for i in (1, 2, 3, 4):
        lo = sell_stages[i].get("price_zone_low")
        hi = sell_stages[i].get("price_zone_high")
        if lo is None or hi is None:
            continue
        try:
            lo_f, hi_f = float(lo), float(hi)
        except (TypeError, ValueError):
            continue
        if prev_hi is not None and lo_f < prev_hi:
            lo_f = prev_hi + pad
            sell_stages[i]["price_zone_low"] = round(lo_f, 2)
        if lo_f >= hi_f:
            hi_f = lo_f + pad * 2
            sell_stages[i]["price_zone_high"] = round(hi_f, 2)
        prev_hi = float(sell_stages[i]["price_zone_high"])


# Fix 5: Sector-specific metrics (AUM for financials, etc.)
_FINANCIAL_TICKERS = frozenset(
    {"BLK", "GS", "MS", "JPM", "BAC", "WFC", "BX", "APO", "KKR", "CG", "ARES", "SCHW", "C"}
)


def _get_sector_specific_metrics(ticker: str, sector: str | None) -> dict:
    """AUM-style and financial metrics for financials; tech metrics for tech."""
    sym = (ticker or "").upper().split("-")[0]
    if sym in _ETFS_SKIP_YAHOO_INFO:
        return {}
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        out = {}
        sector = (sector or "").lower()
        if sym in _FINANCIAL_TICKERS or "financial" in sector:
            aum = info.get("totalAssets") or info.get("enterpriseValue")
            if aum is not None:
                try:
                    aum_b = round(float(aum) / 1e9, 1)
                    out["aum_billions"] = aum_b
                    out["aum_formatted"] = f"${aum_b:.1f}B"
                except (TypeError, ValueError):
                    pass
            if info.get("priceToBook") is not None:
                try:
                    out["price_to_book"] = round(float(info["priceToBook"]), 2)
                except (TypeError, ValueError):
                    pass
            if info.get("returnOnEquity") is not None:
                try:
                    out["roe_pct"] = round(float(info["returnOnEquity"]) * 100, 1)
                except (TypeError, ValueError):
                    pass
            if info.get("profitMargins") is not None:
                try:
                    out["net_margin_pct"] = round(float(info["profitMargins"]) * 100, 1)
                except (TypeError, ValueError):
                    pass
        if "technology" in sector or "tech" in sector:
            if info.get("priceToSalesTrailing12Months") is not None:
                try:
                    out["ps_ratio"] = round(float(info["priceToSalesTrailing12Months"]), 2)
                except (TypeError, ValueError):
                    pass
            if info.get("grossMargins") is not None:
                try:
                    out["gross_margins_pct"] = round(float(info["grossMargins"]) * 100, 1)
                except (TypeError, ValueError):
                    pass
        return out
    except Exception:
        return {}


# Fix 5: Rate sensitivity (correlation with TLT) for financials
def _get_rate_sensitivity(ticker: str, close_ticker: pd.Series | None) -> dict:
    """Correlation of ticker returns with TLT (rates proxy). Important for BLK, financials."""
    if close_ticker is None or len(close_ticker) < 60 or ticker in _ETFS_SKIP_YAHOO_INFO:
        return {}
    try:
        import yfinance as yf
        import time
        t = yf.Ticker(ticker)
        ticker_monthly = close_ticker.resample("ME").last().pct_change().dropna()
        time.sleep(0.3)
        tlt = yf.Ticker("TLT")
        tlt_hist = tlt.history(period="2y")
        if tlt_hist is None or tlt_hist.empty or "Close" not in tlt_hist.columns:
            return {}
        tlt_monthly = tlt_hist["Close"].resample("ME").last().pct_change().dropna()
        aligned = pd.concat([ticker_monthly, tlt_monthly], axis=1, join="inner").dropna()
        aligned.columns = ["ticker", "tlt"]
        if len(aligned) < 12:
            return {}
        corr = float(aligned.corr().iloc[0, 1])
        if corr > 0.4:
            interpretation = "Highly rate-sensitive (falls when rates rise)"
        elif corr > 0.2:
            interpretation = "Moderately rate-sensitive"
        elif corr > -0.2:
            interpretation = "Rate neutral"
        elif corr > -0.4:
            interpretation = "Benefits from rising rates"
        else:
            interpretation = "Strong beneficiary of rising rates"
        return {
            "correlation_with_tlt": round(corr, 3),
            "interpretation": interpretation,
            "note": "TLT = 20yr Treasury ETF. Positive correlation = rate-sensitive.",
        }
    except Exception:
        return {}


def _get_fmp_data(ticker: str, config: dict, current_price: float | None, signal_data: dict, close, range_low: float | None = None, range_high: float | None = None, long_horizon_risk: dict | None = None) -> dict:
    """FMP price target, insider stats, ST/MT/LT target bands. Uses Redis cache."""
    out = {}
    try:
        from signals.fmp_client import (
            fetch_price_target_consensus,
            fetch_analyst_estimates,
            fetch_insider_stats,
            get_api_key,
        )
        from signals.cache import (
            cached_price_target_consensus,
            cached_financial_estimates,
            cached_insider_stats,
        )
        from signals.target_bands import add_target_bands, compute_vol_6m, compute_swing_high_low
        if not get_api_key(config):
            return out

        cons = cached_price_target_consensus(ticker, lambda: fetch_price_target_consensus(config, ticker))
        eps_data = cached_financial_estimates(ticker, lambda: fetch_analyst_estimates(config, ticker))
        insider = cached_insider_stats(ticker, lambda: fetch_insider_stats(config, ticker))

        consensus_median = None
        if cons and isinstance(cons, dict):
            out["cons_low"] = cons.get("low") or cons.get("priceWhenPosted") or cons.get("adjLow")
            out["cons_high"] = cons.get("high") or cons.get("adjHigh") or cons.get("consensus") or cons.get("median")
            consensus_median = (
                cons.get("median")
                or cons.get("consensus")
                or cons.get("targetConsensus")
                or cons.get("medianPriceTarget")
            )
            if consensus_median is not None:
                try:
                    out["consensus_median"] = round(float(consensus_median), 2)
                except (TypeError, ValueError):
                    pass

        eps_fwd = None
        eps_dispersion = None
        if eps_data and isinstance(eps_data, dict):
            eps_fwd = eps_data.get("eps_fwd") or eps_data.get("eps") or eps_data.get("epsEstimate")
            eps_dispersion = eps_data.get("eps_dispersion")
        out["eps_fwd"] = eps_fwd
        if eps_dispersion is not None:
            out["eps_dispersion"] = eps_dispersion

        if insider and isinstance(insider, dict):
            out["insider_stats"] = insider

        if current_price is not None and close is not None and len(close) >= 20:
            vol_6m = compute_vol_6m(close)
            swing_high, swing_low = compute_swing_high_low(close, 20)
            comp = signal_data.get("composite_buy")
            regime = "NEUTRAL"
            if comp is not None:
                regime = "UP" if comp >= 60 else ("DOWN" if comp <= 40 else "NEUTRAL")
            if long_horizon_risk:
                out["long_horizon_risk"] = long_horizon_risk
            band_ev_m = 1.0
            band_ev_note = None
            try:
                from signals.band_context import macro_event_band_context
                from signals.cache import cached_economic_calendar
                from signals.fmp_client import fetch_economic_calendar

                def _cal():
                    ev, _ = fetch_economic_calendar(config, 14)
                    return ev or []

                ctx = macro_event_band_context(cached_economic_calendar(14, _cal))
                band_ev_m = float(ctx.get("multiplier") or 1.0)
                band_ev_note = ctx.get("note")
            except Exception:
                pass

            daily_move_pct = None
            if close is not None and len(close) >= 2:
                try:
                    c0, c1 = float(close.iloc[-2]), float(close.iloc[-1])
                    if c0 > 0:
                        daily_move_pct = round(100.0 * (c1 - c0) / c0, 4)
                except Exception:
                    pass

            row = {
                "ticker": ticker,
                "price": current_price,
                "close": current_price,
                "daily_move_pct": daily_move_pct,
                "ma20": signal_data.get("ma20"),
                "regime": regime,
                "vol_6m": vol_6m or 0.3,
                "short_suggestion": signal_data.get("short_suggestion"),
                "atr14": None,
                "swing_high_20d": swing_high,
                "swing_low_20d": swing_low,
                "eps_fwd": eps_fwd,
                "eps_dispersion": eps_dispersion,
                "consensus_median": consensus_median,
                "fair_pe_low": 18,
                "fair_pe_high": 25,
                "cons_low": out.get("cons_low"),
                "cons_high": out.get("cons_high"),
                "range_52w_low": range_low,
                "range_52w_high": range_high,
                "stress_bear_pct": (long_horizon_risk or {}).get("stress_bear_pct"),
                "band_event_multiplier": band_ev_m,
                "band_event_note": band_ev_note,
            }
            # Proper daily ATR(14) (True Range) for target bands
            try:
                from signals.fetcher import fetch_ohlcv_dataframe
                from signals.volatility import atr14_from_ohlcv_df
                ohlcv_df = fetch_ohlcv_dataframe(ticker, "6mo")
                row["atr14"] = atr14_from_ohlcv_df(ohlcv_df)
            except Exception:
                row["atr14"] = None
            if row.get("atr14") is None and len(close) >= 15:
                # Fallback proxy (older behaviour): 14d std of daily returns * current price
                returns = close.pct_change().dropna().iloc[-14:]
                if len(returns) >= 10:
                    vol = float(returns.std())
                    if vol > 0:
                        row["atr14"] = round(float(vol * close.iloc[-1]), 2)
            add_target_bands(row)
            out["st_band"] = row.get("st_band")
            out["mt_band"] = row.get("mt_band")
            out["lt_band"] = row.get("lt_band")
            out["atr14"] = row.get("atr14")
            out["lt_band_low_confidence"] = row.get("lt_band_low_confidence")
            out["st_checkpoints"] = row.get("st_checkpoints")
            out["mt_checkpoints"] = row.get("mt_checkpoints")
            out["lt_checkpoints"] = row.get("lt_checkpoints")
            out["lt_scenarios"] = row.get("lt_scenarios")
            out["st_level_hit"] = row.get("st_level_hit")
            out["st_target_confidence_pct"] = row.get("st_target_confidence_pct")
            out["mt_target_confidence_pct"] = row.get("mt_target_confidence_pct")
            out["band_event_note"] = row.get("band_event_note")
            out["lt_band_dispersion_note"] = row.get("lt_band_dispersion_note")

        # Street vs model: compare LT band to analyst consensus
        sl = out.get("cons_low")
        sh = out.get("cons_high")
        lt = out.get("lt_band")
        if sl is not None and sh is not None and lt and isinstance(lt, dict):
            try:
                sl, sh = float(sl), float(sh)
                ml, mh = float(lt.get("low", 0)), float(lt.get("high", 0))
                if sl > 0 and sh > 0 and ml > 0 and mh > 0:
                    out["street_vs_model"] = {
                        "street_low": round(sl, 2),
                        "street_high": round(sh, 2),
                        "model_lt_low": round(ml, 2),
                        "model_lt_high": round(mh, 2),
                        "delta_low_pct": round(100 * (ml - sl) / sl, 1),
                        "delta_high_pct": round(100 * (mh - sh) / sh, 1),
                        "model_more_bullish": mh > sh,
                        "divergence_pct": max(abs(100 * (ml - sl) / sl), abs(100 * (mh - sh) / sh)) if sl and sh else None,
                    }
            except (TypeError, ValueError, ZeroDivisionError):
                pass
    except Exception:
        pass
    return out


# Yahoo returns 404 "No fundamentals data found" for ETFs; skip .info for these
_ETFS_SKIP_YAHOO_INFO = frozenset({"SPY", "QQQ", "GLD", "SLV", "DIA", "IWM", "XLF", "XLK", "XLE", "XLV", "XLP", "XLY", "XLI", "XLB", "XLU"})

# Gold ETFs: ~0% dividend; ticker-aware explanation
_GOLD_ETFS = frozenset({"GLD", "IAU", "SGOL", "GLDM", "BAR", "OUNZ"})


def _get_extra_info(ticker: str, config: dict | None = None) -> dict:
    """Company name, beta, dividend yield, 52w high/low. Prefers FMP profile when config has fmp_api_key; 52w from yfinance. Skips ETFs to avoid Yahoo 404."""
    sym = (ticker or "").upper().split("-")[0]
    if sym in _ETFS_SKIP_YAHOO_INFO:
        return {}
    out = {}
    config = config or {}
    api_key = config.get("data", {}).get("fmp_api_key") or config.get("fmp_api_key")
    if api_key:
        try:
            from signals.fmp_client import fetch_profile
            profile, err = fetch_profile(config, ticker)
            if not err and profile and isinstance(profile, dict):
                name = (profile.get("companyName") or profile.get("symbol") or "").strip()
                if name:
                    out["company_name"] = name
                beta = profile.get("beta")
                if beta is not None:
                    try:
                        out["beta"] = round(float(beta), 2)
                    except (TypeError, ValueError):
                        pass
                dy = profile.get("dividendYield")
                if dy is not None:
                    try:
                        dy_f = float(dy)
                        if dy_f > 0:
                            yield_pct = dy_f * 100 if dy_f <= 1 else dy_f
                            if 0 <= yield_pct <= 15:
                                out["dividend_yield"] = round(yield_pct, 2)
                            else:
                                out["dividend_yield_error"] = "yield_out_of_range"
                                out["dividend_yield"] = None
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        if not out.get("company_name"):
            name = (info.get("longName") or info.get("shortName") or "").strip()
            if name:
                out["company_name"] = name
        if "beta" not in out:
            beta = info.get("beta")
            if beta is not None:
                try:
                    out["beta"] = round(float(beta), 2)
                except (TypeError, ValueError):
                    pass
        if "dividend_yield" not in out and "dividend_yield_error" not in out:
            dy = info.get("dividendYield") or info.get("yield")
            if dy is not None:
                try:
                    dy_f = float(dy)
                    if dy_f > 0:
                        yield_pct = dy_f * 100 if dy_f <= 1 else dy_f
                        if yield_pct < 0 or yield_pct > 15:
                            out["dividend_yield_error"] = "yield_out_of_range"
                            out["dividend_yield"] = None
                        else:
                            out["dividend_yield"] = round(yield_pct, 2)
                except (TypeError, ValueError):
                    pass
        for k, v in [("fiftyTwoWeekHigh", "high_52w"), ("fiftyTwoWeekLow", "low_52w")]:
            if v not in out:
                val = info.get(k)
                if val is not None:
                    try:
                        out[v] = round(float(val), 2)
                    except (TypeError, ValueError):
                        pass
        return out
    except Exception:
        return out if out else {}
