"""
Build target hit-rate table (regime x ATR distance -> hit_rate_pct) for ST/MT confidence.
Run monthly or after changing target_bands logic. Writes backend/data/target_hit_rates.json.

Run from backend:  cd backend && python scripts/build_target_hit_rates.py
Requires: yfinance (pip install yfinance), network access for Yahoo Finance.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure we can import and fetch (fail fast with clear message)
try:
    from signals.fetcher import fetch_ohlcv_safe
except ImportError as e:
    print("Import error:", e)
    print("Run from backend directory: cd backend && python scripts/build_target_hit_rates.py")
    sys.exit(1)

from signals.target_confidence import (
    run_target_confidence_backtest,
    load_hit_rates_table,
    save_hit_rates_table,
)


def merge_buckets(acc: dict, new: dict) -> None:
    """Merge new bucket stats into acc: same key -> average hit_rate weighted by n."""
    for key, val in new.items():
        if key not in acc:
            acc[key] = {"hit_rate_pct": val["hit_rate_pct"], "n": val["n"]}
        else:
            n1, n2 = acc[key]["n"], val["n"]
            if n1 + n2 == 0:
                continue
            r1, r2 = acc[key]["hit_rate_pct"], val["hit_rate_pct"]
            acc[key] = {
                "hit_rate_pct": round((r1 * n1 + r2 * n2) / (n1 + n2), 1),
                "n": n1 + n2,
            }


def main() -> None:
    tickers = ["SPY", "QQQ"]
    merged_st = {}
    merged_mt = {}

    print("Building target hit-rate table (regime x ATR distance)...")
    # Quick sanity check: can we fetch SPY at all?
    try:
        test = fetch_ohlcv_safe("SPY", "1y")
        if test is None or len(test) < 252:
            print("Warning: fetch_ohlcv_safe(SPY, 1y) returned", "None" if test is None else f"{len(test)} bars. Check network and yfinance.")
    except Exception as e:
        print("Warning: fetch test failed:", e)

    for ticker in tickers:
        print(f"  {ticker}...", end=" ", flush=True)
        out = run_target_confidence_backtest(ticker, period="5y")
        if out.get("error"):
            # Fallback: try shorter period in case 5y failed (e.g. rate limit or partial data)
            out = run_target_confidence_backtest(ticker, period="2y")
        if out.get("error"):
            print(out["error"])
            continue
        merge_buckets(merged_st, out.get("st_buckets") or {})
        merge_buckets(merged_mt, out.get("mt_buckets") or {})
        print("ok")

    table = {"st": merged_st, "mt": merged_mt}
    path = ROOT / "data" / "target_hit_rates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    save_hit_rates_table(table, path)
    print(f"Saved to {path}")
    if not merged_st and not merged_mt:
        print("Warning: no hit-rate data was produced. Ensure yfinance can fetch SPY/QQQ (e.g. pip install yfinance, then retry with network).")
    else:
        print("Run this script monthly to refresh confidence lookups.")


if __name__ == "__main__":
    main()
