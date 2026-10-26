"""
Forward tracking: "What we said vs what happened" over multiple horizons.
Uses EOD snapshots: signal as-of date D, actual close at D+N (5, 20, 60 trading days).
Extends model validation with multi-horizon returns and signal-based accuracy.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from signals.model_version import MODEL_VERSION

logger = logging.getLogger(__name__)

_EOD_DIR_NAME = "eod"
_DEFAULT_MAX_RECORDS = 2000
_SNAPSHOT_MEM_CACHE: dict[str, dict] = {}
_SNAPSHOT_MEM_CACHE_MAX = 24


def _snapshot_mem_cache_max() -> int:
    import os

    raw = (os.environ.get("EOD_SNAPSHOT_MEM_CACHE_MAX") or "").strip()
    if raw:
        try:
            return max(4, min(64, int(raw)))
        except ValueError:
            pass
    return _SNAPSHOT_MEM_CACHE_MAX


def clear_eod_snapshot_mem_cache() -> dict[str, int]:
    """Clear in-process EOD snapshot dicts (forward-tracking path)."""
    n = len(_SNAPSHOT_MEM_CACHE)
    _SNAPSHOT_MEM_CACHE.clear()
    return {"cleared": n}


def _load_snapshot_mem(eod_dir: Path | None, date_str: str) -> dict | None:
    """Load EOD snapshot with bounded in-process reuse (cleared after heavy jobs)."""
    hit = _SNAPSHOT_MEM_CACHE.get(date_str)
    if hit is not None:
        return hit
    data = _load_snapshot(eod_dir, date_str)
    if data is not None:
        cap = _snapshot_mem_cache_max()
        while len(_SNAPSHOT_MEM_CACHE) >= cap:
            _SNAPSHOT_MEM_CACHE.pop(next(iter(_SNAPSHOT_MEM_CACHE)))
        _SNAPSHOT_MEM_CACHE[date_str] = data
    return data


def _cap_records_recent(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Keep the most recent observations (records are built newest-first per horizon block)."""
    if len(records) <= limit:
        return records
    sorted_rows = sorted(
        records,
        key=lambda r: (str(r.get("as_of_date") or ""), str(r.get("ticker") or "")),
        reverse=True,
    )
    return sorted_rows[:limit]


def _list_eod_dates_redis() -> list[str]:
    """EOD dates from Redis (same source as paper trading / dashboard list)."""
    try:
        from signals.cache import list_eod_dates_redis
        out = list_eod_dates_redis()
        return sorted(out) if out else []
    except Exception:
        return []


def _list_eod_dates(eod_dir: Path) -> list[str]:
    """Merge EOD dates from Redis and from files under eod_dir."""
    seen: set[str] = set()
    dates: list[str] = []
    for d in _list_eod_dates_redis():
        if d not in seen and len(d) == 10 and d[4] == "-" and d[7] == "-":
            seen.add(d)
            dates.append(d)
    if eod_dir and eod_dir.exists():
        for p in eod_dir.glob("*.json"):
            try:
                d = p.stem
                if d not in seen and len(d) == 10 and d[4] == "-" and d[7] == "-":
                    seen.add(d)
                    dates.append(d)
            except Exception:
                pass
    return sorted(set(dates))


def _load_snapshot(eod_dir: Path, date_str: str) -> dict | None:
    """Load EOD snapshot: Redis first, then file (same as paper_trade_logger)."""
    try:
        from signals.cache import get_eod_snapshot_redis
        data = get_eod_snapshot_redis(date_str)
        if data and isinstance(data, dict) and data.get("run_results") is not None:
            return data
    except Exception:
        pass
    if not eod_dir or not (eod_dir / f"{date_str}.json").exists():
        return None
    try:
        with open(eod_dir / f"{date_str}.json") as f:
            return json.load(f)
    except Exception as e:
        logger.debug("Load EOD %s: %s", date_str, e)
        return None


def signal_bucket_from_row(row: dict | None, buy_min: float = 70, sell_max: float = 30) -> str:
    """
    Map composite_buy to signal bucket for accuracy stats.
    Not the same as run_signals' ML-aware `signal` (BUY/STRONG BUY/HOLD): this uses score thresholds only.
    """
    if not row:
        return "N/A"
    score = row.get("composite_buy")
    if score is None:
        return "N/A"
    try:
        score = float(score)
    except (TypeError, ValueError):
        return "N/A"
    em = str(row.get("entry_mode") or "").lower()
    go = str(row.get("go_no_go") or "").lower()
    # High composite without full_go is not an add signal — avoids inflating HOLD/ADD forward stats.
    if em != "full_go":
        if score <= sell_max:
            return "CONSIDER TRIM"
        return "HOLD"
    if score >= buy_min:
        return "HOLD/ADD"
    if score <= sell_max:
        return "CONSIDER TRIM"
    return "HOLD"


