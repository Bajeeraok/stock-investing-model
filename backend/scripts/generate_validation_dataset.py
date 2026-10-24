"""
Generate ML calibration validation dataset from EOD snapshots.

For each (ticker, snapshot_date) row:
  - extract short-horizon ML probability from gate_detail_json ("ml" gate detail text)
  - compute forward returns using closes from LATER snapshots (no lookahead:
    outcome is only known days later — exactly what Platt fitting needs)
  - write CSV rows: horizon, prob, y

Only snapshots that contain gate_detail_json with an "ml" gate contribute.
Forward windows are trading-day counts between snapshot dates.

Usage:
    cd backend && python scripts/generate_validation_dataset.py
    cd backend && python scripts/generate_validation_dataset.py --forward-days 21 --horizon short
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


_ML_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)%\s*vs")


def _load_snapshots(eod_dir: Path) -> dict[str, dict]:
    """date_str -> snapshot dict (only files that parse)."""
    out: dict[str, dict] = {}
    for p in sorted(eod_dir.glob("*.json")):
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(snap, dict):
                out[p.stem] = snap
        except Exception:
            continue
    return out


def _extract_ml_prob_from_gate(row: dict, gate_id: str = "ml") -> float | None:
    """Parse ML probability from the gate detail string.

    Detail formats seen in prod:
      "Marginal pass (30% vs 25.0% threshold) — ..."
      "Validated setup (72% vs 25% threshold)"
      "Weak short ML (12% · need 30%+)"
    Returns the *probability* (left-hand number), in 0-100.
    """
    gd = row.get("gate_detail_json")
    if not gd:
        return None
    try:
        gates = json.loads(gd) if isinstance(gd, str) else gd
    except Exception:
        return None
    if not isinstance(gates, list):
        return None
    for g in gates:
        if not isinstance(g, dict) or g.get("id") != gate_id:
            continue
        detail = str(g.get("detail") or "")
        if "not scored" in detail.lower() or "unscored" in str(g.get("visual_status", "")).lower():
            return None
        m = _ML_PCT_RE.search(detail)
        if m:
            return float(m.group(1))
        # Fallback: first number followed by % in detail
        m2 = re.search(r"(\d+(?:\.\d+)?)%", detail)
        if m2:
            return float(m2.group(1))
    return None


def _closes_by_ticker(snapshots: dict[str, dict]) -> dict[str, dict[str, float]]:
    """ticker -> {date -> close} across all snapshots."""
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for date, snap in snapshots.items():
        for row in snap.get("run_results") or []:
            if not isinstance(row, dict):
                continue
            t = row.get("ticker")
            c = row.get("close")
            if t and c:
                try:
                    cf = float(c)
                    if cf > 0:
                        out[t][date] = cf
                except (TypeError, ValueError):
                    continue
    return out


def _forward_return(
    closes: dict[str, float],
    from_date: str,
    later_dates: list[str],
    forward_days: int,
) -> float | None:
    """Return % change between close at from_date and the close ~forward_days snapshot steps later.

    later_dates = sorted snapshot dates strictly AFTER from_date that contain this ticker.
    Picks the date closest to forward_days steps ahead (index forward_days-1 in the list
    if available; tolerates ±3 steps for sparse snapshots).
    """
    if from_date not in closes:
        return None
    p0 = closes[from_date]
    if p0 <= 0:
        return None
    if not later_dates:
        return None
    target_idx = forward_days - 1
    if len(later_dates) - 1 < target_idx - 3:
        return None  # not enough history
    use_idx = min(target_idx, len(later_dates) - 1)
    if abs(use_idx - target_idx) > 3:
        return None
    p1 = closes.get(later_dates[use_idx])
    if not p1 or p1 <= 0:
        return None
    return 100.0 * (p1 - p0) / p0


def main() -> None:
    ap = argparse.ArgumentParser(description="Build ML calibration dataset from EOD snapshots")
    ap.add_argument("--eod-dir", type=str, default="data/eod")
    ap.add_argument("--out", type=str, default="data/calibration/val_probs.csv")
    ap.add_argument("--forward-days", type=int, default=21,
                    help="Snapshot steps ahead for outcome (21 ≈ 1 trading month)")
    ap.add_argument("--horizon", type=str, default="short",
                    choices=["short", "medium", "long"])
    ap.add_argument("--min-samples", type=int, default=20)
    args = ap.parse_args()

    eod_dir = Path(args.eod_dir)
    if not eod_dir.is_absolute():
        eod_dir = ROOT / eod_dir

    print(f"Loading snapshots from {eod_dir} ...")
    snapshots = _load_snapshots(eod_dir)
    print(f"  {len(snapshots)} snapshots parsed")
    if len(snapshots) < 30:
        print("Need at least ~30 snapshots for a useful dataset. Download prod EOD first.")
        return

    dates_sorted = sorted(snapshots.keys())
    closes = _closes_by_ticker(snapshots)
    print(f"  {len(closes)} tickers with closes")

    # Collect (prob, y) rows for the chosen horizon gate
    rows_out: list[tuple[str, float, int]] = []
    n_scored = n_outcome = 0

    for i, date in enumerate(dates_sorted):
        snap = snapshots[date]
        later = dates_sorted[i + 1:]
        for row in snap.get("run_results") or []:
            if not isinstance(row, dict):
                continue
            t = row.get("ticker")
            if not t:
                continue
            prob = _extract_ml_prob_from_gate(row)
            if prob is None:
                continue
            n_scored += 1
            # Outcome from this ticker's own close series (only dates after `date`)
            t_later = [d for d in later if d in closes.get(t, {})]
            fwd = _forward_return(closes[t], date, t_later, args.forward_days)
            if fwd is None:
                continue
            n_outcome += 1
            y = 1 if fwd > 0 else 0
            rows_out.append((args.horizon, prob / 100.0, y))  # store prob as 0-1

    print(f"  ML-scored (ticker,date) pairs: {n_scored}")
    print(f"  with usable {args.forward_days}-step outcome: {n_outcome}")

    if len(rows_out) < args.min_samples:
        print(f"Only {len(rows_out)} samples (need {args.min_samples}). Check snapshot coverage.")
        return

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["horizon", "prob", "y"])
        for h, p, y in rows_out:
            w.writerow([h, round(p, 4), y])

    wins = sum(y for _, _, y in rows_out)
    print(f"\nWrote {len(rows_out)} rows -> {out_path}")
    print(f"  base rate (y=1, fwd>{args.forward_days}d up): {wins}/{len(rows_out)} = {wins/len(rows_out):.1%}")
    print("\nNext:")
    print(f"  python scripts/fit_probability_calibration.py --csv {args.out} --out data/calibration/ml_horizons.json")


if __name__ == "__main__":
    main()
