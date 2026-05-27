#!/usr/bin/env python3
"""
Build signal audit report JSON + CSV export (Phase 3).

  cd backend && python scripts/build_audit_report.py
  cd backend && python scripts/build_audit_report.py --days 30
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build audit_summary.json + CSV export")
    parser.add_argument("--days", type=int, default=None, help="Limit to signals in last N days")
    parser.add_argument("--no-write", action="store_true", help="Build in memory only")
    args = parser.parse_args()

    from config_loader import load_config
    from signals.signal_audit_report import build_audit_report

    config = load_config()
    report = build_audit_report(
        config,
        days=args.days,
        write_files=not args.no_write,
    )
    summary = report.get("outcome_summary") or {}
    print(f"[build_audit_report] cohort={report.get('cohort_tag')}")
    if report.get("paths"):
        for k, v in report["paths"].items():
            print(f"  {k}: {v}")
    if summary.get("win_rate_pct") is not None:
        print(
            f"  win_rate={summary['win_rate_pct']}% "
            f"resolved={summary.get('resolved_n')}/{summary.get('events_total')}"
        )
    else:
        print(f"  events={summary.get('events_total')} pending_outcomes={summary.get('pending_n')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