def _signal_from_row(row: dict | None, buy_min: float = 70, sell_max: float = 30) -> str:
    """
    Tracking signal bucket aligned with run_signals.
    Prefer ML-aware `signal` field when present; fallback to score-threshold bucket.
    """
    if row and isinstance(row, dict):
        sig = str(row.get("signal") or "").upper().strip()
        if sig:
            if any(x in sig for x in ("STRONG BUY", "BUY", "HOLD/ADD")):
                return "HOLD/ADD"
            if any(x in sig for x in ("TRIM", "SELL", "REDUCE", "AVOID")):
                return "CONSIDER TRIM"
            if sig in ("HOLD", "WATCH"):
                return "HOLD"
    return signal_bucket_from_row(row, buy_min=buy_min, sell_max=sell_max)


def _signal_and_source_from_row(
    row: dict | None,
    buy_min: float = 70,
    sell_max: float = 30,
) -> tuple[str, str]:
    """
    Return normalized tracking bucket and its source:
    - ml_signal: mapped from run_signals `signal`
    - score_fallback: derived from composite_buy thresholds
    """
    if row and isinstance(row, dict):
        sig = str(row.get("signal") or "").upper().strip()
        if sig:
            return _signal_from_row(row, buy_min=buy_min, sell_max=sell_max), "ml_signal"
    return signal_bucket_from_row(row, buy_min=buy_min, sell_max=sell_max), "score_fallback"


