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

    dates = _list_eod_dates(eod_dir)
    if len(dates) < 2:
        return {
            "records": [],
            "summary_by_horizon": {},
            "summary_by_signal": {},
            "message": "Need at least 2 EOD snapshots. Run run_daily.py regularly.",
        }
    # With only 2 snapshots, add 1-day horizon so we get (D, D+1) pairs and can verify tracking
    if len(dates) == 2 and 1 not in horizon_list:
        horizon_list = [1] + horizon_list
    elif len(dates) < 6 and 1 not in horizon_list:
        horizon_list = [1] + horizon_list

    records: list[dict[str, Any]] = []
    by_horizon: dict[int, list[float]] = {h: [] for h in horizon_list}
    by_signal_20: dict[str, list[float]] = {}
    signal_source_counts: dict[str, int] = {"ml_signal": 0, "score_fallback": 0}

    for horizon in horizon_list:
        if horizon >= len(dates):
            continue
        pairs = list(zip(dates[:-horizon], dates[horizon:]))[-max_pairs_per_horizon:]
        for as_of_date, next_date in reversed(pairs):
            snap = _load_snapshot(eod_dir, as_of_date)
            snap_next = _load_snapshot(eod_dir, next_date)
            if not snap or not snap_next:
                continue
            run_by_ticker = {
                str(r["ticker"]).upper(): r
                for r in snap.get("run_results", [])
                if isinstance(r, dict) and r.get("ticker")
            }
            run_next_by_ticker = {
                str(r["ticker"]).upper(): r
                for r in snap_next.get("run_results", [])
                if isinstance(r, dict) and r.get("ticker")
            }

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
                ret_pct = round(100 * (actual - prior) / prior, 2)
                our_signal, signal_source = _signal_and_source_from_row(
                    row, buy_min=buy_min, sell_max=sell_max
                )

                records.append({
                    "as_of_date": as_of_date,
                    "next_date": next_date,
                    "ticker": tk,
                    "horizon_days": horizon,
                    "our_signal": our_signal,
                    "signal_source": signal_source,
                    "actual_return_pct": ret_pct,
                })
                signal_source_counts[signal_source] = signal_source_counts.get(signal_source, 0) + 1
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
        "signal_source_counts": signal_source_counts,
        "message": None if records else "Insufficient EOD snapshots for multi-horizon.",
    }


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

    records: list[dict[str, Any]] = []
    syms = [str(t).upper() for t in tickers]

    for horizon in horizon_list:
        if horizon >= len(dates):
            continue
        pairs = list(zip(dates[:-horizon], dates[horizon:]))[-max_pairs_per_horizon:]
        for as_of_date, next_date in pairs:
            snap = _load_snapshot(eod_dir, as_of_date)
            snap_next = _load_snapshot(eod_dir, next_date)
            if not snap or not snap_next:
                continue
            run_by_ticker = {
                str(r["ticker"]).upper(): r
                for r in snap.get("run_results", [])
                if isinstance(r, dict) and r.get("ticker")
            }
            run_next_by_ticker = {
                str(r["ticker"]).upper(): r
                for r in snap_next.get("run_results", [])
                if isinstance(r, dict) and r.get("ticker")
            }

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
                ret_pct = round(100 * (actual - prior) / prior, 2)
                our_signal, signal_source = _signal_and_source_from_row(
                    row, buy_min=buy_min, sell_max=sell_max
                )
                records.append({
                    "as_of_date": as_of_date,
                    "next_date": next_date,
                    "ticker": tk,
                    "horizon_days": horizon,
                    "our_signal": our_signal,
                    "signal_source": signal_source,
                    "actual_return_pct": ret_pct,
                })

    return records
