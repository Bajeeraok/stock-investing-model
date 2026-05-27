#!/usr/bin/env python3
"""
Resolve signal audit outcomes (Phase 2) from EOD snapshot history.

  cd backend && python scripts/resolve_signal_outcomes.py

Same logic as POST /api/audit/resolve and auto-resolve on Analysis bundle load.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from config_loader import load_config
    from signals.signal_audit_outcomes import resolve_signal_audit_outcomes

    config = load_config()
    result = resolve_signal_audit_outcomes(config)
    if result.get("message"):
        print(result["message"])
    print(
        f"[resolve_signal_outcomes] updated={result.get('updated')} "
        f"pending={result.get('pending_insufficient_history')} "
        f"resolved_total={((result.get('summary') or {}).get('resolved_n'))}"
    )
    summary = result.get("summary") or {}
    if summary.get("win_rate_pct") is not None:
        print(f"  win_rate={summary['win_rate_pct']}% wins={summary.get('wins')} losses={summary.get('losses')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
