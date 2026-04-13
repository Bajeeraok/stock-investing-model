"""
Walk-forward splits with purged gap between train and test to avoid label overlap.

When forward horizon is H days, any train sample whose label window overlaps the test period
must be dropped (purge). Here we use a simple date-based purge: test starts after train_end + purge_days.
"""
from __future__ import annotations

from typing import Any, Iterator


def purged_walk_forward_folds(
    sorted_dates: list[str],
    *,
    train_bars: int,
    test_bars: int,
    purge_bars: int,
    step_bars: int,
) -> Iterator[tuple[list[str], list[str]]]:
    """
    Yields (train_dates, test_dates) where train window has length ~train_bars,
    test follows after purge_bars gap. Dates must be sorted ascending.
    """
    n = len(sorted_dates)
    if n < train_bars + purge_bars + test_bars + 10:
        return
    i = 0
    while True:
        t0 = i
        t1 = t0 + train_bars
        gap_end = t1 + purge_bars
        t2 = gap_end + test_bars
        if t2 > n:
            break
        train = sorted_dates[t0:t1]
        test = sorted_dates[gap_end:t2]
        yield train, test
        i += step_bars


def tune_buy_min(
    rows: list[dict[str, Any]],
    *,
    horizon_key: str = "fwd_63d_pct",
    candidates: tuple[float, ...] = (60.0, 65.0, 70.0, 75.0, 80.0),
) -> tuple[float, dict[str, Any]]:
    """
    Pick buy_min that maximizes mean forward return among rows with composite_buy >= buy_min.
    Rows should be training-only, no lookahead.
    """
    best = candidates[0]
    best_stats: dict[str, Any] = {}
    best_mean = float("-inf")
    for bm in candidates:
        xs = [
            float(r[horizon_key])
            for r in rows
            if r.get(horizon_key) is not None and float(r.get("composite_buy") or 0) >= bm
        ]
        m = sum(xs) / len(xs) if xs else float("-inf")
        if m > best_mean:
            best_mean = m
            best = bm
            best_stats = {"n": len(xs), "mean_fwd_pct": round(m, 4) if xs else None}
    return best, best_stats


def mean_forward_by_acf_bucket(
    rows: list[dict[str, Any]],
    horizon_key: str = "fwd_63d_pct",
    mr_max: float = -0.028,
) -> dict[str, Any]:
    """Rough MR vs trend bucket using acf_lag1 when present."""
    mr = [float(r[horizon_key]) for r in rows if r.get(horizon_key) is not None and r.get("acf_lag1") is not None and float(r["acf_lag1"]) <= mr_max]
    tr = [float(r[horizon_key]) for r in rows if r.get(horizon_key) is not None and r.get("acf_lag1") is not None and float(r["acf_lag1"]) > mr_max]
    def _m(v: list[float]) -> float | None:
        return round(sum(v) / len(v), 4) if v else None
    return {"mean_fwd_mr_acf": _m(mr), "n_mr": len(mr), "mean_fwd_trend_acf": _m(tr), "n_trend": len(tr)}
