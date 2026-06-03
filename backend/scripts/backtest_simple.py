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
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from signals.backtest_earnings import load_earnings_exclusion_state, should_exclude_bar_for_earnings
from signals.backtest_regime import (
    aggregate_walk_forward_by_regime,
    align_benchmark_to_index,
    regime_label_at,
    summarize_regime_distribution,
)
from signals.backtest_universe import apply_universe_config
from signals.composite_bar_score import composite_bar_score_for_backtest
from signals.fetcher import fetch_ohlcv_safe
from signals.score_interpretation import backtest_bucket_style_at_bar
from signals.sector_classifier import (
    classify_ticker,
    describe_sector,
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
    config: dict | None = None,
    live_ctx: Any | None = None,
) -> float | None:
    """Delegate to shared composite (MR-aware bucket semantics when enabled)."""
    return composite_bar_score_for_backtest(close, idx, ticker, config, live_ctx=live_ctx)


def _stats(vals: list[float], excess_vals: list[float] | None = None) -> dict:
    """avg_return_pct, hit_rate, count, margin_of_error_pct (95% CI), optional excess vs benchmark."""
    if not vals:
        return {
            "avg_return_pct": None,
            "hit_rate": None,
            "count": 0,
            "margin_of_error_pct": None,
            "avg_excess_vs_benchmark_pct": None,
        }
    n = len(vals)
    mean_pct = round(100 * float(np.mean(vals)), 2)
    hit_rate = round(100 * float(np.mean([1 if v > 0 else 0 for v in vals])), 1)
    margin_of_error_pct = None
    if n >= 2:
        std = float(np.std(vals, ddof=1))
        moe = 1.96 * std / (n ** 0.5)
        margin_of_error_pct = round(100 * moe, 2)
    excess_avg = None
    if excess_vals and len(excess_vals) == n:
        excess_avg = round(100 * float(np.mean(excess_vals)), 2)
    return {
        "avg_return_pct": mean_pct,
        "hit_rate": hit_rate,
        "count": n,
        "margin_of_error_pct": margin_of_error_pct,
        "avg_excess_vs_benchmark_pct": excess_avg,
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


def _bucket_return_ordering_notes(
    results: dict[str, dict[int, dict]],
    horizon_months: int,
) -> list[str]:
    """
    Explain when adjacent *middle* bucket avg returns are out of ordinal order.

    Under MR bucket mapping, labels are not a linear ladder of "expected quality":
    30–50 and 50–70 mix different raw-score regimes after the flip, so 30–50 can
    beat 50–70 at one horizon without contradicting the dip (70–100) vs momentum (0–30) story.
    """
    notes: list[str] = []
    order = ["0-30", "30-50", "50-70", "70-100"]
    avgs: list[tuple[str, float | None]] = []
    for k in order:
        avg = results.get(k, {}).get(horizon_months, {}).get("avg_return_pct")
        avgs.append((k, avg))

    a30 = avgs[1][1]
    a50 = avgs[2][1]
    fifty_seventy_unique_min = False
    if all(avgs[i][1] is not None for i in range(4)):
        a0, a1, a2, a3 = (avgs[i][1] for i in range(4))
        assert a0 is not None and a1 is not None and a2 is not None and a3 is not None
        m = min(a0, a1, a2, a3)
        fifty_seventy_unique_min = a2 == m and sum(1 for x in (a0, a1, a2, a3) if x == m) == 1

    # 30-50 > 50-70: common under MR mapping (middle bins are not an ordinal ladder).
    if a30 is not None and a50 is not None and a30 > a50:
        r30 = results.get("30-50", {}).get(horizon_months, {})
        r50 = results.get("50-70", {}).get(horizon_months, {})
        m30 = r30.get("margin_of_error_pct")
        m50 = r50.get("margin_of_error_pct")
        moe = ""
        if m30 is not None and m50 is not None:
            moe = f" (MoE +/-{m30:.1f}% vs +/-{m50:.1f}% — ranges may overlap)"
        tail = ""
        if fifty_seventy_unique_min:
            tail = (
                " 50-70 was also the weakest of the four buckets here — "
                "often a thinner mixed slice after (100-score) assignment; check 6m and by-year."
            )
        notes.append(
            f"{horizon_months}m: 30-50 avg ({a30:+.1f}%) > 50-70 ({a50:+.1f}%){moe}. "
            "Middle bins blend different raw-score days under MR mapping; "
            "dip-entry story stays 70-100 vs 0-30."
            f"{tail}"
        )
    elif fifty_seventy_unique_min:
        notes.append(
            f"{horizon_months}m: 50-70 had the lowest avg return of the four buckets — "
            "often a thinner / mixed slice after (100-score) assignment; compare 6m and by-year."
        )

    # 70-100 uniquely lowest (e.g. GOOGL 10y): dip-period rows vs momentum rows in a bull-heavy window.
    if all(avgs[i][1] is not None for i in range(4)):
        b0, b1, b2, b3 = (avgs[i][1] for i in range(4))
        assert b0 is not None and b1 is not None and b2 is not None and b3 is not None
        m4 = min(b0, b1, b2, b3)
        if b3 == m4 and sum(1 for x in (b0, b1, b2, b3) if x == m4) == 1:
            n70 = results.get("70-100", {}).get(horizon_months, {}).get("count")
            n_txt = f" N={n70}." if n70 is not None else ""
            notes.append(
                f"{horizon_months}m: 70-100 had the lowest avg return of the four buckets{n_txt} "
                "Under MR mapping, 70-100 labels dip-period rows; in long bull regimes momentum rows (0-30) "
                "often lead at 3m. Check 6m and by-year; do not tune score.buy_min to match this bucket alone."
            )

    return notes


def _mr_spread_summary(
    results: dict[str, dict[int, dict]],
    horizon_months: int,
    *,
    mr_dominated: bool,
) -> dict[str, Any] | None:
    """Dip (70-100) vs momentum (0-30) spread when MR mapping is active."""
    if not mr_dominated:
        return None
    high = results.get("70-100", {}).get(horizon_months, {})
    low = results.get("0-30", {}).get(horizon_months, {})
    h_avg = high.get("avg_return_pct")
    l_avg = low.get("avg_return_pct")
    if h_avg is None or l_avg is None:
        return None
    edge = round(float(h_avg) - float(l_avg), 2)
    return {
        "horizon_months": horizon_months,
        "dip_bucket": "70-100",
        "momentum_bucket": "0-30",
        "dip_avg_return_pct": h_avg,
        "momentum_avg_return_pct": l_avg,
        "edge_pct": edge,
        "dip_n": high.get("count"),
        "momentum_n": low.get("count"),
        "dip_hit_rate_pct": high.get("hit_rate"),
        "momentum_hit_rate_pct": low.get("hit_rate"),
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

    try:
        from config_loader import load_config

        _cfg = load_config()
    except Exception:
        _cfg = {}

    # Fetch benchmark (SPY) for alpha/beta; skip gracefully if ticker IS the benchmark
    bm_close: pd.Series | None = None
    if benchmark_ticker and benchmark_ticker.upper() != ticker.upper():
        bm_close = fetch_ohlcv_safe(benchmark_ticker, period)
        if bm_close is not None:
            bm_close = bm_close.sort_index()

    rc = (_cfg.get("backtest") or {}).get("regime") or {}
    regime_sym = str(rc.get("benchmark") or "SPY").upper()
    ma_days = int(rc.get("ma_days") or 200)
    spy_regime_series = None
    if regime_sym == (benchmark_ticker or "").upper() and bm_close is not None:
        spy_regime_series = align_benchmark_to_index(bm_close, close.index)
    elif regime_sym == ticker.upper():
        spy_regime_series = align_benchmark_to_index(close, close.index)
    else:
        spy_reg = fetch_ohlcv_safe(regime_sym, period)
        if spy_reg is not None:
            spy_regime_series = align_benchmark_to_index(spy_reg.sort_index(), close.index)

    trading_days_per_month = 21
    bucket_keys = [f"{lo:.0f}-{hi:.0f}" for lo, hi in buckets]

    bucket_returns: dict[str, dict[int, list[float]]] = {k: {m: [] for m in forward_months} for k in bucket_keys}
    bucket_bm_returns: dict[str, dict[int, list[float]]] = {k: {m: [] for m in forward_months} for k in bucket_keys}
    bucket_excess_returns: dict[str, dict[int, list[float]]] = {
        k: {m: [] for m in forward_months} for k in bucket_keys
    }

    live_ctx = None
    try:
        from signals.backtest_live_parity import BacktestLiveContext

        live_ctx = BacktestLiveContext.prepare(close.index, period, _cfg)
    except Exception:
        live_ctx = None
    by_year_raw: dict[str, dict[str, dict[int, list[float]]]] = {}
    by_quarter_raw: dict[str, dict[str, dict[int, list[float]]]] = {}
    by_year_excess_raw: dict[str, dict[str, dict[int, list[float]]]] = {}
    by_quarter_excess_raw: dict[str, dict[str, dict[int, list[float]]]] = {}

    mr_bar_count = 0
    trending_bar_count = 0

    sorted_earnings_ts, earnings_exclusion_meta = load_earnings_exclusion_state(_cfg, ticker, close.index)
    ecfg = (_cfg.get("backtest") or {}).get("earnings_exclusion") or {}
    earnings_days_before = int(ecfg.get("days_before") or 0)
    bars_skipped_earnings = 0

    for i in range(200, len(close) - max(forward_months) * trading_days_per_month):
        if sorted_earnings_ts is not None and should_exclude_bar_for_earnings(
            close.index[i], sorted_earnings_ts, earnings_days_before
        ):
            bars_skipped_earnings += 1
            continue
        score = _composite_for_row(close, i, ticker, _cfg, live_ctx=live_ctx)
        if score is None:
            continue
        try:
            st = backtest_bucket_style_at_bar(close, i, ticker, _cfg)
            if st == "MEAN_REVERTING":
                mr_bar_count += 1
            else:
                trending_bar_count += 1
        except Exception:
            trending_bar_count += 1
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
            bm_ret = None
            if bm_close is not None and ts in bm_close.index:
                try:
                    bm_i = bm_close.index.get_loc(ts)
                    bm_j = min(bm_i + months * trading_days_per_month, len(bm_close) - 1)
                    bm_p0 = float(bm_close.iloc[bm_i])
                    bm_ret = (float(bm_close.iloc[bm_j]) - bm_p0) / bm_p0 if bm_p0 > 0 else 0.0
                    bucket_bm_returns[bucket_key][months].append(bm_ret)
                    bucket_excess_returns[bucket_key][months].append(net_ret - bm_ret)
                except Exception:
                    pass

            # By year / quarter
            for period_raw, period_dict, period_excess_dict in [
                (year_str, by_year_raw, by_year_excess_raw),
                (quarter_str, by_quarter_raw, by_quarter_excess_raw),
            ]:
                if period_raw not in period_dict:
                    period_dict[period_raw] = {k: {m: [] for m in forward_months} for k in bucket_keys}
                    period_excess_dict[period_raw] = {k: {m: [] for m in forward_months} for k in bucket_keys}
                period_dict[period_raw][bucket_key][months].append(net_ret)
                if bm_ret is not None:
                    period_excess_dict[period_raw][bucket_key][months].append(net_ret - bm_ret)

    def _aggregate(period_returns: dict, period_excess: dict | None = None) -> dict:
        out = {}
        for pk in period_returns:
            out[pk] = {}
            for bk in bucket_keys:
                out[pk][bk] = {}
                for m in forward_months:
                    ex = None
                    if period_excess and pk in period_excess:
                        ex = period_excess[pk][bk].get(m, [])
                    out[pk][bk][m] = _stats(
                        period_returns[pk][bk].get(m, []),
                        period_excess[pk][bk].get(m, []) if period_excess else None,
                    )
        return out

    results: dict[str, dict[int, dict]] = {}
    for key in bucket_keys:
        results[key] = {
            m: _stats(bucket_returns[key][m], bucket_excess_returns[key][m])
            for m in forward_months
        }

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
    ic = ((_cfg.get("score") or {}).get("interpretation") or {})
    bt_cfg = _cfg.get("backtest") or {}
    apply_live = bool(bt_cfg.get("apply_live_adjustments"))
    live_active = live_ctx is not None and getattr(live_ctx, "enabled", False)
    parity_note = str(bt_cfg.get("parity_note") or "").strip()
    bucket_note = (
        "Buckets use ACF mean-reversion detection: on MR tape, assignment uses (100 − raw score) "
        "so high buckets match dip-buy edge (aligned with score.interpretation). "
        + (
            "Scores include live-parity global regime + market-reversal overlay on each bar "
            "(backtest.apply_live_adjustments)."
            if live_active
            else "Scores use bar composite only — enable backtest.apply_live_adjustments for regime + MRO parity."
        )
        if ic.get("apply_to_backtest_buckets", True)
        else "Buckets use raw composite score only."
    )
    if parity_note:
        bucket_note = f"{bucket_note} {parity_note}"

    n_style = mr_bar_count + trending_bar_count
    if n_style > 0:
        pct_mr = round(100.0 * mr_bar_count / n_style, 1)
        pct_tr = round(100.0 * trending_bar_count / n_style, 1)
        bucket_assignment_stats = {
            "n_bars_scored": n_style,
            "mean_reverting_bar_count": mr_bar_count,
            "trending_bar_count": trending_bar_count,
            "pct_mean_reverting": pct_mr,
            "pct_trending": pct_tr,
        }
    else:
        bucket_assignment_stats = {
            "n_bars_scored": 0,
            "mean_reverting_bar_count": 0,
            "trending_bar_count": 0,
            "pct_mean_reverting": None,
            "pct_trending": None,
        }

    mr_dominated = bool(
        (bucket_assignment_stats.get("pct_mean_reverting") or 0) >= 50
    )

    bucket_return_ordering_notes: list[str] = []
    for hm in forward_months:
        bucket_return_ordering_notes.extend(_bucket_return_ordering_notes(results, hm))

    earnings_exclusion_out = dict(earnings_exclusion_meta)
    earnings_exclusion_out["bars_skipped"] = bars_skipped_earnings

    spy_regime_summary = None
    if spy_regime_series is not None and len(spy_regime_series):
        lo = 200
        hi = len(close) - max(forward_months) * trading_days_per_month
        summ = summarize_regime_distribution(spy_regime_series, lo, hi, ma_days)
        spy_regime_summary = {
            "benchmark": regime_sym,
            "ma_days": ma_days,
            **summ,
            "note": (
                f"{regime_sym} vs {ma_days}d SMA on scored bars — market regime context only; "
                "composite scores unchanged."
            ),
        }

    return {
        "ticker": ticker,
        "period": period,
        "schema_version": 2,
        "score_parity": {
            "apply_live_adjustments": apply_live,
            "live_ctx_active": live_active,
            "question": "A",
            "question_label": "Historical dip edge (backtest buckets)",
            "note": (
                "Not a pass/fail for today's trade — compares bucketed historical forward returns."
            ),
        },
        "bucket_assignment_note": bucket_note,
        "bucket_assignment_stats": bucket_assignment_stats,
        "bucket_return_ordering_notes": bucket_return_ordering_notes,
        "mr_spread_3m": _mr_spread_summary(results, 3, mr_dominated=mr_dominated),
        "mr_spread_6m": _mr_spread_summary(results, 6, mr_dominated=mr_dominated),
        "earnings_exclusion": earnings_exclusion_out,
        "spy_regime_summary": spy_regime_summary,
        "sector": sector,
        "sector_description": describe_sector(ticker),
        "transaction_cost_pct": round(transaction_cost * 100, 3),
        "benchmark": benchmark_ticker,
        "buckets": results,
        "by_year": _aggregate(by_year_raw, by_year_excess_raw),
        "by_quarter": _aggregate(by_quarter_raw, by_quarter_excess_raw),
        "calibration": cal,
        "buy_bucket_metrics": full_metrics,
        "suggested_buy_min": _suggest_band(results, "buy", mr_dominated=mr_dominated),
        "suggested_sell_max": _suggest_band(results, "sell", mr_dominated=mr_dominated),
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

    try:
        from config_loader import load_config

        _wf_cfg = load_config()
    except Exception:
        _wf_cfg = {}

    sorted_earnings_ts, _earn_meta = load_earnings_exclusion_state(_wf_cfg, ticker, close.index)
    ecfg_wf = (_wf_cfg.get("backtest") or {}).get("earnings_exclusion") or {}
    earnings_days_before_wf = int(ecfg_wf.get("days_before") or 0)

    wf_live_ctx = None
    try:
        from signals.backtest_live_parity import BacktestLiveContext

        wf_live_ctx = BacktestLiveContext.prepare(close.index, period, _wf_cfg)
    except Exception:
        wf_live_ctx = None

    rc_wf = (_wf_cfg.get("backtest") or {}).get("regime") or {}
    regime_sym_wf = str(rc_wf.get("benchmark") or "SPY").upper()
    ma_days_wf = int(rc_wf.get("ma_days") or 200)
    spy_wf = fetch_ohlcv_safe(regime_sym_wf, period)
    spy_aligned_wf = align_benchmark_to_index(spy_wf.sort_index(), close.index) if spy_wf is not None else None

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
            if sorted_earnings_ts is not None and should_exclude_bar_for_earnings(
                close.index[i], sorted_earnings_ts, earnings_days_before_wf
            ):
                continue
            score = _composite_for_row(close, i, ticker, _wf_cfg, live_ctx=wf_live_ctx)
            if score is None or score < buy_threshold:
                continue
            price_today = float(close.iloc[i])
            for months in forward_months:
                j = min(i + months * trading_days_per_month, len(close) - 1)
                gross_ret = (float(close.iloc[j]) - price_today) / price_today
                window_returns[months].append(gross_ret - transaction_cost)

        spy_reg = "unknown"
        if spy_aligned_wf is not None:
            spy_reg = regime_label_at(spy_aligned_wf, test_start, ma_days_wf)

        windows.append({
            "train_start": str(close.index[start])[:10],
            "train_end": str(close.index[test_start - 1])[:10],
            "test_start": str(close.index[test_start])[:10],
            "test_end": str(close.index[test_end - 1])[:10],
            "spy_regime": spy_reg,
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

    regime_breakdown = aggregate_walk_forward_by_regime(windows, 3) if windows else {}

    wf_bt = _wf_cfg.get("backtest") or {}
    wf_live = bool(wf_bt.get("apply_live_adjustments")) and wf_live_ctx is not None and wf_live_ctx.enabled

    return {
        "ticker": ticker,
        "sector": classify_ticker(ticker),
        "train_years": train_years,
        "test_months": test_months,
        "buy_threshold": buy_threshold,
        "score_parity": {
            "apply_live_adjustments": bool(wf_bt.get("apply_live_adjustments")),
            "live_ctx_active": wf_live,
            "question": "A",
            "question_label": "Walk-forward OOS (high-score bars only)",
        },
        "transaction_cost_pct": round(transaction_cost * 100, 3),
        "windows": windows,
        "consistency": consistency,
        "earnings_exclusion": _earn_meta,
        "regime_benchmark": regime_sym_wf,
        "regime_ma_days": ma_days_wf,
        "regime_breakdown": regime_breakdown,
        "regime_note": (
            f"Each window labeled by {regime_sym_wf} vs {ma_days_wf}d SMA at test start — "
            "split walk-forward stats by coarse market regime."
        ),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _suggest_band(results: dict, band_type: str, *, mr_dominated: bool = False) -> str:
    try:
        if band_type == "buy":
            cands = [
                (k, v.get(3, {}).get("hit_rate"), v.get(3, {}).get("avg_return_pct"))
                for k, v in results.items()
            ]
            cands = [(k, hr, ar) for k, hr, ar in cands if hr is not None and hr > 55]
            if cands:
                best = max(cands, key=lambda x: (x[1], x[2] or 0))
                if mr_dominated:
                    return (
                        f"MR-mapped buckets: 3m hit-rate leader is {best[0]} ({best[1]:.1f}%) — "
                        "not a raw buy_min threshold. Keep score.buy_min from config; read 70-100 vs 0-30 as dip vs momentum."
                    )
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
    calibration_ok_min = float((config.get("backtest") or {}).get("calibration_ok_min", config.get("score", {}).get("buy_min", 70)))

    tickers, uni_meta = apply_universe_config(
        config,
        tickers,
        backend_root=ROOT,
        fetch_close=fetch_ohlcv_safe,
    )
    if uni_meta.get("note"):
        print(f"  Universe ({uni_meta.get('mode', '?')}): {uni_meta['note']}")
    if uni_meta.get("dropped"):
        print(f"  Dropped: {', '.join(uni_meta['dropped'][:12])}{' …' if len(uni_meta['dropped']) > 12 else ''}")

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
            flag = "OK" if cal["calibration_score"] >= calibration_ok_min and cal.get("monotonic") else "WARN"
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
