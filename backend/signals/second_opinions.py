"""
Second opinions: outside-style ratings shown next to our call and scored in forward tracking.

- Technical rating (1D / 1W / 1M): our own computation of TradingView's published "Technical
  Ratings" method (moving-average votes + oscillator votes, averaged). Not TradingView data.
- Wall Street analyst consensus (~12 months): FMP grades-consensus counts.
- Finnhub recommendation trends (~12 months): only when FINNHUB_API_KEY is configured.

Agreement with another source is not evidence either is right; forward tracking scores all of
them against the same forward returns.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TV_HORIZONS = (("tv_1d", "1D", "Days to weeks"), ("tv_1w", "1W", "Weeks to months"), ("tv_1m", "1M", "Months"))
SOURCE_LABELS = {
    "ours": "Our model",
    "tv_1d": "Technical rating (daily)",
    "tv_1w": "Technical rating (weekly)",
    "tv_1m": "Technical rating (monthly)",
    "analyst": "Analyst consensus",
    "finnhub": "Finnhub analysts",
}


def label_from_score(score: float | None, *, analyst: bool = False) -> str | None:
    if score is None or not np.isfinite(score):
        return None
    hi, lo = (0.5, 0.15) if analyst else (0.5, 0.1)
    neutral = "Hold" if analyst else "Neutral"
    if score >= hi:
        return "Strong Buy"
    if score >= lo:
        return "Buy"
    if score > -lo:
        return neutral
    if score > -hi:
        return "Sell"
    return "Strong Sell"


def bias_from_label(label: str | None) -> str | None:
    if not label:
        return None
    u = str(label).upper()
    if "BUY" in u or u in ("ADD", "ACCUMULATE"):
        return "bullish"
    if any(k in u for k in ("SELL", "TRIM", "REDUCE", "AVOID", "EXIT")):
        return "bearish"
    return "neutral"


# ── Technical rating (TradingView-style) ────────────────────────────────────

def _cols(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series | None]:
    c = {str(k).lower(): k for k in df.columns}
    close = df[c["close"]].astype(float)
    high = df[c["high"]].astype(float) if "high" in c else close
    low = df[c["low"]].astype(float) if "low" in c else close
    vol = df[c["volume"]].astype(float) if "volume" in c else None
    return close, high, low, vol


def _last2(s: pd.Series) -> tuple[float, float]:
    s = s.dropna()
    if len(s) < 2:
        return float("nan"), float("nan")
    return float(s.iloc[-1]), float(s.iloc[-2])


def _rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _wma(s: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda x: float(np.dot(x, w) / w.sum()), raw=True)


def _vote(cond_buy: bool, cond_sell: bool) -> int:
    return 1 if cond_buy else (-1 if cond_sell else 0)


def technical_rating(df: pd.DataFrame | None) -> dict[str, Any] | None:
    """TradingView-style rating on one timeframe. Indicators without enough bars are skipped."""
    if df is None or len(df) < 30:
        return None
    try:
        close, high, low, vol = _cols(df)
    except Exception:
        return None
    price = float(close.iloc[-1])
    ma_votes: list[int] = []
    for n in (10, 20, 30, 50, 100, 200):
        if len(close) >= n:
            for ma in (close.rolling(n).mean(), close.ewm(span=n, adjust=False).mean()):
                v = float(ma.iloc[-1])
                ma_votes.append(_vote(v < price, v > price))
    if len(close) >= 26:
        base = float((high.rolling(26).max() + low.rolling(26).min()).iloc[-1] / 2)
        ma_votes.append(_vote(base < price, base > price))
    if vol is not None and len(close) >= 20 and float(vol.iloc[-20:].sum()) > 0:
        vwma = float((close * vol).rolling(20).sum().iloc[-1] / vol.rolling(20).sum().iloc[-1])
        ma_votes.append(_vote(vwma < price, vwma > price))
    if len(close) >= 12:
        hull = _wma(2 * _wma(close, 4) - _wma(close, 9), 3)
        hv = float(hull.iloc[-1])
        if np.isfinite(hv):
            ma_votes.append(_vote(hv < price, hv > price))

    osc: list[int] = []
    r, rp = _last2(_rsi(close, 14))
    if np.isfinite(r):
        osc.append(_vote(r < 30 and r > rp, r > 70 and r < rp))
    if len(close) >= 20:
        ll, hh = low.rolling(14).min(), high.rolling(14).max()
        k = (100 * (close - ll) / (hh - ll).replace(0, np.nan)).rolling(3).mean()
        d = k.rolling(3).mean()
        kv, dv = float(k.iloc[-1]), float(d.iloc[-1])
        if np.isfinite(kv) and np.isfinite(dv):
            osc.append(_vote(kv < 20 and kv > dv, kv > 80 and kv < dv))
        wr, wrp = _last2(-100 * (hh - close) / (hh - ll).replace(0, np.nan))
        if np.isfinite(wr):
            osc.append(_vote(wr < -80 and wr > wrp, wr > -20 and wr < wrp))
    if len(close) >= 21:
        tp = (high + low + close) / 3
        md = tp.rolling(20).apply(lambda x: float(np.mean(np.abs(x - x.mean()))), raw=True)
        cci, ccip = _last2((tp - tp.rolling(20).mean()) / (0.015 * md.replace(0, np.nan)))
        if np.isfinite(cci):
            osc.append(_vote(cci < -100 and cci > ccip, cci > 100 and cci < ccip))
    if len(close) >= 30:
        up, dn = high.diff(), -low.diff()
        pdm = up.where((up > dn) & (up > 0), 0.0)
        ndm = dn.where((dn > up) & (dn > 0), 0.0)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
        pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr
        ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / atr
        adx = (100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)).ewm(alpha=1 / 14, adjust=False).mean()
        a, p, n_ = float(adx.iloc[-1]), float(pdi.iloc[-1]), float(ndi.iloc[-1])
        if np.isfinite(a):
            osc.append(_vote(a > 20 and p > n_, a > 20 and n_ > p))
    if len(close) >= 34:
        mid = (high + low) / 2
        ao, aop = _last2(mid.rolling(5).mean() - mid.rolling(34).mean())
        osc.append(_vote(ao > 0 and ao > aop, ao < 0 and ao < aop))
    if len(close) >= 12:
        mom, momp = _last2(close - close.shift(10))
        osc.append(_vote(mom > momp, mom < momp))
    if len(close) >= 35:
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        sig = macd.ewm(span=9, adjust=False).mean()
        osc.append(_vote(float(macd.iloc[-1]) > float(sig.iloc[-1]), float(macd.iloc[-1]) < float(sig.iloc[-1])))
    if len(close) >= 34:
        rs = _rsi(close, 14)
        srsi = 100 * (rs - rs.rolling(14).min()) / (rs.rolling(14).max() - rs.rolling(14).min()).replace(0, np.nan)
        sk = srsi.rolling(3).mean()
        sd = sk.rolling(3).mean()
        kv, dv = float(sk.iloc[-1]), float(sd.iloc[-1])
        if np.isfinite(kv) and np.isfinite(dv):
            osc.append(_vote(kv < 20 and kv > dv, kv > 80 and kv < dv))
    if len(close) >= 15:
        ema13 = close.ewm(span=13, adjust=False).mean()
        bbp, bbpp = _last2(high + low - 2 * ema13)
        uptrend = price > float(ema13.iloc[-1])
        osc.append(_vote(uptrend and bbp < 0 and bbp > bbpp, (not uptrend) and bbp > 0 and bbp < bbpp))
    if len(close) >= 30:
        pc = close.shift()
        bp = close - pd.concat([low, pc], axis=1).min(axis=1)
        tr2 = pd.concat([high, pc], axis=1).max(axis=1) - pd.concat([low, pc], axis=1).min(axis=1)
        avg = lambda n: bp.rolling(n).sum() / tr2.rolling(n).sum().replace(0, np.nan)  # noqa: E731
        uo = float((100 * (4 * avg(7) + 2 * avg(14) + avg(28)) / 7).iloc[-1])
        if np.isfinite(uo):
            osc.append(_vote(uo > 70, uo < 30))

    if not ma_votes or not osc:
        return None
    ma_s = sum(ma_votes) / len(ma_votes)
    osc_s = sum(osc) / len(osc)
    score = (ma_s + osc_s) / 2
    label = label_from_score(score)
    return {
        "score": round(score, 3),
        "label": label,
        "bias": bias_from_label(label),
        "ma": {"score": round(ma_s, 3), "buy": ma_votes.count(1), "neutral": ma_votes.count(0), "sell": ma_votes.count(-1)},
        "osc": {"score": round(osc_s, 3), "buy": osc.count(1), "neutral": osc.count(0), "sell": osc.count(-1)},
        "bars": int(len(close)),
    }


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame | None:
    try:
        d = df.copy()
        d.columns = [str(c).lower() for c in d.columns]
        d.index = pd.to_datetime(d.index)
        agg = {"close": "last"}
        if "high" in d:
            agg["high"] = "max"
        if "low" in d:
            agg["low"] = "min"
        if "volume" in d:
            agg["volume"] = "sum"
        out = d.resample(rule).agg(agg).dropna(subset=["close"])
        return out
    except Exception as e:
        logger.debug("second_opinions resample %s: %s", rule, e)
        return None


def technical_ratings(df: pd.DataFrame | None) -> dict[str, dict[str, Any] | None]:
    if df is None or len(df) < 30:
        return {k: None for k, _, _ in TV_HORIZONS}
    return {
        "tv_1d": technical_rating(df),
        "tv_1w": technical_rating(_resample(df, "W-FRI")),
        "tv_1m": technical_rating(_resample(df, "ME")),
    }


# ── Analyst consensus ───────────────────────────────────────────────────────

def analyst_score(dist: dict | None) -> float | None:
    if not dist or not dist.get("total"):
        return None
    t = float(dist["total"])
    return (2 * dist.get("strong_buy", 0) + dist.get("buy", 0) - dist.get("sell", 0) - 2 * dist.get("strong_sell", 0)) / (2 * t)


def _analyst_entry(dist: dict | None) -> dict[str, Any] | None:
    s = analyst_score(dist)
    if s is None:
        return None
    label = label_from_score(s, analyst=True)
    return {
        "score": round(s, 3),
        "label": label,
        "bias": bias_from_label(label),
        "total": dist.get("total"),
        "bullish_pct": dist.get("bullish_pct"),
        "counts": {k: dist.get(k, 0) for k in ("strong_buy", "buy", "hold", "sell", "strong_sell")},
        "provider": dist.get("source"),
    }


def fmp_analyst_distribution(config: dict, ticker: str) -> dict | None:
    """FMP grades-consensus only (no Yahoo fallback) — cheap enough for every EOD row."""
    from signals.analyst_ratings import _ETFS_SKIP, normalize_rating_distribution

    sym = (ticker or "").upper().split("-")[0]
    if sym in _ETFS_SKIP or "-USD" in (ticker or "").upper():
        return None
    try:
        from signals.cache import cached_grades_consensus
        from signals.fmp_client import fetch_grades_consensus, get_api_key

        if not get_api_key(config):
            return None
        raw = cached_grades_consensus(sym, lambda: fetch_grades_consensus(config, sym))
        return normalize_rating_distribution(raw, "fmp")
    except Exception as e:
        logger.debug("fmp analyst dist %s: %s", ticker, e)
        return None


_FH_CACHE: dict[str, tuple[float, dict | None]] = {}
_FH_TTL_S = 12 * 3600


def finnhub_distribution(config: dict, ticker: str) -> dict | None:
    import time

    hit = _FH_CACHE.get((ticker or "").upper())
    if hit and time.time() - hit[0] < _FH_TTL_S:
        return hit[1]
    out = _finnhub_distribution_uncached(config, ticker)
    from signals.finnhub_client import get_api_key

    if get_api_key(config):
        _FH_CACHE[(ticker or "").upper()] = (time.time(), out)
    return out


def _finnhub_distribution_uncached(config: dict, ticker: str) -> dict | None:
    try:
        from signals.analyst_ratings import normalize_rating_distribution
        from signals.finnhub_client import _request, get_api_key

        if not get_api_key(config) or "-USD" in (ticker or "").upper():
            return None
        data = _request(config, "/stock/recommendation", {"symbol": ticker.upper()})
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return normalize_rating_distribution(data[0], "finnhub")
    except Exception as e:
        logger.debug("finnhub dist %s: %s", ticker, e)
    return None


def build_second_opinions(
    config: dict,
    ticker: str,
    df: pd.DataFrame | None,
    *,
    analyst_dist: dict | None = None,
    include_finnhub: bool = True,
) -> dict[str, Any]:
    """Full payload for the ticker page: {opinions: [...], finnhub_configured, note}."""
    tv = technical_ratings(df)
    dist = analyst_dist if analyst_dist is not None else fmp_analyst_distribution(config, ticker)
    fh = finnhub_distribution(config, ticker) if include_finnhub else None
    try:
        from signals.finnhub_client import get_api_key as _fh_key

        fh_configured = bool(_fh_key(config))
    except Exception:
        fh_configured = False
    opinions: list[dict[str, Any]] = []
    for key, tf, horizon in TV_HORIZONS:
        e = tv.get(key)
        opinions.append({"key": key, "source": SOURCE_LABELS[key], "timeframe": tf, "horizon": horizon, **(e or {}), "available": e is not None})
    a = _analyst_entry(dist)
    opinions.append({"key": "analyst", "source": SOURCE_LABELS["analyst"], "horizon": "~12 months", **(a or {}), "available": a is not None})
    f = _analyst_entry(fh)
    opinions.append({"key": "finnhub", "source": SOURCE_LABELS["finnhub"], "horizon": "~12 months", **(f or {}), "available": f is not None})
    return {
        "opinions": opinions,
        "compact": compact_opinions(tv, a, f),
        "finnhub_configured": fh_configured,
        "note": (
            "Technical ratings are our own calculation of TradingView's published method, not TradingView data. "
            "Agreement is not proof; the Track tab scores every source against the same forward returns."
        ),
    }


def compact_opinions(tv: dict[str, Any], analyst: dict | None, finnhub: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, _, _ in TV_HORIZONS:
        e = tv.get(key)
        if e and e.get("label"):
            out[key] = e["label"]
    if analyst and analyst.get("label"):
        out["analyst"] = analyst["label"]
    if finnhub and finnhub.get("label"):
        out["finnhub"] = finnhub["label"]
    return out


def compact_for_row(config: dict, ticker: str, df: pd.DataFrame | None, *, use_fmp: bool = True) -> dict[str, str]:
    """Labels saved on each signal / EOD row so forward tracking can score them later."""
    tv = technical_ratings(df)
    a = _analyst_entry(fmp_analyst_distribution(config, ticker)) if use_fmp else None
    f = _analyst_entry(finnhub_distribution(config, ticker))
    return compact_opinions(tv, a, f)


# ── Forward-tracking scorecard ──────────────────────────────────────────────

def aggregate_second_opinions(records: list[dict[str, Any]], horizons: tuple[int, ...] = (1, 5, 20)) -> dict[str, Any] | None:
    """Per source × bias: avg forward return, edge vs holding the same stock, excess vs SPY.

    Only records that carry saved second opinions are used, and our model is scored on the
    same subset so the comparison is like-for-like.
    """
    from signals.forward_tracking_metrics import _quality_rows

    rows = [
        r for r in _quality_rows(records)
        if isinstance(r.get("second_opinions"), dict) and r.get("actual_return_pct") is not None
    ]
    if not rows:
        return None
    out: dict[str, Any] = {}
    for h in horizons:
        hrows = [r for r in rows if r.get("horizon_days") == h]
        if not hrows:
            continue
        by_tk: dict[str, list[float]] = {}
        for r in hrows:
            by_tk.setdefault(str(r.get("ticker") or "").upper(), []).append(float(r["actual_return_pct"]))
        base = {t: sum(v) / len(v) for t, v in by_tk.items()}
        sources: dict[str, Any] = {}
        for src in SOURCE_LABELS:
            buckets: dict[str, list[dict]] = {}
            for r in hrows:
                lab = r.get("our_signal") if src == "ours" else (r.get("second_opinions") or {}).get(src)
                b = bias_from_label(lab)
                if b:
                    buckets.setdefault(b, []).append(r)
            if not buckets:
                continue
            stats: dict[str, Any] = {}
            for b, grp in buckets.items():
                rets = [float(r["actual_return_pct"]) for r in grp]
                edges = [float(r["actual_return_pct"]) - base[str(r.get("ticker") or "").upper()] for r in grp]
                exc = [float(r["excess_return_pct"]) for r in grp if r.get("excess_return_pct") is not None]
                stats[b] = {
                    "n": len(grp),
                    "tickers": len({str(r.get("ticker") or "").upper() for r in grp}),
                    "avg_return_pct": round(sum(rets) / len(rets), 2),
                    "edge_vs_hold_pct": round(sum(edges) / len(edges), 2),
                    "avg_excess_vs_spy_pct": round(sum(exc) / len(exc), 2) if exc else None,
                }
            spread = None
            if "bullish" in stats and "bearish" in stats:
                spread = round(stats["bullish"]["avg_return_pct"] - stats["bearish"]["avg_return_pct"], 2)
            sources[src] = {"label": SOURCE_LABELS[src], "by_bias": stats, "bull_minus_bear_pct": spread}
        out[str(h)] = {"n": len(hrows), "dates": len({r.get("as_of_date") for r in hrows}), "sources": sources}
    if not out:
        return None
    return {
        "by_horizon": out,
        "note": (
            "Edge vs hold = return after that call minus the same stock's average over all tracked days. "
            "Bull − bear = avg return after bullish calls minus after bearish calls (higher = better ranking). "
            "Overlapping windows; small samples are noisy."
        ),
    }
