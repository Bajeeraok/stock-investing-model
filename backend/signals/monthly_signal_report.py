"""
Monthly aggregation: signal bucket (score-based) → forward returns at EOD horizons 5 and 20.

Uses EOD snapshots under data/eod/ (same source as forward_tracking). Horizons are **snapshot steps**:
if you save one snapshot per trading day, horizon 5 ≈ 5 trading days apart in the snapshot list.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signals.forward_tracking import collect_forward_records

logger = logging.getLogger(__name__)


def _stats(returns: list[float]) -> dict[str, Any]:
    if not returns:
        return {}
    n = len(returns)
    pos = sum(1 for r in returns if r > 0)
    sorted_r = sorted(returns)
    mid = n // 2
    if n % 2 == 1:
        med = float(sorted_r[mid])
    else:
        med = (sorted_r[mid - 1] + sorted_r[mid]) / 2
    return {
        "n": n,
        "avg_return_pct": round(sum(returns) / n, 2),
        "median_return_pct": round(med, 2),
        "hit_rate_pct": round(100 * pos / n, 1),
    }


def aggregate_monthly_by_bucket(
    records: list[dict[str, Any]],
    horizons: list[int] | None = None,
) -> dict[str, Any]:
    """
    Group records by calendar month of as_of_date, then by our_signal, then by horizon_days.
    """
    want = set(horizons or [5, 20])
    # month -> signal -> horizon -> list of returns
    nest: dict[str, dict[str, dict[int, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    for r in records:
        h = r.get("horizon_days")
        if h not in want:
            continue
        ad = r.get("as_of_date")
        if not isinstance(ad, str) or len(ad) < 7:
            continue
        month = ad[:7]
        sig = str(r.get("our_signal") or "N/A")
        try:
            ret = float(r["actual_return_pct"])
        except (KeyError, TypeError, ValueError):
            continue
        nest[month][sig][h].append(ret)

    months_out: list[dict[str, Any]] = []
    for month in sorted(nest.keys()):
        buckets: dict[str, Any] = {}
        for sig, by_h in nest[month].items():
            buckets[sig] = {}
            for h in sorted(by_h.keys()):
                st = _stats(by_h[h])
                if st:
                    buckets[sig][str(h)] = st
        months_out.append({"month": month, "buckets": buckets})

    # Overall (all months) for each signal × horizon
    overall: dict[str, dict[str, Any]] = defaultdict(dict)
    for r in records:
        h = r.get("horizon_days")
        if h not in want:
            continue
        sig = str(r.get("our_signal") or "N/A")
        try:
            ret = float(r["actual_return_pct"])
        except (KeyError, TypeError, ValueError):
            continue
        overall[sig].setdefault(h, []).append(ret)

    overall_out: dict[str, Any] = {}
    for sig, by_h in overall.items():
        overall_out[sig] = {}
        for h, rets in sorted(by_h.items()):
            st = _stats(rets)
            if st:
                overall_out[sig][str(h)] = st

    # Per-ticker overall (all months), same bucket × horizon stats
    t_acc: dict[str, dict[str, dict[int, list[float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in records:
        h = r.get("horizon_days")
        if h not in want:
            continue
        tk = str(r.get("ticker") or "").upper()
        if not tk:
            continue
        sig = str(r.get("our_signal") or "N/A")
        try:
            ret = float(r["actual_return_pct"])
        except (KeyError, TypeError, ValueError):
            continue
        t_acc[tk][sig][h].append(ret)

    by_ticker_out: dict[str, Any] = {}
    for tk, sig_map in t_acc.items():
        by_ticker_out[tk] = {}
        for sig, by_h in sig_map.items():
            by_ticker_out[tk][sig] = {}
            for h, rets in sorted(by_h.items()):
                st = _stats(rets)
                if st:
                    by_ticker_out[tk][sig][str(h)] = st

    return {
        "months": months_out,
        "overall_by_bucket": overall_out,
        "by_ticker_overall": by_ticker_out,
        "n_records_used": len([r for r in records if r.get("horizon_days") in want]),
        "horizons": sorted(want),
    }


def build_monthly_signal_report(
    data_root: Path | None = None,
    *,
    horizons: list[int] | None = None,
    tickers: list[str] | None = None,
    max_pairs_per_horizon: int = 2000,
) -> dict[str, Any]:
    """
    Full report dict for API / JSON file. Includes note on methodology.
    """
    hr = horizons or [5, 20]
    records = collect_forward_records(
        data_root=data_root,
        tickers=tickers,
        horizons=hr,
        max_pairs_per_horizon=max_pairs_per_horizon,
    )
    agg = aggregate_monthly_by_bucket(records, horizons=hr)
    from signals.time_et import now_iso_et

    agg["generated_at"] = now_iso_et()
    agg["methodology"] = (
        "Buckets from composite_buy vs config score.buy_min / score.sell_max (HOLD/ADD, HOLD, CONSIDER TRIM). "
        "Forward returns use EOD snapshot closes; horizon N = N snapshot steps forward (not calendar days if snapshots are missing)."
    )
    if not records:
        agg["message"] = "No forward records — need multiple EOD snapshots under data/eod/ covering watchlist tickers."
    else:
        agg["message"] = None
    return agg


def save_monthly_report_json(
    data_root: Path | None = None,
    path: Path | None = None,
    **kwargs: Any,
) -> tuple[Path, dict[str, Any]]:
    """Write report JSON next to EOD data (or explicit path). Returns (path, report dict)."""
    report = build_monthly_signal_report(data_root=data_root, **kwargs)
    root = data_root
    if root is None:
        try:
            from config_loader import get_data_root

            root = get_data_root()
        except Exception:
            root = Path(__file__).resolve().parent.parent / "data"
    out = path or (root / "reports" / "monthly_signal_buckets.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Wrote monthly signal report to %s", out)
    return out, report
