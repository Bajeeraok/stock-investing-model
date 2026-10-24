"""
Compare our indicators (close, RSI, MA, MACD, bias) vs Yahoo, Alpha Vantage, Polygon, Finnhub.
Computes margin of error and returns results for dashboard display.
Config: data.alpha_vantage_api_key, data.polygon_api_key, data.finnhub_apikey
"""
from __future__ import annotations

import logging
from typing import Any

from .alpha_vantage_client import fetch_global_quote, fetch_rsi, fetch_sma, fetch_macd
from .finnhub_client import fetch_quote, fetch_recommendation
from .polygon_client import fetch_last_close

logger = logging.getLogger(__name__)

_COMPARE_TICKERS = ["SPY", "QQQ", "GLD", "SLV"]

# Alpha Vantage free tier = 5 requests/min. We only call AV for the first ticker (SPY)
# so one dashboard load uses 5 calls (quote + RSI + SMA20 + SMA50 + MACD) and stays under limit.
_ALPHA_VANTAGE_TICKER_ONLY = _COMPARE_TICKERS[0]  # "SPY"


def _yahoo_last_close(ticker: str) -> float | None:
    """Last close from Yahoo (yfinance) for comparison. Uses OHLCV download only to avoid 404 on ETFs (SPY/QQQ/GLD/SLV have no fundamentals)."""
    try:
        from .fetcher import fetch_ohlcv_safe
        close_series = fetch_ohlcv_safe(ticker, period="5d")
        if close_series is not None and len(close_series) > 0:
            return float(close_series.iloc[-1])
    except Exception as e:
        logger.debug("Yahoo close for %s: %s", ticker, e)
    return None


