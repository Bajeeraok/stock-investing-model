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
from signals.score_interpretation import effective_buy_min


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


def _build_close_index(eod_dir: Path) -> dict[str, dict[str, float]]:
    """ticker -> {date -> close} across all local EOD snapshots."""
    out: dict[str, dict[str, float]] = {}
    for p in sorted(eod_dir.glob("*.json")):
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in snap.get("run_results") or []:
            if not isinstance(row, dict):
                continue
            t, c = row.get("ticker"), row.get("close")
            if not t or c is None:
                continue
            try:
                cf = float(c)
            except (TypeError, ValueError):
                continue
            if cf > 0:
                out.setdefault(t, {})[p.stem] = cf
    return out


def _forward_return_from_snapshots(
    closes: dict[str, float],
    sorted_dates: list[str],
    from_date: str,
    steps: int,
) -> float | None:
    """% change between close at from_date and close ~steps snapshot-dates later.

    Uses local EOD closes — no network. `steps` counts snapshot entries for the
    ticker (approx trading days when snapshots are daily).
    """
    if from_date not in closes:
        return None
    p0 = closes[from_date]
    if p0 <= 0:
        return None
    later = [d for d in sorted_dates if d > from_date and d in closes]
    if len(later) < max(3, steps - 3):
        return None
    use_date = later[min(steps - 1, len(later) - 1)]
    p1 = closes.get(use_date)
    if not p1 or p1 <= 0:
        return None
    return 100.0 * (p1 - p0) / p0


