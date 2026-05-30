"""
Build unified evaluation panel (ticker × date) with regime, composite, suggestions, fwd returns, baselines.

  cd backend && python scripts/run_evaluation_harness.py --tickers SPY,QQQ --out data/evaluation/panel.jsonl

Uses evaluation.* and watchlist from config when --tickers omitted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

from signals.evaluation_harness import (
    build_evaluation_panel,
    equal_weight_portfolio_forward,
    summarize_vs_baselines,
    write_jsonl,
)
from signals.gate_backtest import format_gate_backtest_report, summarize_gate_backtest


def _load_config() -> dict:
    path = ROOT / "config" / "config.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def main() -> None:
    ap = argparse.ArgumentParser(description="Unified evaluation harness panel")
    ap.add_argument("--tickers", type=str, default="", help="Comma-separated (default: config watchlist)")
    ap.add_argument("--period", type=str, default="5y")
    ap.add_argument("--step", type=int, default=0, help="Bar step (0 = default from config evaluation.default_step)")
    ap.add_argument("--out", type=str, default="data/evaluation/panel.jsonl")
    ap.add_argument("--summary-horizon", type=int, default=63)
    ap.add_argument("--buy-min", type=float, default=70.0)
    args = ap.parse_args()

    cfg = _load_config()
    ev = cfg.get("evaluation") or {}
    step = args.step or int(ev.get("default_step") or 5)
    if args.tickers.strip():
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = [str(t).upper() for t in (cfg.get("watchlist") or []) if t]

    if not tickers:
        print("No tickers: pass --tickers or set watchlist in config.yaml", file=sys.stderr)
        sys.exit(1)

    rows = build_evaluation_panel(
        tickers,
        config=cfg,
        period=args.period,
        step=step,
        horizons=tuple(ev.get("horizons_trading_days") or (21, 63, 126, 252)),
        spy_ticker=str(ev.get("spy_ticker") or "SPY"),
    )
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    write_jsonl(rows, out_path)
    summ = summarize_vs_baselines(rows, horizon=args.summary_horizon, buy_min=args.buy_min)
    gate_summ = summarize_gate_backtest(
        rows,
        horizons=tuple(ev.get("horizons_trading_days") or (21, 63, 126)),
        buy_min=args.buy_min,
    )
    out_obj: dict = {"n_rows": len(rows), "out": str(out_path), "summary": summ, "gate_backtest": gate_summ}
    if len(tickers) >= 2:
        by_sym: dict = {}
        for r in rows:
            by_sym.setdefault(r["ticker"], []).append(r)
        ew = equal_weight_portfolio_forward(by_sym, args.summary_horizon)
        if ew:
            m = sum(x["ew_fwd_pct"] for x in ew) / len(ew)
            out_obj["equal_weight_portfolio"] = {
                "horizon_trading_days": args.summary_horizon,
                "mean_ew_fwd_pct": round(m, 4),
                "n_dates": len(ew),
            }
    print(json.dumps(out_obj, indent=2))
    if rows and rows[0].get("gates_passed") is not None:
        print()
        print(format_gate_backtest_report(gate_summ))


if __name__ == "__main__":
    main()