def get_forward_tracking(
    eod_dir: Path | None = None,
    data_root: Path | None = None,
    tickers: list[str] | None = None,
    horizons: list[int] | None = None,
    max_pairs_per_horizon: int = 30,
    buy_min: float | None = None,
    sell_max: float | None = None,
    max_records: int | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    Multi-horizon forward returns and signal accuracy.

    Horizons are measured in **EOD snapshot steps** (sorted snapshot dates). If you save one snapshot
    per trading day, horizon=20 ≈ 20 trading days; missing days shift the pairing.

    For each (date D, date D+N) where N = horizon steps in the snapshot list:
    - Compute actual_return_pct for SPY/QQQ from EOD `close` (same series as run_signals).
    - Bucket `our_signal` from **composite_buy** only via _signal_from_row (not ML `signal`).

    Returns:
      - records: [{as_of_date, next_date, ticker, horizon_days, our_signal, actual_return_pct}]
      - summary_by_horizon: {horizon_days: {avg_return_pct, n_observations}}
      - summary_by_signal: {signal: {avg_return_20d, n}} for horizon 20
    """
    if eod_dir is None and data_root is not None:
        eod_dir = data_root / _EOD_DIR_NAME
    if eod_dir is None:
        eod_dir = Path(__file__).resolve().parent.parent / "data" / _EOD_DIR_NAME

    if buy_min is None or sell_max is None:
        try:
            from config_loader import load_config
            sc = load_config().get("score", {}) or {}
            if buy_min is None:
                buy_min = float(sc.get("buy_min", 70))
            if sell_max is None:
                sell_max = float(sc.get("sell_max", 30))
        except Exception:
            buy_min = buy_min if buy_min is not None else 70.0
            sell_max = sell_max if sell_max is not None else 30.0

    syms = tickers or ["SPY", "QQQ"]
    horizon_list = list(horizons or [5, 20, 60])
    record_cap = max_records if max_records is not None else _DEFAULT_MAX_RECORDS
    ft_cfg = (config or {}).get("forward_tracking") or {}
    enrich_gates = bool(ft_cfg.get("enrich_gates_from_eod", True))

    dates = _list_eod_dates(eod_dir)
    if len(dates) < 2:
        return {
            "records": [],
            "summary_by_horizon": {},
            "summary_by_signal": {},
            "summary_by_gates": {},
            "message": "Need at least 2 EOD snapshots. Run run_daily.py regularly.",
        }
    # Always include 1-step horizon when possible — freshest completed as-of is dates[-2], not dates[-6] (5d).
    if len(dates) >= 2 and 1 not in horizon_list:
        horizon_list = [1] + horizon_list

    # Score every ticker the EOD job actually snapshots (~116), not only the dashboard /
    # audit list passed in (~45) — otherwise names like REGN never get a track record even
    # though their daily rows are sitting in every snapshot.
    # Only for the full panel computes (they pass config); narrow SPY/QQQ hit-rate probes don't.
    # ── Per-run snapshot index ─────────────────────────────────────────────
    # Load each snapshot this run can touch exactly ONCE, keyed {date: {ticker: row}}.
    # Previously every (horizon × pair × ticker) re-loaded up to 60 path snapshots through a
    # 24-entry LRU and linearly scanned ~116 rows per step (~600k loads for 116 tickers ×
    # 60 pairs × 1/5/20/60d) — the full refresh ran past 10 minutes on Railway and never landed.
    max_h = max([h for h in horizon_list if h < len(dates)] or [1])
    first_needed = max(0, len(dates) - max_pairs_per_horizon - max_h - 1)
    rows_by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for d in dates[first_needed:]:
        snap_d = _load_snapshot(eod_dir, d)
        if not snap_d:
            continue
        rows_by_date[d] = {
            str(r["ticker"]).upper(): r
            for r in snap_d.get("run_results", [])
            if isinstance(r, dict) and r.get("ticker")
        }

    if config is not None and bool(ft_cfg.get("include_eod_universe", True)):
        latest_snap = {"run_results": list((rows_by_date.get(dates[-1]) or {}).values())}
        seen_syms = {str(t).upper() for t in syms}
        extra = [
            str(r["ticker"]).upper()
            for r in latest_snap.get("run_results", [])
            if isinstance(r, dict) and r.get("ticker") and str(r["ticker"]).upper() not in seen_syms
        ]
        syms = list(syms) + sorted(set(extra))

    records: list[dict[str, Any]] = []
    signal_source_counts: dict[str, int] = {"ml_signal": 0, "score_fallback": 0}
    use_intraday = bool(ft_cfg.get("use_intraday_touch", True))
    date_to_idx = {d: i for i, d in enumerate(dates)}
    # (as_of, ticker) → (enriched row, passes gate): enrichment is horizon-independent.
    prepared_rows: dict[tuple[str, str], tuple[dict[str, Any], bool]] = {}

    try:
        from signals.tracking_gate import enrich_tracking_row, passes_tracking_gate
        from signals.forward_tracking_metrics import (
            aggregate_by_gates,
            aggregate_by_signal,
            aggregate_by_trim_gates,
            aggregate_horizon_stats,
            bars_from_index,
            compute_validated_forward_return,
            entry_band_position,
            path_metrics,
            read_frozen_gates,
            read_frozen_trim_gates,
            st_stop_target_from_row,
            trim_outcome_metrics,
        )
    except Exception as imp_err:
        return {
            "records": [],
            "summary_by_horizon": {},
            "summary_by_signal": {},
            "summary_by_gates": {},
            "message": f"Forward tracking metrics unavailable: {imp_err}",
        }

    from signals.alpha.excess import excess_return_pct

    bench_tk = str(ft_cfg.get("benchmark_ticker") or "SPY").upper()
    for horizon in horizon_list:
        if horizon >= len(dates):
            continue
        pairs = list(zip(dates[:-horizon], dates[horizon:]))[-max_pairs_per_horizon:]
        for as_of_date, next_date in reversed(pairs):
            run_by_ticker = rows_by_date.get(as_of_date)
            run_next_by_ticker = rows_by_date.get(next_date)
            if not run_by_ticker or not run_next_by_ticker:
                continue
            start_idx = date_to_idx.get(as_of_date)
            if start_idx is None:
                continue
            bench_ret_pct: float | None = None
            b_row, b_next = run_by_ticker.get(bench_tk), run_next_by_ticker.get(bench_tk)
            if b_row and b_next:
                try:
                    bench_ret_pct, _bq = compute_validated_forward_return(
                        b_row, b_next, horizon=horizon, ticker=bench_tk
                    )
                except Exception:
                    bench_ret_pct = None

            for ticker in syms:
                tk = str(ticker).upper()
                row = run_by_ticker.get(tk)
                row_next = run_next_by_ticker.get(tk)
                if not row or not row_next:
                    continue
                prior = row.get("close")
                actual = row_next.get("close")
                if prior is None or actual is None:
                    continue
                try:
                    prior = float(prior)
                    actual = float(actual)
                except (TypeError, ValueError):
                    continue
                if prior <= 0:
                    continue
                cache_key = (as_of_date, tk)
                cached_row = prepared_rows.get(cache_key)
                if cached_row is None:
                    row_work = dict(row)
                    if enrich_gates:
                        if not row_work.get("gates_frozen"):
                            enrich_tracking_row(row_work)
                    try:
                        from signals.retail_action_payload import align_ml_signal_with_retail_gates

                        align_ml_signal_with_retail_gates(row_work)
                    except Exception:
                        pass
                    passed = passes_tracking_gate(row_work, config, "forward_tracking")
                    prepared_rows[cache_key] = (row_work, passed)
                else:
                    row_work, passed = cached_row
                if not passed:
                    continue
                ret_pct, data_quality = compute_validated_forward_return(
                    row_work,
                    row_next,
                    horizon=horizon,
                    ticker=tk,
                )
                gate = read_frozen_gates(row_work)
                trim_gate = read_frozen_trim_gates(row_work)
                our_signal, signal_source = _signal_and_source_from_row(
                    row_work, buy_min=buy_min, sell_max=sell_max
                )
                go_key = str(gate.get("go_no_go") or "unknown").lower()
                if go_key not in ("go", "no_go"):
                    go_key = "unknown"
                close_at_signal_val = float(row_work.get("close") or prior)
                stop, target = st_stop_target_from_row(row_work)
                entry_band_pos = entry_band_position(close_at_signal_val, stop, target)

                if data_quality == "stale_session":
                    rec = {
                        "as_of_date": as_of_date,
                        "next_date": next_date,
                        "ticker": tk,
                        "horizon_days": horizon,
                        "our_signal": our_signal,
                        "signal_source": signal_source,
                        "actual_return_pct": None,
                        "forward_status": "pending",
                        "data_quality": data_quality,
                        "pending_reason": "No new OHLCV session between snapshots (holiday or duplicate EOD)",
                        "close_at_signal": round(close_at_signal_val, 4),
                        "close_at_forward": round(float(row_next.get("close") or actual), 4),
                        "entry_band_position": entry_band_pos,
                        "gate_cleared": gate.get("gate_cleared"),
                        "go_no_go": gate.get("go_no_go"),
                        "entry_mode": (
                            gate.get("entry_mode")
                            or row_work.get("entry_mode")
                            or (row_work.get("retail_status") or {}).get("entry_mode")
                        ),
                        "gates_passed": gate.get("gates_passed"),
                        "gates_total": gate.get("gates_total"),
                        "gates_frozen": bool(row_work.get("gates_frozen")),
                        "trim_gate_cleared": trim_gate.get("trim_gate_cleared"),
                        "trim_gates_passed": trim_gate.get("trim_gates_passed"),
                        "trim_gates_total": trim_gate.get("trim_gates_total"),
                        "trim_score_triggered": trim_gate.get("trim_score_triggered"),
                        "trim_recommendation": trim_gate.get("trim_recommendation"),
                        "trim_gates_frozen": bool(row_work.get("trim_gates_frozen")),
                        "model_version": row_work.get("model_version"),
                    }
                    records.append(rec)
                    signal_source_counts[signal_source] = signal_source_counts.get(signal_source, 0) + 1
                    continue

                if ret_pct is None:
                    continue

                path_bars = bars_from_index(dates, start_idx, horizon, tk, rows_by_date)
                path = path_metrics(
                    float(row_work.get("close") or prior),
                    path_bars,
                    stop,
                    target,
                    use_intraday=use_intraday,
                )
                trim_m = trim_outcome_metrics(ret_pct, our_signal)

                rec: dict[str, Any] = {
                    "as_of_date": as_of_date,
                    "next_date": next_date,
                    "ticker": tk,
                    "horizon_days": horizon,
                    "our_signal": our_signal,
                    "signal_source": signal_source,
                    "actual_return_pct": ret_pct,
                    "benchmark_ticker": bench_tk,
                    "benchmark_return_pct": bench_ret_pct,
                    "excess_return_pct": excess_return_pct(ret_pct, bench_ret_pct),
                    "composite_buy": row_work.get("composite_buy"),
                    "forward_status": "complete",
                    "data_quality": data_quality,
                    "close_at_signal": round(close_at_signal_val, 4),
                    "close_at_forward": round(float(row_next.get("close") or actual), 4),
                    "entry_band_position": entry_band_pos,
                    "gate_cleared": gate.get("gate_cleared"),
                    "go_no_go": gate.get("go_no_go"),
                    "entry_mode": (
                        gate.get("entry_mode")
                        or row_work.get("entry_mode")
                        or (row_work.get("retail_status") or {}).get("entry_mode")
                    ),
                    "gates_passed": gate.get("gates_passed"),
                    "gates_total": gate.get("gates_total"),
                    "gates_frozen": bool(row_work.get("gates_frozen")),
                    "trim_gate_cleared": trim_gate.get("trim_gate_cleared"),
                    "trim_gates_passed": trim_gate.get("trim_gates_passed"),
                    "trim_gates_total": trim_gate.get("trim_gates_total"),
                    "trim_score_triggered": trim_gate.get("trim_score_triggered"),
                    "trim_recommendation": trim_gate.get("trim_recommendation"),
                    "trim_gates_frozen": bool(row_work.get("trim_gates_frozen")),
                    "ml_short_prob": row_work.get("ml_short_prob"),
                    "falling_knife": row_work.get("falling_knife"),
                    "st_stop_at_signal": stop,
                    "st_target_at_signal": target,
                    "hit_st_stop": path.get("hit_st_stop"),
                    "hit_st_target": path.get("hit_st_target"),
                    "max_gain_pct": path.get("max_gain_pct"),
                    "max_drawdown_pct": path.get("max_drawdown_pct"),
                    "model_version": row_work.get("model_version"),
                }
                if trim_m:
                    rec.update(trim_m)
                records.append(rec)
                signal_source_counts[signal_source] = signal_source_counts.get(signal_source, 0) + 1

    summary_by_horizon: dict[str, Any] = {}
    for h in horizon_list:
        hrows = [r for r in records if r.get("horizon_days") == h]
        if hrows:
            summary_by_horizon[h] = aggregate_horizon_stats(hrows)

    summary_by_signal = aggregate_by_signal(records, 20)
    # Back-compat keys for ModelHealthStrip
    for sig, stats in list(summary_by_signal.items()):
        if stats.get("avg_return_pct") is not None:
            stats["avg_return_20d_pct"] = stats["avg_return_pct"]

    summary_by_go_no_go: dict[str, dict[str, Any]] = {}
    for go_key in ("go", "no_go", "unknown"):
        grows = [
            r
            for r in records
            if r.get("horizon_days") == 20
            and str(r.get("go_no_go") or "unknown").lower() == go_key
        ]
        if grows:
            summary_by_go_no_go[go_key] = aggregate_horizon_stats(grows)
            summary_by_go_no_go[go_key]["avg_return_20d_pct"] = summary_by_go_no_go[go_key].get(
                "avg_return_pct"
            )
            summary_by_go_no_go[go_key]["hit_rate_pct"] = summary_by_go_no_go[go_key].get(
                "win_rate_pct"
            )

    summary_by_entry_mode: dict[str, dict[str, Any]] = {}
    for em_key in ("full_go", "starter_only", "hard_lock"):
        em_rows = [
            r
            for r in records
            if r.get("horizon_days") == 20 and str(r.get("entry_mode") or "").lower() == em_key
        ]
        if em_rows:
            summary_by_entry_mode[em_key] = aggregate_horizon_stats(em_rows)
            summary_by_entry_mode[em_key]["avg_return_20d_pct"] = summary_by_entry_mode[em_key].get(
                "avg_return_pct"
            )
            summary_by_entry_mode[em_key]["hit_rate_pct"] = summary_by_entry_mode[em_key].get(
                "win_rate_pct"
            )

    actionable_buy_rows = [
        r
        for r in records
        if r.get("horizon_days") == 20
        and str(r.get("entry_mode") or "").lower() == "full_go"
        and str(r.get("our_signal") or "") == "HOLD/ADD"
    ]
    summary_actionable_buy: dict[str, Any] = {}
    if actionable_buy_rows:
        summary_actionable_buy = aggregate_horizon_stats(actionable_buy_rows)
        summary_actionable_buy["avg_return_20d_pct"] = summary_actionable_buy.get("avg_return_pct")
        summary_actionable_buy["label"] = "full_go + HOLD/ADD (entry slice)"
        band_counts: dict[str, int] = {}
        for r in actionable_buy_rows:
            k = str(r.get("entry_band_position") or "unknown")
            band_counts[k] = band_counts.get(k, 0) + 1
        summary_actionable_buy["entry_band_breakdown"] = band_counts

    # "Filled at the buy band, not chasing" slice — same full_go + HOLD/ADD cohort as
    # summary_actionable_buy, restricted to rows where signal-day close was actually inside
    # the model's own entry band (st_band). Mirrors paper_trade_logger's limit_touch discipline
    # so we can see whether entry-band-only fills change the win rate / avg return.
    in_band_buy_rows = [r for r in actionable_buy_rows if r.get("entry_band_position") == "inside"]
    summary_actionable_buy_in_band: dict[str, Any] = {}
    if in_band_buy_rows:
        summary_actionable_buy_in_band = aggregate_horizon_stats(in_band_buy_rows)
        summary_actionable_buy_in_band["avg_return_20d_pct"] = summary_actionable_buy_in_band.get(
            "avg_return_pct"
        )
        summary_actionable_buy_in_band["label"] = (
            "full_go + HOLD/ADD, entry-band fills only (excludes chasing above band)"
        )

    summary_by_entry_band_position: dict[str, dict[str, Any]] = {}
    for pos_key in ("inside", "above", "below"):
        pos_rows = [
            r
            for r in records
            if r.get("horizon_days") == 20 and r.get("entry_band_position") == pos_key
        ]
        if pos_rows:
            summary_by_entry_band_position[pos_key] = aggregate_horizon_stats(pos_rows)
            summary_by_entry_band_position[pos_key]["avg_return_20d_pct"] = (
                summary_by_entry_band_position[pos_key].get("avg_return_pct")
            )
            summary_by_entry_band_position[pos_key]["hit_rate_pct"] = (
                summary_by_entry_band_position[pos_key].get("win_rate_pct")
            )

    summary_by_gates = aggregate_by_gates([r for r in records if r.get("horizon_days") == 20])
    summary_by_ml_bucket = _aggregate_by_ml_bucket(records, aggregate_horizon_stats)
    summary_by_trim_gates = aggregate_by_trim_gates(
        [r for r in records if r.get("horizon_days") == 20 and r.get("trim_score_triggered")]
    )

    # Segments win-rate/return stats by which gate/band/regime logic version produced
    # the signal — mixing pre- and post-fix signals into one number can't tell you
    # whether the *current* model is any good, only some blend across versions of it.
    # Versions aren't known ahead of time (hand-bumped in signals/model_version.py), so
    # this iterates the distinct set actually seen rather than a fixed tuple.
    summary_by_model_version: dict[str, dict[str, Any]] = {}
    version_keys = sorted({str(r.get("model_version") or "legacy") for r in records})
    for v_key in version_keys:
        v_rows = [
            r
            for r in records
            if r.get("horizon_days") == 20 and str(r.get("model_version") or "legacy") == v_key
        ]
        if v_rows:
            summary_by_model_version[v_key] = aggregate_horizon_stats(v_rows)
            summary_by_model_version[v_key]["avg_return_20d_pct"] = summary_by_model_version[v_key].get(
                "avg_return_pct"
            )
            summary_by_model_version[v_key]["hit_rate_pct"] = summary_by_model_version[v_key].get(
                "win_rate_pct"
            )

    total_records = len(records)
    by_ticker = _build_by_ticker_index(records)
    capped = _cap_records_recent(records, record_cap)
    as_of_dates = [str(r.get("as_of_date") or "") for r in records if r.get("as_of_date")]
    newest_completed_as_of = dates[-2] if len(dates) >= 2 else None
    meta = {
        "eod_date_first": dates[0] if dates else None,
        "eod_date_last": dates[-1] if dates else None,
        "eod_snapshot_count": len(dates),
        "records_total": total_records,
        "records_returned": len(capped),
        "as_of_date_min": min(as_of_dates) if as_of_dates else None,
        "as_of_date_max": max(as_of_dates) if as_of_dates else None,
        "newest_completed_as_of": newest_completed_as_of,
        "ticker_count": len(syms),
        "current_model_version": MODEL_VERSION,
    }

    result = {
        "records": capped,
        "summary_by_horizon": summary_by_horizon,
        "summary_by_signal": summary_by_signal,
        "summary_by_go_no_go": summary_by_go_no_go,
        "summary_by_entry_mode": summary_by_entry_mode,
        "summary_by_model_version": summary_by_model_version,
        "summary_actionable_buy": summary_actionable_buy if summary_actionable_buy else None,
        "summary_actionable_buy_in_band": (
            summary_actionable_buy_in_band if summary_actionable_buy_in_band else None
        ),
        "summary_by_entry_band_position": summary_by_entry_band_position,
        "summary_by_gates": summary_by_gates,
        "summary_by_ml_bucket": summary_by_ml_bucket,
        "summary_by_trim_gates": summary_by_trim_gates,
        "summary_timing_vs_hold": _timing_vs_hold(records),
        "signal_source_counts": signal_source_counts,
        # Per-ticker stats + recent daily calls from ALL records (records above are capped to
        # the newest N watchlist-wide, which silently truncated single-ticker history).
        # Server-side only — stripped from HTTP responses (see _strip_forward_tracking_heavy).
        "by_ticker": by_ticker,
        "meta": meta,
        "data_source_note": (
            "Returns and ST stop/target touches from EOD OHLCV between snapshot dates "
            "(not paper trades). Stale holiday duplicates and impossible close jumps are "
            "excluded; 1d rows may use daily_move_pct when close chain is broken. "
            "HOLD/ADD bucket requires full_go entry_mode; ML BUY without full_go is downgraded. "
            "See summary_actionable_buy for entry slice; summary_actionable_buy_in_band restricts "
            "that slice to signals where price was inside the entry band (not chasing) at signal "
            "time, mirroring the paper-trading book's limit_touch fill discipline. "
            "Gate buckets differ from audit verdict rules. "
            "summary_by_model_version segments these stats by which gate/band/regime logic "
            "version produced the signal (meta.current_model_version is the live one) — "
            "records predating versioning show as 'legacy'."
        ),
        "message": None if records else "Insufficient EOD snapshots for multi-horizon.",
    }
    try:
        from signals.forward_tracking_lens import build_summary_by_lens

        result["summary_by_lens"] = build_summary_by_lens(result)
    except Exception as lens_err:
        logger.debug("summary_by_lens: %s", lens_err)
        result["summary_by_lens"] = {}
    return result


_DAILY_CALLS_PER_TICKER = 30

_ML_BUCKETS = ((0, 40, "<40%"), (40, 55, "40–55%"), (55, 70, "55–70%"), (70, 101, "≥70%"))


def _aggregate_by_ml_bucket(records: list[dict[str, Any]], aggregate) -> dict[str, Any]:
    """Win rate / avg return by short-ML probability bucket, split falling-knife vs normal,
    for 5d and 20d — the calibration check for "highest ML probs sit on falling knives".
    ml_short_prob is stored as 0–1 or 0–100 depending on source; normalized here."""
    out: dict[str, Any] = {}
    for h in (5, 20):
        hrows = [r for r in records if r.get("horizon_days") == h and r.get("ml_short_prob") is not None]
        block: dict[str, Any] = {}
        for lo, hi, label in _ML_BUCKETS:
            for knife_key, knife_val in (("falling_knife", True), ("normal", False)):
                rows = []
                for r in hrows:
                    p = float(r["ml_short_prob"])
                    p = p * 100.0 if p <= 1.0 else p
                    if lo <= p < hi and bool(r.get("falling_knife")) is knife_val:
                        rows.append(r)
                if rows:
                    block.setdefault(label, {})[knife_key] = aggregate(rows)
        if block:
            out[str(h)] = block
    return out


def _call_right(signal: str, ret: float | None) -> bool | None:
    """Direction check for a daily call: ADD right if up, TRIM right if down, HOLD unscored."""
    if ret is None:
        return None
    s = (signal or "").upper()
    if "ADD" in s:
        return ret > 0
    if "TRIM" in s:
        return ret < 0
    return None


def _timing_vs_hold(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    from signals.forward_tracking_metrics import aggregate_timing_vs_hold

    try:
        return aggregate_timing_vs_hold(records, 20) or None
    except Exception as e:
        logger.debug("timing_vs_hold: %s", e)
        return None


def _build_by_ticker_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    from signals.forward_tracking_metrics import (
        build_ticker_track_record,
        build_ticker_track_record_all_horizons,
    )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        tk = str(r.get("ticker") or "").upper()
        if tk:
            grouped.setdefault(tk, []).append(r)
    out: dict[str, Any] = {}
    for tk, rows in grouped.items():
        try:
            track = build_ticker_track_record(rows, tk, current_model_version=MODEL_VERSION)
            track["by_horizon"] = build_ticker_track_record_all_horizons(
                rows, tk, current_model_version=MODEL_VERSION
            ).get("by_horizon")
        except Exception as e:
            logger.debug("by_ticker %s: %s", tk, e)
            continue
        daily = sorted(
            (r for r in rows if r.get("horizon_days") == 1),
            key=lambda r: str(r.get("as_of_date") or ""),
            reverse=True,
        )[:_DAILY_CALLS_PER_TICKER]
        track["daily_calls"] = [
            {
                "date": r.get("as_of_date"),
                "next_date": r.get("next_date"),
                "signal": r.get("our_signal"),
                "close": r.get("close_at_signal"),
                "next_close": r.get("close_at_forward"),
                "return_pct": r.get("actual_return_pct"),
                "status": r.get("forward_status"),
                "gates_passed": r.get("gates_passed"),
                "gates_total": r.get("gates_total"),
                "model_version": r.get("model_version") or "legacy",
                "right": _call_right(str(r.get("our_signal") or ""), r.get("actual_return_pct")),
            }
            for r in daily
        ]
        track["latest_call_date"] = track["daily_calls"][0]["date"] if track["daily_calls"] else None
        out[tk] = track
    return out


def collect_forward_records(
    data_root: Path | None = None,
    tickers: list[str] | None = None,
    horizons: list[int] | None = None,
    buy_min: float | None = None,
    sell_max: float | None = None,
    max_pairs_per_horizon: int = 2000,
    eod_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """
    All (as_of, ticker, horizon) forward return observations from EOD snapshots — for reports / monthly buckets.
    Horizons are **EOD snapshot steps** (same semantics as get_forward_tracking).
    """
    if buy_min is None or sell_max is None:
        try:
            from config_loader import load_config

            cfg = load_config()
            sc = cfg.get("score", {}) or {}
            if buy_min is None:
                buy_min = float(sc.get("buy_min", 70))
            if sell_max is None:
                sell_max = float(sc.get("sell_max", 30))
        except Exception:
            if buy_min is None:
                buy_min = 70.0
            if sell_max is None:
                sell_max = 30.0

    if tickers is None:
        try:
            from config_loader import load_config

            wl = load_config().get("watchlist") or []
            tickers = [str(t).upper() for t in wl if t]
        except Exception:
            tickers = ["SPY", "QQQ"]

    horizon_list = list(horizons or [5, 20])
    if eod_dir is None and data_root is not None:
        eod_dir = data_root / _EOD_DIR_NAME
    if eod_dir is None:
        eod_dir = Path(__file__).resolve().parent.parent / "data" / _EOD_DIR_NAME

    dates = _list_eod_dates(eod_dir)
    if len(dates) < 2:
        return []

    from signals.forward_tracking_metrics import compute_validated_forward_return

    # Same per-run snapshot index as get_forward_tracking — previously every
    # (horizon × pair) re-loaded and re-scanned two full snapshots.
    horizon_list = [h for h in horizon_list if h < len(dates)]
    if not horizon_list:
        return []
    max_h = max(horizon_list)
    first_needed = max(0, len(dates) - max_pairs_per_horizon - max_h - 1)
    rows_by_date: dict[str, dict[str, dict[str, Any]]] = {}
    for d in dates[first_needed:]:
        snap_d = _load_snapshot(eod_dir, d)
        if not snap_d:
            continue
        rows_by_date[d] = {
            str(r["ticker"]).upper(): r
            for r in snap_d.get("run_results", [])
            if isinstance(r, dict) and r.get("ticker")
        }

    records: list[dict[str, Any]] = []
    syms = [str(t).upper() for t in tickers]

    for horizon in horizon_list:
        pairs = list(zip(dates[:-horizon], dates[horizon:]))[-max_pairs_per_horizon:]
        for as_of_date, next_date in pairs:
            run_by_ticker = rows_by_date.get(as_of_date)
            run_next_by_ticker = rows_by_date.get(next_date)
            if not run_by_ticker or not run_next_by_ticker:
                continue

            for tk in syms:
                row = run_by_ticker.get(tk)
                row_next = run_next_by_ticker.get(tk)
                if not row or not row_next:
                    continue
                prior = row.get("close")
                actual = row_next.get("close")
                if prior is None or actual is None:
                    continue
                try:
                    prior = float(prior)
                    actual = float(actual)
                except (TypeError, ValueError):
                    continue
                if prior <= 0:
                    continue
                ret_pct, dq = compute_validated_forward_return(
                    row, row_next, horizon=horizon, ticker=tk
                )
                our_signal, signal_source = _signal_and_source_from_row(
                    row, buy_min=buy_min, sell_max=sell_max
                )
                if dq == "stale_session":
                    records.append({
                        "as_of_date": as_of_date,
                        "next_date": next_date,
                        "ticker": tk,
                        "horizon_days": horizon,
                        "our_signal": our_signal,
                        "signal_source": signal_source,
                        "actual_return_pct": None,
                        "forward_status": "pending",
                        "data_quality": dq,
                    })
                    continue
                if ret_pct is None:
                    continue
                records.append({
                    "as_of_date": as_of_date,
                    "next_date": next_date,
                    "ticker": tk,
                    "horizon_days": horizon,
                    "our_signal": our_signal,
                    "signal_source": signal_source,
                    "actual_return_pct": ret_pct,
                    "forward_status": "complete",
                    "data_quality": dq,
                })

    return records
