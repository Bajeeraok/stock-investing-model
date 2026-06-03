"""
Path-aware forward metrics and TRIM scoring for forward_tracking panel.
Uses EOD high/low between as-of and forward dates (not paper trades).
"""
from __future__ import annotations

import json
from typing import Any

TRIM_SIGNALS = frozenset({"CONSIDER TRIM", "TRIM", "SELL", "REDUCE", "AVOID"})


def freeze_gate_fields_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Compact frozen gate snapshot for EOD persistence."""
    from signals.tracking_gate import gate_snapshot_from_row, primary_gates_detail

    snap = gate_snapshot_from_row(row)
    detail = primary_gates_detail(row)
    out = dict(snap)
    if detail:
        out["gate_detail_json"] = json.dumps(detail, default=str)
    out["gates_frozen"] = True
    return out


def read_frozen_gates(row: dict[str, Any]) -> dict[str, Any]:
    """Prefer frozen EOD gate fields; fall back to gate_snapshot_from_row."""
    if row.get("gates_frozen") or row.get("gate_detail_json"):
        passed = row.get("gates_passed")
        total = row.get("gates_total") or 4
        try:
            passed = int(passed) if passed is not None else None
        except (TypeError, ValueError):
            passed = None
        if passed is None and row.get("gate_detail_json"):
            try:
                detail = json.loads(row["gate_detail_json"])
                if isinstance(detail, list):
                    passed = sum(1 for g in detail if isinstance(g, dict) and g.get("pass"))
            except Exception:
                pass
        if passed is None:
            from signals.tracking_gate import gate_snapshot_from_row

            snap = gate_snapshot_from_row(row)
            passed = snap.get("gates_passed")
            total = snap.get("gates_total") or total
        return {
            "gate_cleared": bool(passed is not None and passed >= total),
            "go_no_go": row.get("go_no_go"),
            "gates_passed": passed if passed is not None else 0,
            "gates_total": int(total),
            "gates_frozen": True,
        }
    from signals.tracking_gate import gate_snapshot_from_row

    return gate_snapshot_from_row(row)


def st_stop_target_from_row(row: dict[str, Any]) -> tuple[float | None, float | None]:
    """ST band low ≈ stop side, high ≈ target (target_bands convention)."""
    st = row.get("st_band") if isinstance(row.get("st_band"), dict) else None
    if not st:
        return None, None
    stop = _f(st.get("low"))
    target = _f(st.get("high"))
    return stop, target


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def bars_between_dates(
    dates: list[str],
    start_idx: int,
    horizon: int,
    ticker: str,
    load_snapshot,
    eod_dir,
) -> list[dict[str, float | None]]:
    bars: list[dict[str, float | None]] = []
    for k in range(1, horizon + 1):
        j = start_idx + k
        if j >= len(dates):
            break
        snap = load_snapshot(eod_dir, dates[j])
        if not snap:
            continue
        want = ticker.upper()
        for r in snap.get("run_results") or []:
            if not isinstance(r, dict) or str(r.get("ticker") or "").upper() != want:
                continue
            bars.append(
                {
                    "close": _f(r.get("close")),
                    "high": _f(r.get("high")),
                    "low": _f(r.get("low")),
                }
            )
            break
    return bars


def path_metrics(
    entry: float,
    bars: list[dict[str, float | None]],
    stop: float | None,
    target: float | None,
    *,
    use_intraday: bool = True,
) -> dict[str, Any]:
    """First-touch stop/target and max gain/drawdown over path."""
    hit_stop: int | None = None
    hit_target: int | None = None
    max_gain = None
    max_dd = None

    for bar in bars:
        hi = bar.get("high") if use_intraday else None
        lo = bar.get("low") if use_intraday else None
        cl = bar.get("close")

        if entry > 0:
            candidates_high = [entry]
            candidates_low = [entry]
            if use_intraday:
                if hi is not None:
                    candidates_high.append(hi)
                if lo is not None:
                    candidates_low.append(lo)
            if cl is not None:
                candidates_high.append(cl)
                candidates_low.append(cl)
            g = 100.0 * (max(candidates_high) - entry) / entry
            d = 100.0 * (min(candidates_low) - entry) / entry
            max_gain = g if max_gain is None else max(max_gain, g)
            max_dd = d if max_dd is None else min(max_dd, d)

        if hit_stop is None and stop is not None:
            if (lo is not None and lo <= stop) or (cl is not None and cl <= stop):
                hit_stop = 1
        if hit_target is None and target is not None:
            if (hi is not None and hi >= target) or (cl is not None and cl >= target):
                hit_target = 1
        if hit_stop == 1:
            break

    if bars:
        if hit_stop is None:
            hit_stop = 0
        if hit_target is None:
            hit_target = 0

    return {
        "hit_st_stop": hit_stop,
        "hit_st_target": hit_target,
        "max_gain_pct": round(max_gain, 2) if max_gain is not None else None,
        "max_drawdown_pct": round(max_dd, 2) if max_dd is not None else None,
    }


def trim_outcome_metrics(actual_return_pct: float, signal: str) -> dict[str, Any] | None:
    """
    TRIM / CONSIDER TRIM: score avoiding loss vs missed gain (not raw return as 'win').
    trim_net_score_pct > 0 => sidestepping helped (price fell).
    """
    sig = (signal or "").upper()
    if sig not in TRIM_SIGNALS and "TRIM" not in sig:
        return None
    avoided = round(max(0.0, -actual_return_pct), 2)
    missed = round(max(0.0, actual_return_pct), 2)
    net = round(-actual_return_pct, 2)
    label = "helped_avoid_drawdown" if net > 0 else ("missed_rally" if net < 0 else "flat")
    return {
        "trim_avoided_loss_pct": avoided,
        "trim_missed_gain_pct": missed,
        "trim_net_score_pct": net,
        "trim_outcome_label": label,
    }


def aggregate_horizon_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    rets = [float(r["actual_return_pct"]) for r in rows if r.get("actual_return_pct") is not None]
    n = len(rets)
    if n == 0:
        return {"n_observations": 0}
    wins = sum(1 for x in rets if x > 0)
    st_hits = [r for r in rows if r.get("hit_st_target") == 1]
    stop_hits = [r for r in rows if r.get("hit_st_stop") == 1]
    trim_rows = [r for r in rows if r.get("trim_net_score_pct") is not None]
    out: dict[str, Any] = {
        "avg_return_pct": round(sum(rets) / n, 2),
        "n_observations": n,
        "win_rate_pct": round(100.0 * wins / n, 1),
        "st_target_hit_rate_pct": round(100.0 * len(st_hits) / n, 1) if n else None,
        "st_stop_hit_rate_pct": round(100.0 * len(stop_hits) / n, 1) if n else None,
    }
    if trim_rows:
        nets = [float(r["trim_net_score_pct"]) for r in trim_rows]
        out["trim_avg_net_score_pct"] = round(sum(nets) / len(nets), 2)
        out["trim_helped_pct"] = round(
            100.0 * sum(1 for x in nets if x > 0) / len(nets),
            1,
        )
        out["trim_n"] = len(trim_rows)
    return out


def aggregate_by_gates(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        p = r.get("gates_passed")
        t = r.get("gates_total") or 4
        try:
            key = f"{int(p)}/{int(t)}"
        except (TypeError, ValueError):
            key = "unknown"
        buckets.setdefault(key, []).append(r)
    return {k: aggregate_horizon_stats(v) for k, v in buckets.items()}


def aggregate_by_signal(rows: list[dict[str, Any]], horizon: int) -> dict[str, dict[str, Any]]:
    by_sig: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("horizon_days") != horizon:
            continue
        sig = r.get("our_signal") or "N/A"
        by_sig.setdefault(sig, []).append(r)
    out: dict[str, dict[str, Any]] = {}
    for sig, grp in by_sig.items():
        stats = aggregate_horizon_stats(grp)
        if sig.upper() in TRIM_SIGNALS or "TRIM" in sig.upper():
            stats["metric_note"] = "TRIM uses trim_net_score (avoided drawdown), not raw return win rate"
        out[sig] = {
            "avg_return_pct": stats.get("avg_return_pct"),
            "avg_return_20d_pct": stats.get("avg_return_pct") if horizon == 20 else None,
            "n_observations": stats.get("n_observations"),
            "hit_rate_pct": stats.get("win_rate_pct"),
            "trim_avg_net_score_pct": stats.get("trim_avg_net_score_pct"),
            "trim_helped_pct": stats.get("trim_helped_pct"),
            "st_target_hit_rate_pct": stats.get("st_target_hit_rate_pct"),
            "st_stop_hit_rate_pct": stats.get("st_stop_hit_rate_pct"),
        }
    return out
