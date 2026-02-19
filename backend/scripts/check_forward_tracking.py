"""
Run forward tracking on EOD snapshots and print results.
Use to verify "what we said vs what happened" with 2+ EOD files.

  python backend/scripts/check_forward_tracking.py

  With --horizon 1: only 1-day forward (useful when you have exactly 2 snapshots).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from signals.forward_tracking import get_forward_tracking


def main() -> None:
    parser = argparse.ArgumentParser(description="Check forward tracking on EOD snapshots")
    parser.add_argument("--data-root", type=Path, default=ROOT / "data", help="Data root (eod/ under it)")
    parser.add_argument("--horizon", type=int, action="append", dest="horizons", help="Horizon(s) in trading days (default: 5,20,60; use --horizon 1 for 2 snapshots)")
    parser.add_argument("--tickers", nargs="+", default=["SPY", "QQQ"], help="Tickers to track")
    parser.add_argument("--json", action="store_true", help="Output full JSON")
    args = parser.parse_args()

    horizons = args.horizons if args.horizons else [5, 20, 60]
    out = get_forward_tracking(
        data_root=args.data_root,
        tickers=args.tickers,
        horizons=horizons,
    )

    if args.json:
        print(json.dumps(out, indent=2))
        return

    if out.get("message"):
        print("Message:", out["message"])
    print("Records:", len(out["records"]))
    if out["records"]:
        for r in out["records"][:20]:
            print(f"  {r['as_of_date']} -> {r['next_date']}  {r['ticker']}  horizon={r['horizon_days']}d  signal={r['our_signal']}  return={r['actual_return_pct']:+.2f}%")
        if len(out["records"]) > 20:
            print("  ...")
    print("Summary by horizon:", out.get("summary_by_horizon") or "{}")
    print("Summary by signal (20d):", out.get("summary_by_signal") or "{}")


if __name__ == "__main__":
    main()
