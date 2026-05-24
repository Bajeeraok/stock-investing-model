"""
Unified market state for Overview panel and GET /api/market-state.

Aggregates macro regime, pre-market + catalysts, next-day outlook, typical move, intraday.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _now_et() -> datetime:
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    return datetime.now(ZoneInfo("America/New_York"))


def _load_premarket_file() -> dict | None:
    try:
        from config_loader import get_data_root

        path = get_data_root() / "pre_market_latest.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.debug("market_state premarket file: %s", e)
        return None


def build_market_state(config: dict | None = None) -> dict[str, Any]:
    """Single payload for MarketStatePanel and digest hooks."""
    config = config or {}
    premarket = _load_premarket_file()
    catalysts = None
    if premarket:
        try:
            from signals.market_catalysts import attach_catalysts_to_premarket

            enriched = attach_catalysts_to_premarket(dict(premarket), config)
            premarket = enriched
            catalysts = enriched.get("market_catalysts")
        except Exception as e:
            logger.debug("market_state catalysts: %s", e)

    macro_regime = None
    global_regime = None
    macro_regime_bundle = None
    market_regime = None
    portfolio_doctor_v2 = None
    retail_briefing = None
    avg_portfolio_score = None
    per_holding: list[dict] = []
    dash: dict | None = None
    next_day: list[dict] = []
    typical_move: dict | None = None

    try:
        from signals.cache import get_cached_dashboard

        dash = get_cached_dashboard()
        if isinstance(dash, dict):
            macro_regime = dash.get("macro_regime")
            global_regime = dash.get("global_market_regime")
            macro_regime_bundle = dash.get("macro_regime_bundle")
            market_regime = dash.get("market_regime")
            portfolio_doctor_v2 = dash.get("portfolio_doctor_v2")
            retail_briefing = dash.get("retail_briefing")
            next_day = dash.get("next_day_outlook") or []
            typical_move = dash.get("typical_move")
            port = dash.get("portfolio") or {}
            per_holding = port.get("per_holding") or []
            avg_portfolio_score = port.get("avg_score")
    except Exception as e:
        logger.debug("market_state dashboard cache: %s", e)

    if not next_day:
        try:
            from signals.cache import cached_next_day_backtest
            from signals.next_day_bias import next_day_outlook_for_symbols, run_next_day_backtest

            cache = {"SPY": cached_next_day_backtest("SPY", lambda: run_next_day_backtest("SPY", period="5y"))}
            next_day = next_day_outlook_for_symbols(["SPY", "QQQ"], cache)
        except Exception as e:
            logger.debug("market_state next_day: %s", e)

    if not typical_move:
        try:
            from signals.typical_move import typical_move_for_symbols

            typical_move = typical_move_for_symbols(["SPY", "QQQ", "GLD", "SLV"])
        except Exception as e:
            logger.debug("market_state typical_move: %s", e)

    flip_stats = None
    try:
        from signals.market_flip_stats import load_market_flip_stats

        flip_stats = load_market_flip_stats()
    except Exception:
        pass

    retail_decisions = None
    try:
        from signals.retail_market_decisions import build_retail_market_decisions

        retail_decisions = build_retail_market_decisions(
            config=config,
            macro_regime=macro_regime,
            macro_regime_bundle=macro_regime_bundle,
            market_regime=market_regime,
            market_catalysts=catalysts,
            portfolio_doctor_v2=portfolio_doctor_v2,
            retail_briefing=retail_briefing,
            per_holding=per_holding,
            avg_portfolio_score=avg_portfolio_score,
            flip_stats=flip_stats,
        )
    except Exception as e:
        logger.debug("retail_market_decisions: %s", e)

    ms_cfg = (config.get("market_state") or {}) if config else {}
    polling_ms = int(ms_cfg.get("intraday_poll_ms") or 300000)

    now = _now_et()
    hour, minute = now.hour, now.minute
    is_weekday = now.weekday() < 5
    is_premarket = is_weekday and ((hour >= 4 and hour < 9) or (hour == 9 and minute < 30))
    is_rth = is_weekday and ((hour == 9 and minute >= 30) or (10 <= hour < 16) or (hour == 16 and minute == 0))

    return {
        "as_of_et": now.isoformat(),
        "macro_regime": macro_regime,
        "global_market_regime": global_regime,
        "premarket": premarket,
        "market_catalysts": catalysts,
        "retail_market_decisions": retail_decisions,
        "next_day_outlook": next_day,
        "typical_move": typical_move,
        "market_flip_stats": flip_stats,
        "polling": {
            "premarket_poll_ms": 300000 if is_premarket else 1800000,
            "intraday_poll_ms": polling_ms if is_rth else 0,
            "is_premarket_et": is_premarket,
            "is_rth_et": is_rth,
        },
        "disclaimer": "Decision support only — historical setup stats, not release forecasts.",
    }
