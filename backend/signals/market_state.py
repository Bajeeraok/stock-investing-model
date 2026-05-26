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
            next_day = next_day_outlook_for_symbols(["SPY", "QQQ", "GLD", "SLV"], cache)
        except Exception as e:
            logger.debug("market_state next_day: %s", e)

    if not typical_move:
        try:
            from signals.typical_move import typical_move_for_symbols

            typical_move = typical_move_for_symbols(["SPY", "QQQ", "GLD", "SLV"])
        except Exception as e:
            logger.debug("market_state typical_move: %s", e)

    next_day_summary = None
    if next_day:
        notes = [r.get("display_note") for r in next_day if r.get("display_note")]
        weak = sum(1 for r in next_day if r.get("edge_strength") == "none")
        if weak >= max(2, len(next_day) // 2):
            next_day_summary = notes[0] if notes else "Next-day edge is minimal across benchmarks — tape-driven session."
        elif all((r.get("bias") or "Neutral") == "Neutral" for r in next_day):
            next_day_summary = "All benchmarks neutral — coin-flip setup; use trigger levels instead of directional bets."

    if isinstance(typical_move, dict):
        typical_list = typical_move.get("symbols") or typical_move.get("items") or []
    elif isinstance(typical_move, list):
        typical_list = typical_move
    else:
        typical_list = []

    es_pct = (premarket or {}).get("es_pct") if isinstance(premarket, dict) else None
    if typical_list and es_pct is not None:
        for row in typical_list:
            if not isinstance(row, dict):
                continue
            if (row.get("ticker") or "").upper() == "SPY":
                typ = row.get("typical_pct_1d") or row.get("typical_pct")
                if typ and typ > 0:
                    used = round(min(100.0, abs(float(es_pct)) / float(typ) * 100), 0)
                    row["range_used_pct"] = used
                    row["premarket_pct"] = es_pct
                    if used >= 40:
                        row["range_note"] = f"Pre-market used ~{used:.0f}% of typical daily range — less room to run today."
                    break

    if premarket and isinstance(premarket, dict):
        try:
            signals_by_ticker = {}
            if isinstance(dash, dict):
                for s in dash.get("signals") or []:
                    if isinstance(s, dict) and s.get("ticker"):
                        signals_by_ticker[str(s["ticker"]).upper()] = s
            for bucket in ("tech_movers",):
                movers = premarket.get(bucket) or []
                enriched = []
                for m in movers:
                    if not isinstance(m, dict):
                        continue
                    t = str(m.get("ticker", "")).upper()
                    why = None
                    sig = signals_by_ticker.get(t) or {}
                    if sig.get("earnings_note"):
                        why = sig["earnings_note"]
                    elif sig.get("regime") == "DOWN":
                        why = "Weak trend/score — profit-taking or macro pressure."
                    elif (m.get("pct") or 0) < -1:
                        why = "Pre-market sell pressure — check news; may be dip if bull regime intact."
                    elif (m.get("pct") or 0) > 1:
                        why = "Pre-market bid — momentum continuation risk if extended."
                    enriched.append({**m, "why": why})
                if enriched:
                    premarket = {**premarket, f"{bucket}_detail": enriched}
        except Exception as e:
            logger.debug("market_state premarket enrich: %s", e)

    flip_stats = None
    try:
        from signals.market_flip_stats import load_market_flip_stats

        flip_stats = load_market_flip_stats()
    except Exception:
        pass

    try:
        from config_loader import get_data_root

        _dr = get_data_root()
    except Exception:
        _dr = None

    retail_decisions = None
    try:
        from signals.retail_market_decisions import build_retail_market_decisions

        retail_decisions = build_retail_market_decisions(
            config=config,
            macro_regime=macro_regime,
            global_market_regime=global_regime,
            macro_regime_bundle=macro_regime_bundle,
            market_regime=market_regime,
            market_catalysts=catalysts,
            portfolio_doctor_v2=portfolio_doctor_v2,
            retail_briefing=retail_briefing,
            per_holding=per_holding,
            avg_portfolio_score=avg_portfolio_score,
            flip_stats=flip_stats,
            cross_asset=dash.get("cross_asset") if isinstance(dash, dict) else None,
            premarket=premarket,
            data_root=_dr,
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
        "next_day_summary": next_day_summary,
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
