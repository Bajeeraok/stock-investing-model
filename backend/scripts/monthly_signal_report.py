"""
Write monthly signal-bucket report JSON from EOD snapshots.

  cd backend && python scripts/monthly_signal_report.py

Output: data/reports/monthly_signal_buckets.json (or override with --out)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config_loader import get_data_root
from signals.monthly_signal_report import save_monthly_report_json


def main() -> None:
    p = argparse.ArgumentParser(description="Build monthly signal → forward return report from EOD snapshots")
    p.add_argument("--out", type=Path, default=None, help="Output JSON path")
    args = p.parse_args()
    root = get_data_root()
    path, report = save_monthly_report_json(data_root=root, path=args.out)
    print(path)
    if report.get("message"):
        print(report["message"], file=sys.stderr)


if __name__ == "__main__":
    main()
