"""
Print model fair value vs Yahoo 12m mean and FMP consensus (same payload as investor_summary.fair_value_vs_external).

Usage (from repo root):
  cd backend && python scripts/verify_fair_value_external.py META
  cd backend && python scripts/verify_fair_value_external.py AAPL MSFT
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from config_loader import load_config
    from api.ticker_detail import get_ticker_detail

    tickers = [t.upper() for t in sys.argv[1:] if t.strip() and not t.startswith("-")]
    if not tickers:
        print("Usage: python scripts/verify_fair_value_external.py TICKER [TICKER ...]")
        return 1

    config = load_config()
    for t in tickers:
        detail = get_ticker_detail(t, config)
        inv = detail.get("investor_summary") or {}
        fv = inv.get("fair_value")
        ext = inv.get("fair_value_vs_external")
        print(f"=== {t} ===")
        print(f"  Model fair value: ${fv}" if fv is not None else "  Model fair value: (n/a)")
        if ext:
            print("  " + json.dumps(ext, indent=2).replace("\n", "\n  "))
        else:
            print("  fair_value_vs_external: (n/a — investor_summary missing or old backend)")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
