"""
High 1-day event risk strip — ranks watchlist/portfolio names for Scout overview.

Combines: earnings proximity + historical expected move, ATR (typical daily range),
velocity (breakout fuel). Enriches top rows with pre-earnings bias and post-earnings
price targets from price_targets._compute_earnings_target_block (walk-forward calibration).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _default_cfg(config: dict | None) -> dict[str, Any]:
    base = {
        "enabled": True,
        "max_earnings_days": 14,
        "max_lookback_days": 21,
        "limit": 8,
        "min_score": 12.0,
        "atr_weight": 0.55,
        "velocity_weight": 0.30,
        "earnings_weight": 0.35,
    }
    raw = (config or {}).get("event_risk_strip") or {}
    if isinstance(raw, dict):
        base.update({k: raw[k] for k in base if k in raw})
    return base


def _atr_pct(row: dict[str, Any]) -> float | None:
    try:
        close = float(row.get("close") or 0)
        atr = float(row.get("atr_14") or 0)
        if close <= 0 or atr <= 0:
            return None
        return round(100.0 * atr / close, 2)
    except (TypeError, ValueError):
        return None


def _quick_event_score(row: dict[str, Any], cfg: dict[str, Any]) -> float:
    """Fast rank score before optional earnings-target enrichment."""
    atr_pct = _atr_pct(row) or 0.0
    vel = float(row.get("velocity_score") or 0.0)
    days = row.get("earnings_days_until")
    earn_pts = 0.0
    max_er = int(cfg.get("max_earnings_days", 14))
    if days is not None:
        try:
            d = int(days)
        except (TypeError, ValueError):
            d = None
        if d is not None and 0 <= d <= max_er:
            earn_pts = (max_er - d + 1) / (max_er + 1) * 25.0
        elif d is not None and max_er < d <= int(cfg.get("max_lookback_days", 21)):
            earn_pts = 4.0
    rvol = row.get("rvol")
    rvol_boost = 0.0
    if rvol is not None:
        try:
            rvol_boost = min(8.0, max(0.0, (float(rvol) - 1.0) * 3.0))
        except (TypeError, ValueError):
            pass
    return (
        atr_pct * float(cfg.get("atr_weight", 0.55))
        + vel * float(cfg.get("velocity_weight", 0.30))
        + earn_pts * float(cfg.get("earnings_weight", 0.35))
        + rvol_boost
    )


def _event_tags(row: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    days = row.get("earnings_days_until")
    max_er = int(cfg.get("max_earnings_days", 14))
    if days is not None:
        try:
            d = int(days)
            if 0 <= d <= max_er:
                tags.append("earnings")
        except (TypeError, ValueError):
            pass
    if row.get("velocity_triggered") or float(row.get("velocity_score") or 0) >= 55:
        tags.append("velocity")
    atr_pct = _atr_pct(row)
    if atr_pct is not None and atr_pct >= 4.0:
        tags.append("high_atr")
    return tags or ["watch"]


def _enrich_earnings_target(row: dict[str, Any], config: dict | None) -> dict[str, Any] | None:
    ticker = str(row.get("ticker") or "").upper()
    if not ticker:
        return None
    days = row.get("earnings_days_until")
    max_er = int(_default_cfg(config).get("max_earnings_days", 14))
    if days is None:
        return None
    try:
        if int(days) > max_er or int(days) < 0:
            return None
    except (TypeError, ValueError):
        return None

    try:
        from signals.fetcher import fetch_ohlcv_safe
        from signals.price_targets import _compute_earnings_target_block

        period = (config or {}).get("data", {}).get("period", "5y")
        close = fetch_ohlcv_safe(ticker, period)
        if close is None or len(close) < 40:
            return None
        price = float(row.get("close") or close.iloc[-1])
        ml_short = row.get("ml_short_prob")
        short_prob = float(ml_short) if ml_short is not None else None
        earnings_info = {
            "days_until_earnings": days,
            "next_earnings_date": None,
        }
        block = _compute_earnings_target_block(
            ticker,
            price=price,
            close=close,
            short_prob=short_prob,
            earnings_info=earnings_info,
        )
        if not block.get("available"):
            return None
        return block
    except Exception as exc:
        logger.debug("event_risk earnings target %s: %s", ticker, exc)
        return None


def _row_payload(
    row: dict[str, Any],
    *,
    score: float,
    cfg: dict[str, Any],
    earnings_target: dict[str, Any] | None,
) -> dict[str, Any]:
    atr_pct = _atr_pct(row)
    days = row.get("earnings_days_until")
    tags = _event_tags(row, cfg)
    et = earnings_target or {}

    expected_move = et.get("expected_move_pct")
    if expected_move is None and atr_pct is not None:
        expected_move = round(atr_pct * 0.65, 1)

    bias = et.get("bias")
    if not bias and row.get("ml_short_prob") is not None:
        try:
            p = float(row["ml_short_prob"])
            if p >= 0.55:
                bias = "Bullish"
            elif p <= 0.45:
                bias = "Bearish"
            else:
                bias = "Neutral"
        except (TypeError, ValueError):
            bias = "Neutral"

    hit_rate = et.get("calibration_hit_rate")
    backtest_n = et.get("backtest_events") or 0
    calibration_note = None
    if hit_rate is not None and backtest_n > 0:
        pct = round(float(hit_rate) * 100)
        calibration_note = (
            f"Walk-forward: realized move within expected band on {pct}% of last {backtest_n} earnings "
            f"(MAE {et.get('calibration_mae_pct')}%)"
        )
    elif et.get("method_note"):
        calibration_note = str(et.get("method_note"))

    return {
        "ticker": str(row.get("ticker") or "").upper(),
        "event_score": round(score, 1),
        "event_tags": tags,
        "close": row.get("close"),
        "atr_pct": atr_pct,
        "atr_14": row.get("atr_14"),
        "velocity_score": row.get("velocity_score"),
        "velocity_triggered": bool(row.get("velocity_triggered")),
        "rvol": row.get("rvol"),
        "earnings_days_until": days,
        "expected_move_pct": expected_move,
        "pre_earnings_bias": bias,
        "bias_prob_pct": et.get("bias_prob_pct"),
        "post_earnings_upside": et.get("upside_target"),
        "post_earnings_downside": et.get("downside_target"),
        "post_earnings_directional": et.get("directional_target"),
        "calibration_hit_rate": hit_rate,
        "calibration_mae_pct": et.get("calibration_mae_pct"),
        "calibration_confidence_pct": et.get("confidence_pct"),
        "calibration_events": backtest_n,
        "calibration_note": calibration_note,
        "historical_avg_abs_move_pct": et.get("historical_avg_abs_move_pct"),
        "recent_earnings_moves": [
            {
                "date": ev.get("event_date"),
                "move_pct": ev.get("realized_move_pct"),
            }
            for ev in (et.get("recent_events") or [])[-3:]
            if isinstance(ev, dict)
        ],
    }


def build_event_risk_strip(
    results: list[dict[str, Any]] | None,
    config: dict | None = None,
    *,
    watchlist_tickers: list[str] | None = None,
    portfolio_tickers: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Rank tickers for Scout 1-day event risk strip.
    Returns { rows, message, as_of_note }.
    """
    cfg = _default_cfg(config)
    if not cfg.get("enabled", True):
        return {"rows": [], "message": "disabled", "rank_note": None}

    cap = int(limit if limit is not None else cfg.get("limit", 8))
    min_score = float(cfg.get("min_score", 12.0))
    watch = {str(t).upper() for t in (watchlist_tickers or []) if t}
    portfolio = {str(t).upper() for t in (portfolio_tickers or []) if t}
    priority = watch | portfolio

    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in results or []:
        if not isinstance(row, dict) or row.get("error"):
            continue
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        if priority and ticker not in priority:
            continue
        score = _quick_event_score(row, cfg)
        tags = _event_tags(row, cfg)
        if score < min_score and "earnings" not in tags:
            continue
        candidates.append((score, row))

    candidates.sort(key=lambda x: (-x[0], str(x[1].get("ticker") or "")))

    rows_out: list[dict[str, Any]] = []
    for score, row in candidates[: cap * 2]:
        if len(rows_out) >= cap:
            break
        et = _enrich_earnings_target(row, config)
        payload = _row_payload(row, score=score, cfg=cfg, earnings_target=et)
        if payload["event_score"] < min_score and "earnings" not in payload["event_tags"]:
            continue
        rows_out.append(payload)

    rank_note = (
        "Ranked by earnings window (≤{}d) + ATR daily range + velocity/RVOL. "
        "Pre-earnings bias from short-horizon ML; post-earnings targets from historical "
        "reaction band ± expected move (walk-forward calibration when history exists)."
    ).format(cfg.get("max_earnings_days", 14))

    return {
        "rows": rows_out[:cap],
        "rank_note": rank_note,
        "message": None if rows_out else "No names above event-risk threshold in watchlist/portfolio.",
    }
