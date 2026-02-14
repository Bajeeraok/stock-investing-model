"""
Target calibration: ST/MT band hit rates from historical data.
For each date with enough history, compute st_band/mt_band, then check
if price hit target or stop first within the horizon.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config_loader import load_config
from signals.fetcher import fetch_ohlcv_safe
from signals.indicators import composite_score
from signals.regime import get_regime
from signals.target_bands import add_target_bands, compute_vol_6m, compute_swing_high_low


def _st_hit_first(close, i: int, stop: float, target: float, days: int) -> str | None:
    """Check next N days: target hit first, stop hit first, or neither. Returns 'target'|'stop'|None."""
    for j in range(1, min(days + 1, len(close) - i)):
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
    """Compute ST and MT band hit rates."""
    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < 300:
        return {"error": f"Insufficient data for {ticker}"}

    close = close.sort_index()
    st_target_hits = 0
    st_stop_hits = 0
    st_neither = 0
    mt_target_hits = 0
    mt_stop_hits = 0
    mt_neither = 0

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

        # ST hit check
        result = _st_hit_first(close, i, float(st_stop), float(st_target), st_days)
        if result == "target":
            st_target_hits += 1
        elif result == "stop":
            st_stop_hits += 1
        else:
            st_neither += 1

        # MT hit check (if we have mt_band)
        if mt and isinstance(mt, dict):
            mt_low = mt.get("low")
            mt_high = mt.get("high")
            if mt_low is not None and mt_high is not None:
                result = _st_hit_first(close, i, float(mt_low), float(mt_high), mt_days)
                if result == "target":
                    mt_target_hits += 1
                elif result == "stop":
                    mt_stop_hits += 1
                else:
                    mt_neither += 1

    n_st = st_target_hits + st_stop_hits + st_neither
    n_mt = mt_target_hits + mt_stop_hits + mt_neither
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
    }


def main() -> None:
    config = load_config()
    tickers = config.get("backtest_tickers", ["SPY", "QQQ"])[:3]
    period = config.get("data", {}).get("period", "5y") or "5y"

    print("TARGET CALIBRATION (ST/MT band hit rates)")
    print("=" * 60)
    print("ST = 21 days, MT = 126 days. Target hit first vs stop hit first vs neither.")
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
        print()

    print("Ideal: target 40-60%, stop 20-40%, neither remainder. Adjust ATR mult in target_bands if needed.")


if __name__ == "__main__":
    main()
