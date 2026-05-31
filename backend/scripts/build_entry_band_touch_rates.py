"""
Build entry-band touch table (regime × spot vs band × ATR distance → touch % within N sessions).
Uses historical EOD OHLCV — same philosophy as build_target_hit_rates.py (not paper trades).

Run from backend:  cd backend && python scripts/build_entry_band_touch_rates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from signals.entry_band_touch import (
    run_entry_band_touch_backtest,
    load_entry_touch_table,
    save_entry_touch_table,
    _merge_bucket_stats,
)


def main() -> None:
    tickers = ["SPY", "QQQ"]
    merged: dict = {}
    windows = None

    print("Building entry-band touch table (EOD OHLCV backtest)...")
    for ticker in tickers:
        print(f"  {ticker}...", end=" ", flush=True)
        out = run_entry_band_touch_backtest(ticker, period="5y")
        if out.get("error"):
            out = run_entry_band_touch_backtest(ticker, period="2y")
        if out.get("error"):
            print(out["error"])
            continue
        if windows is None:
            windows = out.get("windows")
        _merge_bucket_stats(merged, out.get("buckets") or {})
        print("ok")

    table = {"buckets": merged, "windows": windows or {"short": 20, "medium": 63}}
    path = ROOT / "data" / "entry_band_touch_rates.json"
    save_entry_touch_table(table, path)
    print(f"Saved to {path} ({len(merged)} bucket keys)")
    if not merged:
        print("Warning: no buckets — check network/yfinance.")


if __name__ == "__main__":
    main()
