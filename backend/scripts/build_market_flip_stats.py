"""
Build market_flip_stats.json — gap fade, CPI/NFP/FOMC tables, pre-market vs close.

Run monthly from backend:
  cd backend && python scripts/build_market_flip_stats.py

Requires network (yfinance) for SPY/ES history.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from signals.market_flip_stats import build_market_flip_stats, save_market_flip_stats


def main() -> None:
    print("Building market flip stats (gap fade, event-day tables)...")
    payload = build_market_flip_stats(period="13y")
    path = save_market_flip_stats(payload)
    print(f"Saved to {path}")
    for et, stats in (payload.get("events") or {}).items():
        gf = stats.get("pct_gap_fade")
        n = stats.get("n_events")
        print(f"  {et}: n={n}, gap_fade={gf}%, next-day avg={stats.get('avg_return_pct')}%")
    pm = payload.get("premarket_vs_close")
    if pm:
        print(f"  premarket vs close: contradict {pm.get('pct_contradict')}% (n={pm.get('n_days')})")
    else:
        print("  premarket vs close: insufficient archived history (run pre-market scheduler + EOD daily)")


if __name__ == "__main__":
    main()
