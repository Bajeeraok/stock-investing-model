"""
QA harness: compare our indicators (MAs, RSI, returns) vs a reference source.

- Primary: FMP adjusted close when api_key in config, else yfinance.
- Reference: yfinance (same EOD adjusted close from a different vendor).

For 5–10 tickers, computes MA20/50/200, RSI(14), and 1m/3m/6m returns from both
sources, then logs mean absolute % error (MAE). If within ~1–2% on MAs and returns,
and within a few RSI points, we're "close enough" for pro-site parity.

Usage (from repo root or backend):
  python backend/scripts/qa_indicators.py
  python scripts/qa_indicators.py   # when cwd is backend
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config_loader import load_config
from signals.fetcher import fetch_ohlcv_safe, fetch_ohlcv_with_config
from signals.indicators import compute_indicators

# House-style return periods (trading days)
RETURN_PERIODS = {"1m": 21, "3m": 63, "6m": 126}


def _returns_over_periods(close, periods_days: dict) -> dict:
    """Compute % return from last date over each period. {label: pct_return}."""
    if close is None or len(close) < 2:
        return {}
    last = float(close.iloc[-1])
    if last <= 0:
        return {}
    out = {}
    for label, days in periods_days.items():
        if len(close) < days + 1:
            continue
        past_price = float(close.iloc[-1 - days])
        if past_price and past_price > 0:
            out[label] = round(100 * (last - past_price) / past_price, 2)
    return out


def _metrics_from_series(close):
    """Compute last MA20/50/200, RSI, and 1m/3m/6m returns from a close series."""
    if close is None or len(close) < 50:
        return None
    df = compute_indicators(close)
    last = df.iloc[-1]
    ret = _returns_over_periods(close, RETURN_PERIODS)
    return {
        "close": float(last["close"]),
        "MA20": float(last["MA20"]) if last.get("MA20") is not None else None,
        "MA50": float(last["MA50"]) if last.get("MA50") is not None else None,
        "MA200": float(last["MA200"]) if last.get("MA200") is not None else None,
        "RSI": float(last["RSI"]) if last.get("RSI") is not None else None,
        "ret_1m": ret.get("1m"),
        "ret_3m": ret.get("3m"),
        "ret_6m": ret.get("6m"),
    }


def main():
    config = load_config()
    tickers = config.get("qa_indicators", {}).get("tickers") or [
        "META", "NFLX", "SPY", "GLD", "AAPL", "MSFT", "GOOGL"
    ]
    period = config.get("qa_indicators", {}).get("period") or "1y"

    use_fmp = bool(config.get("data", {}).get("fmp_api_key") or config.get("fmp_api_key"))
    primary_label = "FMP" if use_fmp else "yfinance"
    print(f"QA indicators: primary={primary_label}, reference=yfinance")
    print(f"Tickers: {tickers}")
    print(f"Period: {period}")
    print()

    results = []
    for ticker in tickers:
        primary_close = fetch_ohlcv_with_config(ticker, period, config)
        ref_close = fetch_ohlcv_safe(ticker, period)
        primary_m = _metrics_from_series(primary_close)
        ref_m = _metrics_from_series(ref_close)
        if primary_m is None:
            print(f"  {ticker}: skip (primary no data)")
            continue
        if ref_m is None:
            print(f"  {ticker}: skip (reference no data)")
            continue
        results.append({
            "ticker": ticker,
            "primary": primary_m,
            "reference": ref_m,
        })

    if not results:
        print("No tickers had both primary and reference data. Exiting.")
        return

    # Table: ticker | primary close | ref close | MA20 p/r | MA50 p/r | MA200 p/r | RSI p/r | ret_1m p/r | ret_3m p/r | ret_6m p/r
    print("Per-ticker comparison (primary vs reference)")
    print("-" * 100)
    for r in results:
        t, p, ref = r["ticker"], r["primary"], r["reference"]
        ma20_s = f"{p['MA20']:.2f} / {ref['MA20']:.2f}" if p.get("MA20") and ref.get("MA20") else "–"
        ma50_s = f"{p['MA50']:.2f} / {ref['MA50']:.2f}" if p.get("MA50") and ref.get("MA50") else "–"
        ma200_s = f"{p['MA200']:.2f} / {ref['MA200']:.2f}" if p.get("MA200") and ref.get("MA200") else "–"
        rsi_s = f"{p['RSI']:.1f} / {ref['RSI']:.1f}" if p.get("RSI") is not None and ref.get("RSI") is not None else "–"
        ret1 = f"{p['ret_1m']} / {ref['ret_1m']}" if p.get("ret_1m") is not None and ref.get("ret_1m") is not None else "–"
        ret3 = f"{p['ret_3m']} / {ref['ret_3m']}" if p.get("ret_3m") is not None and ref.get("ret_3m") is not None else "–"
        ret6 = f"{p['ret_6m']} / {ref['ret_6m']}" if p.get("ret_6m") is not None and ref.get("ret_6m") is not None else "–"
        print(f"  {t:6}  close {p['close']:.2f}/{ref['close']:.2f}  MA20 {ma20_s}  MA50 {ma50_s}  MA200 {ma200_s}  RSI {rsi_s}  1m {ret1}  3m {ret3}  6m {ret6}")

    # MAE summary
    ma_keys = ["MA20", "MA50", "MA200"]
    rsi_errors = []
    ret_errors = {k: [] for k in ["ret_1m", "ret_3m", "ret_6m"]}
    ma_errors = {k: [] for k in ma_keys}
    for r in results:
        p, ref = r["primary"], r["reference"]
        for k in ma_keys:
            if p.get(k) is not None and ref.get(k) is not None and ref[k] != 0:
                ma_errors[k].append(abs(p[k] - ref[k]) / abs(ref[k]) * 100)
        if p.get("RSI") is not None and ref.get("RSI") is not None:
            rsi_errors.append(abs(p["RSI"] - ref["RSI"]))
        for k in ret_errors:
            if p.get(k) is not None and ref.get(k) is not None:
                ret_errors[k].append(abs(p[k] - ref[k]))

    def mean(lst):
        return sum(lst) / len(lst) if lst else None

    print()
    print("Mean absolute error (MAE)")
    print("-" * 50)
    for k in ma_keys:
        m = mean(ma_errors[k])
        if m is not None:
            print(f"  MAE % {k}:  {m:.3f}%")
    if rsi_errors:
        print(f"  MAE RSI (points):  {mean(rsi_errors):.2f}")
    for k in ["ret_1m", "ret_3m", "ret_6m"]:
        m = mean(ret_errors[k])
        if m is not None:
            print(f"  MAE {k} (pp):  {m:.2f}")

    print()
    ma_all = []
    for k in ma_keys:
        ma_all.extend(ma_errors[k])
    mae_ma_overall = mean(ma_all) if ma_all else None
    mae_rsi = mean(rsi_errors) if rsi_errors else None
    if mae_ma_overall is not None and mae_ma_overall < 2 and (mae_rsi is None or mae_rsi < 5):
        print("  Result: within ~1-2% on MAs and a few RSI points -> close enough for pro-site parity.")
    else:
        print("  Result: review differences (vendor adjustments or rounding). Ensure same price series and time cut-off.")


if __name__ == "__main__":
    main()
