"""
Walk-forward + purged CV on evaluation harness rows: tune buy_min on train, score on test.

  cd backend && python scripts/run_evaluation_harness.py --tickers SPY --out data/evaluation/spy.jsonl
  cd backend && python scripts/walk_forward_purged_cv.py --panel data/evaluation/spy.jsonl

Requires a panel JSONL from run_evaluation_harness.py (one object per line).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.evaluation_harness import summarize_vs_baselines
from signals.walk_forward_cv import purged_walk_forward_folds, tune_buy_min


def _load_rows(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Purged walk-forward CV on harness panel")
    ap.add_argument("--panel", type=str, required=True, help="JSONL from run_evaluation_harness.py")
    ap.add_argument("--train-bars", type=int, default=200)
    ap.add_argument("--test-bars", type=int, default=40)
    ap.add_argument("--purge-bars", type=int, default=252, help="Gap between train and test (max horizon)")
    ap.add_argument("--step-bars", type=int, default=40)
    ap.add_argument("--horizon", type=int, default=63)
    args = ap.parse_args()

    path = Path(args.panel)
    if not path.is_absolute():
        path = ROOT / path
    rows = _load_rows(path)
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_ticker[str(r.get("ticker", ""))].append(r)

    report: dict = {"folds": []}
    for sym, trows in sorted(by_ticker.items()):
        trows.sort(key=lambda x: str(x.get("date", "")))
        dates = [str(r["date"]) for r in trows if r.get("date")]
        folds = list(
            purged_walk_forward_folds(
                dates,
                train_bars=args.train_bars,
                test_bars=args.test_bars,
                purge_bars=args.purge_bars,
                step_bars=args.step_bars,
            )
        )
        fold_idx = 0
        for train_d, test_d in folds:
            train_rows = [r for r in trows if r.get("date") in set(train_d)]
            test_rows = [r for r in trows if r.get("date") in set(test_d)]
            if len(train_rows) < 10 or len(test_rows) < 5:
                continue
            best_bm, tr = tune_buy_min(train_rows, horizon_key=f"fwd_{args.horizon}d_pct")
            te = summarize_vs_baselines(test_rows, horizon=args.horizon, buy_min=best_bm)
            report["folds"].append(
                {
                    "ticker": sym,
                    "fold": fold_idx,
                    "train_buy_min": best_bm,
                    "train_tune_stats": tr,
                    "test_summary": te,
                }
            )
            fold_idx += 1

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