def run_indicator_comparison(
    config: dict,
    our_signals_by_ticker: dict[str, dict[str, Any]],
    next_day_outlook: list[dict[str, Any]] | None = None,
    tickers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Compare our close, RSI, MA20, MA50, MACD hist, and bias to Yahoo, AV, Polygon, Finnhub.
    our_signals_by_ticker: ticker -> { close, rsi, ma20?, ma50?, macd_hist? } (from run_signals).
    next_day_outlook: list of { ticker, bias } for bias comparison.
    Returns list of { ticker, close, rsi, ma, macd, bias } with comparisons and margins.
    """
    syms = tickers or _COMPARE_TICKERS
    our_bias_by_ticker = {}
    if next_day_outlook:
        for o in next_day_outlook:
            if isinstance(o, dict) and o.get("ticker"):
                our_bias_by_ticker[o["ticker"]] = o.get("bias")

    out = []
    for t in syms:
        our = our_signals_by_ticker.get(t) or {}
        our_close = our.get("close")
        our_rsi = our.get("rsi")
        our_ma20 = our.get("ma20")
        our_ma50 = our.get("ma50")
        our_macd_hist = our.get("macd_hist")
        our_bias = our_bias_by_ticker.get(t)

        # Close: Yahoo, Alpha Vantage (SPY only to stay under 5 req/min), Polygon, Finnhub
        close_comp = []
        if our_close is not None and float(our_close) > 0:
            def _av_quote():
                return fetch_global_quote(config, t) if t == _ALPHA_VANTAGE_TICKER_ONLY else None
            for name, fetch_fn in [
                ("Yahoo", lambda: _yahoo_last_close(t)),
                ("Alpha Vantage", _av_quote),
                ("Polygon", lambda: fetch_last_close(config, t)),
                ("Finnhub", lambda: fetch_quote(config, t)),
            ]:
                try:
                    val = fetch_fn()
                except Exception:
                    val = None
                if val is not None:
                    try:
                        # Fixed: Added validation to prevent ZeroDivisionError
                        if float(our_close) > 0:
                            margin_pct = round(abs(float(our_close) - float(val)) / float(our_close) * 100, 4)
                        else:
                            margin_pct = None
                    except (TypeError, ValueError, ZeroDivisionError):
                        margin_pct = None
                    close_comp.append({"source": name, "value": round(float(val), 4), "margin_pct": margin_pct})
        max_margin_pct = max((c["margin_pct"] for c in close_comp if c.get("margin_pct") is not None), default=None)

        # RSI: Alpha Vantage (SPY only – free tier 5 req/min)
        rsi_comp = []
        if our_rsi is not None and t == _ALPHA_VANTAGE_TICKER_ONLY:
            try:
                av_rsi = fetch_rsi(config, t)
            except Exception:
                av_rsi = None
            if av_rsi is not None:
                margin_abs = round(abs(float(our_rsi) - float(av_rsi)), 2)
                rsi_comp.append({"source": "Alpha Vantage", "value": round(float(av_rsi), 2), "margin_abs": margin_abs})
        max_margin_abs = max((c["margin_abs"] for c in rsi_comp if c.get("margin_abs") is not None), default=None)

        # MA20, MA50: Alpha Vantage SMA (SPY only – free tier 5 req/min)
        ma_comp = []
        if (our_ma20 is not None or our_ma50 is not None) and t == _ALPHA_VANTAGE_TICKER_ONLY:
            for period, our_val in [(20, our_ma20), (50, our_ma50)]:
                if our_val is None:
                    continue
                try:
                    av_sma = fetch_sma(config, t, time_period=period)
                except Exception:
                    av_sma = None
                if av_sma is not None and float(our_val) > 0:
                    try:
                        # Fixed: Added validation to prevent ZeroDivisionError
                        margin_pct = round(abs(float(our_val) - float(av_sma)) / float(our_val) * 100, 4)
                    except (TypeError, ValueError, ZeroDivisionError):
                        margin_pct = None
                    ma_comp.append({"series": f"MA{period}", "ours": round(float(our_val), 4), "source": "Alpha Vantage", "value": round(float(av_sma), 4), "margin_pct": margin_pct})
        max_ma_margin_pct = max((c["margin_pct"] for c in ma_comp if c.get("margin_pct") is not None), default=None)

        # MACD hist: Alpha Vantage MACD (SPY only – free tier 5 req/min)
        macd_comp = []
        if our_macd_hist is not None and t == _ALPHA_VANTAGE_TICKER_ONLY:
            try:
                av_macd = fetch_macd(config, t)
            except Exception:
                av_macd = None
            if av_macd is not None and "MACD_Hist" in av_macd:
                margin_abs = round(abs(float(our_macd_hist) - float(av_macd["MACD_Hist"])), 4)
                macd_comp.append({"source": "Alpha Vantage", "value": round(float(av_macd["MACD_Hist"]), 4), "margin_abs": margin_abs})
        max_macd_margin_abs = max((c["margin_abs"] for c in macd_comp if c.get("margin_abs") is not None), default=None)

        # Bias: Finnhub (Yahoo in indicator_validation)
        bias_comp = []
        try:
            fh_bias, fh_label = fetch_recommendation(config, t)
        except Exception:
            fh_bias, fh_label = None, None
        if fh_bias is not None:
            status = "aligned" if our_bias == fh_bias else "divergent" if our_bias else "no_ours"
            bias_comp.append({"source": "Finnhub", "rating": fh_label, "status": status})
        if our_bias and not bias_comp:
            bias_comp.append({"source": "Finnhub", "rating": None, "status": "no_data"})

        out.append({
            "ticker": t,
            "close": {
                "ours": round(float(our_close), 4) if our_close is not None else None,
                "comparisons": close_comp,
                "max_margin_pct": max_margin_pct,
            },
            "rsi": {
                "ours": round(float(our_rsi), 2) if our_rsi is not None else None,
                "comparisons": rsi_comp,
                "max_margin_abs": max_margin_abs,
            },
            "ma": {
                "comparisons": ma_comp,
                "max_margin_pct": max_ma_margin_pct,
            },
            "macd": {
                "ours": round(float(our_macd_hist), 4) if our_macd_hist is not None else None,
                "comparisons": macd_comp,
                "max_margin_abs": max_macd_margin_abs,
            },
            "bias": {
                "ours": our_bias,
                "comparisons": bias_comp,
            },
        })
    return out
