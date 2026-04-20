#!/usr/bin/env python3
"""
Backtest regime calls vs forward returns (Issue 4 — historical regime hit rates).

For each EOD snapshot, reads the global market regime, then looks up the close
price `horizon` snapshot-steps later. Groups observations by:
  - regime label (BULL / NEUTRAL / BEAR / STRONG_BULL / STRONG_BEAR)
  - HMM confidence bucket (low / medium / high from bull_probability)
  - horizon (5, 20, 60 snapshot steps ≈ trading days)

Computes hit_rate_pct (positive return), avg_return_pct, and n per bucket.
Output: backend/data/regime_hit_rates.json

Usage:
    cd backend && python scripts/backtest_regime.py
    cd backend && python scripts/backtest_regime.py --horizons 5 20 60 --tickers SPY QQQ
    cd backend && python scripts/backtest_regime.py --eod-dir /path/to/eod
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Ensure backend/ is on the path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_EOD_DIR  = Path(__file__).resolve().parent.parent / "data" / "eod"
_DEFAULT_OUT_FILE = Path(__file__).resolve().parent.parent / "data" / "regime_hit_rates.json"
_DEFAULT_TICKERS  = ["SPY", "QQQ"]
_DEFAULT_HORIZONS = [5, 20, 60]


# ---------------------------------------------------------------------------
# Snapshot helpers (mirror regime_persistence / forward_tracking to avoid circular import)
# ---------------------------------------------------------------------------

def _list_eod_dates(eod_dir: Path) -> list[str]:
    seen: set[str] = set()
    dates: list[str] = []
    try:
        from signals.cache import list_eod_dates_redis
        for d in list_eod_dates_redis():
            if d not in seen and len(d) == 10 and d[4] == "-":
                seen.add(d); dates.append(d)
    except Exception:
        pass
    if eod_dir.exists():
        for p in eod_dir.glob("*.json"):
            d = p.stem
            if d not in seen and len(d) == 10 and d[4] == "-":
                seen.add(d); dates.append(d)
    return sorted(seen)


def _load_snapshot(eod_dir: Path, date_str: str) -> dict | None:
    try:
        from signals.cache import get_eod_snapshot_redis
        data = get_eod_snapshot_redis(date_str)
        if data and isinstance(data, dict) and data.get("run_results"):
            return data
    except Exception:
        pass
    p = eod_dir / f"{date_str}.json"
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _regime_from_snapshot(snap: dict) -> str | None:
    for key in ("global_market_regime", "market_regime"):
        r = snap.get(key)
        if r and isinstance(r, str) and r.strip():
            return r.upper().strip()
    for row in snap.get("run_results") or []:
        if isinstance(row, dict) and not row.get("error"):
            reg = row.get("_global_market_regime")
            if reg and isinstance(reg, str):
                return reg.upper().strip()
    return None


def _hmm_bull_prob(snap: dict, ticker: str = "SPY") -> float | None:
    tk = ticker.upper()
    for row in snap.get("run_results") or []:
        if not isinstance(row, dict) or str(row.get("ticker") or "").upper() != tk:
            continue
        # Try nested confidence.hmm.bull_probability
        conf = row.get("confidence") or {}
        if isinstance(conf, dict):
            hmm = conf.get("hmm") or {}
            if isinstance(hmm, dict):
                try:
                    bp = hmm.get("bull_probability")
                    if bp is not None:
                        return float(bp)
                except (TypeError, ValueError):
                    pass
        # Try direct fields
        for field in ("hmm_bull_prob", "bull_probability"):
            bp = row.get(field)
            if bp is not None:
                try:
                    return float(bp)
                except (TypeError, ValueError):
                    pass
    return None


def _ticker_close(snap: dict, ticker: str) -> float | None:
    tk = ticker.upper()
    for row in snap.get("run_results") or []:
        if isinstance(row, dict) and str(row.get("ticker") or "").upper() == tk:
            c = row.get("close")
            if c is not None:
                try:
                    return float(c)
                except (TypeError, ValueError):
                    pass
    return None


def _confidence_bucket(bull_prob: float | None) -> str:
    if bull_prob is None:
        return "medium"
    if bull_prob >= 0.75:
        return "high"
    if bull_prob <= 0.35:
        return "low"
    return "medium"


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _stats(rets: list[float]) -> dict[str, Any]:
    if not rets:
        return {}
    n = len(rets)
    avg = round(sum(rets) / n, 3)
    hit = round(100.0 * sum(1 for r in rets if r > 0) / n, 1)
    return {"hit_rate_pct": hit, "avg_return_pct": avg, "n": n}


def build_regime_hit_rates(
    horizons: list[int] = _DEFAULT_HORIZONS,
    tickers: list[str] = _DEFAULT_TICKERS,
    eod_dir: Path = _DEFAULT_EOD_DIR,
    out_file: Path = _DEFAULT_OUT_FILE,
) -> dict[str, Any]:
    """
    Build regime hit-rate table from all available EOD snapshots.

    Each observation = (as_of regime, confidence bucket, horizon) → forward return.
    Saves to out_file as JSON and returns the same dict.
    """
    dates = _list_eod_dates(eod_dir)
    logger.info("Found %d EOD snapshots in %s", len(dates), eod_dir)
    if len(dates) < max(horizons, default=1) + 5:
        logger.warning(
            "Only %d snapshots — need at least %d for horizon %dd. "
            "Run run_daily.py regularly and retry.",
            len(dates), max(horizons) + 5, max(horizons),
        )

    # observations[regime][bucket][horizon] → list of avg returns across tickers
    observations: dict[str, dict[str, dict[int, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    for i, as_of_date in enumerate(dates):
        snap = _load_snapshot(eod_dir, as_of_date)
        if not snap:
            continue

        regime = _regime_from_snapshot(snap)
        if not regime:
            continue

        # Use the first listed ticker's HMM bull prob for the confidence bucket
        bull_prob = _hmm_bull_prob(snap, tickers[0]) if tickers else None
        bucket = _confidence_bucket(bull_prob)

        for horizon in horizons:
            j = i + horizon
            if j >= len(dates):
                continue
            snap_next = _load_snapshot(eod_dir, dates[j])
            if not snap_next:
                continue

            rets: list[float] = []
            for ticker in tickers:
                p0 = _ticker_close(snap, ticker)
                p1 = _ticker_close(snap_next, ticker)
                if p0 and p1 and p0 > 0:
                    rets.append(100.0 * (p1 - p0) / p0)

            if not rets:
                continue

            avg_ret = sum(rets) / len(rets)
            observations[regime][bucket][horizon].append(avg_ret)

    # Build output structure
    _BUCKETS = ("low", "medium", "high")
    out: dict[str, Any] = {}

    for regime in sorted(observations):
        entry: dict[str, Any] = {}

        # Overall stats (all buckets pooled)
        for h in horizons:
            all_rets: list[float] = []
            for bkt in _BUCKETS:
                all_rets.extend(observations[regime][bkt][h])
            if all_rets:
                entry[f"{h}d"] = _stats(all_rets)

        # Confidence-stratified stats
        by_conf: dict[str, dict] = {}
        for bkt in _BUCKETS:
            bkt_data: dict[str, Any] = {}
            for h in horizons:
                rets = observations[regime][bkt][h]
                if rets:
                    bkt_data[f"{h}d"] = _stats(rets)
            if bkt_data:
                by_conf[bkt] = bkt_data
        if by_conf:
            entry["by_confidence"] = by_conf

        out[regime] = entry

    total_obs = sum(
        len(observations[r]["medium"][horizons[0]])
        + len(observations[r]["low"][horizons[0]])
        + len(observations[r]["high"][horizons[0]])
        for r in observations
        if horizons
    )
    out["_meta"] = {
        "tickers":          tickers,
        "horizons":         horizons,
        "snapshots_found":  len(dates),
        "total_observations": total_obs,
        "note": (
            "Horizons are EOD snapshot steps, not calendar days. "
            "Refresh monthly: cd backend && python scripts/backtest_regime.py"
        ),
    }

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(out, f, indent=2)
    logger.info("Wrote %s", out_file)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build regime_hit_rates.json from EOD snapshots."
    )
    parser.add_argument("--horizons", nargs="+", type=int, default=_DEFAULT_HORIZONS,
                        help="Forward-return horizons in snapshot steps (default: 5 20 60)")
    parser.add_argument("--tickers", nargs="+", default=_DEFAULT_TICKERS,
                        help="Tickers used for forward return (default: SPY QQQ)")
    parser.add_argument("--eod-dir", type=Path, default=_DEFAULT_EOD_DIR,
                        help="Path to EOD snapshot directory")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT_FILE,
                        help="Output JSON file path")
    args = parser.parse_args()

    result = build_regime_hit_rates(
        horizons=args.horizons,
        tickers=args.tickers,
        eod_dir=args.eod_dir,
        out_file=args.out,
    )

    regimes = [k for k in result if not k.startswith("_")]
    logger.info("Regimes found: %s", regimes)
    for r in sorted(regimes):
        for h in args.horizons:
            s = result[r].get(f"{h}d")
            if s:
                logger.info(
                    "  %-14s %3dd  hit=%5.1f%%  avg=%+6.2f%%  n=%d",
                    r, h, s["hit_rate_pct"], s["avg_return_pct"], s["n"],
                )


if __name__ == "__main__":
    main()