def main() -> None:
    import pandas as pd
    global pd

    dates = _list_eod_dates()
    if len(dates) < 5:
        print("Need EOD snapshots. Run: cd backend && python scripts/run_daily.py")
        print("Then re-run this script after a few days of data.")
        return

    config = load_config()
    score_cfg = config.get("score", {})
    sell_max = score_cfg.get("sell_max", 30)
    global_buy_min = score_cfg.get("buy_min", 70)

    # Pre-index all closes from local snapshots — no per-pair network fetches
    close_idx = _build_close_index(ROOT / "data" / "eod")
    all_dates = sorted(close_idx and dates or dates)

    # Forward horizons: 1m=21, 3m=63, 6m=126 snapshot steps (~trading days)
    horizons = [(21, "1m"), (63, "3m"), (126, "6m")]
    buy_by_horizon: dict[int, list[float]] = {d: [] for d, _ in horizons}
    sell_by_horizon: dict[int, list[float]] = {d: [] for d, _ in horizons}
    hold_by_horizon: dict[int, list[float]] = {d: [] for d, _ in horizons}
    pred_vs_actual: list[dict] = []

    for date_str in dates[:-21] if len(dates) > 21 else dates:  # skip tail w/o outcome window
        snapshot = load_eod_snapshot(date_str)
        if not snapshot:
            continue
        run_rows = snapshot.get("run_results") if isinstance(snapshot.get("run_results"), list) else snapshot
        if isinstance(run_rows, list):
            rows_iter = ((r.get("ticker"), r) for r in run_rows if isinstance(r, dict))
        else:
            rows_iter = snapshot.items()
        for ticker, row in rows_iter:
            if not isinstance(row, dict):
                continue
            score = row.get("composite_buy")
            if score is None:
                continue
            # Use stored per-ticker threshold when present; else config overrides/global
            bm = row.get("buy_min")
            if bm is None:
                bm = effective_buy_min(ticker, score_cfg)
            pred = "BUY" if score >= bm else ("SELL" if score <= sell_max else "HOLD")
            entry = {"date": date_str, "ticker": ticker, "score": score, "pred": pred}
            for days, label in horizons:
                fwd = _forward_return_from_snapshots(
                    close_idx.get(ticker, {}), all_dates, date_str, days
                )
                if fwd is None:
                    continue
                entry[f"fwd_{label}"] = fwd
                if pred == "BUY":
                    buy_by_horizon[days].append(fwd)
                elif pred == "SELL":
                    sell_by_horizon[days].append(fwd)
                else:
                    hold_by_horizon[days].append(fwd)
            if any(k.startswith("fwd_") for k in entry):
                pred_vs_actual.append(entry)

    if not pred_vs_actual:
        print("No (date, ticker) pairs with forward data. Need more EOD history.")
        return

    # Summary
    print("=" * 60)
    print("SIGNAL BACKTEST (predictions vs actual forward returns)")
    print("=" * 60)
    ovr = score_cfg.get("buy_min_by_ticker") or {}
    print(f"Thresholds: global BUY >= {global_buy_min}, SELL <= {sell_max}")
    if ovr:
        print(f"  Per-ticker buy_min overrides: {ovr}")
    print(f"Data: {len(pred_vs_actual)} (date, ticker) pairs from EOD snapshots")
    print()

    def _stats(arr: list[float], label: str) -> None:
        if not arr:
            print(f"  {label}: no data")
            return
        avg = sum(arr) / len(arr)
        hit = sum(1 for r in arr if r > 0) / len(arr) * 100
        print(f"  {label}: n={len(arr)}  avg_return={avg:.2f}%  hit_rate={hit:.1f}%")

    for days, label in horizons:
        print(f"Forward {label} return by prediction:")
        _stats(buy_by_horizon[days], "BUY")
        _stats(hold_by_horizon[days], "HOLD")
        _stats(sell_by_horizon[days], "SELL")
        print()

    # Precision / Recall (for 1m horizon)
    buy_ret_1m = buy_by_horizon[21]
    sell_ret_1m = sell_by_horizon[21]
    all_pos = sum(1 for e in pred_vs_actual if (e.get("fwd_1m") or 0) > 0)
    all_neg = sum(1 for e in pred_vs_actual if (e.get("fwd_1m") or 0) < 0)
    tp = sum(1 for e in pred_vs_actual if e.get("pred") == "BUY" and (e.get("fwd_1m") or 0) > 0)
    tn = sum(1 for e in pred_vs_actual if e.get("pred") == "SELL" and (e.get("fwd_1m") or 0) < 0)
    n_buy = len(buy_ret_1m)
    n_sell = len(sell_ret_1m)
    precision_buy = 100 * tp / n_buy if n_buy else None
    recall_buy = 100 * tp / all_pos if all_pos else None
    precision_sell = 100 * tn / n_sell if n_sell else None
    recall_sell = 100 * tn / all_neg if all_neg else None
    print("Precision / Recall (1m horizon):")
    if precision_buy is not None:
        print(f"  BUY:  precision={precision_buy:.1f}% (when we said BUY, % correct)  recall={recall_buy:.1f}% (of all ups, % we flagged)" if recall_buy is not None else f"  BUY:  precision={precision_buy:.1f}%")
    if precision_sell is not None:
        print(f"  SELL: precision={precision_sell:.1f}% (when we said SELL, % correct)  recall={recall_sell:.1f}%" if recall_sell is not None else f"  SELL: precision={precision_sell:.1f}%")
    print()

    # Directional accuracy
    total = n_buy + n_sell
    if total > 0:
        directional_accuracy = 100 * (tp + tn) / total
        print(f"Directional accuracy (BUY->up, SELL->down): {directional_accuracy:.1f}%")
    print()

    # Suggested tuning
    if buy_ret_1m and (sum(buy_ret_1m) / len(buy_ret_1m)) < 0:
        print("Suggestion: BUY signals underperforming. Consider raising buy_min (e.g. 72–75).")
    if sell_ret_1m and (sum(sell_ret_1m) / len(sell_ret_1m)) > 0:
        print("Suggestion: SELL signals may be early. Consider lowering sell_max (e.g. 25–28).")
    print()
    print("For regime validation: python scripts/regime_backtest.py")
    print("For score buckets: python scripts/backtest_simple.py")


if __name__ == "__main__":
    main()
