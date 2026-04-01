"""
Ablation: baseline composite backtest vs macro-gated (historical FRED + VIX).

Point-in-time: daily series are forward-filled from last known FRED print; monthly UNRATE
change is ffilled to daily (approximation — not release-date aware). Use to see whether
filtering “macro bear” days changes buy-bucket forward returns; not a guarantee of live edge.

Earnings-quality historical ablation needs stored fundamentals — not included here.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from signals.fetcher import fetch_ohlcv_safe
from signals.fred_client import (
    SERIES_10Y,
    SERIES_2Y,
    SERIES_HY_OAS,
    SERIES_UNRATE,
    fetch_series_range,
)
from signals.macro_regime import classify_macro_regime

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def _load_backtest_simple():
    spec = importlib.util.spec_from_file_location("backtest_simple", ROOT / "scripts" / "backtest_simple.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_bt = None


def _bt_mod():
    global _bt
    if _bt is None:
        _bt = _load_backtest_simple()
    return _bt


def _obs_to_series(obs: list[dict]) -> pd.Series:
    pts: list[tuple[pd.Timestamp, float]] = []
    for o in obs:
        d = o.get("date")
        v = o.get("value")
        if v in (None, ".") or not d:
            continue
        try:
            pts.append((pd.Timestamp(d), float(v)))
        except (TypeError, ValueError):
            continue
    if not pts:
        return pd.Series(dtype=float)
    s = pd.Series({d: v for d, v in pts})
    return s.sort_index()


def _unrate_mom_series(obs: list[dict]) -> pd.Series:
    """Monthly UNRATE; MoM % change as fraction; index month-end."""
    s = _obs_to_series(obs)
    if s.empty:
        return pd.Series(dtype=float)
    sm = s.resample("M").last().dropna()
    if len(sm) < 2:
        return pd.Series(dtype=float)
    mom = sm.pct_change()
    return mom.dropna()


def build_macro_panel(
    config: dict,
    trading_index: pd.DatetimeIndex,
    *,
    vix_period: str = "5y",
) -> tuple[pd.DataFrame | None, str | None]:
    """
    Align macro factors + macro_score + macro_regime to trading_index.
    """
    if trading_index.empty:
        return None, "empty index"
    start = (trading_index.min() - pd.Timedelta(days=800)).strftime("%Y-%m-%d")
    end = trading_index.max().strftime("%Y-%m-%d")

    o10, e1 = fetch_series_range(config, SERIES_10Y, start, end)
    o2, e2 = fetch_series_range(config, SERIES_2Y, start, end)
    ohy, e3 = fetch_series_range(config, SERIES_HY_OAS, start, end)
    our, e4 = fetch_series_range(config, SERIES_UNRATE, start, end)
    errs = [e1, e2, e3, e4]
    if not o10 or not o2:
        return None, errs[0] or errs[1] or "FRED yield series empty (check FRED_API_KEY)"

    d10 = _obs_to_series(o10).reindex(trading_index).ffill()
    d2 = _obs_to_series(o2).reindex(trading_index).ffill()
    yc = d10 - d2

    hy = (
        _obs_to_series(ohy).reindex(trading_index).ffill()
        if ohy
        else pd.Series(dtype=float, index=trading_index)
    )

    um_m = _unrate_mom_series(our) if our else pd.Series(dtype=float)
    um_daily = um_m.reindex(trading_index).ffill()

    vix_close = fetch_ohlcv_safe("^VIX", vix_period or "5y")
    if vix_close is not None and len(vix_close) > 20:
        vx = vix_close.reindex(trading_index).ffill()
    else:
        vx = pd.Series(dtype=float, index=trading_index)

    rows = []
    for dt in trading_index:
        fac: dict[str, Any] = {}
        ycv = yc.loc[dt] if dt in yc.index else np.nan
        if pd.notna(ycv):
            fac["yield_curve_2s10s"] = round(float(ycv), 3)
        hyv = hy.loc[dt] if dt in hy.index else np.nan
        if pd.notna(hyv):
            fac["hy_oas_bp"] = round(float(hyv), 2)
        vxv = vx.loc[dt] if dt in vx.index else np.nan
        if pd.notna(vxv):
            fac["vix"] = round(float(vxv), 2)
        umv = um_daily.loc[dt] if dt in um_daily.index else np.nan
        if pd.notna(umv):
            fac["unemployment_mom_pct"] = round(float(umv), 4)
        cl = classify_macro_regime(fac)
        rows.append(
            {
                "date": dt,
                "macro_score": cl["macro_score"],
                "macro_regime": cl["macro_regime"],
            }
        )

    df = pd.DataFrame(rows).set_index("date")
    return df, None


def _stats(vals: list[float]) -> dict:
    mod = _bt_mod()
    return mod._stats(vals)


def _gate_pass(
    row: pd.Series,
    min_macro_score: float,
    exclude_bear: bool,
) -> bool:
    if row is None or row.empty:
        return False
    if exclude_bear and row.get("macro_regime") == "BEAR":
        return False
    ms = row.get("macro_score")
    if ms is not None and float(ms) < min_macro_score:
        return False
    return True


def run_macro_gate_ablation(
    ticker: str,
    period: str = "5y",
    *,
    config: dict | None = None,
    buy_bucket_lo: float = 70.0,
    buy_bucket_hi: float = 100.0,
    forward_months: int = 3,
    transaction_cost: float | None = None,
    min_macro_score: float = 40.0,
    exclude_macro_bear: bool = True,
    benchmark_ticker: str = "SPY",
) -> dict[str, Any]:
    """
    Compare forward returns on days in the buy bucket (score in [buy_bucket_lo, buy_bucket_hi))
    with vs without macro gate. Same scoring rules as run_backtest (sector-aware composite).
    """
    mod = _bt_mod()
    if transaction_cost is None:
        transaction_cost = mod.DEFAULT_TRANSACTION_COST

    from signals.composite_bar_score import composite_bar_score_for_backtest
    from signals.backtest_earnings import load_earnings_exclusion_state, should_exclude_bar_for_earnings

    try:
        from config_loader import load_config

        _cfg = load_config() if config is None else config
    except Exception:
        _cfg = config or {}

    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < 250:
        return {"error": f"Insufficient data for {ticker}"}
    close = close.sort_index()

    macro_df, macro_err = build_macro_panel(_cfg, close.index, vix_period=period)
    if macro_df is None:
        return {
            "error": "macro_panel_failed",
            "macro_error": macro_err,
            "hint": "Set data.fred_api_key in config for FRED; VIX uses Yahoo ^VIX.",
        }

    bm_close: pd.Series | None = None
    if benchmark_ticker and benchmark_ticker.upper() != ticker.upper():
        bm_close = fetch_ohlcv_safe(benchmark_ticker, period)
        if bm_close is not None:
            bm_close = bm_close.sort_index()

    trading_days_per_month = 21
    fwd = forward_months * trading_days_per_month

    ecfg = (_cfg.get("backtest") or {}).get("earnings_exclusion") or {}
    earnings_days_before = int(ecfg.get("days_before") or 0)
    sorted_earnings_ts, _ = load_earnings_exclusion_state(_cfg, ticker, close.index)

    baseline_rets: list[float] = []
    gated_rets: list[float] = []
    baseline_bm: list[float] = []
    gated_bm: list[float] = []

    for i in range(200, len(close) - fwd):
        if sorted_earnings_ts is not None and should_exclude_bar_for_earnings(
            close.index[i], sorted_earnings_ts, earnings_days_before
        ):
            continue
        score = composite_bar_score_for_backtest(close, i, ticker, _cfg)
        if score is None or not (buy_bucket_lo <= score < buy_bucket_hi):
            continue

        dt = close.index[i]
        price_today = float(close.iloc[i])
        j = min(i + fwd, len(close) - 1)
        gross_ret = (float(close.iloc[j]) - price_today) / price_today
        net_ret = gross_ret - transaction_cost

        baseline_rets.append(net_ret)

        mrow = macro_df.loc[dt] if dt in macro_df.index else None
        if mrow is not None and _gate_pass(
            mrow,
            min_macro_score=min_macro_score,
            exclude_bear=exclude_macro_bear,
        ):
            gated_rets.append(net_ret)

        if bm_close is not None:
            ts = pd.Timestamp(dt)
            if ts in bm_close.index:
                try:
                    bm_i = bm_close.index.get_loc(ts)
                    bm_j = min(bm_i + fwd, len(bm_close) - 1)
                    bm_p0 = float(bm_close.iloc[bm_i])
                    bm_ret = (float(bm_close.iloc[bm_j]) - bm_p0) / bm_p0 if bm_p0 > 0 else 0.0
                    baseline_bm.append(bm_ret)
                    if mrow is not None and _gate_pass(
                        mrow,
                        min_macro_score=min_macro_score,
                        exclude_bear=exclude_macro_bear,
                    ):
                        gated_bm.append(bm_ret)
                except Exception:
                    pass

    b_base = _stats(baseline_rets)
    b_gated = _stats(gated_rets)
    full_metrics_base = mod.comprehensive_backtest_metrics(
        baseline_rets,
        benchmark_returns=baseline_bm if len(baseline_bm) == len(baseline_rets) else None,
        holding_months=forward_months,
    )
    full_metrics_gated = mod.comprehensive_backtest_metrics(
        gated_rets,
        benchmark_returns=gated_bm if len(gated_bm) == len(gated_rets) else None,
        holding_months=forward_months,
    )

    def _diff_pp(a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        return round(float(a) - float(b), 2)

    return {
        "ticker": ticker.upper(),
        "period": period,
        "buy_bucket": f"{buy_bucket_lo:.0f}-{buy_bucket_hi:.0f}",
        "forward_months": forward_months,
        "gate": {
            "min_macro_score": min_macro_score,
            "exclude_macro_bear": exclude_macro_bear,
        },
        "baseline": {
            "n": b_base["count"],
            "stats_3m": b_base,
            "buy_bucket_metrics": full_metrics_base,
        },
        "gated": {
            "n": b_gated["count"],
            "stats_3m": b_gated,
            "buy_bucket_metrics": full_metrics_gated,
        },
        "delta": {
            "n_lost": b_base["count"] - b_gated["count"],
            "avg_return_pct_diff": _diff_pp(b_gated.get("avg_return_pct"), b_base.get("avg_return_pct")),
            "hit_rate_pp_diff": _diff_pp(b_gated.get("hit_rate"), b_base.get("hit_rate")),
        },
        "note": (
            "Macro panel uses FRED (yields, HY OAS, UNRATE) + Yahoo VIX; "
            "UNRATE change is monthly ffilled. "
            "Positive delta_avg_return means gated (macro filter) beat baseline on average."
        ),
    }
