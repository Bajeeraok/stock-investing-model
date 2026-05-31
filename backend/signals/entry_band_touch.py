"""
Historical probability that price touches the horizon entry band within N EOD sessions.

Uses the same OHLCV walk as target_confidence (yfinance / fetcher) — not paper-trade logs.
Paper trades track forward outcomes of signals we logged; this table is built from
recomputed entry zones (horizon_entry_calculator) on past bars.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from signals.horizon_entry_calculator import (
    MediumTermInputs,
    ShortTermInputs,
    compute_medium_term_entry,
    compute_short_term_entry,
)
from signals.regime import get_regime
from signals.target_confidence import _atr_bucket

DEFAULT_WINDOWS = {"short": 20, "medium": 63}


def _default_table_path() -> Path:
    for base in [Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent.parent.parent]:
        d = base / "data"
        if d.exists() or base == Path(__file__).resolve().parent.parent:
            d.mkdir(parents=True, exist_ok=True)
            return d / "entry_band_touch_rates.json"
    return Path("data") / "entry_band_touch_rates.json"


def _spot_vs_band(price: float, el: float, eh: float) -> str:
    lo, hi = min(el, eh), max(el, eh)
    if price > hi * 1.002:
        return "above"
    if price < lo * 0.998:
        return "below"
    return "inside"


def _touched_in_window(
    lows: Any,
    highs: Any,
    closes: Any,
    start_i: int,
    el: float,
    eh: float,
    window: int,
) -> tuple[bool, int | None]:
    """First session offset (1..window) where bar intersects [el, eh], else (False, None)."""
    lo_b, hi_b = min(el, eh), max(el, eh)
    n = len(closes)
    for j in range(1, window + 1):
        k = start_i + j
        if k >= n:
            break
        try:
            bar_lo = float(lows.iloc[k]) if lows is not None else float(closes.iloc[k])
            bar_hi = float(highs.iloc[k]) if highs is not None else float(closes.iloc[k])
        except Exception:
            bar_lo = bar_hi = float(closes.iloc[k])
        if bar_lo <= hi_b and bar_hi >= lo_b:
            return True, j
    return False, None


def _inputs_at_bar(
    close,
    i: int,
    *,
    ohlcv_df=None,
    atr_series=None,
) -> dict[str, Any] | None:
    from signals.indicators import composite_score
    from signals.target_bands import compute_swing_high_low

    subset = close.iloc[: i + 1]
    if len(subset) < 50:
        return None
    sig = composite_score(subset)
    score = sig.get("composite_buy")
    if score is None:
        return None
    regime = get_regime(score)
    p = float(close.iloc[i])
    ma20 = float(sig.get("ma20") or p)
    ma50 = float(sig.get("ma50") or ma20)
    ma200 = float(sig.get("ma200") or ma50)
    rsi = float(sig.get("rsi") or 50.0)
    atr = None
    if atr_series is not None and len(atr_series) > i:
        try:
            a = float(atr_series.iloc[i])
            if a > 0:
                atr = a
        except Exception:
            atr = None
    if atr is None:
        returns = subset.pct_change().dropna().iloc[-14:]
        atr = 0.02 * p
        if len(returns) >= 10 and float(returns.std()) > 0:
            atr = float(returns.std() * p)
    swing_h, swing_l = compute_swing_high_low(subset, 20)
    vwap = p
    if ohlcv_df is not None and not ohlcv_df.empty and i < len(ohlcv_df):
        try:
            row = ohlcv_df.iloc[i]
            if "volume" in ohlcv_df.columns and float(row.get("volume") or 0) > 0:
                tp = (float(row["high"]) + float(row["low"]) + float(row["close"])) / 3.0
                vwap = tp
        except Exception:
            pass
    vol_ratio = 1.0
    if ohlcv_df is not None and "volume" in ohlcv_df.columns and i >= 20:
        try:
            vol = ohlcv_df["volume"].iloc[: i + 1]
            avg = float(vol.iloc[-20:].mean())
            last = float(vol.iloc[-1])
            if avg > 0:
                vol_ratio = last / avg
        except Exception:
            pass
    return {
        "regime": regime,
        "price": p,
        "rsi": rsi,
        "atr": atr,
        "vwap": vwap,
        "ma50": ma50,
        "ma200": ma200,
        "support": float(swing_l or min(p, ma20)),
        "resistance": float(swing_h or max(p, ma20)),
        "regime_bull_pct": 55.0 if regime == "UP" else (35.0 if regime == "DOWN" else 50.0),
        "pattern_score": min(100.0, max(0.0, float(score))),
        "volume_ratio": vol_ratio,
        "ml_prob": 50.0,
    }


def run_entry_band_touch_backtest(
    ticker: str,
    period: str = "5y",
    *,
    windows: dict[str, int] | None = None,
    fetcher=None,
) -> dict[str, Any]:
    """
    Walk historical EOD bars; at each date compute ST/MT entry zones and record
    whether price touched the band within the horizon window.
    """
    if fetcher is None:
        from signals.fetcher import fetch_ohlcv_safe

        fetcher = fetch_ohlcv_safe

    windows = windows or DEFAULT_WINDOWS
    max_window = max(windows.values())

    ohlcv_df = None
    try:
        from signals.fetcher import fetch_ohlcv_dataframe

        ohlcv_df = fetch_ohlcv_dataframe(ticker, period)
    except Exception:
        ohlcv_df = None

    close = None
    lows = highs = None
    if ohlcv_df is not None and not ohlcv_df.empty and "close" in ohlcv_df.columns:
        close = ohlcv_df["close"].sort_index()
        if "low" in ohlcv_df.columns:
            lows = ohlcv_df["low"].sort_index()
        if "high" in ohlcv_df.columns:
            highs = ohlcv_df["high"].sort_index()
    else:
        close = fetcher(ticker, period)

    if close is None or len(close) < 300:
        return {
            "error": f"Insufficient data for {ticker}",
            "buckets": {},
        }

    close = close.sort_index()
    atr_series = None
    try:
        if ohlcv_df is not None and {"high", "low", "close"}.issubset(set(ohlcv_df.columns)):
            from signals.volatility import atr_series_wilder

            ohlcv_df = ohlcv_df.sort_index()
            atr_series = atr_series_wilder(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"], window=14)
    except Exception:
        atr_series = None

    # bucket_key -> list of (touched: bool, days: int|None)
    buckets: dict[str, list[tuple[bool, int | None]]] = {}

    for i in range(200, len(close) - max_window - 1):
        inp = _inputs_at_bar(close, i, ohlcv_df=ohlcv_df, atr_series=atr_series)
        if not inp:
            continue
        p = inp["price"]
        regime = inp["regime"]
        atr = inp["atr"]

        short_sig = compute_short_term_entry(
            ShortTermInputs(
                current_price=p,
                ml_prob=inp["ml_prob"],
                rsi=inp["rsi"],
                atr=atr,
                vwap=inp["vwap"],
                support_level=inp["support"],
                resistance_level=inp["resistance"],
                regime_bull_pct=inp["regime_bull_pct"],
                pattern_score=inp["pattern_score"],
                volume_ratio=inp["volume_ratio"],
            )
        )
        st_el, st_eh = short_sig.entry_zone.low, short_sig.entry_zone.high

        med_sig = compute_medium_term_entry(
            MediumTermInputs(
                current_price=p,
                ml_prob=inp["ml_prob"],
                ma50=inp["ma50"],
                ma200=inp["ma200"],
                atr=atr,
                regime_bull_pct=inp["regime_bull_pct"],
                pattern_score=inp["pattern_score"],
                days_to_earnings=None,
                options_sentiment_score=50.0,
                insider_activity_score=50.0,
                fundamentals_score=50.0,
                short_entry_low=st_el,
                short_entry_high=st_eh,
            )
        )
        mt_el, mt_eh = med_sig.entry_zone.low, med_sig.entry_zone.high

        for horizon, el, eh in (
            ("short", st_el, st_eh),
            ("medium", mt_el, mt_eh),
        ):
            w = windows.get(horizon, 20)
            pos = _spot_vs_band(p, el, eh)
            dist_atr = 0.0
            if atr and atr > 0 and pos == "above":
                dist_atr = (p - max(el, eh)) / atr
            elif atr and atr > 0 and pos == "below":
                dist_atr = (min(el, eh) - p) / atr
            bucket_atr = _atr_bucket(dist_atr) if pos != "inside" else "inside"
            key = f"{horizon}|{regime}|{pos}|{bucket_atr}"
            touched, days = _touched_in_window(lows, highs, close, i, el, eh, w)
            buckets.setdefault(key, []).append((touched, days))

    def _agg(entries: list[tuple[bool, int | None]]) -> dict:
        n = len(entries)
        if n == 0:
            return {"touch_rate_pct": 0, "median_sessions_to_touch": None, "n": 0}
        hits = [e for e in entries if e[0]]
        touch_rate = round(100.0 * len(hits) / n, 1)
        days_list = sorted([e[1] for e in hits if e[1] is not None])
        median = None
        if days_list:
            mid = len(days_list) // 2
            median = days_list[mid] if len(days_list) % 2 else (days_list[mid - 1] + days_list[mid]) // 2
        return {
            "touch_rate_pct": touch_rate,
            "median_sessions_to_touch": median,
            "n": n,
        }

    out_buckets = {k: _agg(v) for k, v in buckets.items()}
    return {"ticker": ticker, "buckets": out_buckets, "windows": windows}


def load_entry_touch_table(path: Path | None = None) -> dict:
    path = path or _default_table_path()
    if not path.exists():
        return {"buckets": {}, "windows": DEFAULT_WINDOWS}
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"buckets": {}, "windows": DEFAULT_WINDOWS}


def save_entry_touch_table(merged: dict, path: Path | None = None) -> bool:
    path = path or _default_table_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w") as f:
            json.dump(merged, f, indent=2)
        return True
    except Exception:
        return False


def _merge_bucket_stats(acc: dict, new: dict) -> None:
    for key, val in new.items():
        if key not in acc:
            acc[key] = dict(val)
            continue
        n1, n2 = acc[key].get("n", 0), val.get("n", 0)
        if n1 + n2 == 0:
            continue
        r1, r2 = acc[key].get("touch_rate_pct", 0), val.get("touch_rate_pct", 0)
        m1, m2 = acc[key].get("median_sessions_to_touch"), val.get("median_sessions_to_touch")
        merged_median = None
        if m1 is not None and m2 is not None:
            merged_median = int(round((m1 + m2) / 2))
        elif m1 is not None:
            merged_median = m1
        elif m2 is not None:
            merged_median = m2
        acc[key] = {
            "touch_rate_pct": round((r1 * n1 + r2 * n2) / (n1 + n2), 1),
            "median_sessions_to_touch": merged_median,
            "n": n1 + n2,
        }


def get_entry_band_touch_forecast(
    *,
    regime: str,
    price: float,
    entry_low: float,
    entry_high: float,
    atr: float,
    horizon: str = "short",
    table: dict | None = None,
) -> dict[str, Any] | None:
    """
    Lookup touch probability and median sessions from prebuilt table.
    """
    if table is None:
        table = load_entry_touch_table()
    buckets = table.get("buckets") or {}
    windows = table.get("windows") or DEFAULT_WINDOWS
    window = int(windows.get(horizon, DEFAULT_WINDOWS.get(horizon, 20)))

    if not (price > 0 and entry_low > 0 and entry_high > 0):
        return None

    pos = _spot_vs_band(price, entry_low, entry_high)
    lo_b, hi_b = min(entry_low, entry_high), max(entry_low, entry_high)
    dist_atr = 0.0
    if atr and atr > 0 and pos == "above":
        dist_atr = (price - hi_b) / atr
    elif atr and atr > 0 and pos == "below":
        dist_atr = (lo_b - price) / atr
    bucket_atr = _atr_bucket(dist_atr) if pos != "inside" else "inside"

    key = f"{horizon}|{regime}|{pos}|{bucket_atr}"
    entry = buckets.get(key)
    if not entry and pos == "above":
        for k, v in buckets.items():
            if k.startswith(f"{horizon}|{regime}|above|"):
                entry = v
                break
    if not entry and pos != "inside":
        for k, v in buckets.items():
            if k.startswith(f"{horizon}|{regime}|") and pos in k:
                entry = v
                break

    if not entry or entry.get("n", 0) < 5:
        return None

    touch_pct = entry.get("touch_rate_pct")
    median = entry.get("median_sessions_to_touch")
    n = entry.get("n", 0)

    if pos == "inside":
        note = (
            f"Price is already inside the entry band — historical '{horizon}' setups "
            f"often stayed actionable within {window} sessions (n={n}, pooled index history)."
        )
    elif pos == "above":
        note = (
            f"When spot started ~{dist_atr:.1f} ATR above a similar band in {regime} tape, "
            f"price touched the zone within ~{window} sessions about {touch_pct}% of the time"
            + (f" (median ~{median} sessions when touched)" if median else "")
            + f" — n={n} pooled bars, not a guarantee."
        )
    else:
        note = (
            f"Spot is below band low — touch stats assume pullback from above; "
            f"pooled {regime} history n={n}."
        )

    return {
        "horizon": horizon,
        "window_sessions": window,
        "spot_vs_band": pos,
        "touch_probability_pct": touch_pct,
        "median_sessions_to_touch": median,
        "sample_n": n,
        "data_source": "eod_ohlcv_backtest",
        "note": note,
    }


def enrich_horizons_entry_touch(
    payload: dict[str, Any],
    *,
    regime: str,
    current_price: float,
    atr: float,
    table: dict | None = None,
) -> None:
    """Attach entry_touch_forecast to short/medium horizon dicts in place."""
    for horizon in ("short", "medium"):
        h = payload.get(horizon)
        if not isinstance(h, dict):
            continue
        ez = h.get("entry_zone") or {}
        el = ez.get("low")
        eh = ez.get("high")
        if el is None or eh is None:
            continue
        fc = get_entry_band_touch_forecast(
            regime=regime,
            price=current_price,
            entry_low=float(el),
            entry_high=float(eh),
            atr=float(atr) if atr else current_price * 0.02,
            horizon=horizon,
            table=table,
        )
        if fc:
            h["entry_touch_forecast"] = fc
