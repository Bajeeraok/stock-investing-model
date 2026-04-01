"""
Institutional-style proxies: FMP insider list (role/size weighted), short float, holder trend.
Complements SEC Form 4 flow in edgar_insider — not real-time options flow.
"""
from __future__ import annotations

import logging
from typing import Any

from signals.fmp_client import (
    fetch_institutional_holder_summary,
    fetch_insider_trading_list,
    fetch_short_float_summary,
)

logger = logging.getLogger(__name__)

_ROLE_WEIGHTS = (
    ("Chief Executive Officer", 1.0),
    ("Chief Financial Officer", 0.9),
    ("President", 0.8),
    ("Director", 0.5),
    ("VP", 0.3),
)


def _role_weight(reporting_name: str) -> float:
    name = (reporting_name or "").strip()
    for key, w in _ROLE_WEIGHTS:
        if key in name:
            return w
    return 0.2


def _tx_is_buy(action: str) -> bool:
    a = (action or "").lower()
    return "purchase" in a or "buy" in a or "acquisition" in a


def _tx_is_sell(action: str) -> bool:
    a = (action or "").lower()
    return "sale" in a or "sell" in a or "disposition" in a


def get_weighted_insider_signal(config: dict, ticker: str, limit: int = 20) -> dict[str, Any]:
    rows, err = fetch_insider_trading_list(config, ticker, limit=limit)
    if err or not rows:
        return {"signal": 0.0, "buy_score": 0.0, "sell_score": 0.0, "n": 0, "error": err}

    buy_score = 0.0
    sell_score = 0.0
    for tx in rows[:limit]:
        role = tx.get("reportingName") or tx.get("reportingCik") or ""
        action = tx.get("transactionType") or tx.get("type") or ""
        try:
            value = abs(float(tx.get("value") or tx.get("securitiesTransacted") or 0))
        except (TypeError, ValueError):
            value = 0.0
        w = _role_weight(str(role))
        size_w = min(value / 1_000_000.0, 5.0) if value else 0.1
        if _tx_is_buy(action):
            buy_score += w * size_w
        elif _tx_is_sell(action):
            sell_score += w * size_w

    net = buy_score - sell_score
    signal = max(-100.0, min(100.0, net * 10.0))
    return {
        "signal": round(signal, 2),
        "buy_score": round(buy_score, 2),
        "sell_score": round(sell_score, 2),
        "n": len(rows[:limit]),
    }


def get_short_interest_signal(config: dict, ticker: str) -> dict[str, Any]:
    row, err = fetch_short_float_summary(config, ticker)
    if err or not row:
        return {"short_float_pct": None, "signal": "UNKNOWN", "error": err}

    sf = row.get("shortPercentOfFloat")
    if sf is None:
        sf = row.get("shortFloatPercent") or row.get("shortFloat")
    try:
        short_float = float(sf)
    except (TypeError, ValueError):
        return {"short_float_pct": None, "signal": "UNKNOWN", "raw": row}

    # FMP may return 0–1 or 0–100
    if short_float > 1.0:
        short_float = short_float / 100.0

    pct = short_float * 100.0
    if short_float > 0.20:
        label = "HIGH_SHORT — squeeze risk or justified caution"
    elif short_float > 0.10:
        label = "ELEVATED_SHORT — monitor"
    else:
        label = "LOW_SHORT — clean"

    return {"short_float_pct": round(pct, 2), "signal": label}


def get_institutional_trend_proxy(config: dict, ticker: str) -> dict[str, Any]:
    rows, err = fetch_institutional_holder_summary(config, ticker)
    if err or not rows or len(rows) < 2:
        return {"trend": "UNKNOWN", "error": err, "total_institutions": len(rows or [])}

    increasing = 0
    for h in rows:
        ch = h.get("change") or h.get("changeInShares") or h.get("changeInHoldings")
        try:
            if ch is not None and float(ch) > 0:
                increasing += 1
        except (TypeError, ValueError):
            continue
    total = len(rows)
    pct_inc = increasing / total if total else 0.0
    trend = (
        "ACCUMULATING" if pct_inc > 0.60 else
        "DISTRIBUTING" if pct_inc < 0.40 else
        "NEUTRAL"
    )
    return {
        "pct_institutions_increasing": round(pct_inc, 3),
        "trend": trend,
        "total_institutions": total,
    }


def build_institutional_bundle(config: dict, ticker: str) -> dict[str, Any]:
    """Single-ticker snapshot for API / insights."""
    t = (ticker or "").upper().strip()
    return {
        "ticker": t,
        "insider_weighted": get_weighted_insider_signal(config, t),
        "short_interest": get_short_interest_signal(config, t),
        "institutional_trend": get_institutional_trend_proxy(config, t),
    }
