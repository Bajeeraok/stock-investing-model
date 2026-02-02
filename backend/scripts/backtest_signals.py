"""
Backtest daily signals vs actual EOD outcomes.
Compares model predictions (BUY/HOLD/SELL) against forward returns.
Use to tune thresholds and assess error margin.

Run: cd backend && python scripts/backtest_signals.py

Requires EOD snapshots from run_daily.py. If none exist, run run_daily first.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config_loader import load_config
from scripts.run_daily import load_eod_snapshot


def _list_eod_dates() -> list[str]:
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
    return sorted(dates)


def _forward_return(ticker: str, from_date: str, days: int) -> float | None:
    """Fetch price at from_date and from_date+days, return % change."""
    import pandas as pd
    from signals.fetcher import fetch_ohlcv_safe
    close = fetch_ohlcv_safe(ticker, "2y")
    if close is None or len(close) < 100:
        return None
    close = close.sort_index()
    try:
        from_ts = pd.Timestamp(from_date)
        to_ts = from_ts + pd.Timedelta(days=days + 30)
        subset = close[(close.index >= from_ts) & (close.index <= to_ts)]
        if len(subset) < 5:
            return None
        p0 = float(subset.iloc[0])
        p1 = float(subset.iloc[-1])
        if p0 <= 0:
            return None
        return 100 * (p1 - p0) / p0
    except Exception:
        return None


def main() -> None:
    import pandas as pd
    global pd

    dates = _list_eod_dates()
    if len(dates) < 5:
        print("Need EOD snapshots. Run: cd backend && python scripts/run_daily.py")
        print("Then re-run this script after a few days of data.")
        return

    config = load_config()
    buy_min = config.get("score", {}).get("buy_min", 70)
    sell_max = config.get("score", {}).get("sell_max", 30)

    # Collect: for each (date, ticker) with score, get forward 1m return
    buy_returns: list[float] = []
    sell_returns: list[float] = []
    hold_returns: list[float] = []
    pred_vs_actual: list[dict] = []

    for date_str in dates[-30:]:  # Last 30 snapshots
        snapshot = load_eod_snapshot(date_str)
        if not snapshot:
            continue
        for ticker, row in snapshot.items():
            score = row.get("composite_buy")
            if score is None:
                continue
            fwd = _forward_return(ticker, date_str, 21)  # ~1 month
            if fwd is None:
                continue
            pred = "BUY" if score >= buy_min else ("SELL" if score <= sell_max else "HOLD")
            pred_vs_actual.append({"date": date_str, "ticker": ticker, "score": score, "pred": pred, "fwd_1m": fwd})
            if pred == "BUY":
                buy_returns.append(fwd)
            elif pred == "SELL":
                sell_returns.append(fwd)
            else:
                hold_returns.append(fwd)

    if not pred_vs_actual:
        print("No (date, ticker) pairs with forward data. Need more EOD history.")
        return

    # Summary
    print("=" * 60)
    print("SIGNAL BACKTEST (predictions vs actual 1m forward return)")
    print("=" * 60)
    print(f"Thresholds: BUY >= {buy_min}, SELL <= {sell_max}")
    print(f"Data: {len(pred_vs_actual)} (date, ticker) pairs from EOD snapshots")
    print()

    def _stats(arr: list[float], label: str) -> None:
        if not arr:
            print(f"  {label}: no data")
            return
        avg = sum(arr) / len(arr)
        hit = sum(1 for r in arr if r > 0) / len(arr) * 100
        print(f"  {label}: n={len(arr)}  avg_return={avg:.2f}%  hit_rate={hit:.1f}%")

    print("Forward 1m return by prediction:")
    _stats(buy_returns, "BUY")
    _stats(hold_returns, "HOLD")
    _stats(sell_returns, "SELL")
    print()

    # Error margin: when we said BUY, expected positive; when SELL, expected negative
    buy_correct = sum(1 for r in buy_returns if r > 0) if buy_returns else 0
    sell_correct = sum(1 for r in sell_returns if r < 0) if sell_returns else 0
    total = len(buy_returns) + len(sell_returns)
    if total > 0:
        directional_accuracy = 100 * (buy_correct + sell_correct) / total
        print(f"Directional accuracy (BUY->up, SELL->down): {directional_accuracy:.1f}%")
    print()

    # Suggested tuning
    if buy_returns and (sum(buy_returns) / len(buy_returns)) < 0:
        print("Suggestion: BUY signals underperforming. Consider raising buy_min (e.g. 72–75).")
    if sell_returns and (sum(sell_returns) / len(sell_returns)) > 0:
        print("Suggestion: SELL signals may be early. Consider lowering sell_max (e.g. 25–28).")
    print()
    print("For fuller backtest, run: python scripts/backtest_simple.py")


if __name__ == "__main__":
    main()
