"""
Diagnose BUY ml_signal win % vs headline actionable win %.

Run on Railway/UAT data root (signal_audit.db) or locally:
  cd backend && python scripts/analyze_buy_win_gap.py
  cd backend && python scripts/analyze_buy_win_gap.py --data-root /data
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config_loader import get_audit_cohort_tag, load_config
from signals.signal_audit_store import SignalAuditStore, analyze_buy_win_gap


def main() -> None:
    parser = argparse.ArgumentParser(description="BUY win-rate gap analysis")
    parser.add_argument("--data-root", type=Path, default=None, help="DATA_ROOT override")
    parser.add_argument("--json", action="store_true", help="Print raw JSON")
    args = parser.parse_args()

    config = load_config()
    tag = get_audit_cohort_tag(config)
    store = SignalAuditStore(data_root=args.data_root)
    with store._connect() as conn:
        report = analyze_buy_win_gap(conn, tag)

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print("=== BUY win-rate gap analysis ===")
    print(report.get("methodology_note", ""))
    print()
    for key in (
        "buy_all",
        "buy_full_go",
        "buy_go_4_gates",
        "buy_starter_only",
        "buy_hard_lock",
        "hold_no_go_reference",
    ):
        block = report.get(key) or {}
        if not block.get("n"):
            continue
        print(
            f"{key}: n={block['n']} win%={block.get('actionable_win_rate_pct')}% "
            f"(W={block.get('wins')} L={block.get('losses')} N={block.get('neutral')}) "
            f"avg_score={block.get('avg_score')}"
        )
    print()
    if report.get("buy_loss_verdict_rules"):
        print("Top BUY LOSS verdict rules:")
        for r in report["buy_loss_verdict_rules"]:
            print(f"  {r['n']:4d}  {r['rule']}")
    print()
    if report.get("buy_loss_top_gate_failures"):
        print("Failed gates on BUY losses:")
        for g in report["buy_loss_top_gate_failures"]:
            print(f"  {g['n']:4d}  {g['gate']}")
    print()
    if report.get("recommendations"):
        print("Recommendations:")
        for note in report["recommendations"]:
            print(f"  • {note}")


if __name__ == "__main__":
    main()
