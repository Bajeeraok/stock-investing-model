"""
Build data/universe/sp500_membership.csv (survivorship-aware S&P 500 membership ranges).

    cd backend && python scripts/build_universe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signals.alpha.universe import fetch_sp500_membership, fetch_sp500_membership_with_history, save_membership


def main() -> None:
    try:
        df = fetch_sp500_membership_with_history()
    except Exception as e:
        print(f"history source failed ({e}); falling back to current constituents only")
        df = fetch_sp500_membership()
    p = save_membership(df)
    print(f"{len(df)} ranges, {df['ticker'].nunique()} tickers, {int(df['end_date'].notna().sum())} removed -> {p}")


if __name__ == "__main__":
    main()
