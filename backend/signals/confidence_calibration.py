"""
Confidence calibration audit — reliability diagram.

Compares predicted confidence levels from forward tracking / paper trades
against actual outcomes to produce a reliability diagram:
  predicted confidence bucket -> actual win rate

Surfaced via the ticker detail "Analysis" tab and the dashboard Model Health section.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CalibrationBucket:
    """One bucket in the reliability diagram."""
    bucket_label: str          # e.g. "40-60%"
    predicted_avg: float       # mean predicted confidence in bucket
    actual_win_rate: float     # fraction of trades that hit target
    count: int                 # number of observations
    avg_return_pct: float      # mean return in this bucket


@dataclass
class CalibrationReport:
    """Full reliability diagram + summary stats."""
    buckets: list[CalibrationBucket] = field(default_factory=list)
    total_observations: int = 0
    is_well_calibrated: bool = False
    calibration_error: float | None = None  # mean absolute calibration error
    monotonic: bool = False
    note: str = ""


def _load_forward_tracking_records(data_root: Path) -> list[dict]:
    """Load forward tracking CSV/JSON records."""
    ft_path = data_root / "forward_tracking.json"
    if ft_path.exists():
        try:
            with open(ft_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data.get("records", [])
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def _load_paper_trades(data_root: Path) -> list[dict]:
    """Load paper trades CSV records."""
    import csv
    pt_path = data_root / "paper_trades.csv"
    if not pt_path.exists():
        return []
    try:
        with open(pt_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row for row in reader if isinstance(row, dict)]
    except Exception:
        return []


def _load_eod_snapshots(data_root: Path) -> list[dict]:
    """Load recent EOD snapshots for confidence + outcome pairing."""
    eod_dir = data_root / "eod"
    if not eod_dir.is_dir():
        return []
    records: list[dict] = []
    try:
        files = sorted(eod_dir.glob("*.json"), reverse=True)[:90]
        for fp in files:
            try:
                with open(fp, encoding="utf-8") as f:
                    snap = json.load(f)
                if isinstance(snap, dict) and snap.get("tickers"):
                    date = fp.stem
                    for ticker_data in snap["tickers"]:
                        if not isinstance(ticker_data, dict):
                            continue
                        records.append({
                            "date": date,
                            **ticker_data,
                        })
            except Exception:
                continue
    except Exception:
        pass
    return records


def build_calibration_report(
    data_root: str | Path,
    *,
    bucket_edges: list[int] | None = None,
) -> CalibrationReport:
    """
    Build a reliability diagram from available data.

    Looks for confidence + outcome pairs from:
    1. Forward tracking records (has signal + 20d return)
    2. Paper trades (has confidence + outcome)
    3. EOD snapshots (has confidence + next-day/5d returns)

    Returns a CalibrationReport with buckets ready for UI rendering.
    """
    data_root = Path(data_root)
    if bucket_edges is None:
        bucket_edges = [0, 20, 40, 55, 70, 85, 100]

    # Collect (predicted_confidence_pct, actual_return_pct, hit_target_bool) triples
    observations: list[tuple[float, float, bool]] = []

    # Source 1: Forward tracking
    ft_records = _load_forward_tracking_records(data_root)
    for rec in ft_records:
        c1 = _safe_float(rec.get("confidence_pct"))
        conf = c1 if c1 is not None else _safe_float(rec.get("model_confidence_pct"))
        r1 = _safe_float(rec.get("return_20d_pct"))
        ret = r1 if r1 is not None else _safe_float(rec.get("return_pct"))
        if conf is not None and ret is not None:
            hit = ret > 0
            observations.append((conf, ret, hit))

    # Source 2: Paper trades
    pt_records = _load_paper_trades(data_root)
    for rec in pt_records:
        c1 = _safe_float(rec.get("confidence_pct"))
        conf = c1 if c1 is not None else _safe_float(rec.get("model_confidence_pct"))
        ret = _safe_float(rec.get("return_pct"))
        if conf is not None and ret is not None:
            hit = ret > 0
            observations.append((conf, ret, hit))

    # Source 3: EOD snapshots (model_confidence_pct + composite_buy score as proxy)
    eod_records = _load_eod_snapshots(data_root)
    paired = _pair_eod_outcomes(eod_records)
    for conf, ret in paired:
        observations.append((conf, ret, ret > 0))

    if len(observations) < 10:
        return CalibrationReport(
            note=f"Insufficient data for calibration ({len(observations)} observations, need 10+). "
                 "Run the model for more days or add paper trades to build history.",
        )

    # Bucket observations
    buckets: list[CalibrationBucket] = []
    for i in range(len(bucket_edges) - 1):
        lo, hi = bucket_edges[i], bucket_edges[i + 1]
        label = f"{lo}-{hi}%"
        in_bucket = [(c, r, h) for c, r, h in observations if lo <= c < hi]
        if not in_bucket:
            continue
        pred_avg = sum(c for c, _, _ in in_bucket) / len(in_bucket)
        win_rate = sum(1 for _, _, h in in_bucket if h) / len(in_bucket) * 100
        avg_ret = sum(r for _, r, _ in in_bucket) / len(in_bucket)
        buckets.append(CalibrationBucket(
            bucket_label=label,
            predicted_avg=round(pred_avg, 1),
            actual_win_rate=round(win_rate, 1),
            count=len(in_bucket),
            avg_return_pct=round(avg_ret, 2),
        ))

    if not buckets:
        return CalibrationReport(note="No observations fell into calibration buckets.")

    # Calibration metrics
    cal_errors = [abs(b.predicted_avg - b.actual_win_rate) for b in buckets]
    mean_cal_error = sum(cal_errors) / len(cal_errors)

    # Monotonicity: higher confidence -> higher win rate
    win_rates = [b.actual_win_rate for b in buckets]
    monotonic = all(win_rates[i] <= win_rates[i + 1] for i in range(len(win_rates) - 1))
    well_calibrated = mean_cal_error < 15 and monotonic

    note_parts = []
    if well_calibrated:
        note_parts.append("Model is well-calibrated: higher confidence correlates with higher win rates.")
    else:
        if not monotonic:
            note_parts.append("Monotonicity violated: some lower-confidence buckets outperform higher ones.")
        if mean_cal_error >= 15:
            note_parts.append(f"Mean calibration error is {mean_cal_error:.1f}pp (target < 15pp).")

    return CalibrationReport(
        buckets=buckets,
        total_observations=len(observations),
        is_well_calibrated=well_calibrated,
        calibration_error=round(mean_cal_error, 1),
        monotonic=monotonic,
        note=" ".join(note_parts),
    )


def _pair_eod_outcomes(records: list[dict]) -> list[tuple[float, float]]:
    """
    Pair EOD confidence with forward returns (20d later).

    Groups by ticker, sorts by date, pairs record[i].confidence with
    record[i+20].close to compute a forward return.
    """
    from collections import defaultdict

    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        t = rec.get("ticker")
        if not t:
            continue
        by_ticker[t].append(rec)

    pairs: list[tuple[float, float]] = []
    for _ticker, recs in by_ticker.items():
        recs.sort(key=lambda r: str(r.get("date", "")))
        for i in range(len(recs) - 20):
            conf = _safe_float(
                recs[i].get("model_confidence_pct")
                or recs[i].get("confidence_pct")
            )
            close_now = _safe_float(recs[i].get("close") or recs[i].get("current_price"))
            close_fwd = _safe_float(recs[i + 20].get("close") or recs[i + 20].get("current_price"))
            if conf is not None and close_now and close_fwd and close_now > 0:
                ret = (close_fwd / close_now - 1.0) * 100
                pairs.append((conf, ret))
    return pairs


def _safe_float(v: Any) -> float | None:
    if v is None or v == "" or v == "None":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def calibration_report_to_dict(report: CalibrationReport) -> dict:
    """Serialize a CalibrationReport for JSON API response."""
    return {
        "buckets": [
            {
                "label": b.bucket_label,
                "predicted_avg": b.predicted_avg,
                "actual_win_rate": b.actual_win_rate,
                "count": b.count,
                "avg_return_pct": b.avg_return_pct,
            }
            for b in report.buckets
        ],
        "total_observations": report.total_observations,
        "is_well_calibrated": report.is_well_calibrated,
        "calibration_error": report.calibration_error,
        "monotonic": report.monotonic,
        "note": report.note,
    }
