"""
Populate Redis dashboard cache by calling GET /api/dashboard (same work as a user load).

Usage (cron / Railway scheduled job):
  cd backend && set WARM_DASHBOARD_URL=https://your-api/api/dashboard && python scripts/warm_dashboard_cache.py

Local:
  WARM_DASHBOARD_URL=http://127.0.0.1:8002/api/dashboard python scripts/warm_dashboard_cache.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    url = (os.environ.get("WARM_DASHBOARD_URL") or "http://127.0.0.1:8002/api/dashboard").strip()
    try:
        import requests
    except ImportError:
        print("requests required", file=sys.stderr)
        return 1
    print(f"Warming dashboard cache: {url[:100]}...")
    try:
        r = requests.get(url, timeout=900)
        print(f"HTTP {r.status_code} ({len(r.content)} bytes)")
        return 0 if r.ok else 1
    except Exception as e:
        print(f"Failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
