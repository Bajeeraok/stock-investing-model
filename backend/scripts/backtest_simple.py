"""
Phase 4: Simple backtest - historical composite scores vs forward 1/3/6 month returns.
Validates that higher score ≈ better forward returns. Use to tune BUY/HOLD/SELL bands.

Features:
  - Sector-aware composite scoring (different weight profiles per asset class)
  - comprehensive_backtest_metrics(): Sharpe, Sortino, drawdown, profit factor, alpha/beta, IR
  - calibration_score(): does your 70-score bucket actually win 70% of the time?
  - walk_forward_backtest(): discrete out-of-sample windows to check regime robustness
  - Transaction-cost-adjusted returns throughout
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from signals.fetcher import fetch_ohlcv_safe
from signals.indicators import composite_score
from signals.sector_classifier import (
    classify_ticker,
    describe_sector,
    get_sector_score_bias,
    get_sector_weights,
)

# Default round-trip transaction cost: 0.10% commission + 0.05% slippage each way
DEFAULT_TRANSACTION_COST = 0.0030  # 0.30% total (entry + exit)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _composite_for_row(
    close: pd.Series,
    idx: int,
    ticker: str = "",
) -> float | None:
    """
    Compute sector-aware composite score for bar idx using only data up to that bar.
    Applies sector weight profile and score bias for the ticker.
    """
    subset = close.iloc[: idx + 1]
    if len(subset) < 50:
        return None
    weights = get_sector_weights(ticker) if ticker else None
    sig = composite_score(subset, weights=weights)
    raw = sig.get("composite_buy")
    if raw is None:
        return None
    bias = get_sector_score_bias(ticker) if ticker else 0.0
    return float(np.clip(raw + bias, 0.0, 100.0))


def _stats(vals: list[float]) -> dict:
    """avg_return_pct, hit_rate, count, margin_of_error_pct (95% CI)."""
    if not vals:
        return {"avg_return_pct": None, "hit_rate": None, "count": 0, "margin_of_error_pct": None}
    n = len(vals)
    mean_pct = round(100 * float(np.mean(vals)), 2)
    hit_rate = round(100 * float(np.mean([1 if v > 0 else 0 for v in vals])), 1)
    margin_of_error_pct = None
    if n >= 2:
        std = float(np.std(vals, ddof=1))
        moe = 1.96 * std / (n ** 0.5)
        margin_of_error_pct = round(100 * moe, 2)
    return {
        "avg_return_pct": mean_pct,
        "hit_rate": hit_rate,
        "count": n,
        "margin_of_error_pct": margin_of_error_pct,
    }


# ---------------------------------------------------------------------------
# Comprehensive metrics
# ---------------------------------------------------------------------------

def comprehensive_backtest_metrics(
    returns: list[float],
    benchmark_returns: list[float] | None = None,
    holding_months: int = 3,
) -> dict:
    """
    Institutional-quality metrics for a list of per-trade forward returns.

    returns:           per-trade forward returns as fractions (not %)
    benchmark_returns: SPY returns for the same holding periods (same length)
    holding_months:    used to annualise Sharpe/Sortino/IR

    Metrics returned:
      - Sharpe, Sortino (annualised)
      - Max drawdown + duration (in trade-count units)
      - Win rate, profit factor, avg win/loss ratio
      - Alpha, beta, information ratio vs benchmark (if provided)
    """
    if not returns:
        return {"error": "no returns"}

    arr = np.array(returns, dtype=float)
    n = len(arr)

    # Annualisation: scale from per-holding-period to per-year
    ann_factor = np.sqrt(max(12 / holding_months, 1))

    # Return quality
    total_return = float(np.prod(1 + arr) - 1)
    years_approx = max(n * holding_months / 12, 0.5)
    cagr = float((1 + total_return) ** (1.0 / years_approx) - 1)

    mean_ret = float(arr.mean())
    std_ret = float(arr.std(ddof=1)) if n > 1 else 0.0
    sharpe = round(mean_ret / std_ret * ann_factor, 2) if std_ret > 0 else 0.0

    downside = arr[arr < 0]
    std_down = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino_raw = mean_ret / std_down * ann_factor if std_down > 0 else float("inf")
    sortino = round(min(sortino_raw, 99.99), 2)

    # Drawdown on equity curve (sequential trade ordering — approximate for overlapping signals)
    equity = np.cumprod(1 + arr)
    rolling_max = np.maximum.accumulate(equity)
    dd = (equity - rolling_max) / rolling_max
    max_drawdown = float(dd.min())
    # Longest consecutive stretch spent in drawdown (in trades)
    max_dd_duration, cur = 0, 0
    for in_dd in (dd < 0):
        cur = cur + 1 if in_dd else 0
        max_dd_duration = max(max_dd_duration, cur)

    # Signal quality
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    win_rate = float((arr > 0).mean())
    pf_raw = float(wins.sum()) / abs(float(losses.sum())) if len(losses) > 0 and losses.sum() != 0 else float("inf")
    profit_factor = round(min(pf_raw, 99.99), 2)
    wl_raw = float(wins.mean()) / abs(float(losses.mean())) if len(wins) > 0 and len(losses) > 0 else float("inf")
    avg_win_loss_ratio = round(min(wl_raw, 99.99), 2)

    # Vs benchmark
    alpha, beta_val, info_ratio = None, None, None
    if benchmark_returns is not None and len(benchmark_returns) == n:
        bm = np.array(benchmark_returns, dtype=float)
        bm_var = float(bm.var())
        if bm_var > 0:
            beta_val = round(float(np.cov(arr, bm)[0, 1] / bm_var), 3)
            alpha = round(float(mean_ret - beta_val * bm.mean()) * 100, 3)
        excess = arr - bm
        excess_std = float(excess.std(ddof=1)) if len(excess) > 1 else 0.0
        if excess_std > 0:
            info_ratio = round(float(excess.mean() / excess_std * ann_factor), 2)

    return {
        "n_trades": n,
        "holding_months": holding_months,
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "max_drawdown_duration_trades": max_dd_duration,
        "win_rate_pct": round(win_rate * 100, 1),
        "profit_factor": profit_factor,
        "avg_win_loss_ratio": avg_win_loss_ratio,
        "alpha_per_trade_pct": alpha,
        "beta": beta_val,
        "information_ratio": info_ratio,
    }


def calibration_score(bucket_hit_rates: dict[str, float]) -> dict:
    """
    Calibration: do higher score buckets actually win more often?

    bucket_hit_rates: {'0-30': 40.2, '30-50': 48.1, '50-70': 55.3, '70-100': 63.4}

    A well-calibrated signal has:
      1. Monotonically increasing hit rates across buckets
      2. High correlation between bucket midpoint and hit rate
      3. Meaningful spread (>10pp) between lowest and highest bucket

    If your 70-100 bucket only wins 52% vs 48% for 30-50, your confidence
    scores are misleading — they look different but predict the same outcome.
    """
    ordered = ["0-30", "30-50", "50-70", "70-100"]
    midpoints = [15.0, 40.0, 60.0, 85.0]
    rates = [(bucket_hit_rates.get(k), m) for k, m in zip(ordered, midpoints) if bucket_hit_rates.get(k) is not None]

    if len(rates) < 2:
        return {"calibration_score": None, "monotonic": None, "notes": ["insufficient buckets"]}

    rate_vals = [r for r, _ in rates]
    mid_vals = [m for _, m in rates]

    # Monotonicity violations: bucket[i+1] should be > bucket[i]
    violations = sum(1 for a, b in zip(rate_vals, rate_vals[1:]) if b <= a)
    monotonic = violations == 0

    # Pearson correlation between midpoint and hit rate
    if len(rate_vals) >= 2:
        corr = float(np.corrcoef(mid_vals, rate_vals)[0, 1])
        cal_score = round(float(np.clip(corr * 100, 0, 100)), 1)
    else:
        corr, cal_score = 0.0, 0.0

    spread_pp = round(rate_vals[-1] - rate_vals[0], 1)

    notes = []
    if not monotonic:
        notes.append(
            f"{violations} monotonicity violation(s) — a higher score bucket has a lower win rate"
        )
    if spread_pp < 10:
        notes.append(
            f"spread only {spread_pp:.1f}pp between lowest and highest bucket — "
            "scores have weak predictive power"
        )
    if cal_score < 60:
        notes.append(
            "calibration < 60 — confidence scores are poorly calibrated "
            "(a 70-score signal doesn't win 70% of the time)"
        )
    if not notes and cal_score >= 80 and monotonic:
        notes.append("well-calibrated — score buckets reliably predict win-rate ordering")

    return {
        "calibration_score": cal_score,
        "monotonic": monotonic,
        "spread_pp": spread_pp,
        "corr_score_vs_winrate": round(corr, 3),
        "hit_rates_by_bucket": {k: bucket_hit_rates.get(k) for k in ordered},
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Main backtest
# ---------------------------------------------------------------------------

def run_backtest(
    ticker: str = "SPY",
    period: str = "10y",
    buckets: list[tuple[float, float]] | None = None,
    forward_months: list[int] | None = None,
    transaction_cost: float = DEFAULT_TRANSACTION_COST,
    benchmark_ticker: str = "SPY",
) -> dict:
    """
    For each date with enough history, compute sector-aware composite score, bucket it,
    compute forward 1/3/6 month return net of transaction costs.

    Also returns:
      - comprehensive_backtest_metrics for the buy bucket (score 70-100) at 3m horizon
      - calibration_score across all buckets
      - sector profile used for scoring
    """
    if buckets is None:
        buckets = [(0, 30), (30, 50), (50, 70), (70, 100)]
    if forward_months is None:
        forward_months = [1, 3, 6]

    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < 250:
        return {"error": f"Insufficient data for {ticker}"}
    close = close.sort_index()

    # Fetch benchmark (SPY) for alpha/beta; skip gracefully if ticker IS the benchmark
    bm_close: pd.Series | None = None
    if benchmark_ticker and benchmark_ticker.upper() != ticker.upper():
        bm_close = fetch_ohlcv_safe(benchmark_ticker, period)
        if bm_close is not None:
            bm_close = bm_close.sort_index()

    trading_days_per_month = 21
    bucket_keys = [f"{lo:.0f}-{hi:.0f}" for lo, hi in buckets]

    bucket_returns: dict[str, dict[int, list[float]]] = {k: {m: [] for m in forward_months} for k in bucket_keys}
    bucket_bm_returns: dict[str, dict[int, list[float]]] = {k: {m: [] for m in forward_months} for k in bucket_keys}
    by_year_raw: dict[str, dict[str, dict[int, list[float]]]] = {}
    by_quarter_raw: dict[str, dict[str, dict[int, list[float]]]] = {}

    for i in range(200, len(close) - max(forward_months) * trading_days_per_month):
        score = _composite_for_row(close, i, ticker)
        if score is None:
            continue
        price_today = float(close.iloc[i])
        dt = close.index[i]
        ts = pd.Timestamp(dt)
        year_str = str(ts.year)
        quarter_str = f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"

        bucket_key = next(
            (f"{lo:.0f}-{hi:.0f}" for lo, hi in buckets if lo <= score < hi), None
        )
        if bucket_key is None:
            continue

        for months in forward_months:
            j = min(i + months * trading_days_per_month, len(close) - 1)
            gross_ret = (float(close.iloc[j]) - price_today) / price_today
            net_ret = gross_ret - transaction_cost
            bucket_returns[bucket_key][months].append(net_ret)

            # Benchmark return for the same window
            if bm_close is not None and ts in bm_close.index:
                try:
                    bm_i = bm_close.index.get_loc(ts)
                    bm_j = min(bm_i + months * trading_days_per_month, len(bm_close) - 1)
                    bm_p0 = float(bm_close.iloc[bm_i])
                    bm_ret = (float(bm_close.iloc[bm_j]) - bm_p0) / bm_p0 if bm_p0 > 0 else 0.0
                    bucket_bm_returns[bucket_key][months].append(bm_ret)
                except Exception:
                    pass

            # By year / quarter
            for period_raw, period_dict in [(year_str, by_year_raw), (quarter_str, by_quarter_raw)]:
                if period_raw not in period_dict:
                    period_dict[period_raw] = {k: {m: [] for m in forward_months} for k in bucket_keys}
                period_dict[period_raw][bucket_key][months].append(net_ret)

    def _aggregate(period_returns: dict) -> dict:
        return {
            pk: {bk: {m: _stats(period_returns[pk][bk].get(m, [])) for m in forward_months} for bk in bucket_keys}
            for pk in period_returns
        }

    results: dict[str, dict[int, dict]] = {}
    for key in bucket_keys:
        results[key] = {m: _stats(bucket_returns[key][m]) for m in forward_months}

    # Calibration: hit rates across all buckets at 3-month horizon
    bucket_hit_rates_3m = {
        k: results[k][3]["hit_rate"]
        for k in bucket_keys
        if results[k][3]["hit_rate"] is not None
    }
    cal = calibration_score(bucket_hit_rates_3m)

    # Comprehensive metrics on the buy bucket (70-100) at 3m
    buy_bucket = "70-100"
    buy_returns_3m = bucket_returns.get(buy_bucket, {}).get(3, [])
    buy_bm_returns_3m = bucket_bm_returns.get(buy_bucket, {}).get(3, [])
    full_metrics = comprehensive_backtest_metrics(
        buy_returns_3m,
        benchmark_returns=buy_bm_returns_3m if len(buy_bm_returns_3m) == len(buy_returns_3m) else None,
        holding_months=3,
    )

    sector = classify_ticker(ticker)

    return {
        "ticker": ticker,
        "period": period,
        "sector": sector,
        "sector_description": describe_sector(ticker),
        "transaction_cost_pct": round(transaction_cost * 100, 3),
        "benchmark": benchmark_ticker,
        "buckets": results,
        "by_year": _aggregate(by_year_raw),
        "by_quarter": _aggregate(by_quarter_raw),
        "calibration": cal,
        "buy_bucket_metrics": full_metrics,
        "suggested_buy_min": _suggest_band(results, "buy"),
        "suggested_sell_max": _suggest_band(results, "sell"),
    }


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def walk_forward_backtest(
    ticker: str = "SPY",
    period: str = "10y",
    train_years: int = 3,
    test_months: int = 6,
    buy_threshold: float = 65.0,
    forward_months: list[int] | None = None,
    transaction_cost: float = DEFAULT_TRANSACTION_COST,
) -> dict:
    """
    Walk-forward out-of-sample validation.

    Divides history into discrete train/test windows rolling forward by test_months.
    Signals are computed using only data available up to each bar (no lookahead).
    Only evaluates bars in the test window where score >= buy_threshold.

    Returns per-window performance so you can check if the signal holds up
    across bull, bear, and sideways regimes — not just in aggregate.
    """
    if forward_months is None:
        forward_months = [1, 3, 6]

    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < 252:
        return {"error": f"Insufficient data for {ticker}"}
    close = close.sort_index()

    trading_days_per_month = 21
    train_bars = train_years * 252
    test_bars = test_months * trading_days_per_month
    max_fwd_bars = max(forward_months) * trading_days_per_month

    windows: list[dict] = []
    start = 0

    while start + train_bars + max_fwd_bars < len(close):
        test_start = start + train_bars
        test_end = min(test_start + test_bars, len(close) - max_fwd_bars)
        if test_end <= test_start:
            break

        window_returns: dict[int, list[float]] = {m: [] for m in forward_months}

        for i in range(test_start, test_end):
            score = _composite_for_row(close, i, ticker)
            if score is None or score < buy_threshold:
                continue
            price_today = float(close.iloc[i])
            for months in forward_months:
                j = min(i + months * trading_days_per_month, len(close) - 1)
                gross_ret = (float(close.iloc[j]) - price_today) / price_today
                window_returns[months].append(gross_ret - transaction_cost)

        windows.append({
            "train_start": str(close.index[start])[:10],
            "train_end": str(close.index[test_start - 1])[:10],
            "test_start": str(close.index[test_start])[:10],
            "test_end": str(close.index[test_end - 1])[:10],
            "results": {m: _stats(window_returns[m]) for m in forward_months},
        })
        start += test_bars

    # Consistency summary: low hit-rate std = signal held up across regimes
    consistency: dict[int, dict] = {}
    for months in forward_months:
        hit_rates = [w["results"][months]["hit_rate"] for w in windows if w["results"][months]["hit_rate"] is not None]
        avg_returns = [w["results"][months]["avg_return_pct"] for w in windows if w["results"][months]["avg_return_pct"] is not None]
        if hit_rates:
            std_hr = round(float(np.std(hit_rates)), 1)
            consistency[months] = {
                "avg_hit_rate_pct": round(float(np.mean(hit_rates)), 1),
                "std_hit_rate_pct": std_hr,
                "avg_net_return_pct": round(float(np.mean(avg_returns)), 2) if avg_returns else None,
                "consistent": std_hr < 15.0,
                "window_count": len(hit_rates),
            }

    return {
        "ticker": ticker,
        "sector": classify_ticker(ticker),
        "train_years": train_years,
        "test_months": test_months,
        "buy_threshold": buy_threshold,
        "transaction_cost_pct": round(transaction_cost * 100, 3),
        "windows": windows,
        "consistency": consistency,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _suggest_band(results: dict, band_type: str) -> str:
    try:
        if band_type == "buy":
            cands = [
                (k, v.get(3, {}).get("hit_rate"), v.get(3, {}).get("avg_return_pct"))
                for k, v in results.items()
            ]
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


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import yaml
    config_path = ROOT / "config" / "config.yaml"
    config = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}

    tickers = config.get("backtest_tickers", ["SPY", "QQQ"])
    period = config.get("data", {}).get("period", "10y") or "10y"
    txn_cost = config.get("backtest_transaction_cost", DEFAULT_TRANSACTION_COST)

    print("BACKTEST: Sector-aware composite score vs forward returns (net of transaction costs)")
    print(f"  Transaction cost: {txn_cost*100:.2f}% round-trip  |  Benchmark: SPY")
    print("=" * 80)

    for ticker in tickers[:6]:
        out = run_backtest(ticker, period, transaction_cost=txn_cost)
        if out.get("error"):
            print(f"\n{ticker}: {out['error']}")
            continue

        sector_label = out.get("sector_description", out.get("sector", ""))
        print(f"\n{ticker}  [{sector_label}]")

        for bucket, months_data in out["buckets"].items():
            m3 = months_data.get(3, {})
            ar, hr, cnt = m3.get("avg_return_pct"), m3.get("hit_rate"), m3.get("count", 0)
            if ar is not None:
                print(f"  Score {bucket:8}  3m net: {ar:+.2f}%  win rate: {hr:.1f}%  (n={cnt})")

        if out.get("suggested_buy_min"):
            print(f"  -> {out['suggested_buy_min']}")
        if out.get("suggested_sell_max"):
            print(f"  -> {out['suggested_sell_max']}")

        # Calibration
        cal = out.get("calibration", {})
        if cal.get("calibration_score") is not None:
            flag = "OK" if cal["calibration_score"] >= 70 and cal.get("monotonic") else "WARN"
            print(
                f"  Calibration: {cal['calibration_score']:.0f}/100  "
                f"spread {cal.get('spread_pp', 0):.1f}pp  monotonic={cal.get('monotonic')}  [{flag}]"
            )
            for note in cal.get("notes", []):
                print(f"    ! {note}")

        # Buy-bucket comprehensive metrics
        bm = out.get("buy_bucket_metrics", {})
        if bm and not bm.get("error") and bm.get("n_trades", 0) > 0:
            print(
                f"  Buy-bucket (70-100): Sharpe {bm.get('sharpe', '-')}  "
                f"Sortino {bm.get('sortino', '-')}  "
                f"MaxDD {bm.get('max_drawdown_pct', 0):.1f}%  "
                f"PF {bm.get('profit_factor', '-')}  "
                f"W/L {bm.get('avg_win_loss_ratio', '-')}"
            )
            if bm.get("alpha_per_trade_pct") is not None:
                print(
                    f"    Alpha {bm['alpha_per_trade_pct']:+.3f}%/trade  "
                    f"Beta {bm.get('beta', '-')}  "
                    f"IR {bm.get('information_ratio', '-')}"
                )

    print("\n" + "=" * 80)
    print("WALK-FORWARD VALIDATION (3yr train / 6mo test windows)")
    print("  High hit-rate std (>15pp) = signal is regime-sensitive, not robust.")
    print("=" * 80)

    for ticker in tickers[:4]:
        wf = walk_forward_backtest(ticker, period, transaction_cost=txn_cost)
        if wf.get("error"):
            print(f"\n{ticker}: {wf['error']}")
            continue
        print(f"\n{ticker}  [sector: {wf.get('sector', '?')}]")
        for w in wf["windows"]:
            r3 = w["results"].get(3, {})
            ar, hr, cnt = r3.get("avg_return_pct"), r3.get("hit_rate"), r3.get("count", 0)
            label = f"  [{w['test_start']} – {w['test_end']}]"
            if cnt == 0:
                print(f"{label}  no signals above threshold")
            elif ar is not None:
                print(f"{label}  3m net: {ar:+.2f}%  win rate: {hr:.1f}%  (n={cnt})")
        c3 = wf["consistency"].get(3, {})
        if c3:
            flag = "OK" if c3["consistent"] else "WARN — inconsistent across regimes"
            print(
                f"  Consistency 3m: avg win rate {c3['avg_hit_rate_pct']:.1f}%  "
                f"std {c3['std_hit_rate_pct']:.1f}pp  [{flag}]"
            )


if __name__ == "__main__":
    main()
