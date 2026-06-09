"""
Write macro-gate ablation results to data/reports/ for scheduled runs or CI.

Usage (from backend/):
  python scripts/run_ablation_report.py
  python scripts/run_ablation_report.py --tickers SPY,QQQ,NVDA --period 5y

Cron (weekly):
  0 6 * * 1  cd /path/to/backend && python scripts/run_ablation_report.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    import yaml

    from config_loader import get_data_root
    from signals.backtest_ablation import run_macro_gate_ablation

    ap = argparse.ArgumentParser(description="Save ablation JSON to data/reports/")
    ap.add_argument(
        "--tickers",
        default="",
        help="Comma-separated symbols (default: first 5 from config watchlist or SPY)",
    )
    ap.add_argument("--period", default="5y", help="OHLCV period")
    ap.add_argument("--min-macro-score", type=float, default=40.0)
    ap.add_argument("--no-exclude-bear", action="store_true")
    args = ap.parse_args()

    config_path = ROOT / "config" / "config.yaml"
    config: dict = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    if args.tickers.strip():
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        wl = config.get("watchlist") or []
        tickers = [str(t).upper() for t in wl[:5]] if wl else ["SPY"]

    data_root = get_data_root()
    reports_dir = Path(data_root) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    from signals.time_et import format_et_compact, now_iso_et

    stamp = format_et_compact()
    out_rows: list[dict] = []
    for t in tickers:
        out = run_macro_gate_ablation(
            t,
            args.period,
            config=config,
            min_macro_score=args.min_macro_score,
            exclude_macro_bear=not args.no_exclude_bear,
        )
        out_rows.append({"ticker": t, "result": out})

    payload = {
        "generated_at": now_iso_et(),
        "period": args.period,
        "min_macro_score": args.min_macro_score,
        "exclude_macro_bear": not args.no_exclude_bear,
        "tickers": tickers,
        "runs": out_rows,
    }

    out_path = reports_dir / f"ablation_{stamp}.json"
    latest = reports_dir / "ablation_latest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"Wrote {out_path}")
    print(f"Updated {latest}")


if __name__ == "__main__":
    main()
