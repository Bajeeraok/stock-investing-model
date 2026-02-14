"""
Ticker detail: thesis, earnings, benchmarks (SPY, industry ETF, peers), model accuracy.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from behavior.thesis import load_theses
from signals.fetcher import fetch_ohlcv_safe, fetch_ohlcv_with_volume
from signals.indicators import multi_horizon_scores
from signals.providers import get_next_earnings, get_sector_and_industry, get_peers

try:
    import pandas as pd
except ImportError:
    pd = None


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
    """
    ticker = ticker.upper()
    theses = load_theses()
    thesis_data = theses.get(ticker, {})

    # Sector & industry
    sector_info = get_sector_and_industry(ticker) or {}
    sector_etf = sector_info.get("sector_etf", "SPY")

    # Peers (exclude ETFs)
    peers_raw = get_peers(ticker, config)
    peers = [str(p).upper() for p in (peers_raw or []) if str(p).upper() not in ("SPY", "QQQ", "GLD", "SLV")][:6]

    # Earnings
    earnings = get_next_earnings(ticker, config)

    # Price data for ticker, SPY, sector ETF
    period = config.get("data", {}).get("period", "2y") or "2y"
    close_ticker, volume = fetch_ohlcv_with_volume(ticker, period)
    if close_ticker is None:
        close_ticker = fetch_ohlcv_safe(ticker, period)
    close_spy = fetch_ohlcv_safe("SPY", period)
    close_sector = fetch_ohlcv_safe(sector_etf, period) if sector_etf != "SPY" else close_spy

    periods = {"1m": 21, "3m": 63, "6m": 126, "1y": 252}

    ret_ticker = _returns_over_periods(close_ticker, periods)
    ret_spy = _returns_over_periods(close_spy, periods)
    ret_sector = _returns_over_periods(close_sector, periods)

    # Peer returns (sample)
    peer_returns = []
    for p in peers[:4]:
        c = fetch_ohlcv_safe(p, period)
        r = _returns_over_periods(c, periods)
        if r:
            peer_returns.append({"ticker": p, "returns": r})

    # Current price
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

    drawdown_52w = None
    if close_ticker is not None and len(close_ticker) >= 252 and current_price:
        high_52w = float(close_ticker.iloc[-252:].max())
        if high_52w and high_52w > 0:
            drawdown_52w = round(100 * (current_price - high_52w) / high_52w, 1)

    # Signal reasoning (HOLD/BUY/SELL with brief why)
    signal_data = {}
    price_reasoning: dict[str, str] = {}
    if close_ticker is not None and not close_ticker.empty and pd is not None:
        try:
            sig = multi_horizon_scores(close_ticker)
            buy_p = sig.get("suggested_buy_price")
            sell_p = sig.get("suggested_sell_price")
            supp = sig.get("support_level")
            rsi = sig.get("rsi")
            score = sig.get("composite_buy")
            signal_data = {
                "short_suggestion": sig.get("short_suggestion"),
                "medium_suggestion": sig.get("medium_suggestion"),
                "long_suggestion": sig.get("long_suggestion"),
                "short_reason": sig.get("short_reason"),
                "medium_reason": sig.get("medium_reason"),
                "long_reason": sig.get("long_reason"),
                "suggested_buy_price": buy_p,
                "suggested_sell_price": sell_p,
                "support_level": supp,
                "ma20": sig.get("ma20"),
                "ma50": sig.get("ma50"),
                "ma200": sig.get("ma200"),
            }
            # Human-readable reasoning for modal (helps learn and understand)
            if buy_p is not None:
                price_reasoning["buy"] = f"Buy: ${buy_p:.2f} – add on pullback to MA50"
            else:
                price_reasoning["buy"] = "Buy: – (no add level; price below MA50 or insufficient data)"

            if sell_p is not None:
                price_reasoning["sell"] = f"Sell: ${sell_p:.2f} – consider trim/exit (overbought or weak)"
            else:
                rsi_s = f"RSI {rsi:.0f}" if rsi is not None else "RSI n/a"
                score_s = f"score {score:.0f}" if score is not None else "score n/a"
                price_reasoning["sell"] = f"Sell: – (no sell signal; {rsi_s}, {score_s})"

            if supp is not None:
                price_reasoning["support"] = f"Support: ${supp:.2f} – MA20 support; break below suggests caution"
            else:
                price_reasoning["support"] = "Support: – (price below MA20 or no data)"
        except Exception:
            pass

    return {
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
        "seasonal_note": _seasonal_note(ticker),
        "price_reasoning": price_reasoning,
        "volume_ratio": volume_ratio,
        "volume_unusual": volume_unusual,
        "drawdown_52w": drawdown_52w,
        **_get_extra_info(ticker),
        **signal_data,
        **_get_fmp_data(ticker, config, current_price, signal_data, close_ticker),
    }


