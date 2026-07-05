"""Persist user Income Book settings and trade journal (separate from long-term portfolio)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from config_loader import get_data_root

DEFAULT_SETTINGS = {
    "goal_usd": 5000.0,
    "timeframe_months": 3,
    "capital_usd": 100000.0,
    "risk_pct": 1.5,
    "max_open_trades": 3,
    "exclude_long_term_holdings": True,
}


def income_book_path(data_root: Path | None = None) -> Path:
    root = data_root or get_data_root()
    return root / "income_book.yaml"


def default_book() -> dict[str, Any]:
    return {
        "settings": dict(DEFAULT_SETTINGS),
        "open_trades": [],
        "closed_trades": [],
        "updated_at": None,
    }


def load_income_book(path: Path | None = None) -> dict[str, Any]:
    p = path or income_book_path()
    if not p.exists():
        return default_book()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return default_book()
    book = default_book()
    if isinstance(data.get("settings"), dict):
        book["settings"].update(data["settings"])
    book["open_trades"] = list(data.get("open_trades") or [])
    book["closed_trades"] = list(data.get("closed_trades") or [])
    book["updated_at"] = data.get("updated_at")
    return book


def save_income_book(book: dict[str, Any], path: Path | None = None) -> None:
    p = path or income_book_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "settings": book.get("settings") or dict(DEFAULT_SETTINGS),
        "open_trades": book.get("open_trades") or [],
        "closed_trades": book.get("closed_trades") or [],
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(out, f, default_flow_style=False, sort_keys=False)


def update_settings(book: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    settings = dict(book.get("settings") or DEFAULT_SETTINGS)
    for key in (
        "goal_usd",
        "timeframe_months",
        "capital_usd",
        "risk_pct",
        "max_open_trades",
        "exclude_long_term_holdings",
    ):
        if key in patch and patch[key] is not None:
            settings[key] = patch[key]
    book["settings"] = settings
    return book


def _new_trade_id() -> str:
    return f"ib-{uuid4().hex[:10]}"


def enter_trade(
    book: dict[str, Any],
    *,
    ticker: str,
    entry_price: float,
    shares: float | None = None,
    stop: float | None = None,
    t1: float | None = None,
    t2: float | None = None,
    setup: str | None = None,
    notional_usd: float | None = None,
) -> dict[str, Any]:
    sym = (ticker or "").upper().strip()
    if not sym:
        raise ValueError("ticker required")
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    settings = book.get("settings") or {}
    max_open = int(settings.get("max_open_trades") or 3)
    open_trades = list(book.get("open_trades") or [])
    if len(open_trades) >= max_open:
        raise ValueError(f"max {max_open} open trades")
    if any(str(t.get("ticker") or "").upper() == sym for t in open_trades):
        raise ValueError(f"{sym} already open in income book")
    if shares is None and notional_usd is not None and entry_price > 0:
        shares = round(float(notional_usd) / entry_price, 4)
    trade = {
        "id": _new_trade_id(),
        "ticker": sym,
        "entered_at": datetime.now().strftime("%Y-%m-%d"),
        "entry_price": round(float(entry_price), 4),
        "shares": round(float(shares or 0), 4),
        "stop": round(float(stop), 4) if stop is not None else None,
        "t1": round(float(t1), 4) if t1 is not None else None,
        "t2": round(float(t2), 4) if t2 is not None else None,
        "setup": setup,
        "status": "in_trade",
    }
    open_trades.append(trade)
    book["open_trades"] = open_trades
    return trade


def close_trade(
    book: dict[str, Any],
    *,
    trade_id: str | None = None,
    ticker: str | None = None,
    exit_price: float,
    exit_reason: str = "manual",
) -> dict[str, Any]:
    open_trades = list(book.get("open_trades") or [])
    closed = list(book.get("closed_trades") or [])
    target = None
    for t in open_trades:
        if trade_id and t.get("id") == trade_id:
            target = t
            break
        if ticker and str(t.get("ticker") or "").upper() == ticker.upper():
            target = t
            break
    if not target:
        raise ValueError("trade not found")
    entry = float(target.get("entry_price") or 0)
    shares = float(target.get("shares") or 0)
    if entry <= 0 or shares <= 0:
        raise ValueError("invalid open trade")
    pnl = round(shares * (float(exit_price) - entry), 2)
    ret_pct = round(100.0 * (float(exit_price) - entry) / entry, 2)
    record = {
        **target,
        "closed_at": datetime.now().strftime("%Y-%m-%d"),
        "exit_price": round(float(exit_price), 4),
        "exit_reason": exit_reason,
        "realized_pnl_usd": pnl,
        "return_pct": ret_pct,
        "status": "closed",
    }
    open_trades = [t for t in open_trades if t.get("id") != target.get("id")]
    closed.append(record)
    book["open_trades"] = open_trades
    book["closed_trades"] = closed
    return record
