"""
Run lightweight backtest validation (SPY) and write data/model_health.json for the dashboard strip.
Schedule weekly:  cd backend && python scripts/update_model_health.py

Uses scripts.backtest_simple.run_backtest and walk_forward_backtest (same calibration / walk-forward
logic as backtest_simple.py main).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config_loader import get_data_root, load_config  # noqa: E402

from scripts.backtest_simple import (  # noqa: E402
    DEFAULT_TRANSACTION_COST,
    run_backtest,
    walk_forward_backtest,
)


def main() -> None:
    config = load_config()
    data_root = get_data_root()
    tickers = config.get("backtest_tickers", ["SPY"])
    period = config.get("data", {}).get("period", "10y") or "10y"
    txn_cost = config.get("backtest_transaction_cost", DEFAULT_TRANSACTION_COST)
    cal_min = float((config.get("backtest") or {}).get("calibration_ok_min", config.get("score", {}).get("buy_min", 70)))

    ticker = tickers[0] if tickers else "SPY"
    out_bt = run_backtest(ticker, period, transaction_cost=txn_cost)
    if out_bt.get("error"):
        print(f"Backtest error: {out_bt['error']}")
        sys.exit(1)
    cal = (out_bt or {}).get("calibration") or {}
    cal_score = cal.get("calibration_score")
    cal_ok = cal_score is not None and float(cal_score) >= cal_min and bool(cal.get("monotonic"))

    wf = walk_forward_backtest(ticker, period, transaction_cost=txn_cost)
    wf_cons = (wf or {}).get("consistency") or {}
    c3 = wf_cons.get(3) or {}
    wf_ok = bool(c3.get("consistent")) if c3 else None
    if wf.get("error"):
        wf_ok = None

    wf_rb = (wf or {}).get("regime_breakdown") or {}

    payload = {
        "backtest_last_run": datetime.now(timezone.utc).isoformat(),
        "backtest_ticker": ticker,
        "calibration_score": float(cal_score) if cal_score is not None else None,
        "calibration_ok": cal_ok,
        "walk_forward_ok": wf_ok,
        "walk_forward_note": None,
        "walk_forward_regime_breakdown": wf_rb,
    }
    if c3 and not c3.get("consistent"):
        payload["walk_forward_note"] = (
            f"3m win-rate std {c3.get('std_hit_rate_pct', 0):.1f}pp — review regime sensitivity"
        )

    data_root.mkdir(parents=True, exist_ok=True)
    path = data_root / "model_health.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {path}")
    print(f"  calibration_score={payload['calibration_score']} ok={payload['calibration_ok']}")
    print(f"  walk_forward_ok={payload['walk_forward_ok']}")


if __name__ == "__main__":
    main()
