"""
Path-aware forward metrics and TRIM scoring for forward_tracking panel.
Uses EOD high/low between as-of and forward dates (not paper trades).
"""
from __future__ import annotations

import json
from typing import Any

from signals.stock_splits import align_prices_across_split

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


def freeze_trim_gate_fields_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Compact frozen trim gate snapshot for EOD persistence."""
    from signals.trim_gates import primary_trim_gates_detail, trim_gate_snapshot_from_row

    snap = trim_gate_snapshot_from_row(row)
    detail = primary_trim_gates_detail(row)
    out = dict(snap)
    if detail:
        out["trim_gate_detail_json"] = json.dumps(detail, default=str)
    out["trim_gates_frozen"] = True
    return out


def read_frozen_trim_gates(row: dict[str, Any]) -> dict[str, Any]:
    """Prefer frozen EOD trim gate fields; fall back to live row."""
    if row.get("trim_gates_frozen") or row.get("trim_gate_detail_json"):
        passed = row.get("trim_gates_passed")
        total = row.get("trim_gates_total") or 4
        try:
            passed = int(passed) if passed is not None else None
        except (TypeError, ValueError):
            passed = None
        if passed is None and row.get("trim_gate_detail_json"):
            try:
                detail = json.loads(row["trim_gate_detail_json"])
                if isinstance(detail, list):
                    passed = sum(1 for g in detail if isinstance(g, dict) and g.get("pass"))
            except Exception:
                pass
        if passed is None:
            from signals.trim_gates import trim_gate_snapshot_from_row

            snap = trim_gate_snapshot_from_row(row)
            passed = snap.get("trim_gates_passed")
            total = snap.get("trim_gates_total") or total
        min_pass = int(row.get("trim_min_pass") or 2)
        cleared = row.get("trim_gate_cleared")
        if cleared is None and passed is not None:
            cleared = passed >= min_pass
        return {
            "trim_gate_cleared": bool(cleared),
            "trim_gates_passed": passed if passed is not None else 0,
            "trim_gates_total": int(total),
            "trim_score_triggered": bool(row.get("trim_score_triggered")),
            "trim_recommendation": row.get("trim_recommendation"),
            "trim_gates_frozen": True,
        }
    from signals.trim_gates import trim_gate_snapshot_from_row

    return trim_gate_snapshot_from_row(row)


def aggregate_by_trim_gates(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Trim cohort stats by trim_gates_passed/total (score-triggered rows only)."""
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        if not r.get("trim_score_triggered"):
            continue
        p = r.get("trim_gates_passed")
        t = r.get("trim_gates_total") or 4
        try:
            key = f"{int(p)}/{int(t)}"
        except (TypeError, ValueError):
            key = "unknown"
        buckets.setdefault(key, []).append(r)
    return {k: aggregate_horizon_stats(v) for k, v in buckets.items()}


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
    stop = _positive_price(st.get("low"))
    target = _positive_price(st.get("high"))
    return stop, target


def entry_band_position(close_at_signal: float | None, band_low: float | None, band_high: float | None) -> str:
    """
    Where the signal-day close sat vs the model's own entry band (st_band, same band that
    gates ``inside_buy_band`` in retail_action_payload and the paper-trading limit_touch fill).

    "above" = the model would call this chasing (price already ran past the buy zone) —
    a naive close-to-close forward return still scores it as if it filled there today.
    """
    if close_at_signal is None or band_low is None or band_high is None:
        return "unknown"
    lo, hi = min(band_low, band_high), max(band_low, band_high)
    if hi <= lo:
        return "unknown"
    if close_at_signal < lo:
        return "below"
    if close_at_signal > hi:
        return "above"
    return "inside"


def _f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _positive_price(x: Any) -> float | None:
    v = _f(x)
    return v if v is not None and v > 0 else None


# Max |return| without extra OHLC scrutiny (horizon = EOD snapshot steps)
_FORWARD_ABS_CAP = {1: 18.0, 5: 30.0, 20: 50.0, 60: 90.0}


