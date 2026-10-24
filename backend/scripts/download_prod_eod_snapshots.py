"""
Download EOD snapshots from production API into local data/eod/.

Pulls the snapshot index from /api/eod/snapshots then downloads each
snapshot JSON from /api/eod/snapshots/{date} into data/eod/{date}.json
so local backtest/calibration tooling can use prod history.

Usage:
    cd backend && python scripts/download_prod_eod_snapshots.py
    cd backend && python scripts/download_prod_eod_snapshots.py --base https://thrive-alpha.up.railway.app --max 30
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import urllib.request
import urllib.error


def _fetch_json(url: str, timeout: int = 60) -> dict | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {url}")
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Download EOD snapshots from production")
    ap.add_argument("--base", type=str, default="https://thrive-alpha.up.railway.app",
                    help="Base URL of production API")
    ap.add_argument("--out-dir", type=str, default="data/eod",
                    help="Output directory relative to backend/")
    ap.add_argument("--max", type=int, default=0, help="Max snapshots to download (0 = all)")
    ap.add_argument("--skip-existing", action="store_true", default=True,
                    help="Skip files that already exist locally")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching snapshot index from {base}/api/eod/snapshots ...")
    index = _fetch_json(f"{base}/api/eod/snapshots")
    if not index:
        print("Failed to fetch snapshot index")
        return

    snapshots = index.get("snapshots") or []
    if not snapshots:
        print("No snapshots listed")
        return

    dates = [s.get("date") for s in snapshots if isinstance(s, dict) and s.get("date")]
    # Sort descending (latest first); index likely already sorted, but be safe
    dates = sorted(dates, reverse=True)
    if args.max > 0:
        dates = dates[: args.max]

    print(f"Index reports {len(snapshots)} snapshots; downloading {len(dates)}")

    downloaded = skipped = failed = 0
    for i, date_str in enumerate(dates, 1):
        out_path = out_dir / f"{date_str}.json"
        if out_path.exists() and args.skip_existing:
            skipped += 1
            continue

        snap = _fetch_json(f"{base}/api/eod/snapshots/{date_str}", timeout=120)
        if snap is None:
            failed += 1
            print(f"  [{i}/{len(dates)}] {date_str}: FAILED")
            continue

        # Strip _meta added by the endpoint (not part of snapshot file)
        snap.pop("_meta", None)
        out_path.write_text(json.dumps(snap), encoding="utf-8")
        downloaded += 1
        print(f"  [{i}/{len(dates)}] {date_str}: saved ({len(json.dumps(snap)) // 1024} KB)")

        # Be polite to prod
        time.sleep(0.4)

    print(f"\nDone. downloaded={downloaded} skipped={skipped} failed={failed}")
    print(f"Snapshots in: {out_dir}")


if __name__ == "__main__":
    main()
