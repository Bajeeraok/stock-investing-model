"""
Add or update thesis for a ticker. Edit data/theses.yaml directly for bulk updates.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from behavior.thesis import save_thesis, load_theses


def main() -> None:
    if len(sys.argv) < 4:
        print("Usage: python add_thesis.py TICKER 'thesis text' 'exit condition'")
        print("Example: python add_thesis.py AAPL 'iPhone ecosystem, services growth' 'trim if regime DOWN'")
        sys.exit(1)
    ticker = sys.argv[1].upper()
    thesis = sys.argv[2]
    exit_condition = sys.argv[3]
    save_thesis(ticker, thesis, exit_condition)
    print(f"Thesis saved for {ticker}. Run run_daily.py to see nudges.")


if __name__ == "__main__":
    main()
