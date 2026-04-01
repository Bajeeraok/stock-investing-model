"""
Ablation: buy-bucket (70–100) forward returns — baseline vs macro-gated.

Requires: FRED API key in config (data.fred_api_key) for yields/HY/UNRATE; Yahoo for VIX and prices.

Usage (from backend/):
  python scripts/backtest_ablation.py --ticker SPY --period 5y
  python scripts/backtest_ablation.py --ticker NVDA --period 10y --min-macro-score 45 --no-exclude-bear
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    import yaml

    from signals.backtest_ablation import run_macro_gate_ablation

    ap = argparse.ArgumentParser(description="Baseline vs macro-gated buy-bucket backtest")
    ap.add_argument("--ticker", default="SPY", help="Symbol to score (default SPY)")
    ap.add_argument("--period", default="5y", help="OHLCV period (default 5y)")
    ap.add_argument("--min-macro-score", type=float, default=40.0, help="Keep bar if macro_score >= this (default 40)")
    ap.add_argument(
        "--no-exclude-bear",
        action="store_true",
        help="Do not drop bars when macro_regime == BEAR (only min-macro-score applies)",
    )
    ap.add_argument("--json", action="store_true", help="Print machine-readable JSON only")
    args = ap.parse_args()

    config_path = ROOT / "config" / "config.yaml"
    config = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    out = run_macro_gate_ablation(
        args.ticker,
        args.period,
        config=config,
        min_macro_score=args.min_macro_score,
        exclude_macro_bear=not args.no_exclude_bear,
    )

    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return

    if out.get("error"):
        print("ERROR:", out.get("error"))
        if out.get("macro_error"):
            print("  FRED/macro:", out["macro_error"])
        if out.get("hint"):
            print(" ", out["hint"])
        sys.exit(1)

    print("ABLATION: buy bucket 70–100, forward 3m (net of default txn cost)")
    print(f"  {out['ticker']}  period={out['period']}  gate={out['gate']}")
    b, g = out["baseline"], out["gated"]
    d = out["delta"]
    print("\n  Baseline (all buy-bucket days):")
    print(f"    n={b['n']}  avg_ret={b['stats_3m'].get('avg_return_pct')}%  hit_rate={b['stats_3m'].get('hit_rate')}%")
    bm = b.get("buy_bucket_metrics") or {}
    if bm and not bm.get("error"):
        print(f"    Sharpe {bm.get('sharpe')}  maxDD {bm.get('max_drawdown_pct')}%")

    print("\n  Macro-gated (passes min_macro_score + bear filter unless --no-exclude-bear):")
    print(f"    n={g['n']}  avg_ret={g['stats_3m'].get('avg_return_pct')}%  hit_rate={g['stats_3m'].get('hit_rate')}%")
    gm = g.get("buy_bucket_metrics") or {}
    if gm and not gm.get("error"):
        print(f"    Sharpe {gm.get('sharpe')}  maxDD {gm.get('max_drawdown_pct')}%")

    print("\n  Delta (gated - baseline):")
    print(f"    avg_return_pp: {d.get('avg_return_pct_diff')}  hit_rate_pp: {d.get('hit_rate_pp_diff')}  rows_removed: {d.get('n_lost')}")
    print(f"\n  {out.get('note', '')}")


if __name__ == "__main__":
    main()