def _seasonal_note(ticker: str) -> str | None:
    """Brief seasonal/events note - placeholder for future enhancement."""
    # Could add: earnings season patterns, sector rotation notes
    return None


def _get_fmp_data(ticker: str, config: dict, current_price: float | None, signal_data: dict, close) -> dict:
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

        if cons and isinstance(cons, dict):
            out["cons_low"] = cons.get("low") or cons.get("priceWhenPosted") or cons.get("adjLow")
            out["cons_high"] = cons.get("high") or cons.get("adjHigh") or cons.get("consensus") or cons.get("median")

        eps_fwd = None
        if eps_data and isinstance(eps_data, dict):
            eps_fwd = eps_data.get("eps_fwd") or eps_data.get("eps") or eps_data.get("epsEstimate")
        out["eps_fwd"] = eps_fwd

        if insider and isinstance(insider, dict):
            out["insider_stats"] = insider

        if current_price is not None and close is not None and len(close) >= 20:
            vol_6m = compute_vol_6m(close)
            swing_high, swing_low = compute_swing_high_low(close, 20)
            comp = signal_data.get("composite_buy")
            regime = "NEUTRAL"
            if comp is not None:
                regime = "UP" if comp >= 60 else ("DOWN" if comp <= 40 else "NEUTRAL")
            row = {
                "price": current_price,
                "close": current_price,
                "ma20": signal_data.get("ma20"),
                "regime": regime,
                "vol_6m": vol_6m or 0.3,
                "short_suggestion": signal_data.get("short_suggestion"),
                "atr14": None,
                "swing_high_20d": swing_high,
                "swing_low_20d": swing_low,
                "eps_fwd": eps_fwd,
                "fair_pe_low": 18,
                "fair_pe_high": 25,
                "cons_low": out.get("cons_low"),
                "cons_high": out.get("cons_high"),
            }
            if len(close) >= 15:
                returns = close.pct_change().dropna().iloc[-14:]
                if len(returns) >= 10:
                    vol = float(returns.std())
                    if vol > 0:
                        row["atr14"] = round(float(vol * close.iloc[-1]), 2)
            add_target_bands(row)
            out["st_band"] = row.get("st_band")
            out["mt_band"] = row.get("mt_band")
            out["lt_band"] = row.get("lt_band")
            out["lt_band_low_confidence"] = row.get("lt_band_low_confidence")
            out["st_checkpoints"] = row.get("st_checkpoints")
            out["mt_checkpoints"] = row.get("mt_checkpoints")
            out["lt_checkpoints"] = row.get("lt_checkpoints")
            out["lt_scenarios"] = row.get("lt_scenarios")
            out["st_level_hit"] = row.get("st_level_hit")
            out["st_target_confidence_pct"] = row.get("st_target_confidence_pct")
            out["mt_target_confidence_pct"] = row.get("mt_target_confidence_pct")

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


def _get_extra_info(ticker: str) -> dict:
    """Dividend yield, 52w high/low, beta from yfinance. Skips ETFs to avoid Yahoo 404."""
    sym = (ticker or "").upper().split("-")[0]
    if sym in _ETFS_SKIP_YAHOO_INFO:
        return {}
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        out = {}
        dy = info.get("dividendYield") or info.get("yield")
        if dy is not None and float(dy) > 0:
            out["dividend_yield"] = round(float(dy) * 100, 2)
        for k, v in [("fiftyTwoWeekHigh", "high_52w"), ("fiftyTwoWeekLow", "low_52w")]:
            val = info.get(k)
            if val is not None:
                try:
                    out[v] = round(float(val), 2)
                except (TypeError, ValueError):
                    pass
        beta = info.get("beta")
        if beta is not None:
            try:
                out["beta"] = round(float(beta), 2)
            except (TypeError, ValueError):
                pass
        return out
    except Exception:
        return {}
