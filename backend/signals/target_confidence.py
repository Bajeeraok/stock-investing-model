"""
Backtest-based confidence for ST/MT target bands.
Buckets by regime and ATR distance; stores hit-rate table; look up confidence for current row.
"""
from __future__ import annotations

import json
from pathlib import Path

# Default path for hit-rate table (under backend/data when run from backend)
def _default_table_path() -> Path:
    for base in [Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent.parent.parent]:
        d = base / "data"
        if d.exists() or base == Path(__file__).resolve().parent.parent:
            d.mkdir(parents=True, exist_ok=True)
            return d / "target_hit_rates.json"
    return Path("data") / "target_hit_rates.json"


def _atr_bucket(distance_atr: float) -> str:
    """Bucket by ATR multiples: 0-1, 1-2, 2-3, 3+."""
    if distance_atr <= 0:
        return "0-1"
    if distance_atr < 1:
        return "0-1"
    if distance_atr < 2:
        return "1-2"
    if distance_atr < 3:
        return "2-3"
    return "3+"


def run_target_confidence_backtest(
    ticker: str,
    period: str = "5y",
    st_days: int = 21,
    mt_days: int = 126,
    fetcher=None,
):
    """
    For each historical date, compute st_band/mt_band, regime, distance in ATR to target.
    Record hit (target hit first) or not; aggregate by (regime, atr_bucket).
    Returns dict: st_buckets, mt_buckets where each is (regime, bucket) -> { hit_rate_pct, n }.
    """
    if fetcher is None:
        from .fetcher import fetch_ohlcv_safe
        fetcher = fetch_ohlcv_safe
    from .indicators import composite_score
    from .regime import get_regime
    from .target_bands import add_target_bands, compute_vol_6m, compute_swing_high_low

    # Prefer full OHLCV so ATR(14) is true-range based (not return-vol proxy)
    ohlcv_df = None
    try:
        from .fetcher import fetch_ohlcv_dataframe
        ohlcv_df = fetch_ohlcv_dataframe(ticker, period)
    except Exception:
        ohlcv_df = None

    close = None
    if ohlcv_df is not None and not ohlcv_df.empty and "close" in ohlcv_df.columns:
        close = ohlcv_df["close"]
    else:
        close = fetcher(ticker, period)

    if close is None:
        return {"error": f"Insufficient data for {ticker} (fetch returned None – check network and yfinance)", "st_buckets": {}, "mt_buckets": {}}
    if len(close) < 300:
        return {"error": f"Insufficient data for {ticker} (got {len(close)} bars, need 300+). Try period='5y' or check data source.", "st_buckets": {}, "mt_buckets": {}}

    close = close.sort_index()
    atr_series = None
    try:
        if ohlcv_df is not None and {"high", "low", "close"}.issubset(set(ohlcv_df.columns)):
            from .volatility import atr_series_wilder
            ohlcv_df = ohlcv_df.sort_index()
            atr_series = atr_series_wilder(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"], window=14)
    except Exception:
        atr_series = None

    def _hit_first(close_ser, i: int, stop: float, target: float, days: int) -> str | None:
        for j in range(1, min(days + 1, len(close_ser) - i)):
            p = float(close_ser.iloc[i + j])
            if target >= stop:
                if p >= target:
                    return "target"
                if p <= stop:
                    return "stop"
            else:
                if p <= target:
                    return "target"
                if p >= stop:
                    return "stop"
        return None

    st_buckets: dict[tuple[str, str], list[bool]] = {}
    mt_buckets: dict[tuple[str, str], list[bool]] = {}

    for i in range(200, len(close) - max(st_days, mt_days) - 1):
        subset = close.iloc[: i + 1]
        if len(subset) < 50:
            continue
        sig = composite_score(subset)
        score = sig.get("composite_buy")
        if score is None:
            continue
        regime = get_regime(score)
        P = float(close.iloc[i])
        vol_6m = compute_vol_6m(subset) or 0.3
        swing_h, swing_l = compute_swing_high_low(subset, 20)
        ma20 = sig.get("ma20") or P
        if swing_h is None:
            swing_h = max(P, ma20)
        if swing_l is None:
            swing_l = min(P, ma20)
        atr = None
        if atr_series is not None and len(atr_series) > i:
            try:
                a = float(atr_series.iloc[i])
                if a > 0:
                    atr = a
            except Exception:
                atr = None
        if atr is None:
            # Fallback proxy (older behaviour) for environments where OHLC is unavailable
            returns = subset.pct_change().dropna().iloc[-14:]
            atr = 0.02 * P
            if len(returns) >= 10 and float(returns.std()) > 0:
                atr = float(returns.std() * P)

        row = {
            "ticker": ticker,
            "price": P,
            "close": P,
            "ma20": float(ma20),
            "atr14": atr,
            "regime": regime,
            "vol_6m": vol_6m,
            "short_suggestion": "HOLD",
            "swing_high_20d": swing_h,
            "swing_low_20d": swing_l,
        }
        add_target_bands(row)
        st = row.get("st_band")
        mt = row.get("mt_band")
        if not st or not isinstance(st, dict):
            continue
        st_stop = st.get("low")
        st_target = st.get("high")
        if st_stop is None or st_target is None:
            continue

        dist_st = (float(st_target) - P) / atr if atr and atr > 0 else 0
        bucket_st = _atr_bucket(dist_st)
        res_st = _hit_first(close, i, float(st_stop), float(st_target), st_days)
        if res_st == "target":
            key = (regime, bucket_st)
            st_buckets.setdefault(key, []).append(True)
        elif res_st == "stop":
            key = (regime, bucket_st)
            st_buckets.setdefault(key, []).append(False)

        if mt and isinstance(mt, dict):
            mt_low = mt.get("low")
            mt_high = mt.get("high")
            if mt_low is not None and mt_high is not None:
                dist_mt = (float(mt_high) - P) / atr if atr and atr > 0 else 0
                bucket_mt = _atr_bucket(dist_mt)
                res_mt = _hit_first(close, i, float(mt_low), float(mt_high), mt_days)
                if res_mt == "target":
                    key = (regime, bucket_mt)
                    mt_buckets.setdefault(key, []).append(True)
                elif res_mt == "stop":
                    key = (regime, bucket_mt)
                    mt_buckets.setdefault(key, []).append(False)

    def _agg(buckets):
        out = {}
        for (regime, bucket), hits in buckets.items():
            n = len(hits)
            hit_rate = round(100 * sum(hits) / n, 1) if n else 0
            key = f"{regime}|{bucket}"
            out[key] = {"hit_rate_pct": hit_rate, "n": n}
        return out

    return {
        "ticker": ticker,
        "st_buckets": _agg(st_buckets),
        "mt_buckets": _agg(mt_buckets),
    }


def load_hit_rates_table(path: Path | None = None) -> dict:
    """Load merged hit-rate table from JSON. Keys: st, mt. Each: regime|bucket -> { hit_rate_pct, n }."""
    path = path or _default_table_path()
    if not path.exists():
        return {"st": {}, "mt": {}}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"st": {}, "mt": {}}


def save_hit_rates_table(merged: dict, path: Path | None = None) -> bool:
    """Save merged hit-rate table. merged = { st: {...}, mt: {...} }."""
    path = path or _default_table_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w") as f:
            json.dump(merged, f, indent=2)
        return True
    except Exception:
        return False


def get_target_confidence(
    regime: str,
    price: float,
    target: float,
    atr: float,
    band_type: str = "st",
    table: dict | None = None,
) -> int | None:
    """
    Look up historical hit rate for (regime, atr_bucket). Return confidence pct or None.
    band_type: "st" or "mt". table from load_hit_rates_table().
    """
    if table is None:
        table = load_hit_rates_table()
    branch = table.get("st" if band_type == "st" else "mt", {})
    if atr is None or atr <= 0:
        atr = 0.02 * price
    distance = (float(target) - price) / atr if atr > 0 else 0
    bucket = _atr_bucket(distance)
    key = f"{regime}|{bucket}"
    entry = branch.get(key)
    if not entry:
        # Fallback: any regime same bucket, or any bucket same regime
        for k, v in branch.items():
            if bucket in k or regime in k:
                return int(round(v.get("hit_rate_pct", 0)))
        return None
    return int(round(entry.get("hit_rate_pct", 0)))
