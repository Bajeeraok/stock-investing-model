"""
Phase 4: Simple backtest - historical composite scores vs forward 1/3/6 month returns.
Validates that higher score ≈ better forward returns. Use to tune BUY/HOLD/SELL bands.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from signals.fetcher import fetch_ohlcv_safe
from signals.indicators import compute_indicators, composite_score


def _composite_for_row(close: pd.Series, idx: int) -> float | None:
    """Compute composite score for a specific bar (needs enough history before idx)."""
    subset = close.iloc[: idx + 1]
    if len(subset) < 50:
        return None
    sig = composite_score(subset)
    return sig.get("composite_buy")


def run_backtest(
    ticker: str = "SPY",
    period: str = "10y",
    buckets: list[tuple[float, float]] | None = None,
    forward_months: list[int] | None = None,
) -> dict:
    """
    For each date with enough history, compute composite score, bucket it,
    compute forward 1/3/6 month return. Return avg return and hit rate by bucket.
    buckets: [(0,30), (30,50), (50,70), (70,100)] - score bands
    """
    if buckets is None:
        buckets = [(0, 30), (30, 50), (50, 70), (70, 100)]
    if forward_months is None:
        forward_months = [1, 3, 6]

    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < 250:
        return {"error": f"Insufficient data for {ticker}"}

    close = close.sort_index()
    trading_days_per_month = 21

    bucket_returns: dict[str, dict[int, list[float]]] = {}
    for (lo, hi) in buckets:
        key = f"{lo:.0f}-{hi:.0f}"
        bucket_returns[key] = {m: [] for m in forward_months}

    # By year/quarter: period_key -> bucket -> month -> [returns]
    by_year_raw: dict[str, dict[str, dict[int, list[float]]]] = {}
    by_quarter_raw: dict[str, dict[str, dict[int, list[float]]]] = {}

    for i in range(200, len(close) - max(forward_months) * trading_days_per_month):
        score = _composite_for_row(close, i)
        if score is None:
            continue
        price_today = close.iloc[i]
        dt = close.index[i]
        if hasattr(dt, "year"):
            year_str = str(dt.year)
            q = (getattr(dt, "month", 1) - 1) // 3 + 1
            quarter_str = f"{dt.year}-Q{q}"
        else:
            year_str = str(pd.Timestamp(dt).year)
            quarter_str = f"{pd.Timestamp(dt).year}-Q{(pd.Timestamp(dt).month - 1) // 3 + 1}"

        bucket_key = None
        for (lo, hi) in buckets:
            if lo <= score < hi:
                bucket_key = f"{lo:.0f}-{hi:.0f}"
                break
        if bucket_key is None:
            continue

        for months in forward_months:
            j = min(i + months * trading_days_per_month, len(close) - 1)
            price_fwd = close.iloc[j]
            ret = (price_fwd - price_today) / price_today
            bucket_returns[bucket_key][months].append(ret)
            # By year
            if year_str not in by_year_raw:
                by_year_raw[year_str] = {bk: {m: [] for m in forward_months} for bk in [f"{lo:.0f}-{hi:.0f}" for (lo, hi) in buckets]}
            if bucket_key not in by_year_raw[year_str]:
                by_year_raw[year_str][bucket_key] = {m: [] for m in forward_months}
            by_year_raw[year_str][bucket_key][months].append(ret)
            # By quarter
            if quarter_str not in by_quarter_raw:
                by_quarter_raw[quarter_str] = {bk: {m: [] for m in forward_months} for bk in [f"{lo:.0f}-{hi:.0f}" for (lo, hi) in buckets]}
            if bucket_key not in by_quarter_raw[quarter_str]:
                by_quarter_raw[quarter_str][bucket_key] = {m: [] for m in forward_months}
            by_quarter_raw[quarter_str][bucket_key][months].append(ret)

    def _stats(vals: list[float]) -> dict:
        """Return avg_return_pct, hit_rate, count, margin_of_error_pct (95% CI)."""
        if not vals:
            return {"avg_return_pct": None, "hit_rate": None, "count": 0, "margin_of_error_pct": None}
        n = len(vals)
        mean_pct = round(100 * np.mean(vals), 2)
        hit_rate = round(100 * np.mean([1 if v > 0 else 0 for v in vals]), 1)
        if n >= 2:
            std = np.std(vals, ddof=1)
            moe = 1.96 * std / (n ** 0.5)
            margin_of_error_pct = round(100 * moe, 2)
        else:
            margin_of_error_pct = None
        return {"avg_return_pct": mean_pct, "hit_rate": hit_rate, "count": n, "margin_of_error_pct": margin_of_error_pct}

    def _aggregate(period_returns: dict) -> dict:
        out = {}
        for period_key, bucket_data in period_returns.items():
            out[period_key] = {}
            for key, months_data in bucket_data.items():
                out[period_key][key] = {}
                for months in forward_months:
                    vals = months_data.get(months, [])
                    out[period_key][key][months] = _stats(vals)
        return out

    results = {}
    for key in bucket_returns:
        results[key] = {}
        for months in forward_months:
            vals = bucket_returns[key][months]
            results[key][months] = _stats(vals)

    by_year = _aggregate(by_year_raw)
    by_quarter = _aggregate(by_quarter_raw)

    return {
        "ticker": ticker,
        "period": period,
        "buckets": results,
        "by_year": by_year,
        "by_quarter": by_quarter,
        "suggested_buy_min": _suggest_band(results, "buy"),
        "suggested_sell_max": _suggest_band(results, "sell"),
    }


def _suggest_band(results: dict, band_type: str) -> str:
    """Suggest buy_min or sell_max from backtest hit rates (3m)."""
    try:
        if band_type == "buy":
            # Prefer bucket with hit_rate > 55% and best avg return
            cands = [(k, v.get(3, {}).get("hit_rate"), v.get(3, {}).get("avg_return_pct")) for k, v in results.items()]
            cands = [(k, hr, ar) for k, hr, ar in cands if hr is not None and hr > 55]
            if cands:
                best = max(cands, key=lambda x: (x[1], x[2] or 0))
                return f"Consider buy_min >= {best[0].split('-')[0]} (3m hit rate {best[1]:.1f}%)"
        else:
            cands = [(k, v.get(3, {}).get("hit_rate")) for k, v in results.items()]
            bad = [(k, hr) for k, hr in cands if hr is not None and hr < 45]
            if bad:
                worst = min(bad, key=lambda x: x[1])
                return f"Consider sell_max <= {worst[0].split('-')[-1]} (3m hit rate {worst[1]:.1f}%)"
    except Exception:
        pass
    return "Review buckets manually"


def main() -> None:
    import yaml
    config_path = ROOT / "config" / "config.yaml"
    config = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
    tickers = config.get("backtest_tickers", ["SPY", "QQQ"])
    period = config.get("data", {}).get("period", "10y") or "10y"

    print("BACKTEST: Composite score vs forward returns")
    print("=" * 60)
    for ticker in tickers[:3]:  # Limit to 3 to avoid long run
        print(f"\n{ticker} ({period}):")
        out = run_backtest(ticker, period)
        if out.get("error"):
            print(f"  {out['error']}")
            continue
        for bucket, months_data in out["buckets"].items():
            m3 = months_data.get(3, {})
            ar = m3.get("avg_return_pct")
            hr = m3.get("hit_rate")
            cnt = m3.get("count", 0)
            if ar is not None:
                print(f"  Score {bucket:8}  3m avg return: {ar:+.2f}%  hit rate: {hr:.1f}%  (n={cnt})")
        if out.get("suggested_buy_min"):
            print(f"  -> {out['suggested_buy_min']}")
        if out.get("suggested_sell_max"):
            print(f"  -> {out['suggested_sell_max']}")
    print("\nRun with your tickers by adding backtest_tickers: [AAPL, MSFT, ...] to config.")


if __name__ == "__main__":
    main()
