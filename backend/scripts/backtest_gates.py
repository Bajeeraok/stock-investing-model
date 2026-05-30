"""
Backtest primary trading gates vs forward returns (historical validation).

Compares:
  - All bars
  - Composite >= buy_min (legacy)
  - Gates >= N/4
  - Full gate clearance (4/4)
  - Composite + gates cleared

Sources:
  walkforward — rebuild panel via evaluation_harness (causal; FV/ML proxies unless configured)
  eod         — use saved EOD snapshots from run_daily.py (closest to live dashboard gates)

Run:
  cd backend && python scripts/backtest_gates.py --source walkforward --tickers SPY,AAPL
  cd backend && python scripts/backtest_gates.py --source eod
  cd backend && python scripts/backtest_gates.py --source walkforward --predict-ml --out data/evaluation/gate_panel.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

from signals.evaluation_harness import build_evaluation_panel, write_jsonl
from signals.gate_backtest import (
    enrich_eod_row_with_gates_from_snapshot,
    format_gate_backtest_report,
    summarize_gate_backtest,
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


def _forward_return_from_eod(ticker: str, from_date: str, trading_days: int) -> float | None:
    import pandas as pd
    from signals.fetcher import fetch_ohlcv_safe

    close = fetch_ohlcv_safe(ticker, "5y")
    if close is None or len(close) < trading_days + 5:
        return None
    close = close.sort_index()
    try:
        from_ts = pd.Timestamp(from_date)
        loc = int(close.index.get_indexer([from_ts], method="nearest")[0])
        if loc < 0 or loc + trading_days >= len(close):
            return None
        p0 = float(close.iloc[loc])
        p1 = float(close.iloc[loc + trading_days])
        if p0 <= 0:
            return None
        return round(100.0 * (p1 - p0) / p0, 4)
    except Exception:
        return None


def rows_from_eod(
    *,
    dates: list[str],
    horizons: tuple[int, ...],
    tickers_filter: set[str] | None,
) -> list[dict]:
    from scripts.run_daily import load_eod_snapshot

    rows: list[dict] = []
    for date_str in dates:
        snap = load_eod_snapshot(date_str)
        if not snap:
            continue
        for ticker, raw in snap.items():
            sym = (ticker or "").upper()
            if tickers_filter and sym not in tickers_filter:
                continue
            row = dict(raw)
            row["ticker"] = sym
            row["date"] = date_str
            row["composite_buy"] = row.get("composite_buy") or row.get("confluence_score")
            enrich_eod_row_with_gates_from_snapshot(row)
            for h in horizons:
                fwd = _forward_return_from_eod(sym, date_str, h)
                row[f"fwd_{h}d_pct"] = fwd
            if any(row.get(f"fwd_{h}d_pct") is not None for h in horizons):
                rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest trading gates vs forward returns")
    ap.add_argument("--source", choices=("walkforward", "eod"), default="walkforward")
    ap.add_argument("--tickers", type=str, default="", help="Comma-separated (default: watchlist)")
    ap.add_argument("--period", type=str, default="5y")
    ap.add_argument("--step", type=int, default=0)
    ap.add_argument("--eod-days", type=int, default=90, help="Max EOD snapshot days (eod source)")
    ap.add_argument("--horizons", type=str, default="", help="e.g. 21,63,126 (default from config)")
    ap.add_argument("--buy-min", type=float, default=0.0, help="0 = use config score.buy_min")
    ap.add_argument("--min-gates", type=int, default=4, help="Min primary gates passed for gates_ge_min cohort")
    ap.add_argument("--predict-ml", action="store_true", help="Run ML inference per bar (slow)")
    ap.add_argument("--out", type=str, default="", help="Optional JSONL output path")
    ap.add_argument("--json", action="store_true", help="Print full summary JSON")
    args = ap.parse_args()

    cfg = _load_config()
    ev = cfg.get("evaluation") or {}
    gb = ev.get("gate_backtest") or {}
    if args.predict_ml:
        gb = {**gb, "predict_ml": True}
        ev = {**ev, "gate_backtest": gb}
        cfg = {**cfg, "evaluation": ev}

    horizons_list = ev.get("horizons_trading_days") or [21, 63, 126]
    if args.horizons.strip():
        horizons_list = [int(x.strip()) for x in args.horizons.split(",") if x.strip()]
    horizons = tuple(int(h) for h in horizons_list)

    score_cfg = cfg.get("score") or {}
    buy_min = args.buy_min or float(score_cfg.get("buy_min", 70))
    sell_max = float(score_cfg.get("sell_max", 35))

    if args.tickers.strip():
        tickers = {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
        tickers_list = sorted(tickers)
    else:
        tickers_list = [str(t).upper() for t in (cfg.get("watchlist") or []) if t]
        tickers = set(tickers_list)

    if not tickers_list:
        print("No tickers: pass --tickers or set watchlist in config.yaml", file=sys.stderr)
        sys.exit(1)

    if args.source == "eod":
        dates = _list_eod_dates(args.eod_days)
        if len(dates) < 3:
            print("Need EOD snapshots. Run: cd backend && python scripts/run_daily.py", file=sys.stderr)
            sys.exit(1)
        rows = rows_from_eod(dates=dates, horizons=horizons, tickers_filter=tickers)
        print(f"EOD source: {len(dates)} snapshot days, {len(rows)} (date,ticker) rows with forward data")
    else:
        step = args.step or int(ev.get("default_step") or 5)
        rows = build_evaluation_panel(
            tickers_list,
            config=cfg,
            period=args.period,
            step=step,
            horizons=horizons,
            spy_ticker=str(ev.get("spy_ticker") or "SPY"),
        )
        print(f"Walk-forward: {len(rows)} panel rows (step={step}, period={args.period})")

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        write_jsonl(rows, out_path)
        print(f"Wrote {out_path}")

    summary = summarize_gate_backtest(
        rows,
        horizons=horizons,
        buy_min=buy_min,
        min_gates_passed=max(1, min(4, args.min_gates)),
        sell_max=sell_max,
    )
    print(format_gate_backtest_report(summary))

    if args.json:
        print(json.dumps(summary, indent=2))

    out_json = ROOT / "data" / "evaluation" / "gate_backtest_summary.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary saved: {out_json}")


if __name__ == "__main__":
    main()
