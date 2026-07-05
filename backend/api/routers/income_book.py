"""Income Book API — ad-hoc swing portfolio for dollar income goals."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_loader import load_config
from signals.income_book_builder import build_income_plan
from signals.income_book_store import (
    close_trade,
    enter_trade,
    load_income_book,
    save_income_book,
    update_settings,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _market_regime(config: dict) -> str | None:
    try:
        from signals.cache import get_cached_dashboard

        dash = get_cached_dashboard()
        if dash:
            return dash.get("global_market_regime") or dash.get("macro_regime")
    except Exception:
        pass
    return (config.get("regime") or {}).get("default")


@router.get("/income-book")
async def get_income_book():
    """Full income plan: goal math, proposed swing slots, open trades, daily changes."""
    cfg = load_config()
    ib_cfg = cfg.get("income_book") or {}
    if ib_cfg.get("enabled") is False:
        return {"enabled": False, "message": "Income book disabled in config."}

    book = load_income_book()
    try:
        plan = build_income_plan(cfg, book=book, market_regime=_market_regime(cfg))
        save_income_book(book)
        return plan
    except Exception as e:
        logger.warning("income-book build failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/income-book")
async def post_income_book(body: dict):
    """
    Actions:
      - update_settings: { action, goal_usd?, timeframe_months?, capital_usd?, risk_pct?, max_open_trades?, exclude_long_term_holdings? }
      - enter_trade: { action, ticker, entry_price, shares?, stop?, t1?, t2?, setup?, notional_usd? }
      - close_trade: { action, trade_id?, ticker?, exit_price, exit_reason? }
    """
    action = str(body.get("action") or "").strip().lower()
    if not action:
        raise HTTPException(status_code=400, detail="action required")

    book = load_income_book()
    try:
        if action == "update_settings":
            update_settings(book, body)
        elif action == "enter_trade":
            enter_trade(
                book,
                ticker=str(body.get("ticker") or ""),
                entry_price=float(body.get("entry_price") or 0),
                shares=_opt_float(body.get("shares")),
                stop=_opt_float(body.get("stop")),
                t1=_opt_float(body.get("t1")),
                t2=_opt_float(body.get("t2")),
                setup=body.get("setup"),
                notional_usd=_opt_float(body.get("notional_usd")),
            )
        elif action == "close_trade":
            close_trade(
                book,
                trade_id=body.get("trade_id"),
                ticker=body.get("ticker"),
                exit_price=float(body.get("exit_price") or 0),
                exit_reason=str(body.get("exit_reason") or "manual"),
            )
        else:
            raise HTTPException(status_code=400, detail=f"unknown action: {action}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("income-book POST failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    save_income_book(book)
    cfg = load_config()
    plan = build_income_plan(cfg, book=book, market_regime=_market_regime(cfg))
    save_income_book(book)
    return plan


def _opt_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
