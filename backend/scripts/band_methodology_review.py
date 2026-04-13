"""
Band methodology checklist: relate ATR multipliers and analyst anchoring to OOS width vs hit rate.

Use together with:
  - scripts/accuracy_price_targets.py (ST target / support err% vs spot)
  - evaluation harness fwd returns at 21/63/126/252d for signal quality

This script prints configured accuracy thresholds and suggests comparing band width percentiles
to realized hit rates from the accuracy report JSON if present.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml


def main() -> None:
    ap = argparse.ArgumentParser(description="Band methodology review (config + optional accuracy JSON)")
    ap.add_argument("--accuracy-json", type=str, default="", help="Optional output from accuracy_price_targets")
    args = ap.parse_args()
    cfg_path = ROOT / "config" / "config.yaml"
    if not cfg_path.exists():
        print("Missing config.yaml", file=sys.stderr)
        sys.exit(1)
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    acc = cfg.get("accuracy") or {}
    print("=== Band / accuracy thresholds (config) ===")
    print(json.dumps({k: acc[k] for k in acc if k != "notes"}, indent=2))
    if args.accuracy_json:
        p = Path(args.accuracy_json)
        if not p.is_absolute():
            p = ROOT / p
        if p.is_file():
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            print("\n=== Accuracy report summary (file) ===")
            if isinstance(data, dict):
                for k in ("by_ticker", "summary", "generated"):
                    if k in data:
                        print(k, ":", json.dumps(data[k], default=str)[:2000])
        else:
            print("Accuracy JSON not found:", p)
    print(
        "\nReview: in trends, fixed ATR multiples often imply tight ST targets (high err%); "
        "in chop, bands can be wide — compare st_target_atr_mult_overrides vs volatility regime."
    )


if __name__ == "__main__":
    main()
