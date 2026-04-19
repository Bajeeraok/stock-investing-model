"""
Target calibration: ST/MT band hit rates from historical data.
For each date with enough history, compute st_band/mt_band, then check
if price hit target or stop first within the horizon.

Uses intraday high/low when OHLC is available (same bar: stop before target if both hit — conservative for longs);
falls back to close-only when high/low are missing. This avoids optimistic target / pessimistic stop bias from
close-only paths. (Forward return / bucket backtests in backtest_simple.py use different mechanics.)
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config_loader import load_config
from signals.fetcher import fetch_ohlcv_safe
from signals.indicators import composite_score
from signals.regime import get_regime
from signals.target_bands import add_target_bands, compute_vol_6m, compute_swing_high_low
from signals.fetcher import fetch_ohlcv_dataframe
from signals.volatility import atr_series_wilder


def _st_hit_first_ohlc(
    high,
    low,
    close,
    i: int,
    stop: float,
    target: float,
    days: int,
) -> str | None:
    """
    Per day: target if high >= target before stop if low <= stop (same-bar: stop first — conservative for longs).
    Falls back to close-only if high/low missing.
    """
    use_hl = high is not None and low is not None
    for j in range(1, min(days + 1, len(close) - i)):
        if use_hl:
            try:
                hi = float(high.iloc[i + j])
                lo = float(low.iloc[i + j])
            except Exception:
                hi = lo = float(close.iloc[i + j])
            hit_t = hi >= target
            hit_s = lo <= stop
            if hit_t and hit_s:
                return "stop"
            if hit_s:
                return "stop"
            if hit_t:
                return "target"
        else:
            p = float(close.iloc[i + j])
            if p >= target:
                return "target"
            if p <= stop:
                return "stop"
    return None


def run_target_calibration(
    ticker: str = "SPY",
    period: str = "5y",
    st_days: int = 21,
    mt_days: int = 126,
) -> dict:
    """Compute ST and MT band hit rates; optional breakdown by MA regime and ATR bucket."""
    ohlcv_df = fetch_ohlcv_dataframe(ticker, period)
    close = None
    high = low = None
    atr_ser = None
    if ohlcv_df is not None and not ohlcv_df.empty and "close" in ohlcv_df.columns:
        close = ohlcv_df["close"]
        if {"high", "low", "close"}.issubset(set(ohlcv_df.columns)):
            high = ohlcv_df["high"]
            low = ohlcv_df["low"]
            atr_ser = atr_series_wilder(ohlcv_df["high"], ohlcv_df["low"], ohlcv_df["close"], window=14)
    if close is None:
        close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < 300:
        return {"error": f"Insufficient data for {ticker}"}

    close = close.sort_index()
    if high is not None:
        high = high.reindex(close.index).sort_index()
    if low is not None:
        low = low.reindex(close.index).sort_index()

    st_target_hits = 0
    st_stop_hits = 0
    st_neither = 0
    mt_target_hits = 0
    mt_stop_hits = 0
    mt_neither = 0

    by_regime: dict[str, dict[str, int]] = defaultdict(lambda: {"target": 0, "stop": 0, "neither": 0})

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
        if atr_ser is not None and len(atr_ser) > i:
            try:
                a = float(atr_ser.iloc[i])
                if a > 0:
                    atr = a
            except Exception:
                atr = None
        if atr is None:
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

        result = _st_hit_first_ohlc(high, low, close, i, float(st_stop), float(st_target), st_days)
        if result == "target":
            st_target_hits += 1
            by_regime[regime]["target"] += 1
        elif result == "stop":
            st_stop_hits += 1
            by_regime[regime]["stop"] += 1
        else:
            st_neither += 1
            by_regime[regime]["neither"] += 1

        if mt and isinstance(mt, dict):
            mt_low = mt.get("low")
            mt_high = mt.get("high")
            if mt_low is not None and mt_high is not None:
                result = _st_hit_first_ohlc(high, low, close, i, float(mt_low), float(mt_high), mt_days)
                if result == "target":
                    mt_target_hits += 1
                elif result == "stop":
                    mt_stop_hits += 1
                else:
                    mt_neither += 1

    n_st = st_target_hits + st_stop_hits + st_neither
    n_mt = mt_target_hits + mt_stop_hits + mt_neither

    st_by_regime_out = {}
    for reg, d in by_regime.items():
        n = d["target"] + d["stop"] + d["neither"]
        if n == 0:
            continue
        st_by_regime_out[reg] = {
            "n": n,
            "target_hit_pct": round(100 * d["target"] / n, 1),
            "stop_hit_pct": round(100 * d["stop"] / n, 1),
            "neither_pct": round(100 * d["neither"] / n, 1),
        }

    return {
        "ticker": ticker,
        "period": period,
        "st_days": st_days,
        "mt_days": mt_days,
        "st": {
            "n": n_st,
            "target_hit_pct": round(100 * st_target_hits / n_st, 1) if n_st else None,
            "stop_hit_pct": round(100 * st_stop_hits / n_st, 1) if n_st else None,
            "neither_pct": round(100 * st_neither / n_st, 1) if n_st else None,
        },
        "mt": {
            "n": n_mt,
            "target_hit_pct": round(100 * mt_target_hits / n_mt, 1) if n_mt else None,
            "stop_hit_pct": round(100 * mt_stop_hits / n_mt, 1) if n_mt else None,
            "neither_pct": round(100 * mt_neither / n_mt, 1) if n_mt else None,
        },
        "st_by_regime": st_by_regime_out,
    }


def main() -> None:
    config = load_config()
    tickers = config.get("backtest_tickers", ["SPY", "QQQ"])[:3]
    period = config.get("data", {}).get("period", "5y") or "5y"

    print("TARGET CALIBRATION (ST/MT band hit rates)")
    print("=" * 60)
    print("ST = 21 days, MT = 126 days. Intraday high/low when OHLC available; same-bar stop wins if both hit.")
    print()

    for ticker in tickers:
        out = run_target_calibration(ticker, period)
        if out.get("error"):
            print(f"{ticker}: {out['error']}")
            continue
        print(f"{ticker}:")
        for band, label in [("st", "ST (21d)"), ("mt", "MT (126d)")]:
            d = out.get(band, {})
            n = d.get("n", 0)
            if n == 0:
                continue
            print(f"  {label}: n={n}  target_hit={d.get('target_hit_pct')}%  stop_hit={d.get('stop_hit_pct')}%  neither={d.get('neither_pct')}%")
        br = out.get("st_by_regime") or {}
        if br:
            print("  ST by regime:", br)
        print()

    print("Ideal: target 40-60%, stop 20-40%, neither remainder. Adjust ATR mult in target_bands if needed.")


if __name__ == "__main__":
    main()
