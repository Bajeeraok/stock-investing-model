"""
Historical validation of primary trading gates (valuation, regime, momentum, ML).

Uses the same thresholds as signals.retail_action_payload / dashboard GO/NO-GO.
Supports:
  - EOD snapshots (run_daily + enrich_dashboard_signal_row) — full fidelity when available
  - Walk-forward evaluation panel rows — causal bar features + optional ML inference

No lookahead: gate inputs use only data available at the signal bar.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from signals.retail_action_payload import (
    PRIMARY_GATE_IDS,
    build_trading_gates,
)

# Re-export for scripts
PRIMARY_GATE_COUNT = len(PRIMARY_GATE_IDS)


def _derive_entry_mode_from_gates(per_gate: dict[str, bool], cleared: bool) -> str:
    """
    Lightweight entry_mode derivation for backtest rows where only gate pass/fail is known.
    Full derivation (with assessment_pct, zone context) happens in retail_action_payload.
    """
    val_pass = per_gate.get("valuation", False)
    tech_ok = all(per_gate.get(g, False) for g in ("regime", "momentum", "ml"))
    if cleared and val_pass and tech_ok:
        return "full_go"
    if val_pass:
        return "starter_only"
    return "hard_lock"


def _gate_summary(gates: list[dict[str, Any]]) -> dict[str, Any]:
    primary = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS]
    passed = sum(1 for g in primary if g.get("pass"))
    total = len(primary) if primary else 4
    per_gate = {str(g.get("id")): bool(g.get("pass")) for g in primary}
    cleared = passed == total and total > 0
    return {
        "gates": gates,
        "gates_passed": passed,
        "gates_total": total,
        "gate_cleared": cleared,
        "go_no_go": "go" if cleared else "no_go",
        "entry_mode": _derive_entry_mode_from_gates(per_gate, cleared),
        "valuation_pass": per_gate.get("valuation"),
        "regime_pass": per_gate.get("regime"),
        "momentum_pass": per_gate.get("momentum"),
        "ml_pass": per_gate.get("ml"),
    }


def evaluate_gates_at_point(
    *,
    assessment_pct: float,
    regime_bull_pct: float | None,
    pattern_score: float | None,
    short_ml_prob: float | None,
    rsi: float | None,
    confidence_mid: float | None = None,
    include_confidence_gate: bool = False,
    ticker: str | None = None,
    market_regime_bull_pct: float | None = None,
) -> dict[str, Any]:
    """Evaluate primary gates at a single historical point (same rules as live UI)."""
    gates = build_trading_gates(
        assessment_pct=assessment_pct,
        regime_bull_pct=regime_bull_pct,
        pattern_score=pattern_score,
        short_ml_prob=short_ml_prob,
        rsi=rsi,
        confidence_mid=confidence_mid,
        include_confidence=include_confidence_gate,
        ticker=ticker,
        market_regime_bull_pct=market_regime_bull_pct,
    )
    return _gate_summary(gates)


def fair_value_proxy_for_backtest(
    close: float,
    sig: dict[str, Any],
    indicator_row: Any | None = None,
) -> float | None:
    """
    Causal FV proxy when full fair_value_estimator is not run per bar.
    Prefers suggested buy / MA200 anchors from the signal bar.
    """
    if close <= 0:
        return None
    sb = sig.get("suggested_buy_price")
    if sb is not None:
        try:
            v = float(sb)
            if v > 0:
                return v * 1.05
        except (TypeError, ValueError):
            pass
    if indicator_row is not None:
        ma200 = indicator_row.get("MA200") if hasattr(indicator_row, "get") else None
        if ma200 is not None:
            try:
                m = float(ma200)
                if m > 0:
                    return m if close <= m else close * 0.97
            except (TypeError, ValueError):
                pass
    comp = float(sig.get("composite_buy") or sig.get("confluence_score") or 50)
    # Modest discount vs spot when composite is strong (aligns with “value” gate stress tests)
    discount = max(0.0, min(0.25, (comp - 45) / 200.0))
    return close * (1.0 + discount)


def _ml_prob_at_bar(
    ticker: str,
    close_slice: Any,
    *,
    predict_ml: bool,
) -> float | None:
    if not predict_ml:
        return None
    try:
        import pandas as pd
        from signals.ml_models import predict_probability as _ml_predict

        df = pd.DataFrame({"close": close_slice})
        p = _ml_predict(
            ticker,
            df,
            force_retrain=False,
            horizon_key="short",
            inference_only=True,
        )
        if p is None:
            return None
        return float(p) * 100.0 if p <= 1.0 else float(p)
    except Exception:
        return None


def enrich_row_with_gates(
    row: dict[str, Any],
    *,
    close: float,
    sig: dict[str, Any],
    regime_bull_pct: float | None,
    rsi: float | None,
    indicator_row: Any | None = None,
    ticker: str | None = None,
    market_regime_bull_pct: float | None = None,
    predict_ml: bool = False,
    close_series: Any | None = None,
    include_confidence_gate: bool = False,
) -> dict[str, Any]:
    """Attach gate_* fields to an evaluation / backtest row (mutates and returns row)."""
    fv = fair_value_proxy_for_backtest(close, sig, indicator_row)
    assessment_pct = 0.0
    if fv and fv > 0 and close > 0:
        assessment_pct = 100.0 * (fv - close) / close

    ml_prob = row.get("ml_short_prob")
    if ml_prob is not None and ml_prob <= 1:
        ml_prob = float(ml_prob) * 100.0
    if ml_prob is None and predict_ml and close_series is not None and ticker:
        ml_prob = _ml_prob_at_bar(ticker, close_series, predict_ml=True)

    pattern = sig.get("confluence_score") or row.get("confluence_score") or row.get("composite_buy")
    conf = row.get("confidence_proxy")
    conf_mid = float(conf) * 100.0 if conf is not None and conf <= 1 else conf

    summary = evaluate_gates_at_point(
        assessment_pct=assessment_pct,
        regime_bull_pct=regime_bull_pct,
        pattern_score=float(pattern) if pattern is not None else None,
        short_ml_prob=float(ml_prob) if ml_prob is not None else None,
        rsi=float(rsi) if rsi is not None else None,
        confidence_mid=float(conf_mid) if conf_mid is not None else None,
        include_confidence_gate=include_confidence_gate,
        ticker=ticker,
        market_regime_bull_pct=market_regime_bull_pct,
    )
    row.update({k: v for k, v in summary.items() if k != "gates"})
    row["gate_detail_json"] = json.dumps(summary.get("gates") or [], default=str)
    row["assessment_pct_gate"] = round(assessment_pct, 2)
    row["fair_value_proxy"] = round(float(fv), 4) if fv else None
    return row


def enrich_eod_row_with_gates_from_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    """
    Read gates from EOD row if run_daily already enriched retail_status; else recompute.
    Also reads entry_mode from retail_status when present.
    """
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    gates = rs.get("gates") if isinstance(rs.get("gates"), list) else None
    if gates:
        summary = _gate_summary(gates)
        row.update({k: v for k, v in summary.items() if k != "gates"})
        # Prefer explicit entry_mode from retail_status over the derived value
        if rs.get("entry_mode"):
            row["entry_mode"] = rs["entry_mode"]
        return row
    if row.get("gate_cleared") is not None:
        row.setdefault("gates_passed", row.get("gates_passed"))
        row.setdefault("gates_total", row.get("gates_total") or 4)
        row.setdefault("go_no_go", "go" if row.get("gate_cleared") else "no_go")
        # Propagate entry_mode from top-level row if already set (e.g. run_daily wrote it)
        if not row.get("entry_mode") and rs.get("entry_mode"):
            row["entry_mode"] = rs["entry_mode"]
        return row
    try:
        from signals.retail_action_payload import enrich_dashboard_signal_row

        enrich_dashboard_signal_row(row, regime_bull_pct=None)
        rs2 = row.get("retail_status") or {}
        if rs2.get("gates"):
            summary = _gate_summary(rs2["gates"])
            row.update({k: v for k, v in summary.items() if k != "gates"})
        if rs2.get("entry_mode") and not row.get("entry_mode"):
            row["entry_mode"] = rs2["entry_mode"]
    except Exception:
        pass
    return row


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _hit_rate(xs: list[float]) -> float | None:
    if not xs:
        return None
    return round(100.0 * sum(1 for x in xs if x > 0) / len(xs), 2)


def cohort_forward_stats(
    rows: list[dict[str, Any]],
    fwd_key: str,
    *,
    predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    vals = [
        float(r[fwd_key])
        for r in rows
        if r.get(fwd_key) is not None and (predicate(r) if predicate else True)
    ]
    return {
        "n": len(vals),
        "mean_fwd_pct": _mean(vals),
        "hit_rate_pct": _hit_rate(vals),
    }


def summarize_gate_backtest(
    rows: list[dict[str, Any]],
    *,
    horizons: tuple[int, ...] = (21, 63, 126),
    buy_min: float = 70.0,
    min_gates_passed: int = 4,
    sell_max: float = 35.0,
) -> dict[str, Any]:
    """
    Compare forward returns across cohorts:
      - all bars
      - composite >= buy_min (legacy score filter)
      - gates_passed >= min_gates_passed (primary gate rule)
      - gate_cleared (4/4 primary)
      - composite >= buy_min AND gate_cleared
    """
    if not rows:
        return {"error": "no_rows"}

    def _ge_gates(r: dict[str, Any]) -> bool:
        gp = r.get("gates_passed")
        return gp is not None and int(gp) >= min_gates_passed

    def _cleared(r: dict[str, Any]) -> bool:
        if r.get("gate_cleared") is True:
            return True
        return str(r.get("go_no_go") or "").lower() == "go"

    def _entry_mode_is(mode: str) -> Callable[[dict[str, Any]], bool]:
        def _f(r: dict[str, Any]) -> bool:
            em = str(r.get("entry_mode") or "")
            if em:
                return em == mode
            # Fallback for rows that pre-date entry_mode: derive from per-gate fields —
            # but only when at least one is actually present. Some EOD snapshot rows
            # carry only the aggregate gates_passed/gate_cleared count, not which
            # specific gates passed; deriving from four missing (None) fields would
            # silently default every such row to "hard_lock" rather than reflecting
            # that entry_mode genuinely isn't knowable from this row. Those rows
            # count toward "unknown" instead.
            pg_raw = {
                "valuation": r.get("valuation_pass"),
                "regime": r.get("regime_pass"),
                "momentum": r.get("momentum_pass"),
                "ml": r.get("ml_pass"),
            }
            if all(v is None for v in pg_raw.values()):
                return mode == "unknown"
            em = _derive_entry_mode_from_gates(
                {k: bool(v) for k, v in pg_raw.items()},
                bool(r.get("gate_cleared")),
            )
            return em == mode
        return _f

    def _composite_buy(r: dict[str, Any]) -> bool:
        return float(r.get("composite_buy") or 0) >= buy_min

    def _composite_sell(r: dict[str, Any]) -> bool:
        return float(r.get("composite_buy") or 0) <= sell_max

    cohorts: dict[str, Callable[[dict[str, Any]], bool] | None] = {
        "all_bars": None,
        "composite_ge_buy_min": _composite_buy,
        "gates_ge_min": _ge_gates,
        "gate_cleared_4of4": _cleared,
        "entry_mode_full_go": _entry_mode_is("full_go"),
        "entry_mode_starter_only": _entry_mode_is("starter_only"),
        "entry_mode_hard_lock": _entry_mode_is("hard_lock"),
        "entry_mode_unknown": _entry_mode_is("unknown"),
        "composite_and_gate_cleared": lambda r: _composite_buy(r) and _cleared(r),
        "composite_sell": _composite_sell,
    }

    by_horizon: dict[str, Any] = {}
    for h in horizons:
        key = f"fwd_{h}d_pct"
        by_horizon[str(h)] = {
            name: cohort_forward_stats(rows, key, predicate=pred)
            for name, pred in cohorts.items()
        }

    # Per-gate pass rate: computed over rows that actually carry that gate's pass/fail
    # detail, not over all rows. Some EOD snapshot rows only store the aggregate
    # gates_passed/gate_cleared count (not which specific gates passed) — for those,
    # `{gid}_pass` is None, and counting None as "not passed" would silently report a
    # misleading 0% instead of "not measurable from this data."
    gate_pass_rates: dict[str, Any] = {}
    gate_pass_coverage_n: dict[str, Any] = {}
    n = len(rows)
    if n:
        for gid in PRIMARY_GATE_IDS:
            k = f"{gid}_pass"
            available = [r for r in rows if r.get(k) is not None]
            gate_pass_coverage_n[gid] = len(available)
            if available:
                hits = sum(1 for r in available if r.get(k) is True)
                gate_pass_rates[gid] = round(100.0 * hits / len(available), 2)
            else:
                gate_pass_rates[gid] = None
        cleared_n = sum(1 for r in rows if _cleared(r))
        gate_pass_rates["gate_cleared_pct"] = round(100.0 * cleared_n / n, 2)

    rows_missing_gate_detail = sum(
        1 for r in rows if all(r.get(f"{gid}_pass") is None for gid in PRIMARY_GATE_IDS)
    )
    # Walk-forward-specific proxy caveats only apply to rows that actually came from
    # that path (identifiable by fields evaluation_harness.py alone sets) — showing
    # them unconditionally was itself misleading on eod-source reports.
    looks_walkforward = any(r.get("regime_bull_prob") is not None for r in rows[:20])

    notes: list[str] = []
    if rows_missing_gate_detail:
        notes.append(
            f"{rows_missing_gate_detail}/{n} rows carry only the aggregate gates_passed/gate_cleared "
            "count, not which specific gates passed — their valuation/regime/momentum/ml pass rates "
            "are excluded (null if that leaves zero rows for a gate) rather than shown as a misleading "
            "0%, and their entry_mode is counted under entry_mode_unknown rather than defaulted to "
            "hard_lock. gates_ge_min / gate_cleared_4of4 are unaffected either way — those read the "
            "aggregate fields directly, which are reliably present."
        )
    if looks_walkforward:
        notes.append("Walk-forward rows use SPY regime bull % proxy unless EOD retail_status is present.")
        notes.append("FV for walk-forward uses suggested_buy/MA200 proxy — prefer --source eod for production-like gates.")
    notes.append("ML gate requires ml_short_prob on row or evaluation.gate_backtest.predict_ml: true.")

    return {
        "n_rows": n,
        "buy_min": buy_min,
        "sell_max": sell_max,
        "min_gates_passed": min_gates_passed,
        "primary_gate_ids": list(PRIMARY_GATE_IDS),
        "gate_pass_rates_pct": gate_pass_rates,
        "gate_pass_coverage_n": gate_pass_coverage_n,
        "by_horizon_trading_days": by_horizon,
        "notes": notes,
    }


def format_gate_backtest_report(summary: dict[str, Any]) -> str:
    """Human-readable report for CLI."""
    if summary.get("error"):
        return f"No data: {summary['error']}"
    lines = [
        "=" * 60,
        "GATE BACKTEST (historical forward returns)",
        "=" * 60,
        f"Rows: {summary.get('n_rows')} · buy_min={summary.get('buy_min')} · "
        f"min_gates={summary.get('min_gates_passed')}/4",
    ]
    gpr = summary.get("gate_pass_rates_pct") or {}
    if gpr:
        parts = []
        for k, v in gpr.items():
            if k == "gate_cleared_pct":
                continue
            parts.append(f"{k}={v}%" if v is not None else f"{k}=n/a (no per-gate detail in this data)")
        lines.append("Gate pass rates: " + ", ".join(parts))
        if gpr.get("gate_cleared_pct") is not None:
            lines.append(f"  Full 4/4 cleared: {gpr['gate_cleared_pct']}% of bars")
    for h, cohorts in (summary.get("by_horizon_trading_days") or {}).items():
        lines.append(f"\n--- Horizon ~{h} trading days ---")
        for name, st in cohorts.items():
            if not st or st.get("n", 0) == 0:
                continue
            lines.append(
                f"  {name:28} n={st['n']:4}  mean_fwd={st.get('mean_fwd_pct')}%  "
                f"hit={st.get('hit_rate_pct')}%"
            )
    for note in summary.get("notes") or []:
        lines.append(f"  · {note}")
    return "\n".join(lines)
