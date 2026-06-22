#!/usr/bin/env python3
"""
Scan signal universe for tickers missing from ASSET_REGISTRY and infer equity profiles.

Usage:
  cd backend
  python scripts/scan_asset_registry.py              # report only
  python scripts/scan_asset_registry.py --write      # persist to data/asset_registry_inferred.json
  python scripts/scan_asset_registry.py --universe dashboard
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from config_loader import get_dashboard_signal_universe, get_eod_signal_universe, load_config
from signals.pre_flight.asset_classifier import ASSET_REGISTRY
from signals.pre_flight.asset_registry_cache import cache_path, save_inferred_batch
from signals.pre_flight.asset_registry_infer import infer_asset_meta_from_ticker


def scan_universe(tickers: list[str], config: dict, write: bool) -> int:
    unknown = [t for t in tickers if t.upper() not in ASSET_REGISTRY]
    unknown.sort()

    print(f"Signal universe: {len(tickers)} tickers")
    print(f"Curated registry: {len(ASSET_REGISTRY)} tickers")
    print(f"Missing from registry: {len(unknown)}")
    print()

    inferred: dict = {}
    failed: list[str] = []

    for sym in unknown:
        meta = infer_asset_meta_from_ticker(sym, config)
        if meta is None:
            failed.append(sym)
            print(f"  FAIL  {sym:<8}  (no profile — will default to standard equity)")
            continue
        inferred[sym] = meta
        print(
            f"  OK    {sym:<8}  {meta.asset_type.value:<20}  "
            f"{meta.sector:<28}  beta={meta.beta if meta.beta is not None else '—'}"
        )

    print()
    print(f"Inferred: {len(inferred)}  Failed: {len(failed)}")

    if write and inferred:
        save_inferred_batch(inferred)
        print(f"Wrote {len(inferred)} entries → {cache_path()}")
    elif inferred and not write:
        print("Dry run — pass --write to persist data/asset_registry_inferred.json")

    return len(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan signal universe and infer asset profiles")
    parser.add_argument(
        "--universe",
        choices=("eod", "dashboard"),
        default="eod",
        help="eod = dashboard + audit cohort (default); dashboard = portfolio/watchlist/demo only",
    )
    parser.add_argument("--write", action="store_true", help="Save inferred profiles to JSON cache")
    args = parser.parse_args()

    config = load_config()
    if args.universe == "dashboard":
        tickers = get_dashboard_signal_universe(config)
    else:
        tickers = get_eod_signal_universe(config)

    failed = scan_universe(tickers, config, write=args.write)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
