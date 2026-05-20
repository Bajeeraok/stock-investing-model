"""
Shell payload builder: instant read path for GET /api/dashboard/shell.
"""
from __future__ import annotations

from typing import Any

# Fields needed for Overview + Portfolio tabs without heavy analysis / opportunities scan.
SHELL_KEYS: tuple[str, ...] = (
    "as_of_date",
    "data_freshness",
    "signal_scores",
    "signals",
    "signals_deferred",
    "opportunities_deferred",
    "opportunities_bundle_enabled",
    "analysis_deferred",
    "watchlist",
    "story_changes",
    "portfolio",
    "portfolios",
    "portfolio_names",
    "trim_candidates",
    "opportunities",
    "portfolio_doctor_recommendations",
    "thesis_check",
    "what_changed",
    "earnings_risk_count",
    "retail_briefing",
    "morning_newsletter",
    "market_regime",
    "global_market_regime",
    "macro_regime",
    "macro_regime_bundle",
    "market_reversal_overlay",
    "next_day_outlook",
    "typical_move",
    "guidelines",
    "cross_asset",
    "economic_calendar",
    "market_scenarios",
    "macro_analog",
    "market_forecast",
    "portfolio_stress",
    "portfolio_risk_metrics",
    "portfolio_doctor_v2",
    "performance_vs_benchmark",
    "tax_aware_exits",
    "known_limits",
    "config",
    "crypto",
    "cot_by_ticker",
    "redis_status",
    "eod_snapshots",
    "eod_snapshot_latest_date",
    "model_health",
    "after_hours_earnings",
    "stale",
    "refresh_status",
)

# Loaded when user opens Analysis tab.
ANALYSIS_BUNDLE_KEYS: tuple[str, ...] = (
    "model_validation",
    "forward_tracking",
    "regime_validation",
    "confidence_calibration",
    "paper_trading",
    "paper_vs_backtest_drift",
    "insider_flow",
    "indicator_validation",
    "indicator_comparisons",
    "fmp_plan_status",
)


def build_shell_from_full(full: dict, *, include_full_signals: bool = False) -> dict:
    """Trim a full dashboard dict to shell fields; defer heavy nested sections."""
    out: dict[str, Any] = {}
    for key in SHELL_KEYS:
        if key in full:
            out[key] = full[key]
    out.setdefault("signals_deferred", True)
    out.setdefault("opportunities_deferred", True)
    out.setdefault("opportunities_bundle_enabled", True)
    out.setdefault("analysis_deferred", True)
    out.setdefault("opportunities", [])
    out.setdefault("portfolio_doctor_recommendations", {})
    if include_full_signals:
        out["signals"] = full.get("signals") or []
        out["signals_deferred"] = False
    else:
        scores = full.get("signal_scores")
        if not scores and isinstance(full.get("signals"), list):
            scores = [
                {
                    "ticker": r.get("ticker"),
                    "composite_buy": r.get("composite_buy"),
                    "regime": r.get("regime"),
                    "error": r.get("error"),
                }
                for r in full["signals"]
                if isinstance(r, dict)
            ]
        out["signal_scores"] = scores or []
        out["signals"] = []
        out["signals_deferred"] = True
    return out


def build_analysis_bundle(full: dict) -> dict:
    return {k: full.get(k) for k in ANALYSIS_BUNDLE_KEYS if k in full}


def empty_analysis_bundle() -> dict:
    return {
        "model_validation": {"records": [], "summary": {}},
        "forward_tracking": {"records": [], "summary_by_horizon": {}, "summary_by_signal": {}, "message": None},
        "regime_validation": {"validated": None, "summary": "Not computed"},
        "confidence_calibration": {"buckets": [], "note": "Not computed"},
        "paper_trading": {},
        "paper_vs_backtest_drift": None,
        "insider_flow": {"insider_buys": [], "insider_sells": [], "ticker_activities": [], "message": None},
        "indicator_validation": [],
        "indicator_comparisons": [],
        "fmp_plan_status": {"has_key": False, "available": [], "unavailable": []},
        "analysis_deferred": False,
    }
