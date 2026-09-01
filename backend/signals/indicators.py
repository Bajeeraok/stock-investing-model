"""
Technical indicators and composite buy score (0-100).
- Gradient trend score (not just 0/50/100)
- RSI with asymmetric scoring: oversold boosts buy, overbought reduces
- MACD for momentum
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """RSI with Wilder's smoothing (alpha=1/14). First RMA = SMA of first 14, then RMA recurrence."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    # Wilder's RMA: first = SMA of first 14, then RMA_t = (RMA_{t-1}*(n-1) + x_t)/n
    avg_gain = pd.Series(index=close.index, dtype=float)
    avg_loss = pd.Series(index=close.index, dtype=float)
    avg_gain.iloc[window - 1] = gain.iloc[:window].mean()
    avg_loss.iloc[window - 1] = loss.iloc[:window].mean()
    for i in range(window, len(close)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (window - 1) + gain.iloc[i]) / window
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (window - 1) + loss.iloc[i]) / window
    rs = np.where(avg_loss == 0, 100.0, avg_gain / avg_loss)
    return pd.Series(100 - (100 / (1 + rs)), index=close.index)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume: cumulative volume signed by daily price direction."""
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).fillna(0.0).cumsum()


def obv_trend_pct(close: pd.Series, volume: pd.Series, window: int = 10) -> float | None:
    """% change in OBV over the trailing `window` sessions.

    Positive = net accumulation (buying pressure) over the window even if a given day's
    raw volume is low; negative = net distribution. Disambiguates "low volume because
    nobody's interested" from "low volume because sellers have dried up" — a single
    day's volume_ratio can't tell those apart, a multi-day OBV slope can.
    """
    if close is None or volume is None or len(close) < window + 1 or len(volume) < window + 1:
        return None
    obv = compute_obv(close, volume)
    start = float(obv.iloc[-window - 1])
    end = float(obv.iloc[-1])
    denom = abs(start) if abs(start) > 1e-9 else max(abs(end), float(volume.iloc[-window:].mean()) or 1.0)
    if denom <= 0:
        return None
    return round((end - start) / denom * 100.0, 2)


def compute_indicators(close: pd.Series) -> pd.DataFrame:
    """Compute MA20, MA50, MA200, RSI(14), MACD. Drops leading NaNs where needed."""
    df = pd.DataFrame({"close": close})

    # Market-standard windows on daily data (SMA). Use full window min_periods so early values are NaN
    # rather than a shorter SMA that can diverge from external sources.
    df["MA20"] = close.rolling(20, min_periods=20).mean()
    df["MA50"] = close.rolling(50, min_periods=50).mean()
    df["MA200"] = close.rolling(200, min_periods=200).mean()
    df["RSI"] = _rsi(close, 14)
    macd_line, signal_line, hist = _macd(close, 12, 26, 9)
    df["MACD"] = macd_line
    df["MACD_signal"] = signal_line
    df["MACD_hist"] = hist

    return df


def _trend_score_gradient(row: pd.Series) -> float:
    """
    Trend score 0-100 using gradient: price vs MA50 vs MA200.
    Strong uptrend: price > MA50 > MA200 -> high score.
    Strong downtrend: price < MA50 < MA200 -> low score.
    """
    c, ma50, ma200 = row["close"], row["MA50"], row["MA200"]
    if pd.isna(ma200) or ma200 <= 0:
        return 50.0
    if pd.isna(ma50):
        return 50.0

    # Order: best = c > MA50 > MA200, worst = c < MA50 < MA200
    if c > ma50 and ma50 > ma200:
        # Distance above MA200 as % of MA200 -> cap at 100
        pct_above = (c - ma200) / ma200
        return min(100.0, 60.0 + 40.0 * min(pct_above * 10, 1.0))
    if c < ma50 and ma50 < ma200:
        pct_below = (ma200 - c) / ma200
        return max(0.0, 40.0 - 40.0 * min(pct_below * 10, 1.0))
    # Mixed: between 30 and 70
    if c > ma50:
        return 55.0
    if c < ma50:
        return 45.0
    return 50.0


def _rsi_score_asymmetric(rsi: float) -> float:
    """
    Asymmetric: oversold (RSI < 30) boosts buy score; overbought (RSI > 70) reduces.
    Returns a score contribution roughly in 0-100 (centered ~50).
    """
    if pd.isna(rsi):
        return 50.0
    if rsi <= 30:
        # Oversold -> bullish for swing buy; map 0-30 -> 60-80
        return 60.0 + (30 - rsi) / 30 * 20
    if rsi >= 70:
        # Overbought -> bearish; map 70-100 -> 20-40
        return 40.0 - (rsi - 70) / 30 * 20
    # 30-70: linear map to 40-60
    return 40.0 + (rsi - 30) / 40 * 20


def _macd_score(hist: float) -> float:
    """MACD histogram: positive -> bullish (up to 100), negative -> bearish (down to 0)."""
    if pd.isna(hist) or hist == 0:
        return 50.0
    # Normalize by typical range; clip to 0-100
    strength = np.clip(hist * 500, -50, 50)  # rough scaling
    return 50.0 + strength


def _overbought_penalty(
    rsi: float,
    close: float,
    ma200: float | None,
    rsi_70_penalty: int = 5,
    rsi_80_penalty: int = 5,
    extension_20_penalty: int = 5,
    extension_35_penalty: int = 5,
) -> float:
    """
    Penalty when price is extended and RSI is high (cuts 70-100 signals before drawdowns).
    RSI > 70: +5; RSI > 80: +5 more. Extension > 20% above MA200: +5; > 35%: +5 more.
    """
    penalty = 0.0
    if not pd.isna(rsi):
        if rsi > 80:
            penalty += rsi_80_penalty + rsi_70_penalty
        elif rsi > 70:
            penalty += rsi_70_penalty
    if ma200 is not None and ma200 > 0 and close > 0:
        extension = (close - ma200) / ma200
        if extension > 0.35:
            penalty += extension_35_penalty + extension_20_penalty
        elif extension > 0.20:
            penalty += extension_20_penalty
    return penalty


def _zscore_to_score(z: float) -> float:
    """Map z-score to 0-100 centered at 50. clamp(50 + 50*z, 0, 100)."""
    return float(np.clip(50.0 + 50.0 * np.clip(z, -2, 2), 0, 100))


def _trend_strength_zscore(close: pd.Series, df: pd.DataFrame) -> tuple[float, float | None]:
    """
    Spec: TS_raw = 0.6*(price-MA50)/MA50 + 0.4*(MA50-MA200)/MA200
    TS = clamp(50 + 50*zscore(TS_raw), 0, 100)
    """
    if len(df) < 200:
        return 50.0, None
    ts_raw = 0.6 * (df["close"] - df["MA50"]) / df["MA50"].replace(0, np.nan) + \
             0.4 * (df["MA50"] - df["MA200"]) / df["MA200"].replace(0, np.nan)
    ts_raw = ts_raw.dropna()
    if len(ts_raw) < 50:
        return 50.0, None
    current_val = float(ts_raw.iloc[-1])
    history = ts_raw.iloc[:-1]  # exclude current bar from normalization distribution
    mean_, std_ = history.mean(), history.std()
    if std_ is None or std_ == 0 or pd.isna(std_):
        return 50.0, current_val
    z = (current_val - mean_) / std_
    return _zscore_to_score(z), float(ts_raw.iloc[-1])


def _momentum_zscore(close: pd.Series, rsi_val: float) -> tuple[float, float | None]:
    """
    Spec: r_3m, r_6m = total return; mom_raw = 0.4*r_3m + 0.4*r_6m + 0.2*((RSI14-50)/50)
    MOM = clamp(50 + 50*zscore(mom_raw), 0, 100); if RSI>70: MOM -= 10
    """
    if len(close) < 127:
        return 50.0, None
    r_3m = (float(close.iloc[-1]) - float(close.iloc[-63])) / float(close.iloc[-63]) if len(close) >= 63 else 0
    r_6m = (float(close.iloc[-1]) - float(close.iloc[-126])) / float(close.iloc[-126]) if len(close) >= 126 else 0
    rsi_norm = ((rsi_val - 50) / 50) if not pd.isna(rsi_val) else 0
    mom_raw = 0.4 * r_3m + 0.4 * r_6m + 0.2 * rsi_norm
    # Build rolling mom_raw for zscore (simplified: use last 252 bars)
    mom_series = []
    for i in range(max(0, len(close) - 252), len(close) - 1):
        if i + 126 < len(close):
            r3 = (close.iloc[i] - close.iloc[max(0, i - 63)]) / close.iloc[max(0, i - 63)] if i >= 63 else 0
            r6 = (close.iloc[i] - close.iloc[max(0, i - 126)]) / close.iloc[max(0, i - 126)] if i >= 126 else 0
            rsi_i = _rsi(close.iloc[: i + 1], 14).iloc[-1] if i >= 14 else 50
            mom_series.append(0.4 * r3 + 0.4 * r6 + 0.2 * ((rsi_i - 50) / 50))
    if not mom_series:
        return 50.0, mom_raw
    arr = np.array(mom_series)
    mean_, std_ = arr.mean(), arr.std()
    if std_ is None or std_ == 0:
        mom = 50.0
    else:
        z = (mom_raw - mean_) / std_
        mom = _zscore_to_score(z)
    if not pd.isna(rsi_val) and rsi_val > 70:
        mom = max(0, mom - 10)
    return round(mom, 1), mom_raw


# Tickers that typically trade at high P/E (30+). If FMP/yfinance returns very low PE
# (e.g. 17 for NVDA after split-adjustment error), we cross-check with price/EPS.
_HIGH_PE_GROWTH_TICKERS = frozenset(
    {"NVDA", "AVGO", "META", "AMD", "TSLA", "CRM", "NOW", "SNOW", "PLTR", "NET", "DDOG", "MDB", "CRWD", "PANW"}
)


def _valuation_score(ticker: str, config: dict | None) -> tuple[float | None, float | None]:
    """
    VAL: forward PE vs SPY (market proxy). Cheaper = higher score.
    Returns (VAL 0-100, raw val for debugging) or (None, None) if unavailable.
    For high-PE growth names, sanity-check FMP PE: if suspiciously low (<22), use yfinance price/EPS.
    """
    if not config or not ticker:
        return None, None
    km = _fetch_key_metrics_cached(ticker, config)
    spy_km = _fetch_key_metrics_cached("SPY", config)
    fwd_pe = _get_forward_pe(km)
    spy_pe = _get_forward_pe(spy_km)
    # Sanity: NVDA etc. should not show 17x — often split or stale data; cross-check with yfinance
    if (
        fwd_pe is not None
        and 0 < fwd_pe < 22
        and ticker.upper().split(".")[0] in _HIGH_PE_GROWTH_TICKERS
    ):
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = getattr(t, "info", None) or {}
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            eps = info.get("trailingEps") or info.get("forwardEps")
            if price is not None and eps is not None and float(eps) > 0:
                pe_yf = float(price) / float(eps)
                if 25 <= pe_yf <= 80:
                    fwd_pe = round(pe_yf, 2)
        except Exception:
            pass
    if fwd_pe is None or spy_pe is None or fwd_pe <= 0 or spy_pe <= 0:
        return None, None
    # val_raw: (sector_PE - fwd_PE) / sector_PE; cheaper => positive
    val_raw = (spy_pe - fwd_pe) / spy_pe
    val = float(np.clip(50.0 + 50.0 * np.clip(val_raw * 2, -1, 1), 0, 100))
    return round(val, 1), val_raw


def _quality_score(ticker: str, config: dict | None) -> float | None:
    """
    QLT: roe, operatingMargin, debtToEquity from key_metrics. Threshold-based 0-100.
    """
    if not config or not ticker:
        return None
    km = _fetch_key_metrics_cached(ticker, config)
    if not km:
        return None
    roe = km.get("roe") or km.get("returnOnEquity")
    op_margin = km.get("operatingMargin") or km.get("operatingProfitMargin")
    de = km.get("debtToEquity")
    # FMP: roe/operatingMargin as decimal (0.15 = 15%) or percent (15 = 15%)
    roe_score = 50.0
    if roe is not None:
        try:
            r = float(roe)
            if r > 1:
                r = r / 100.0  # percent format
            roe_score = min(100, max(0, 50 + r * 250))  # 20% ROE -> 100
        except (TypeError, ValueError):
            pass
    margin_score = 50.0
    if op_margin is not None:
        try:
            m = float(op_margin)
            if m > 1:
                m = m / 100.0  # percent format
            margin_score = min(100, max(0, 50 + m * 250))  # 20% margin -> 100
        except (TypeError, ValueError):
            pass
    leverage_score = 50.0
    if de is not None:
        try:
            d = float(de)
            leverage_score = max(0, min(100, 100 - d * 50))  # D/E=0 -> 100, D/E=2 -> 0
        except (TypeError, ValueError):
            pass
    qlt = 0.4 * roe_score + 0.4 * margin_score + 0.2 * leverage_score
    return round(float(np.clip(qlt, 0, 100)), 1)


def _get_forward_pe(km: dict | None) -> float | None:
    if not km:
        return None
    v = km.get("forwardPE") or km.get("peRatio") or km.get("priceEarningsRatio")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_key_metrics_cached(ticker: str, config: dict) -> dict | None:
    """Fetch key_metrics with cache. Returns None on error or no API key."""
    try:
        from signals.fmp_client import fetch_key_metrics_ttm, get_api_key
        from signals.cache import cached_key_metrics
        if not get_api_key(config):
            return None
        return cached_key_metrics(ticker, lambda: fetch_key_metrics_ttm(config, ticker))
    except Exception:
        return None


def composite_score(
    close: pd.Series,
    weights: dict | None = None,
    use_spec: bool = False,
    ticker: str | None = None,
    config: dict | None = None,
) -> dict:
    """
    Compute composite buy score (0-100) and component values for the latest bar.
    weights: trend, rsi, macd (default 0.5, 0.3, 0.2).
    use_spec: if True, use spec formula (TS, MOM, optional VAL, QLT, regime penalty).
    ticker, config: required for VAL/QLT when use_spec (stocks only; ETFs skipped).
    """
    if weights is None:
        weights = {"trend": 0.5, "rsi": 0.3, "macd": 0.2}

    df = compute_indicators(close)
    if df.empty or len(df) < 2:
        return _empty_signal(close)

    row = df.iloc[-1]
    last_close = float(row["close"])
    rsi_val = float(row["RSI"])
    macd_hist = float(row["MACD_hist"])

    _ETFS = {"SPY", "QQQ", "GLD", "SLV", "IWM", "DIA", "VOO", "VTI", "XLF", "XLK", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE"}
    is_etf = ticker and ticker.upper().split(".")[0] in _ETFS

    ma_regime = None
    if use_spec and len(df) >= 200:
        # Vol 20d: std of daily returns
        ret = close.pct_change().dropna()
        if len(ret) >= 20:
            vol_20 = float(ret.iloc[-20:].std()) if len(ret) >= 20 else None
            vol_20_hist = ret.rolling(20).std().dropna()
            vol_70_pct = float(np.percentile(vol_20_hist, 70)) if len(vol_20_hist) > 10 else None
            from signals.regime import get_regime_ma
            ma_regime = get_regime_ma(
                last_close, float(row["MA50"]), float(row["MA200"]),
                vol_20, vol_70_pct,
            )
        ts, _ = _trend_strength_zscore(close, df)
        mom, _ = _momentum_zscore(close, rsi_val)
        val = None
        qlt = None
        use_val_qlt = config and config.get("use_spec_val_qlt", True)
        if ticker and config and not is_etf and use_val_qlt:
            val, _ = _valuation_score(ticker, config)
            qlt = _quality_score(ticker, config)
        # Spec: Score = 0.35*TS + 0.30*MOM + 0.20*VAL + 0.15*QLT
        if val is not None and qlt is not None:
            composite = 0.35 * ts + 0.30 * mom + 0.20 * val + 0.15 * qlt
        elif val is not None:
            composite = 0.50 * ts + 0.35 * mom + 0.15 * val
        elif qlt is not None:
            composite = 0.50 * ts + 0.40 * mom + 0.10 * qlt
        else:
            composite = 0.55 * ts + 0.45 * mom
        if ma_regime and ma_regime not in ("UP", "UP-HV"):
            composite -= 15
        ob_cfg = (config or {}).get("overbought_penalty") or {}
        if ob_cfg.get("enabled", True):
            penalty = _overbought_penalty(
                rsi_val, last_close, float(row["MA200"]) if pd.notna(row["MA200"]) and row["MA200"] > 0 else None,
                rsi_70_penalty=ob_cfg.get("rsi_70_penalty", 5),
                rsi_80_penalty=ob_cfg.get("rsi_80_penalty", 5),
                extension_20_penalty=ob_cfg.get("extension_20_penalty", 5),
                extension_35_penalty=ob_cfg.get("extension_35_penalty", 5),
            )
            composite = max(0.0, composite - penalty)
        composite = max(0.0, min(100.0, round(composite, 1)))
        out = {
            "close": last_close,
            "trend_score": round(ts, 1),
            "rsi": round(rsi_val, 1),
            "macd_hist": round(macd_hist, 4),
            "rsi_contrib": round(mom, 1),
            "macd_contrib": round(_macd_score(macd_hist), 1),
            "composite_buy": composite,
            "ma_regime": ma_regime,
        }
        if val is not None:
            out["val_score"] = val
        if qlt is not None:
            out["qlt_score"] = qlt
        return out

    trend = _trend_score_gradient(row)
    rsi_contrib = _rsi_score_asymmetric(rsi_val)
    macd_contrib = _macd_score(macd_hist)

    composite = (
        weights["trend"] * trend
        + weights["rsi"] * rsi_contrib
        + weights["macd"] * macd_contrib
    )
    ob_cfg = (config or {}).get("overbought_penalty") or {}
    if ob_cfg.get("enabled", True):
        ma200_val = float(row["MA200"]) if pd.notna(row["MA200"]) and row["MA200"] > 0 else None
        penalty = _overbought_penalty(
            rsi_val, last_close, ma200_val,
            rsi_70_penalty=ob_cfg.get("rsi_70_penalty", 5),
            rsi_80_penalty=ob_cfg.get("rsi_80_penalty", 5),
            extension_20_penalty=ob_cfg.get("extension_20_penalty", 5),
            extension_35_penalty=ob_cfg.get("extension_35_penalty", 5),
        )
        composite = max(0.0, composite - penalty)
    composite = max(0.0, min(100.0, round(composite, 1)))

    return {
        "close": last_close,
        "trend_score": round(trend, 1),
        "rsi": round(rsi_val, 1),
        "macd_hist": round(macd_hist, 4),
        "rsi_contrib": round(rsi_contrib, 1),
        "macd_contrib": round(macd_contrib, 1),
        "composite_buy": composite,
    }


def _empty_signal(close: pd.Series) -> dict:
    last = float(close.iloc[-1]) if len(close) else 0.0
    return {
        "close": last,
        "trend_score": 50.0,
        "rsi": 50.0,
        "macd_hist": 0.0,
        "rsi_contrib": 50.0,
        "macd_contrib": 50.0,
        "composite_buy": 50.0,
    }


def multi_horizon_scores(
    close: pd.Series,
    use_spec: bool = False,
    ticker: str | None = None,
    config: dict | None = None,
    market_regime: str | None = None,
    vix: float | None = None,
    interpretation_style: str = "TRENDING",
) -> dict:
    """
    Short (~1 mo / ~20d), Medium (~3–6 mo / ~60d), Long (~12–18 mo / ~120d) scores — align evaluation horizons (21/63/126/252d) in harness.

    interpretation_style MEAN_REVERTING: invert scores only inside _sugg() so HOLD/ADD vs
    CONSIDER TRIM aligns with dip-buy / rally-trim on choppy tape (raw *_term unchanged).
    - Short: MA20 vs MA50, RSI, 5-day momentum
    - Medium: composite (MA50/200, RSI, MACD or spec TS+MOM+VAL+QLT) – main signal
    - Long: price vs MA200, MA50 vs MA200 alignment
    use_spec: use spec formula (TS, MOM, optional VAL, QLT, regime penalty).
    ticker, config: required for VAL/QLT when use_spec (stocks only).
    market_regime: 5-level (STRONG_BULL, BULL, NEUTRAL, BEAR, STRONG_BEAR) – regime multipliers applied.
    vix: VIX level – calm amplifies, elevated+ suppresses (VIX multiplier on final score).
    """
    sig = composite_score(close, use_spec=use_spec, ticker=ticker, config=config)
    raw = float(sig.get("composite_buy") or 50)
    # Regime multiplier (replace flat -10): BEAR/STRONG_BEAR suppress high scores
    if market_regime:
        from signals.regime import get_regime_multiplier, get_vix_multiplier
        reg_mult, _ = get_regime_multiplier(market_regime, raw)
        adjusted = min(100.0, raw * reg_mult)
        vix_mult, _ = get_vix_multiplier(vix)
        adjusted = min(100.0, adjusted * vix_mult)
        sig = {**sig, "composite_buy": round(adjusted, 1)}
    df = compute_indicators(close)
    if df.empty or len(df) < 50:
        return {
            **sig,
            "ma20": None,
            "ma50": None,
            "short_term": 50.0,
            "medium_term": sig["composite_buy"],
            "long_term": 50.0,
            "short_suggestion": "HOLD",
            "medium_suggestion": "HOLD",
            "long_suggestion": "HOLD",
            "short_reason": "insufficient data",
            "medium_reason": "insufficient data",
            "long_reason": "insufficient data",
            "suggested_buy_price": None,
            "suggested_sell_price": None,
            "support_level": None,
            "buy_target_confidence_pct": None,
            "sell_target_confidence_pct": None,
            "confluence_score": 50.0,
            "trend_signal":     "NEUTRAL",
            "rsi_signal":       "NEUTRAL",
            "macd_signal":      "NEUTRAL",
        }

    row = df.iloc[-1]
    c, ma20, ma50, ma200 = row["close"], row["MA20"], row["MA50"], row["MA200"]
    rsi_val = row["RSI"]

    # Short-term (weeks): MA20 vs MA50 + RSI
    if pd.notna(ma20) and pd.notna(ma50) and ma50 > 0:
        short_trend = 100.0 if c > ma20 > ma50 else (0.0 if c < ma20 < ma50 else 50.0)
    else:
        short_trend = 50.0
    short_rsi = _rsi_score_asymmetric(rsi_val)
    short_term = round(0.6 * short_trend + 0.4 * short_rsi, 1)
    short_term = max(0, min(100, short_term))

    # Medium-term: use composite (already computed)
    medium_term = sig["composite_buy"]

    # Long-term (1–2 yrs): price vs MA200, MA50 vs MA200
    if pd.notna(ma200) and ma200 > 0 and pd.notna(ma50):
        above_200 = (c - ma200) / ma200
        ma50_above_200 = (ma50 - ma200) / ma200 if ma200 > 0 else 0
        long_term = 50.0 + 25 * np.clip(above_200 * 20, -2, 2) + 25 * np.clip(ma50_above_200 * 20, -1, 1)
        # Pullback in uptrend: price below MA200 but MA50 > MA200 (structure intact) -> HOLD, not CONSIDER TRIM
        if c < ma200 and ma50 > ma200 and long_term < 40:
            long_term = 40.0
    else:
        long_term = 50.0
    long_term = round(max(0, min(100, long_term)), 1)

    def _sugg(score: float, buy: float = 65, sell: float = 35) -> str:
        s = float(score)
        if interpretation_style == "MEAN_REVERTING":
            s = 100.0 - s
        if s >= buy:
            return "HOLD/ADD"
        if s <= sell:
            return "CONSIDER TRIM"
        return "HOLD"

    def _short_reason() -> str:
        """Brief reasoning for short-term (weeks) suggestion."""
        parts = []
        if pd.notna(ma20) and pd.notna(ma50) and ma50 > 0:
            if c > ma20 > ma50:
                parts.append("price above MA20 & MA50 (uptrend)")
            elif c < ma20 < ma50:
                parts.append("price below MA20 & MA50 (downtrend)")
            else:
                parts.append("mixed MA setup")
        rsi_val_f = float(rsi_val) if pd.notna(rsi_val) else None
        if rsi_val_f is not None:
            if rsi_val_f >= 70:
                parts.append(f"RSI {rsi_val_f:.0f} overbought")
            elif rsi_val_f <= 30:
                parts.append(f"RSI {rsi_val_f:.0f} oversold")
        return "; ".join(parts) if parts else "insufficient data"

    def _medium_reason() -> str:
        """Brief reasoning for medium-term (months) suggestion."""
        parts = []
        comp = sig["composite_buy"]
        if pd.notna(ma50) and pd.notna(ma200) and ma200 > 0:
            if c > ma50 > ma200:
                parts.append("price > MA50 > MA200 (uptrend)")
            elif c < ma50 < ma200:
                parts.append("price < MA50 < MA200 (downtrend)")
            else:
                parts.append("mixed trend")
        if pd.notna(rsi_val):
            rv = float(rsi_val)
            if rv >= 70:
                parts.append("RSI overbought")
            elif rv <= 30:
                parts.append("RSI oversold")
        macd = sig.get("macd_hist")
        if macd is not None:
            parts.append("MACD bullish" if macd > 0 else "MACD bearish")
        return "; ".join(parts) if parts else f"score {comp:.0f}"

    def _long_reason() -> str:
        """Brief reasoning for long-term (1–2 yr) suggestion. Wording aligned with suggestion (no contradiction)."""
        parts = []
        if pd.notna(ma200) and ma200 > 0 and pd.notna(ma50):
            pct_above = 100 * (c - ma200) / ma200
            if c > ma200:
                parts.append(f"price {pct_above:.1f}% above MA200")
            else:
                parts.append("price below MA200")
            if ma50 > ma200:
                # Bullish structure: pullback in uptrend -> reason supports HOLD/ADD, not trim
                parts.append("MA50 > MA200 (uptrend intact; add on dip or hold)")
            else:
                parts.append("MA50 < MA200 (weaker structure)")
        return "; ".join(parts) if parts else "insufficient data"

    # Suggested sell price: only when actionable (overbought trim or weak exit) = current price
    # Do NOT use MA20 as "sell" - that's support to watch; selling at $186 when at $191 makes no sense
    suggested_sell_price = None
    if not pd.isna(rsi_val) and rsi_val >= 70:
        suggested_sell_price = round(float(c), 2)  # Consider trim at overbought
    elif sig["composite_buy"] <= 35:
        suggested_sell_price = round(float(c), 2)  # Consider exit when score weak

    # Suggested buy price: only when NOT in sell mode – don't encourage adds when we say exit
    # When SELL (RSI≥70 or score≤35), we omit buy level to avoid "consider trim" + "buy at X" contradiction.
    # Only suggest a level at or below current price: MA50 when price > MA50 (add on dip), else MA200 (value).
    # Never suggest MA50 when price < MA50 (that would be above market – not a pullback level).
    suggested_buy_price = None
    if suggested_sell_price is None:  # Only show buy level when we're not recommending exit
        if pd.notna(ma50) and ma50 > 0 and c > ma50:
            suggested_buy_price = round(float(ma50), 2)  # Add on dip to MA50
        elif pd.notna(ma200) and ma200 > 0:
            suggested_buy_price = round(float(ma200), 2)  # Value / add on dip to MA200
        # When price < MA50 and MA200 missing: do not use MA50 (it's above price); leave None
    # Sanity: never suggest a buy level above current price (would imply "buy above market")
    if suggested_buy_price is not None and suggested_buy_price > c:
        suggested_buy_price = None

    # Support levels: primary = MA50, secondary = MA200 (uptrend). MA20 as short-term watch.
    support_level = None
    support_primary = None
    support_secondary = None
    if pd.notna(ma50) and ma50 > 0 and c > ma50:
        support_primary = round(float(ma50), 2)
    if pd.notna(ma200) and ma200 > 0 and c > ma200:
        support_secondary = round(float(ma200), 2)
    # Use primary (MA50) as main support when available; fallback to MA20 for short-term
    if support_primary is not None:
        support_level = support_primary
    elif pd.notna(ma20) and ma20 > 0 and c > ma20:
        support_level = round(float(ma20), 2)

    # Confidence score (0-100) for buy/sell target to support decision-making
    buy_target_confidence_pct = None
    if suggested_buy_price is not None:
        comp = sig.get("composite_buy")
        if comp is not None:
            comp_f = float(comp)
            # Base: composite score (trend/RSI/MACD) = confidence in adding at this level
            buy_target_confidence_pct = round(min(95, max(0, comp_f)), 0)

    sell_target_confidence_pct = None
    if suggested_sell_price is not None:
        rsi_f = float(rsi_val) if pd.notna(rsi_val) else None
        comp = sig.get("composite_buy")
        comp_f = float(comp) if comp is not None else 50
        # Higher confidence when RSI very overbought or score very weak
        from_rsi = 72 + min(23, (rsi_f - 70)) if rsi_f is not None and rsi_f >= 70 else 0
        from_score = 78 - comp_f * 0.8 if comp_f <= 35 else 0
        sell_target_confidence_pct = round(min(95, max(50, from_rsi, from_score)), 0)

    # ── Confluence Score — explicit 4-signal agreement (0-100) ───────────────
    # Unlike composite_buy (which uses regime as a hidden multiplier), each of
    # the four components here is an explicit, equal-weight contributor so the
    # number clearly means "what fraction of independent signals agree it's bullish".
    #
    # Weights: Trend 30% + RSI zone 25% + MACD direction 20% + Regime 25%
    #
    # This is the right metric for the main table because:
    #   - composite_buy = good internal score but not human-interpretable
    #   - ML confidence = probabilistic, expensive to compute for all tickers
    #   - Confluence = fast, transparent, communicates signal agreement

    # Component 1: Trend alignment (price vs MA50 vs MA200 structure)
    if pd.notna(ma50) and pd.notna(ma200) and ma200 > 0:
        if c > ma50 > ma200:       trend_comp = 85.0  # confirmed uptrend
        elif c > ma200 >= ma50:    trend_comp = 65.0  # above 200, MA50 lagging
        elif c > ma50:             trend_comp = 60.0  # above 50, MA50/200 mixed
        elif c < ma50 < ma200:     trend_comp = 15.0  # confirmed downtrend
        else:                      trend_comp = 38.0  # below 50 or mixed
    else:
        trend_comp = 50.0
    trend_signal = "UP" if trend_comp >= 65 else ("DOWN" if trend_comp <= 35 else "NEUTRAL")

    # Component 2: RSI zone (recovery from oversold = best setup, overbought = poor entry)
    _rsi_f = float(rsi_val) if pd.notna(rsi_val) else 50.0
    if _rsi_f < 25:     rsi_comp = 40.0  # deeply oversold, panic — not yet confirmed
    elif _rsi_f < 40:   rsi_comp = 78.0  # oversold recovery zone — ideal entry
    elif _rsi_f < 55:   rsi_comp = 70.0  # healthy momentum
    elif _rsi_f < 70:   rsi_comp = 52.0  # slightly elevated but acceptable
    else:               rsi_comp = 22.0  # overbought — poor new entry
    rsi_signal = "UP" if rsi_comp >= 65 else ("DOWN" if rsi_comp <= 35 else "NEUTRAL")

    # Component 3: MACD histogram direction (positive = buying pressure, negative = selling)
    _macd = float(sig.get("macd_hist") or 0)
    if _macd > 0:   macd_comp = 75.0
    elif _macd < 0: macd_comp = 25.0
    else:           macd_comp = 50.0
    macd_signal = "UP" if macd_comp >= 65 else ("DOWN" if macd_comp <= 35 else "NEUTRAL")

    # Component 4: Regime (explicit contributor, not just a multiplier)
    _mr = market_regime or sig.get("ma_regime", "NEUTRAL")
    regime_comp = {
        "STRONG_BULL": 92.0, "BULL": 80.0, "UP": 80.0,
        "NEUTRAL": 50.0,
        "BEAR": 20.0, "DOWN": 20.0, "STRONG_BEAR": 8.0,
    }.get(str(_mr).upper(), 50.0)

    confluence_score = round(
        0.30 * trend_comp +
        0.25 * rsi_comp +
        0.20 * macd_comp +
        0.25 * regime_comp,
        1,
    )
    confluence_score = max(0.0, min(99.0, confluence_score))  # cap at 99 — never perfect

    return {
        **sig,
        "ma20": round(float(ma20), 2) if pd.notna(ma20) else None,
        "ma50": round(float(ma50), 2) if pd.notna(ma50) else None,
        "ma200": round(float(ma200), 2) if pd.notna(ma200) else None,
        "short_term": short_term,
        "medium_term": medium_term,
        "long_term": long_term,
        "short_suggestion": _sugg(short_term),
        "medium_suggestion": _sugg(medium_term),
        "long_suggestion": _sugg(long_term),
        "short_reason": _short_reason(),
        "medium_reason": _medium_reason(),
        "long_reason": _long_reason(),
        "suggested_buy_price": suggested_buy_price,
        "suggested_sell_price": suggested_sell_price,
        "support_level": support_level,
        "support_primary": support_primary,
        "support_secondary": support_secondary,
        "buy_target_confidence_pct": buy_target_confidence_pct,
        "sell_target_confidence_pct": sell_target_confidence_pct,
        # Confluence score + per-component signals for UI display
        "confluence_score":  confluence_score,
        "trend_signal":      trend_signal,   # "UP" / "NEUTRAL" / "DOWN"
        "rsi_signal":        rsi_signal,
        "macd_signal":       macd_signal,
    }
