"""
Paper vs forward-tracking baseline — drift smoke test.

Compares realized returns on completed paper trades to the unconditional
20-trading-day mean from `get_forward_tracking` (EOD snapshot population).
Not a rigorous A/B (different samples); useful to spot gross divergence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from signals.paper_trade_logger import PaperTradeLogger


def build_paper_vs_backtest_drift(
    forward_tracking: dict[str, Any] | None,
    data_root: Path | None = None,
) -> dict[str, Any] | None:
    """
    Returns a small dict for the dashboard API, or None if nothing to show.
    """
    if forward_tracking is None:
        return None

    root = data_root
    if root is None:
        from config_loader import get_data_root

        root = get_data_root()

    ft_20 = (forward_tracking.get("summary_by_horizon") or {}).get(20)
    forward_mean = None
    forward_n = None
    if isinstance(ft_20, dict):
        forward_mean = ft_20.get("avg_return_pct")
        forward_n = ft_20.get("n_observations")

    # Buy-side forward baseline (HOLD/ADD signal bucket at 20d)
    ft_buy = (forward_tracking.get("summary_by_signal") or {}).get("HOLD/ADD")
    forward_buy_mean = None
    forward_buy_n = None
    if isinstance(ft_buy, dict):
        forward_buy_mean = ft_buy.get("avg_return_20d_pct")
        forward_buy_n = ft_buy.get("n_observations")

    ptl = PaperTradeLogger(root)
    summ = ptl.get_performance_summary(min_completed=3, min_actionable=3)

    completed = int(summ.get("completed") or 0)
    if completed < 3:
        return {
            "status": "insufficient_paper",
            "paper_completed_n": completed,
            "forward_20d_baseline_pct": forward_mean,
            "forward_20d_n": forward_n,
            "forward_buy_baseline_pct": forward_buy_mean,
            "forward_buy_n": forward_buy_n,
            "message": "Need 3+ completed paper trades to compare drift (20d horizon outcomes).",
        }

    paper_avg = summ.get("avg_return_pct")
    drift = None
    if forward_mean is not None and paper_avg is not None:
        try:
            drift = round(float(paper_avg) - float(forward_mean), 2)
        except (TypeError, ValueError):
            pass

    # Buy-side drift: paper BUY/HOLD-ADD avg vs forward HOLD/ADD bucket
    buy_summ = summ.get("buy_signals_summary")
    buy_avg = buy_summ.get("avg_return_pct") if isinstance(buy_summ, dict) else None
    buy_drift = None
    if forward_buy_mean is not None and buy_avg is not None:
        try:
            buy_drift = round(float(buy_avg) - float(forward_buy_mean), 2)
        except (TypeError, ValueError):
            pass

    return {
        "status": summ.get("status") or "ok",
        "paper_completed_n": completed,
        "paper_avg_return_pct": paper_avg,
        "paper_win_rate_pct": summ.get("win_rate_pct"),
        "paper_avg_excess_vs_spy_pct": summ.get("avg_excess_vs_spy_pct"),
        "forward_20d_baseline_pct": forward_mean,
        "forward_20d_n": forward_n,
        "drift_vs_forward_pct": drift,
        # Buy-side slice (more apples-to-apples)
        "buy_signals_avg_return_pct": buy_avg,
        "buy_signals_n": buy_summ.get("completed_n") if isinstance(buy_summ, dict) else None,
        "forward_buy_baseline_pct": forward_buy_mean,
        "forward_buy_n": forward_buy_n,
        "buy_drift_vs_forward_pct": buy_drift,
        "note": (
            "Forward-tracking 20d mean is a population baseline from EOD snapshots; "
            "paper trades are your subset — large drift warrants checking fills and horizons."
        ),
    }
