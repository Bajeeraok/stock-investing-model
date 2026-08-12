"""
Unified evaluation harness: one row per (ticker, date) with signals + forward returns.

No lookahead: features use only closes[:i+1]. Use for tuning thresholds vs buy&hold / MA200 baselines.

Horizons (trading days) default: 21 (~1m), 63 (~3m), 126 (~6m), 252 (~12m) — align copy with ST/MT/LT.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from signals.fetcher import fetch_ohlcv_safe
from signals.indicators import compute_indicators, multi_horizon_scores
from signals.regime import get_global_market_regime
from signals.score_interpretation import detect_interpretation_style


def _regime_to_bull_prob(regime: str) -> float:
    return {
        "STRONG_BULL": 0.90,
        "BULL": 0.75,
        "NEUTRAL": 0.50,
        "BEAR": 0.25,
        "STRONG_BEAR": 0.10,
    }.get(regime, 0.50)


def _forward_return_pct(close: pd.Series, t_idx: int, h: int) -> float | None:
    if t_idx + h >= len(close):
        return None
    a = float(close.iloc[t_idx])
    b = float(close.iloc[t_idx + h])
    if a <= 0:
        return None
    return round(100.0 * (b - a) / a, 4)


def _vol_realized(close: pd.Series, t_idx: int, h: int) -> float | None:
    """Annualized realized vol over next h days from daily log returns."""
    if t_idx + h >= len(close):
        return None
    seg = close.iloc[t_idx : t_idx + h + 1].pct_change().dropna()
    if len(seg) < 5:
        return None
    s = float(seg.std())
    if s <= 0:
        return None
    return round(s * math.sqrt(252) * 100.0, 4)


def _baseline_ma200(close: pd.Series, t_idx: int, h: int) -> float | None:
    """Long-only: forward return if close > MA200 at t, else 0 (cash)."""
    if t_idx < 200:
        return None
    sub = close.iloc[: t_idx + 1]
    ma200 = sub.rolling(200, min_periods=200).mean().iloc[-1]
    c = float(close.iloc[t_idx])
    if pd.isna(ma200) or c <= 0:
        return None
    fr = _forward_return_pct(close, t_idx, h)
    if fr is None:
        return None
    return fr if c > float(ma200) else 0.0


def build_evaluation_panel(
    tickers: list[str],
    *,
    config: dict | None = None,
    period: str = "5y",
    step: int = 5,
    horizons: tuple[int, ...] = (21, 63, 126, 252),
    spy_ticker: str = "SPY",
) -> list[dict[str, Any]]:
    """
    Walk calendar with step bars (default 5). Each row: regime, composite, suggestions, interpretation,
    forward returns, baselines. HMM is not refit per bar (too slow); use SPY 5-level regime + MA200 flag.
    """
    config = config or {}
    spy = fetch_ohlcv_safe(spy_ticker, period)
    if spy is None or len(spy) < 300:
        return []

    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        sym = (ticker or "").upper().strip()
        if not sym:
            continue
        close = fetch_ohlcv_safe(sym, period)
        if close is None or len(close) < 300:
            continue
        close = close.dropna()
        spy_aligned = spy.reindex(close.index).ffill().dropna()
        common = close.index.intersection(spy_aligned.index)
        close = close.loc[common]
        spy_aligned = spy_aligned.loc[common]
        if len(close) < 300:
            continue

        min_i = 200
        for i in range(min_i, len(close) - max(horizons) - 1, step):
            c_slice = close.iloc[: i + 1]
            s_slice = spy_aligned.iloc[: i + 1]
            if len(s_slice) < i + 1:
                continue
            try:
                style, sty_meta = detect_interpretation_style(c_slice, config=config, ticker=sym)
            except Exception:
                style, sty_meta = "TRENDING", {}
            try:
                gr = get_global_market_regime(s_slice)
            except Exception:
                gr = "NEUTRAL"
            try:
                sig = multi_horizon_scores(
                    c_slice,
                    ticker=sym,
                    config=config,
                    market_regime=gr,
                    interpretation_style=style,
                )
            except Exception:
                continue

            df_ind = compute_indicators(c_slice)
            last = df_ind.iloc[-1]
            ma200 = last.get("MA200")
            c0 = float(last["close"])
            above200 = bool(pd.notna(ma200) and ma200 and c0 > float(ma200))

            ts = close.index[i]
            date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]

            comp = float(sig.get("composite_buy") or 50)
            rb = _regime_to_bull_prob(gr)
            rec: dict[str, Any] = {
                "ticker": sym,
                "date": date_str,
                "bar_index": i,
                "interpretation_style": style,
                "spy_regime": gr,
                "regime_bull_prob": rb,
                "hmm_bull": None,
                "composite_buy": comp,
                "short_suggestion": sig.get("short_suggestion"),
                "medium_suggestion": sig.get("medium_suggestion"),
                "long_suggestion": sig.get("long_suggestion"),
                "above_ma200": above200,
                "confidence": None,
                "confidence_proxy": round(0.55 * (comp / 100.0) + 0.45 * rb, 4),
            }
            if isinstance(sty_meta, dict) and sty_meta.get("acf_lag1") is not None:
                rec["acf_lag1"] = sty_meta.get("acf_lag1")

            rsi_val = None
            if pd.notna(last.get("rsi")):
                rsi_val = float(last["rsi"])

            for h in horizons:
                fr = _forward_return_pct(close, i, h)
                rec[f"fwd_{h}d_pct"] = fr
                rv = _vol_realized(close, i, h)
                rec[f"rv_ann_{h}d"] = rv
                if fr is not None and rv is not None and rv > 1e-6:
                    rec[f"fwd_vol_adj_{h}d"] = round(fr / (rv / 100.0), 4)
                else:
                    rec[f"fwd_vol_adj_{h}d"] = None
                bh = _baseline_ma200(close, i, h)
                rec[f"baseline_ma200_fwd_{h}d_pct"] = bh

            gb_cfg = (config.get("evaluation") or {}).get("gate_backtest") or {}
            if gb_cfg.get("enabled", True):
                try:
                    from signals.gate_backtest import enrich_row_with_gates

                    # Gate thresholds (retail_action_payload.REGIME_GATE etc.) are 0-100
                    # scale, e.g. ">= 60" — `rb` above is intentionally 0-1 for the
                    # confidence_proxy blend, so convert here rather than changing `rb`
                    # itself. Bug fixed: this previously passed `rb` (max 0.90) straight
                    # into a ">=60" comparison, so the regime gate could never pass in
                    # walk-forward backtests regardless of actual market regime.
                    enrich_row_with_gates(
                        rec,
                        close=c0,
                        sig=sig,
                        regime_bull_pct=rb * 100.0,
                        rsi=rsi_val,
                        indicator_row=last,
                        ticker=sym,
                        market_regime_bull_pct=rb * 100.0,
                        predict_ml=bool(gb_cfg.get("predict_ml", False)),
                        close_series=c_slice,
                        include_confidence_gate=bool(gb_cfg.get("include_confidence_gate", False)),
                    )
                except Exception:
                    pass

            rows.append(rec)

    return rows


def summarize_vs_baselines(
    rows: list[dict[str, Any]],
    horizon: int = 63,
    *,
    buy_min: float = 70.0,
) -> dict[str, Any]:
    """Mean forward return vs buy&hold, when composite>=buy_min, and MA200 long/flat baseline."""
    key = f"fwd_{horizon}d_pct"
    key_ma = f"baseline_ma200_fwd_{horizon}d_pct"
    vals = [float(r[key]) for r in rows if r.get(key) is not None]
    hi = [
        float(r[key])
        for r in rows
        if r.get(key) is not None and float(r.get("composite_buy") or 0) >= buy_min
    ]
    ma_b = [float(r[key_ma]) for r in rows if r.get(key_ma) is not None]
    def _mean(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 4) if xs else None

    return {
        "horizon_trading_days": horizon,
        "buy_min_threshold": buy_min,
        "n": len(vals),
        "mean_buy_hold_fwd_pct": _mean(vals),
        "mean_fwd_when_composite_ge_buy_min": _mean(hi),
        "mean_baseline_ma200_long_or_cash_fwd_pct": _mean(ma_b),
    }


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def equal_weight_portfolio_forward(
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    horizon: int,
) -> list[dict[str, Any]]:
    """For each date present in all tickers, average fwd return (equal weight)."""
    key = f"fwd_{horizon}d_pct"
    by_date: dict[str, list[float]] = {}
    for sym, rows in rows_by_ticker.items():
        for r in rows:
            d = r.get("date")
            v = r.get(key)
            if d and v is not None:
                by_date.setdefault(str(d), []).append(float(v))
    out = []
    for d, vs in sorted(by_date.items()):
        if len(vs) < 2:
            continue
        out.append({"date": d, "ew_fwd_pct": round(sum(vs) / len(vs), 4), "n": len(vs)})
    return out