def compute_validated_forward_return(
    row_start: dict[str, Any],
    row_end: dict[str, Any],
    *,
    horizon: int,
    ticker: str | None = None,
) -> tuple[float | None, str]:
    """
    Close-to-close return between two EOD rows with sanity checks.

    Drops stale holiday duplicates and impossible 1d jumps (e.g. CRWD -75% from
    mismatched prior close). When horizon=1 and daily_move_pct disagrees with
    close chain, prefer daily_move_pct. Applies known stock splits across the pair.
    """
    prior_raw = _positive_price(row_start.get("close"))
    actual = _positive_price(row_end.get("close"))
    if prior_raw is None or actual is None:
        return None, "missing_close"

    d0 = str(row_start.get("ohlcv_last_date") or "")[:10]
    d1 = str(row_end.get("ohlcv_last_date") or "")[:10]
    prior, _, split_factor = align_prices_across_split(
        ticker, d0, d1, prior_raw, actual
    )
    if prior is None:
        return None, "missing_close"

    ret = round(100.0 * (actual - prior) / prior, 2)

    if prior_raw == actual and (not d0 or not d1 or d0 == d1):
        return None, "stale_session"

    dm = _f(row_end.get("daily_move_pct"))
    hi = _positive_price(row_end.get("high"))
    lo = _positive_price(row_end.get("low"))

    if horizon == 1 and dm is not None and abs(ret - dm) > 3.0 and abs(ret) > 12.0 and abs(dm) < 12.0:
        return round(dm, 2), "reconciled_daily_move"

    if hi is not None and lo is not None and prior > 0:
        band_lo = 100.0 * (lo - prior) / prior
        band_hi = 100.0 * (hi - prior) / prior
        if ret < band_lo - 2.0 or ret > band_hi + 2.0:
            if horizon == 1 and dm is not None and abs(dm) < 12.0:
                return round(dm, 2), "reconciled_daily_move"
            return None, "outlier_vs_ohlc"

    cap = _FORWARD_ABS_CAP.get(int(horizon), 50.0)
    if abs(ret) > cap:
        if horizon == 1 and dm is not None and abs(dm) <= cap:
            return round(dm, 2), "reconciled_daily_move"
        return None, "outlier_abs_cap"

    if split_factor != 1.0:
        return ret, "split_adjusted"

    return ret, "ok"


def _quality_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows with trustworthy forward returns for headline aggregates."""
    ok = frozenset({"ok", "reconciled_daily_move", "split_adjusted"})
    return [r for r in rows if str(r.get("data_quality") or "ok") in ok]


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
                    "close": _positive_price(r.get("close")),
                    "high": _positive_price(r.get("high")),
                    "low": _positive_price(r.get("low")),
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


def aggregate_horizon_stats(
    rows: list[dict[str, Any]],
    *,
    quality_only: bool = True,
) -> dict[str, Any]:
    if quality_only:
        rows = _quality_rows(rows)
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


def build_ticker_track_record(
    records: list[dict[str, Any]],
    ticker: str,
    *,
    current_model_version: str | None = None,
    horizon_days: int = 20,
) -> dict[str, Any]:
    """Per-ticker signal-accuracy summary, filtered from an already-computed records array
    (the watchlist-wide forward-tracking result — see signals/cache.py::get_analysis_slice).
    This function does no I/O and no snapshot loading; it's a cheap in-memory filter/rollup
    over data the caller already has, split by model_version so a ticker's current-model
    accuracy isn't blended with pre-fix history (see signals/model_version.py).
    """
    tk = str(ticker or "").upper().strip()
    ticker_records = [
        r for r in records
        if isinstance(r, dict)
        and str(r.get("ticker") or "").upper() == tk
        and r.get("horizon_days") == horizon_days
    ]
    if not ticker_records:
        return {"available": False, "ticker": tk, "horizon_days": horizon_days}

    by_version: dict[str, list[dict[str, Any]]] = {}
    for r in ticker_records:
        v = str(r.get("model_version") or "legacy")
        by_version.setdefault(v, []).append(r)

    current_rows = by_version.get(current_model_version, []) if current_model_version else []
    legacy_rows = [
        r for v, rows in by_version.items() if v != current_model_version for r in rows
    ]

    def _stats_or_none(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        stats = aggregate_horizon_stats(rows)
        return stats if stats.get("n_observations") else None

    return {
        "available": True,
        "ticker": tk,
        "horizon_days": horizon_days,
        "current_model_version": current_model_version,
        "current": _stats_or_none(current_rows),
        "legacy": _stats_or_none(legacy_rows),
    }


_ALL_HORIZONS: tuple[int, ...] = (1, 5, 20, 60)


def build_ticker_track_record_all_horizons(
    records: list[dict[str, Any]],
    ticker: str,
    *,
    current_model_version: str | None = None,
    horizons: tuple[int, ...] = _ALL_HORIZONS,
) -> dict[str, Any]:
    """
    Same per-ticker current-vs-legacy split as build_ticker_track_record(), but across every
    horizon that has data, not just the 20d default.

    Exists because a just-launched model_version has no chance of a resolved 20d outcome for
    weeks (20 *trading* days must elapse after a signal before that pair can resolve at all) —
    the single-horizon card was correctly showing "not enough data" for 2026.09.4 on every
    ticker, but silently hid the 1d/5d reads that WOULD already be partially resolved by then,
    which is exactly the early signal you'd want in order to sanity-check a new version instead
    of waiting a month to find out something's off. Callers should treat sub-20d "current"
    reads as an early/noisy look, not the headline number — n is small by construction this
    early, and 1d/5d win rates don't necessarily track 20d win rates for the same ticker.
    """
    tk = str(ticker or "").upper().strip()
    by_horizon: dict[int, dict[str, Any]] = {}
    any_available = False
    for h in horizons:
        single = build_ticker_track_record(
            records, tk, current_model_version=current_model_version, horizon_days=h
        )
        if single.get("available"):
            any_available = True
        by_horizon[h] = {
            "current": single.get("current"),
            "legacy": single.get("legacy"),
        }
    return {
        "available": any_available,
        "ticker": tk,
        "current_model_version": current_model_version,
        "by_horizon": by_horizon,
    }
