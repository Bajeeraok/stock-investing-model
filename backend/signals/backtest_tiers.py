"""
Backtest tier enhancements (Questions A/B/C):

  Tier 1 — rule strategy sim, gate cohorts, exit/SELL validation
  Tier 2 — regime-conditional buckets, per-ticker threshold hints, earnings auto for stocks
  Tier 3 — non-overlapping trades, primary KPIs (MR spread 6m + walk-forward 6m), forward-tracking link
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd

from signals.backtest_earnings import load_earnings_exclusion_state, should_exclude_bar_for_earnings
from signals.backtest_regime import align_benchmark_to_index, regime_label_at
from signals.composite_bar_score import composite_bar_score_for_backtest
from signals.fetcher import fetch_ohlcv_safe
from signals.gate_backtest import enrich_row_with_gates, summarize_gate_backtest
from signals.indicators import composite_score, compute_indicators
from signals.score_interpretation import backtest_bucket_style_at_bar

_ETFS = {"SPY", "QQQ", "GLD", "SLV", "IWM", "DIA", "VOO", "VTI", "XLF", "XLK", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE"}
_DIP_BUCKET = "70-100"
_MOM_BUCKET = "0-30"
_DEFAULT_BUCKETS = [(0, 30), (30, 50), (50, 70), (70, 100.1)]
_TRADING_DPM = 21


def effective_earnings_exclusion_config(config: dict, ticker: str) -> dict[str, Any]:
    """Merge config; auto-enable for single stocks when auto_single_stock is true."""
    bt = config.get("backtest") or {}
    ecfg = dict(bt.get("earnings_exclusion") or {})
    sym = (ticker or "").upper().split(".")[0]
    if not ecfg.get("enabled") and ecfg.get("auto_single_stock") and sym not in _ETFS:
        ecfg = {**ecfg, "enabled": True, "auto_single_stock": True}
        if not ecfg.get("days_before"):
            ecfg["days_before"] = 5
    return ecfg


def _merged_backtest_config(config: dict, ticker: str) -> dict:
    """Config with effective earnings exclusion for this ticker."""
    cfg = dict(config or {})
    bt = dict(cfg.get("backtest") or {})
    bt["earnings_exclusion"] = effective_earnings_exclusion_config(cfg, ticker)
    cfg["backtest"] = bt
    return cfg


def _regime_bull_proxy(label: str) -> float:
    if label == "bull":
        return 72.0
    if label == "bear":
        return 38.0
    if label == "neutral":
        return 55.0
    return 50.0


def _bucket_key(score: float, buckets: list[tuple[float, float]]) -> str | None:
    for lo, hi in buckets:
        if lo <= score < hi:
            return f"{lo:.0f}-{hi:.0f}" if hi < 100.1 else "70-100"
    return None


def _stats(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0, "avg_return_pct": None, "hit_rate_pct": None}
    n = len(vals)
    mean = float(np.mean(vals))
    hit = 100.0 * sum(1 for v in vals if v > 0) / n
    return {
        "n": n,
        "avg_return_pct": round(100 * mean, 2),
        "hit_rate_pct": round(hit, 1),
    }


def _forward_pct(close: pd.Series, i: int, trading_days: int) -> float | None:
    j = min(i + trading_days, len(close) - 1)
    if j <= i:
        return None
    p0 = float(close.iloc[i])
    p1 = float(close.iloc[j])
    if p0 <= 0:
        return None
    return 100.0 * (p1 - p0) / p0


def build_tier_enhancements(
    *,
    ticker: str,
    period: str,
    config: dict | None,
    transaction_cost: float,
    bucket_results: dict[str, dict[int, dict]] | None = None,
    mr_dominated: bool = False,
    mr_spread_6m: dict | None = None,
) -> dict[str, Any]:
    """Single-pass panel for gate, exit, regime, and rule-strategy tiers."""
    cfg = _merged_backtest_config(config or {}, ticker)
    score_cfg = cfg.get("score") or {}
    buy_min = float(score_cfg.get("buy_min", 70))
    sell_max = float(score_cfg.get("sell_max", 30))
    min_gates = int(((cfg.get("evaluation") or {}).get("gate_backtest") or {}).get("min_gates_passed", 4))

    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < 300:
        return {"error": f"Insufficient data for tier enhancements ({ticker})"}
    close = close.sort_index()

    rc = (cfg.get("backtest") or {}).get("regime") or {}
    regime_sym = str(rc.get("benchmark") or "SPY").upper()
    ma_days = int(rc.get("ma_days") or 200)
    spy = fetch_ohlcv_safe(regime_sym, period)
    spy_aligned = align_benchmark_to_index(spy.sort_index(), close.index) if spy is not None else None

    live_ctx = None
    try:
        from signals.backtest_live_parity import BacktestLiveContext

        live_ctx = BacktestLiveContext.prepare(close.index, period, cfg)
    except Exception:
        pass

    ecfg = (cfg.get("backtest") or {}).get("earnings_exclusion") or {}
    sorted_earnings_ts, earnings_meta = load_earnings_exclusion_state(cfg, ticker, close.index)
    earnings_days = int(ecfg.get("days_before") or 0)

    buckets = _DEFAULT_BUCKETS
    hold_days = 63
    max_fwd = max(126, hold_days)
    panel: list[dict[str, Any]] = []
    by_regime_raw: dict[str, dict[str, list[float]]] = {
        "bull": {_DIP_BUCKET: [], _MOM_BUCKET: []},
        "bear": {_DIP_BUCKET: [], _MOM_BUCKET: []},
    }

    for i in range(200, len(close) - max_fwd):
        if sorted_earnings_ts and should_exclude_bar_for_earnings(
            close.index[i], sorted_earnings_ts, earnings_days
        ):
            continue

        score = composite_bar_score_for_backtest(close, i, ticker, cfg, live_ctx=live_ctx)
        if score is None:
            continue

        bk = _bucket_key(float(score), buckets)
        if not bk:
            continue

        subset = close.iloc[: i + 1]
        sig = composite_score(subset, ticker=ticker, config=cfg)
        ind = compute_indicators(subset)
        row_ind = ind.iloc[-1] if not ind.empty else None
        rsi = float(row_ind["RSI"]) if row_ind is not None else None

        reg_label = "unknown"
        if spy_aligned is not None:
            reg_label = regime_label_at(spy_aligned, i, ma_days)
        rb_proxy = _regime_bull_proxy(reg_label)

        row: dict[str, Any] = {
            "bar_index": i,
            "date": str(close.index[i])[:10],
            "composite_buy": float(score),
            "bucket": bk,
            "regime_label": reg_label,
        }
        enrich_row_with_gates(
            row,
            close=float(close.iloc[i]),
            sig=sig,
            regime_bull_pct=rb_proxy,
            rsi=rsi,
            indicator_row=row_ind,
            ticker=ticker,
            market_regime_bull_pct=rb_proxy,
            predict_ml=False,
        )
        for td in (21, 63, 126):
            fwd = _forward_pct(close, i, td)
            if fwd is not None:
                row[f"fwd_{td}d_pct"] = round(fwd - 100.0 * transaction_cost, 4)

        panel.append(row)

        fwd_6m = row.get("fwd_126d_pct")
        if fwd_6m is not None and reg_label in by_regime_raw and bk in (_DIP_BUCKET, _MOM_BUCKET):
            by_regime_raw[reg_label][bk].append(float(fwd_6m) / 100.0)

    gate_summary = summarize_gate_backtest(
        panel,
        horizons=(21, 63, 126),
        buy_min=buy_min,
        min_gates_passed=min_gates,
        sell_max=sell_max,
    )

    exit_backtest = _build_exit_backtest(gate_summary, sell_max)

    non_overlap = _non_overlapping_rule_sim(
        panel,
        close,
        transaction_cost=transaction_cost,
        buy_min=buy_min,
        sell_max=sell_max,
        hold_days=hold_days,
        dip_bucket=_DIP_BUCKET,
    )

    by_regime = {}
    for reg, bmap in by_regime_raw.items():
        dip = _stats(bmap[_DIP_BUCKET])
        mom = _stats(bmap[_MOM_BUCKET])
        edge = None
        if dip.get("avg_return_pct") is not None and mom.get("avg_return_pct") is not None:
            edge = round(dip["avg_return_pct"] - mom["avg_return_pct"], 2)
        by_regime[reg] = {
            "dip_bucket_6m": dip,
            "momentum_bucket_6m": mom,
            "mr_spread_6m_edge_pct": edge,
        }

    per_ticker = _per_ticker_threshold_hint(
        ticker,
        cfg,
        bucket_results=bucket_results,
        mr_dominated=mr_dominated,
        mr_spread_6m=mr_spread_6m,
    )

    return {
        "schema_version": 1,
        "question_labels": {
            "A": "Historical dip edge (bucket attribution)",
            "B": "Gate-conditioned forward returns",
            "C": "Live paper vs backtest (dashboard forward tracking)",
        },
        "gate_backtest": gate_summary,
        "exit_backtest": exit_backtest,
        "rule_strategy": {
            "hold_trading_days": hold_days,
            "entry_rule": f"score in {_DIP_BUCKET} (≥{buy_min}) AND gate_cleared (4/4 primary)",
            "exit_rule": f"fixed hold {hold_days}d OR score ≤ {sell_max} (see exit_backtest)",
            "non_overlapping": non_overlap,
            "overlapping_cohort": _overlapping_from_gates(gate_summary, 63),
            "note": (
                "Non-overlapping sim: one open trade at a time. "
                "Overlapping cohort matches gate_backtest composite_and_gate_cleared."
            ),
        },
        "by_regime": by_regime,
        "per_ticker_threshold": per_ticker,
        "earnings_exclusion_effective": earnings_meta,
        "forward_tracking": {
            "dashboard_field": "paper_vs_backtest_drift",
            "note": (
                "Question (C): compare live paper journal and forward ADD hit rates to these "
                "historical buckets on the Analysis tab (Forward tracking + drift panel)."
            ),
        },
        "regime_gate_proxy_note": (
            "Walk-forward gate rows use SPY-vs-SMA regime bull % proxy (72/38/55) when HMM "
            "history is unavailable per bar. Prefer EOD gate backtest for production-like fidelity."
        ),
    }


def _overlapping_from_gates(gate_summary: dict, horizon_td: int) -> dict[str, Any]:
    h = gate_summary.get("by_horizon_trading_days") or {}
    cohort = (h.get(str(horizon_td)) or {}).get("composite_and_gate_cleared") or {}
    return {
        "horizon_trading_days": horizon_td,
        "n": cohort.get("n"),
        "avg_return_pct": cohort.get("mean_fwd_pct"),
        "hit_rate_pct": cohort.get("hit_rate_pct"),
    }


def _build_exit_backtest(gate_summary: dict, sell_max: float) -> dict[str, Any]:
    by_h = gate_summary.get("by_horizon_trading_days") or {}
    out_h: dict[str, Any] = {}
    for td, cohorts in by_h.items():
        all_b = cohorts.get("all_bars") or {}
        sell_c = cohorts.get("composite_sell") or {}
        out_h[td] = {
            "all_bars": all_b,
            "composite_le_sell_max": sell_c,
            "trim_avoided_loss": _trim_signal_quality(all_b, sell_c),
        }
    sell_3m = (by_h.get("63") or {}).get("composite_sell") or {}
    all_3m = (by_h.get("63") or {}).get("all_bars") or {}
    precision_note = (
        "SELL/trim when score ≤ sell_max: forward return still positive in bull regimes — "
        "use for risk reduction, not market timing."
    )
    if sell_3m.get("mean_fwd_pct") is not None and all_3m.get("mean_fwd_pct") is not None:
        if float(sell_3m["mean_fwd_pct"]) < float(all_3m["mean_fwd_pct"]):
            precision_note = (
                "Low-score bars underperform unconditional forward returns at 3m — "
                "trim signal has modest edge."
            )
    return {
        "sell_max": sell_max,
        "by_horizon_trading_days": out_h,
        "sell_precision_3m_pct": sell_3m.get("hit_rate_pct"),
        "sell_avg_fwd_3m_pct": sell_3m.get("mean_fwd_pct"),
        "unconditional_avg_fwd_3m_pct": all_3m.get("mean_fwd_pct"),
        "notes": [precision_note],
    }


def _trim_signal_quality(all_b: dict, sell_c: dict) -> str | None:
    a = all_b.get("mean_fwd_pct")
    s = sell_c.get("mean_fwd_pct")
    if a is None or s is None:
        return None
    if float(s) < float(a):
        return "low_score_underperforms"
    return "low_score_still_positive"


def _non_overlapping_rule_sim(
    panel: list[dict[str, Any]],
    close: pd.Series,
    *,
    transaction_cost: float,
    buy_min: float,
    sell_max: float,
    hold_days: int,
    dip_bucket: str,
) -> dict[str, Any]:
    """One trade at a time: enter dip bucket + gate cleared; hold fixed days."""
    trades: list[float] = []
    next_free = 0

    def _cleared(r: dict) -> bool:
        if r.get("gate_cleared") is True:
            return True
        return str(r.get("go_no_go") or "").lower() == "go"

    for r in panel:
        i = int(r["bar_index"])
        if i < next_free:
            continue
        if r.get("bucket") != dip_bucket:
            continue
        if float(r.get("composite_buy") or 0) < buy_min:
            continue
        if not _cleared(r):
            continue
        j = min(i + hold_days, len(close) - 1)
        p0 = float(close.iloc[i])
        p1 = float(close.iloc[j])
        if p0 <= 0:
            continue
        ret = (p1 - p0) / p0 - transaction_cost
        trades.append(ret)
        next_free = j + 1

    start_i = 200
    end_i = len(close) - 1
    bh_ret = None
    bh_cagr = None
    if end_i > start_i and float(close.iloc[start_i]) > 0:
        bh_ret = float(close.iloc[end_i]) / float(close.iloc[start_i]) - 1.0
        try:
            idx_start = close.index[start_i]
            idx_end = close.index[end_i]
            if hasattr(idx_end - idx_start, "days"):
                years = (idx_end - idx_start).days / 365.25
            else:
                years = (end_i - start_i) / 252.0
        except Exception:
            years = (end_i - start_i) / 252.0
        if years > 0 and bh_ret > -1:
            bh_cagr = (1 + bh_ret) ** (1 / years) - 1

    strat_total = sum(trades) if trades else 0.0
    years_traded = len(trades) * (hold_days / 252.0) if trades else 0
    strat_cagr = None
    if years_traded > 0 and trades:
        compounded = 1.0
        for t in trades:
            compounded *= 1 + t
        strat_cagr = compounded ** (1 / max(years_traded, 0.01)) - 1

    st = _stats(trades)
    return {
        **st,
        "total_return_pct": round(100 * strat_total, 2) if trades else None,
        "strategy_cagr_pct": round(100 * strat_cagr, 2) if strat_cagr is not None else None,
        "buy_hold_cagr_pct": round(100 * bh_cagr, 2) if bh_cagr is not None else None,
        "alpha_vs_buy_hold_cagr_pct": (
            round(100 * (strat_cagr - bh_cagr), 2)
            if strat_cagr is not None and bh_cagr is not None
            else None
        ),
        "buy_hold_total_return_pct": round(100 * bh_ret, 2) if bh_ret is not None else None,
    }


def _per_ticker_threshold_hint(
    ticker: str,
    config: dict,
    *,
    bucket_results: dict | None,
    mr_dominated: bool,
    mr_spread_6m: dict | None,
) -> dict[str, Any]:
    score_cfg = config.get("score") or {}
    buy_min = float(score_cfg.get("buy_min", 70))
    sell_max = float(score_cfg.get("sell_max", 30))
    overrides = score_cfg.get("buy_min_by_ticker") or {}
    force_mr = score_cfg.get("interpretation", {}).get("force_mean_reverting") or []
    sym = ticker.upper()

    note_parts = []
    suggested_buy = overrides.get(sym, buy_min)
    suggested_sell = sell_max

    if mr_spread_6m and mr_spread_6m.get("edge_pct") is not None:
        edge = float(mr_spread_6m["edge_pct"])
        if edge < 0:
            note_parts.append(
                f"MR spread 6m inverted ({edge:+.1f}%) — consider force_mean_reverting or higher buy_min."
            )
            if sym not in force_mr:
                note_parts.append(f"Candidate for score.interpretation.force_mean_reverting: {sym}")
        elif edge < 1.0:
            note_parts.append(f"MR spread 6m thin ({edge:+.1f}%) — prefer 6m horizon; avoid 3m-only tuning.")
        else:
            note_parts.append(f"MR spread 6m edge {edge:+.1f}% — current buy_min={buy_min} reasonable.")

    if bucket_results and mr_dominated:
        b70 = (bucket_results.get("70-100") or {}).get(6, {})
        b0 = (bucket_results.get("0-30") or {}).get(6, {})
        if b70.get("hit_rate") and b0.get("hit_rate"):
            if float(b70["hit_rate"]) < float(b0["hit_rate"]):
                note_parts.append("6m hit rate: 0-30 ≥ 70-100 — bull-heavy window; trust spread not hit rate.")

    return {
        "ticker": sym,
        "config_buy_min": buy_min,
        "config_sell_max": sell_max,
        "suggested_buy_min": suggested_buy,
        "suggested_sell_max": suggested_sell,
        "in_force_mean_reverting": sym in force_mr,
        "notes": note_parts or ["No override suggested — use global score bands."],
    }


def build_primary_kpis(result: dict[str, Any]) -> dict[str, Any]:
    """
    Tier 3 primary KPIs: MR spread 6m + walk-forward 6m consistency (not monotonic hit rate).
    """
    mr6 = result.get("mr_spread_6m") or {}
    wf = result.get("walk_forward") or {}
    wf_cons = (wf.get("consistency") or {}).get(6) or {}
    bas = result.get("bucket_assignment_stats") or {}
    pct_mr = bas.get("pct_mean_reverting")

    edge = mr6.get("edge_pct")
    wf_ret = wf_cons.get("avg_net_return_pct")
    wf_ok = wf_cons.get("consistent")
    dip_hit = mr6.get("dip_hit_rate_pct")

    headline_parts = []
    if edge is not None:
        headline_parts.append(f"MR 6m spread {edge:+.1f}%")
    if wf_ret is not None:
        headline_parts.append(f"walk-forward 6m {wf_ret:+.1f}%")
    if wf_ok:
        headline_parts.append("WF 6m stable")

    recommended = 6 if (pct_mr or 0) >= 50 else 3
    confidence = "moderate"
    if edge is not None and float(edge) >= 2.0 and wf_ok:
        confidence = "good"
    elif edge is not None and float(edge) < 0:
        confidence = "review"

    return {
        "headline": " · ".join(headline_parts) if headline_parts else "Run backtest to compute KPIs",
        "recommended_horizon_months": recommended,
        "mr_spread_6m_edge_pct": edge,
        "walk_forward_6m_avg_return_pct": wf_ret,
        "walk_forward_6m_consistent": wf_ok,
        "dip_bucket_6m_hit_rate_pct": dip_hit,
        "pct_mean_reverting": pct_mr,
        "confidence_band": confidence,
        "calibration_note": (
            "Primary calibration uses MR spread (70–100 vs 0–30) at 6m and walk-forward 6m stability — "
            "not monotonic hit rate across all four buckets under MR mapping."
        ),
    }
