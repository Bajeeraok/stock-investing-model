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

def main() -> None:
    from config_loader import load_config
    from scripts.run_daily import run_eod_snapshot_only

    config = load_config()
    # e.g. "20:00" for 8pm
    schedule_time = config.get("eod_schedule_time", "20:00")
    tz_name = config.get("eod_schedule_tz", "America/New_York")

    # Use pytz for timezone resolution — works on slim Docker images without
    # system tzdata. ZoneInfo requires system /usr/share/zoneinfo or Python
    # tzdata package; pytz bundles its own database.
    import pytz
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz_name = "America/New_York"
        tz = pytz.timezone(tz_name)
        print(f"[scheduler_eod] WARNING: unrecognised tz in config; falling back to {tz_name}")

    from datetime import datetime as _dt
    print(f"[scheduler_eod] Timezone resolved: {tz_name} (system UTC; local now = {_dt.now(tz).strftime('%Y-%m-%d %H:%M %Z')})")

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
        time.sleep(55)  # slightly under 60s to avoid drifting past the target minute
