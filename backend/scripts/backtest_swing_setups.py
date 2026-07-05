"""
Backtest swing classifier setups on historical EOD snapshots.

Recomputes swing_* fields when missing (legacy snapshots) and simulates mechanical
T1/T2/stop/time-stop exits on daily OHLCV.

Run:
  cd backend && python scripts/backtest_swing_setups.py
  cd backend && python scripts/backtest_swing_setups.py --days 180 --tickers AAPL,NVDA
  cd backend && python scripts/backtest_swing_setups.py --use-eod-fields --out data/evaluation/swing_backtest.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

from signals.swing_backtest import (
    backtest_swing_row,
    format_swing_backtest_report,
    summarize_swing_backtest,
)


def _load_config() -> dict:
    path = ROOT / "config" / "config.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _list_eod_dates(limit: int | None = None) -> list[str]:
    eod_dir = ROOT / "data" / "eod"
    if not eod_dir.exists():
        return []
    dates = []
    for p in eod_dir.glob("*.json"):
        try:
            d = datetime.strptime(p.stem, "%Y-%m-%d").date()
            dates.append(d.strftime("%Y-%m-%d"))
        except ValueError:
            pass
    dates = sorted(dates)
    if limit and len(dates) > limit:
        dates = dates[-limit:]
    return dates


def _load_snapshot(date_str: str) -> dict | None:
    from scripts.run_daily import load_eod_snapshot

    by_ticker = load_eod_snapshot(date_str)
    if not by_ticker:
        return None
    return {"run_results": list(by_ticker.values())}


def run_backtest(
    *,
    dates: list[str],
    tickers_filter: set[str] | None,
    config: dict,
    recompute_swing: bool,
    max_signals: int | None,
) -> list[dict]:
    from signals.fetcher import fetch_ohlcv_dataframe

    ohlcv_cache: dict[str, object] = {}
    results: list[dict] = []

    for date_str in dates:
        snap = _load_snapshot(date_str)
        if not snap:
            continue
        for row in snap.get("run_results") or []:
            if not isinstance(row, dict) or row.get("error"):
                continue
            t = str(row.get("ticker") or "").upper().strip()
            if not t:
                continue
            if tickers_filter and t not in tickers_filter:
                continue

            if t not in ohlcv_cache:
                try:
                    ohlcv_cache[t] = fetch_ohlcv_dataframe(t, "5y")
                except Exception:
                    ohlcv_cache[t] = None

            out = backtest_swing_row(
                row,
                signal_date=date_str,
                ohlcv=ohlcv_cache.get(t),
                config=config,
                recompute_swing=recompute_swing,
            )
            if out:
                results.append(out)
                if max_signals and len(results) >= max_signals:
                    return results
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest swing classifier on EOD history")
    parser.add_argument("--days", type=int, default=120, help="Last N EOD snapshot dates")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated filter")
    parser.add_argument(
        "--use-eod-fields",
        action="store_true",
        help="Use persisted swing_* from EOD (skip recompute)",
    )
    parser.add_argument("--max-signals", type=int, default=0, help="Cap signals (0=unlimited)")
    parser.add_argument("--out", type=str, default="", help="Write JSON summary path")
    args = parser.parse_args()

    config = _load_config()
    dates = _list_eod_dates(limit=args.days if args.days > 0 else None)
    if not dates:
        print("No EOD snapshots found under data/eod/. Run run_daily.py first.")
        return 1

    tickers_filter = None
    if args.tickers.strip():
        tickers_filter = {x.strip().upper() for x in args.tickers.split(",") if x.strip()}

    rows = run_backtest(
        dates=dates,
        tickers_filter=tickers_filter,
        config=config,
        recompute_swing=not args.use_eod_fields,
        max_signals=args.max_signals if args.max_signals > 0 else None,
    )
    summary = summarize_swing_backtest(rows)
    summary["dates_scanned"] = len(dates)
    summary["date_from"] = dates[0] if dates else None
    summary["date_to"] = dates[-1] if dates else None
    summary["recompute_swing"] = not args.use_eod_fields

    print(format_swing_backtest_report(summary))

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"summary": summary, "trades": rows[:500]}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\nWrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
