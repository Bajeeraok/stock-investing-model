"""
Alerts background worker (Option B).

Run locally:
  cd backend
  python scripts/run_alerts_worker.py

On Railway:
  create a Worker service with start command:
    python -m alerts.worker
or:
    python backend/scripts/run_alerts_worker.py   (depending on your layout)
"""

from __future__ import annotations

from pathlib import Path

from alerts.worker import run_worker


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parent.parent
    run_worker(data_root=ROOT / "data")

