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

logger = logging.getLogger(__name__)

_EOD_DIR_NAME = "eod"


def _list_eod_dates(eod_dir: Path) -> list[str]:
    if not eod_dir.exists():
        return []
    dates = []
    for p in eod_dir.glob("*.json"):
        try:
            d = p.stem
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
        with open(p) as f:
            return json.load(f)
    except Exception as e:
        logger.debug("Load EOD %s: %s", date_str, e)
        return None


def _signal_from_row(row: dict | None, buy_min: float = 70, sell_max: float = 30) -> str:
    """Map composite_buy/regime to signal bucket for accuracy stats."""
    if not row:
        return "N/A"
    score = row.get("composite_buy")
    if score is None:
        return "N/A"
    if score >= buy_min:
        return "HOLD/ADD"
    if score <= sell_max:
        return "CONSIDER TRIM"
    return "HOLD"


def get_forward_tracking(
    eod_dir: Path | None = None,
    data_root: Path | None = None,
    tickers: list[str] | None = None,
    horizons: list[int] | None = None,
    max_pairs_per_horizon: int = 30,
) -> dict[str, Any]:
    """
    Multi-horizon forward returns and signal accuracy.

    For each (date D, date D+N) where N = horizon trading days:
    - Compute actual_return_pct for SPY/QQQ
    - Record our signal (HOLD/ADD, HOLD, CONSIDER TRIM) from composite_buy

    Returns:
      - records: [{as_of_date, next_date, ticker, horizon_days, our_signal, actual_return_pct}]
      - summary_by_horizon: {horizon_days: {avg_return_pct, n_observations}}
      - summary_by_signal: {signal: {avg_return_20d, n}} for horizon 20
    """
    if eod_dir is None and data_root is not None:
        eod_dir = data_root / _EOD_DIR_NAME
    if eod_dir is None:
        eod_dir = Path(__file__).resolve().parent.parent / "data" / _EOD_DIR_NAME

    syms = tickers or ["SPY", "QQQ"]
    horizon_list = horizons or [5, 20, 60]

    dates = _list_eod_dates(eod_dir)
    if len(dates) < 2:
        return {
            "records": [],
            "summary_by_horizon": {},
            "summary_by_signal": {},
            "message": "Need at least 2 EOD snapshots. Run run_daily.py regularly.",
        }

    records: list[dict[str, Any]] = []
    by_horizon: dict[int, list[float]] = {h: [] for h in horizon_list}
    by_signal_20: dict[str, list[float]] = {}

    for horizon in horizon_list:
        if horizon >= len(dates):
            continue
        pairs = list(zip(dates[:-horizon], dates[horizon:]))[-max_pairs_per_horizon:]
        for as_of_date, next_date in reversed(pairs):
            snap = _load_snapshot(eod_dir, as_of_date)
            snap_next = _load_snapshot(eod_dir, next_date)
            if not snap or not snap_next:
                continue
            run_by_ticker = {r["ticker"]: r for r in snap.get("run_results", [])}
            run_next_by_ticker = {r["ticker"]: r for r in snap_next.get("run_results", [])}

            for ticker in syms:
                row = run_by_ticker.get(ticker)
                row_next = run_next_by_ticker.get(ticker)
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
                ret_pct = round(100 * (actual - prior) / prior, 2)
                our_signal = _signal_from_row(row)

                records.append({
                    "as_of_date": as_of_date,
                    "next_date": next_date,
                    "ticker": ticker,
                    "horizon_days": horizon,
                    "our_signal": our_signal,
                    "actual_return_pct": ret_pct,
                })
                by_horizon[horizon].append(ret_pct)
                if horizon == 20:
                    by_signal_20.setdefault(our_signal, []).append(ret_pct)

    summary_by_horizon = {}
    for h, returns in by_horizon.items():
        if returns:
            summary_by_horizon[h] = {
                "avg_return_pct": round(sum(returns) / len(returns), 2),
                "n_observations": len(returns),
            }

    summary_by_signal = {}
    for sig, returns in by_signal_20.items():
        if returns:
            n_pos = sum(1 for r in returns if r > 0)
            hit_rate_pct = round(100 * n_pos / len(returns), 1) if returns else 0.0
            summary_by_signal[sig] = {
                "avg_return_20d_pct": round(sum(returns) / len(returns), 2),
                "n_observations": len(returns),
                "hit_rate_pct": hit_rate_pct,
            }

    return {
        "records": records[-200:],  # Cap for response size
        "summary_by_horizon": summary_by_horizon,
        "summary_by_signal": summary_by_signal,
        "message": None if records else "Insufficient EOD snapshots for multi-horizon.",
    }
