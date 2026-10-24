"""
Benchmark-relative signal audit — the SPY/QQQ question.

If a signal cohort can't beat simply owning SPY, a retail investor should own
SPY instead. This script measures each cohort's forward excess return
(ticker_fwd - spy_fwd over the same window) and beat-the-index rate, using only
local EOD snapshots — no network.

Cohorts measured: all rows, BUY label, score buckets, entry_mode cohorts,
dip_zone (30-50 score + actionable entry), full_go override path.

Usage:
    cd backend && python scripts/excess_vs_spy.py
    cd backend && python scripts/excess_vs_spy.py --forward-days 63 --benchmark QQQ
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.generate_validation_dataset import (
    _closes_by_ticker,
    _forward_return,
    _load_snapshots,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Excess-return cohort audit vs index")
    ap.add_argument("--eod-dir", type=str, default="data/eod")
    ap.add_argument("--benchmark", type=str, default="SPY")
    ap.add_argument("--forward-days", type=int, default=21)
    ap.add_argument("--min-n", type=int, default=30)
    args = ap.parse_args()

    eod_dir = Path(args.eod_dir)
    if not eod_dir.is_absolute():
        eod_dir = ROOT / eod_dir
    snaps = _load_snapshots(eod_dir)
    dates = sorted(snaps.keys())
    closes = _closes_by_ticker(snaps)
    bench = closes.get(args.benchmark.upper(), {})
    if not bench:
        print(f"No {args.benchmark} closes in snapshots.")
        return

    coh: dict[str, list[float]] = defaultdict(list)
    for i, d in enumerate(dates):
        later = [x for x in dates[i + 1:]]
        bench_f = _forward_return(bench, d, later, args.forward_days)
        if bench_f is None:
            continue
        for row in snaps[d].get("run_results") or []:
            t = row.get("ticker")
            if not t or t.upper() in ("SPY", "QQQ"):
                continue
            tc = closes.get(t, {})
            tl = [x for x in later if x in tc]
            f = _forward_return(tc, d, tl, args.forward_days)
            if f is None:
                continue
            exc = f - bench_f
            score = row.get("composite_buy")
            try:
                score = float(score) if score is not None else None
            except (TypeError, ValueError):
                score = None
            bm = row.get("buy_min") or 70
            em = row.get("entry_mode")

            coh["all"].append(exc)
            if score is not None and score >= bm:
                coh["buy_label"].append(exc)
            if score is not None:
                if score < 30:
                    coh["score_0_30"].append(exc)
                elif score < 50:
                    coh["score_30_50"].append(exc)
                elif score < 70:
                    coh["score_50_70"].append(exc)
                else:
                    coh["score_70_100"].append(exc)
            if em:
                coh[f"mode_{em}"].append(exc)
            if score is not None and 30 <= score < 50 and em in ("starter_only", "full_go"):
                coh["dip_zone"].append(exc)

    print(f"Benchmark: {args.benchmark} · forward window: {args.forward_days} steps")
    print(f"{'cohort':<18} {'n':>6} {'avg_excess':>11} {'beat_idx':>9}")
    print("-" * 48)
    for k in sorted(coh):
        v = coh[k]
        if len(v) < args.min_n:
            print(f"{k:<18} {len(v):>6}   (n < {args.min_n})")
            continue
        avg = sum(v) / len(v)
        hit = sum(1 for x in v if x > 0) / len(v) * 100
        flag = "  <-- alpha" if avg > 1.0 and hit >= 55 else ""
        print(f"{k:<18} {len(v):>6} {avg:>+10.2f}% {hit:>8.1f}%{flag}")
    print()
    print("Read: avg_excess > 0 with beat_idx > 55% = the cohort beats just owning the index.")


if __name__ == "__main__":
    main()
