#!/usr/bin/env python3
"""
One-shot EOD snapshot — for cron, Windows Task Scheduler, or CI.

  cd backend && python scripts/run_eod_snapshot.py

Runs the same logic as POST /api/eod/run (run_eod_snapshot_only): signals + save
data/eod/YYYY-MM-DD.json (+ Redis when configured). Exits 1 on failure.

Schedule after US market close + data settle (config suggests 8pm ET in config.yaml).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from config_loader import load_config
    from scripts.run_daily import run_eod_snapshot_only

    config = load_config()
    result = run_eod_snapshot_only(config)
    if result.get("error"):
        print(f"[run_eod_snapshot] ERROR: {result['error']}", file=sys.stderr)
        return 1
    print(
        f"[run_eod_snapshot] OK date={result.get('snapshot_date')} "
        f"path={result.get('snapshot_path')} tickers={result.get('tickers_count')} pruned={result.get('pruned', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
