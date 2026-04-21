"""
Python scheduler to run EOD snapshot daily at a fixed time (e.g. 8pm ET).
Run as a long-lived process: cd backend && python scripts/scheduler_eod.py

Configure in config.yaml:
  eod_schedule_time: "20:00"   # 8pm (default)
  eod_schedule_tz: "America/New_York"
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore


def main() -> None:
    from config_loader import load_config
    from scripts.run_daily import run_eod_snapshot_only

    config = load_config()
    # e.g. "20:00" for 8pm
    schedule_time = config.get("eod_schedule_time", "20:00")
    tz_name = config.get("eod_schedule_tz", "America/New_York")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/New_York")
    target_hour, target_min = 20, 0
    if ":" in schedule_time:
        parts = schedule_time.strip().split(":")
        target_hour = int(parts[0])
        target_min = int(parts[1]) if len(parts) > 1 else 0

    last_run_date = None

    def job() -> None:
        nonlocal last_run_date
        from datetime import datetime
        now = datetime.now(tz)
        today = now.date()
        if last_run_date == today:
            return
        print(f"[scheduler_eod] Running EOD snapshot at {now.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}")
        result = run_eod_snapshot_only(config)
        if result.get("error"):
            print(f"[scheduler_eod] ERROR: {result['error']}")
            return
        last_run_date = today
        print(f"[scheduler_eod] Saved {result.get('snapshot_path', '')} (tickers={result.get('tickers_count', 0)}, pruned={result.get('pruned', 0)})")

    print(f"[scheduler_eod] EOD snapshot will run daily at {schedule_time} {tz_name}")
    print("[scheduler_eod] Press Ctrl+C to stop.")

    while True:
        from datetime import datetime
        now = datetime.now(tz)
        if now.hour == target_hour and now.minute == target_min:
            job()
        time.sleep(60)
