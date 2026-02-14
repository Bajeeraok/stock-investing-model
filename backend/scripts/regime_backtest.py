"""
Regime backtest: validate that UP/DOWN/NEUTRAL predicts forward returns.
Expectation: UP regime -> positive avg forward return; DOWN -> negative.
Use to tune up_min / down_max in config.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config_loader import load_config
from signals.fetcher import fetch_ohlcv_safe
from signals.indicators import composite_score
from signals.regime import get_regime


def run_regime_backtest(
    ticker: str = "SPY",
    period: str = "10y",
    up_min: float = 60,
    down_max: float = 40,
    forward_days: list[int] | None = None,
) -> dict:
    """
    For each date with enough history, compute regime, then forward return.
    Returns avg return and hit rate by regime for each horizon.
    """
    if forward_days is None:
        forward_days = [21, 63, 126]  # 1m, 3m, 6m

    close = fetch_ohlcv_safe(ticker, period)
    if close is None or len(close) < 250:
        return {"error": f"Insufficient data for {ticker}"}

    close = close.sort_index()
    max_fwd = max(forward_days)

    regime_returns: dict[str, dict[int, list[float]]] = {"UP": {}, "DOWN": {}, "NEUTRAL": {}}
    for r in regime_returns:
        regime_returns[r] = {d: [] for d in forward_days}

    for i in range(200, len(close) - max_fwd - 1):
        subset = close.iloc[: i + 1]
        if len(subset) < 50:
            continue
        sig = composite_score(subset)
        score = sig.get("composite_buy")
        if score is None:
            continue
        regime = get_regime(score, up_min=up_min, down_max=down_max)
        price_today = float(close.iloc[i])

        for days in forward_days:
            j = min(i + days, len(close) - 1)
            price_fwd = float(close.iloc[j])
            ret_pct = 100 * (price_fwd - price_today) / price_today
            regime_returns[regime][days].append(ret_pct)

    def _stats(vals: list[float]) -> dict:
        if not vals:
            return {"avg_pct": None, "hit_rate": None, "count": 0}
        return {
            "avg_pct": round(sum(vals) / len(vals), 2),
            "hit_rate": round(100 * sum(1 for v in vals if v > 0) / len(vals), 1),
            "count": len(vals),
        }

    results = {}
    for regime in ["UP", "NEUTRAL", "DOWN"]:
        results[regime] = {}
        for d in forward_days:
            results[regime][d] = _stats(regime_returns[regime][d])

    return {
        "ticker": ticker,
        "period": period,
        "up_min": up_min,
        "down_max": down_max,
        "by_regime": results,
        "forward_days": {21: "1m", 63: "3m", 126: "6m"},
    }


def main() -> None:
    config = load_config()
    regime_cfg = config.get("regime", {})
    up_min = regime_cfg.get("up_min", 60)
    down_max = regime_cfg.get("down_max", 40)
    tickers = config.get("backtest_tickers", ["SPY", "QQQ"])[:3]
    period = config.get("data", {}).get("period", "10y") or "10y"

    print("REGIME BACKTEST: UP/DOWN/NEUTRAL vs forward returns")
    print("=" * 60)
    print(f"Thresholds: UP >= {up_min}, DOWN <= {down_max}")
    print()

    for ticker in tickers:
        out = run_regime_backtest(ticker, period, up_min, down_max)
        if out.get("error"):
            print(f"{ticker}: {out['error']}")
            continue
        print(f"{ticker}:")
        for regime in ["UP", "NEUTRAL", "DOWN"]:
            row = out["by_regime"][regime]
            parts = []
            for d, label in [(21, "1m"), (63, "3m"), (126, "6m")]:
                s = row.get(d, {})
                ap = s.get("avg_pct")
                hr = s.get("hit_rate")
                n = s.get("count", 0)
                if ap is not None:
                    parts.append(f"{label}: {ap:+.1f}% (hit {hr:.0f}%, n={n})")
            print(f"  {regime:8}  " + "  ".join(parts))
        # Sanity: UP should outperform DOWN
        up_3m = out["by_regime"]["UP"].get(63, {}).get("avg_pct")
        down_3m = out["by_regime"]["DOWN"].get(63, {}).get("avg_pct")
        if up_3m is not None and down_3m is not None:
            if up_3m > down_3m:
                print(f"  -> OK: UP ({up_3m:+.1f}%) > DOWN ({down_3m:+.1f}%) at 3m")
            else:
                print(f"  -> Review: UP ({up_3m:+.1f}%) <= DOWN ({down_3m:+.1f}%) at 3m - consider tuning thresholds")
        print()

    print("Run with backtest_tickers in config. Tune up_min/down_max if UP underperforms DOWN.")


if __name__ == "__main__":
    main()
