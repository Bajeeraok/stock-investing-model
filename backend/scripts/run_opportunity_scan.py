"""
Standalone opportunity scan: identify tickers with long-term growth potential.
Run when you want to discover new opportunities without running the full daily report.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from opportunity.scanner import run_opportunity_scan


def main() -> None:
    config_path = ROOT / "config" / "config.yaml"
    config = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}

    opp_cfg = config.get("opportunity_criteria", {}) or {}
    universe = config.get("opportunity_universe") or []
    portfolio = config.get("portfolio", [])
    portfolio_tickers = [p["ticker"] for p in portfolio if isinstance(p, dict)] if portfolio else []

    opportunities = run_opportunity_scan(
        universe=universe if universe else None,
        period=config.get("data", {}).get("period", "5y"),
        min_score=opp_cfg.get("min_score", 70),
        require_regime_up=opp_cfg.get("require_regime_up", True),
        max_rsi=opp_cfg.get("max_rsi", 75),
        require_price_above_ma200=True,
        min_macd_hist=opp_cfg.get("min_macd_hist", 0),
        up_min=config.get("regime", {}).get("up_min", 60),
        down_max=config.get("regime", {}).get("down_max", 40),
        exclude_from_watchlist=portfolio_tickers,
        max_results=opp_cfg.get("max_results", 25),
        min_volume_ratio=opp_cfg.get("min_volume_ratio", 0.5),
        exclude_earnings_days=opp_cfg.get("exclude_earnings_days"),
        config=config,
    )

    print("DAILY OPPORTUNITIES (long-term growth potential)")
    print("=" * 60)
    print("Candidates to research - not buy recommendations.")
    print("-" * 70)
    if opportunities:
        for o in opportunities:
            print(f"  {o['ticker']:6}  close={o['close']:.2f}  score={o['composite_buy']:.1f}  RSI={o['rsi']:.1f}  {o['regime']:8}  {o['reason']}")
    else:
        print("  No tickers passed criteria. Try relaxing min_score or max_rsi in config.")


if __name__ == "__main__":
    main()
