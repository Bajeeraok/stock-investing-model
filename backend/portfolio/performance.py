"""
Performance vs benchmark: portfolio total return vs SPY and QQQ over 1m, 3m, 6m, 1y.
Uses historical close from yfinance to compute period returns.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PERIODS = [
    ("1m", 21),
    ("3m", 63),
    ("6m", 126),
    ("1y", 252),
]
_BENCHMARK_TICKERS = ["SPY", "QQQ"]


def _trading_days_ago(close_series, n_days: int) -> float | None:
    """Return close price from n trading days ago. close_series has DatetimeIndex."""
    if close_series is None or len(close_series) < n_days + 1:
        return None
    try:
        return float(close_series.iloc[-1 - n_days])
    except (IndexError, TypeError, ValueError):
        return None


def compute_performance_vs_benchmark(
    holdings: list[dict],
    prices_by_ticker: dict[str, float],
    fetcher,
    period_trading_days: list[tuple[str, int]] | None = None,
    benchmark_tickers: list[str] | None = None,
) -> dict[str, Any]:
    """
    Compute portfolio total return vs benchmarks over multiple periods.

    holdings: [{ticker, quantity}, ...] (consolidated from all portfolios)
    prices_by_ticker: {ticker: current_price} - use for "now"
    fetcher: callable(ticker, period) -> Series | None, e.g. signals.fetcher.fetch_ohlcv_safe
    period_trading_days: [(label, n_days), ...], default 1m/3m/6m/1y
    benchmark_tickers: default SPY, QQQ

    Returns:
      {periods: [{period, portfolio_pct, spy_pct, qqq_pct, vs_spy, vs_qqq}], as_of, error?}
    """
    periods_cfg = period_trading_days or _PERIODS
    benchmarks = benchmark_tickers or _BENCHMARK_TICKERS

    # Current portfolio value
    value_now = 0.0
    holdings_needed: list[tuple[str, float]] = []
    for h in holdings:
        ticker = h.get("ticker") if isinstance(h, dict) else h
        qty = float(h.get("quantity", 1) if isinstance(h, dict) else 1)
        price = prices_by_ticker.get(ticker) if prices_by_ticker else None
        if price is not None and qty > 0:
            value_now += qty * float(price)
            holdings_needed.append((ticker, qty))

    if value_now <= 0 or not holdings_needed:
        return {
            "periods": [],
            "as_of": None,
            "message": "No portfolio value (missing prices or holdings)",
        }

    # Fetch historical close for portfolio tickers and benchmarks (1y covers all periods)
    hist: dict[str, Any] = {}
    all_tickers = list({t for t, _ in holdings_needed} | set(benchmarks))
    for ticker in all_tickers:
        try:
            close = fetcher(ticker, "1y") if callable(fetcher) else None
            hist[ticker] = close
        except Exception as e:
            logger.debug("Historical fetch for %s: %s", ticker, e)
            hist[ticker] = None

    periods_out: list[dict] = []

    for period_label, n_days in periods_cfg:
        # Portfolio value at start of period (only include tickers with valid history)
        value_past = 0.0
        for ticker, qty in holdings_needed:
            series = hist.get(ticker)
            past_close = _trading_days_ago(series, n_days)
            if past_close is not None and past_close > 0:
                value_past += qty * past_close

        portfolio_pct = None
        if value_past > 0:
            portfolio_pct = round(100 * (value_now - value_past) / value_past, 2)

        # Benchmark returns
        spy_pct = None
        qqq_pct = None
        bench_now = {}
        bench_past = {}
        for b in benchmarks:
            s = hist.get(b)
            curr = prices_by_ticker.get(b) if prices_by_ticker else None
            if curr is not None:
                bench_now[b] = float(curr)
            past = _trading_days_ago(s, n_days)
            if past is not None and past > 0:
                bench_past[b] = past
            elif curr is not None:
                bench_past[b] = curr

        if "SPY" in bench_past and bench_past["SPY"] > 0 and "SPY" in bench_now:
            spy_pct = round(100 * (bench_now["SPY"] - bench_past["SPY"]) / bench_past["SPY"], 2)
        if "QQQ" in bench_past and bench_past["QQQ"] > 0 and "QQQ" in bench_now:
            qqq_pct = round(100 * (bench_now["QQQ"] - bench_past["QQQ"]) / bench_past["QQQ"], 2)

        vs_spy = round(portfolio_pct - spy_pct, 2) if portfolio_pct is not None and spy_pct is not None else None
        vs_qqq = round(portfolio_pct - qqq_pct, 2) if portfolio_pct is not None and qqq_pct is not None else None

        periods_out.append({
            "period": period_label,
            "portfolio_pct": portfolio_pct,
            "spy_pct": spy_pct,
            "qqq_pct": qqq_pct,
            "vs_spy": vs_spy,
            "vs_qqq": vs_qqq,
        })

    from signals.time_et import now_iso_et

    return {
        "periods": periods_out,
        "as_of": now_iso_et(),
    }
