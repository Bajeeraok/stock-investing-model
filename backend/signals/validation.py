"""
Model validation: compare our next-day bias and estimated range (SPY/QQQ) vs actual closes.
Uses EOD snapshots: prediction as-of date D, actual from snapshot D+1 (next trading day).
Enables direction accuracy, range hit rate, and fine-tuning.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_VALIDATION_TICKERS = ["SPY", "QQQ"]
_EOD_DIR_NAME = "eod"


def _list_eod_dates(eod_dir: Path) -> list[str]:
    if not eod_dir.exists():
        return []
    dates = []
    for p in eod_dir.glob("*.json"):
        try:
            d = p.stem  # YYYY-MM-DD
            if len(d) == 10 and d[4] == "-" and d[7] == "-":
                dates.append(d)
        except Exception:
            pass
    return sorted(dates)


def _load_snapshot(eod_dir: Path, date_str: str) -> dict | None:
    p = eod_dir / f"{date_str}.json"
    if not p.exists():
        return None
    try:
        import json
        with open(p) as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.debug("Load EOD %s: %s", date_str, e)
        return None


def get_validation_records(
    eod_dir: Path | None = None,
    data_root: Path | None = None,
    max_records: int = 60,
    tickers: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Build validation records from EOD snapshots: for each (date D, date D+1) pair,
    compare our prediction (bias + typical range) as-of D to actual close on D+1.
    Returns (records, summary).
    """
    if eod_dir is None and data_root is not None:
        eod_dir = data_root / _EOD_DIR_NAME
    if eod_dir is None:
        eod_dir = Path(__file__).resolve().parent.parent / "data" / _EOD_DIR_NAME
    syms = tickers or _VALIDATION_TICKERS

    dates = _list_eod_dates(eod_dir)
    if len(dates) < 2:
        return [], _empty_summary()

    records: list[dict[str, Any]] = []
    direction_hits = 0
    direction_total = 0
    range_hits = 0
    range_total = 0

    # Use last max_records pairs (most recent first when we reverse)
    pairs = list(zip(dates[:-1], dates[1:]))[-max_records:]
    for as_of_date, next_date in reversed(pairs):
        snap = _load_snapshot(eod_dir, as_of_date)
        snap_next = _load_snapshot(eod_dir, next_date)
        if not snap or not snap_next:
            continue
        run_results = {r["ticker"]: r for r in snap.get("run_results", [])}
        run_next = {r["ticker"]: r for r in snap_next.get("run_results", [])}
        next_day_outlook = snap.get("next_day_outlook") or []
        typical_move = snap.get("typical_move") or []
        our_bias_by_ticker = {o["ticker"]: o for o in next_day_outlook if isinstance(o, dict)}
        typical_by_ticker = {m["ticker"]: m for m in typical_move if isinstance(m, dict)}

        for ticker in syms:
            row = run_results.get(ticker)
            row_next = run_next.get(ticker)
            if not row or not row_next:
                continue
            prior_close = row.get("close")
            actual_close = row_next.get("close")
            if prior_close is None or actual_close is None:
                continue
            try:
                prior_close = float(prior_close)
                actual_close = float(actual_close)
            except (TypeError, ValueError):
                continue
            if prior_close <= 0:
                continue
            actual_return_pct = round(100 * (actual_close - prior_close) / prior_close, 4)
            our = our_bias_by_ticker.get(ticker) or {}
            our_bias = our.get("bias")
            our_pct_green = our.get("pct_green")
            our_typical_range_pct = our.get("typical_range_pct")
            if our_typical_range_pct is None:
                tm = typical_by_ticker.get(ticker) or {}
                our_typical_range_pct = tm.get("typical_pct_1d")
            within_range = (
                abs(actual_return_pct) <= our_typical_range_pct
                if our_typical_range_pct is not None
                else None
            )
            # Direction hit: Bullish -> up, Bearish -> down, Neutral -> no penalty (count as hit for display)
            if our_bias == "Bullish":
                direction_hit = actual_return_pct > 0
            elif our_bias == "Bearish":
                direction_hit = actual_return_pct < 0
            else:
                direction_hit = None  # Neutral: don't count in accuracy
            if direction_hit is not None:
                direction_total += 1
                if direction_hit:
                    direction_hits += 1
            if within_range is not None:
                range_total += 1
                if within_range:
                    range_hits += 1

            records.append({
                "as_of_date": as_of_date,
                "next_date": next_date,
                "ticker": ticker,
                "prior_close": round(prior_close, 2),
                "actual_close": round(actual_close, 2),
                "actual_return_pct": actual_return_pct,
                "our_bias": our_bias,
                "our_pct_green": our_pct_green,
                "our_typical_range_pct": our_typical_range_pct,
                "direction_hit": direction_hit,
                "within_range": within_range,
            })

    summary = {
        "n_records": len(records),
        "direction_accuracy_pct": round(100 * direction_hits / direction_total, 1) if direction_total else None,
        "direction_n": direction_total,
        "range_hit_rate_pct": round(100 * range_hits / range_total, 1) if range_total else None,
        "range_n": range_total,
    }
    return records, summary


def _empty_summary() -> dict[str, Any]:
    return {
        "n_records": 0,
        "direction_accuracy_pct": None,
        "direction_n": 0,
        "range_hit_rate_pct": None,
        "range_n": 0,
    }
