"""
Liquidity score — ADV-based days-to-exit at 20% of average daily volume.

Flags positions that would take >5 days to liquidate without moving the market.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PARTICIPATION_RATE = 0.20  # trade at 20% of ADV


def compute_liquidity_scores(
    per_holding: list[dict],
    *,
    fetch_close_volume=None,
    lookback_days: int = 63,
) -> dict[str, Any]:
    """
    For each holding, compute days to exit based on ADV.

    Returns {
      items: [{ticker, shares, avg_daily_volume, days_to_exit, liquidity_score, flag}],
      illiquid_count, note
    }
    """
    if fetch_close_volume is None:
        from signals.fetcher import fetch_ohlcv_with_volume
        fetch_close_volume = lambda t, p: fetch_ohlcv_with_volume(t, p)

    items: list[dict] = []

    for h in per_holding:
        ticker = h.get("ticker")
        qty = h.get("quantity", 0) or 0
        price = h.get("price") or 0
        pct = h.get("pct") or 0

        if not ticker or qty <= 0:
            items.append({
                "ticker": ticker or "?",
                "avg_daily_volume": None,
                "days_to_exit": None,
                "liquidity_score": None,
                "flag": None,
            })
            continue

        try:
            _close, volume = fetch_close_volume(ticker, "3m")
            if volume is not None and len(volume) >= 20:
                adv = float(volume.tail(lookback_days).mean())
            else:
                adv = None
        except Exception:
            adv = None

        if adv is None or adv <= 0:
            items.append({
                "ticker": ticker,
                "avg_daily_volume": None,
                "days_to_exit": None,
                "liquidity_score": None,
                "flag": "No volume data",
            })
            continue

        tradeable_per_day = adv * PARTICIPATION_RATE
        days_to_exit = qty / tradeable_per_day if tradeable_per_day > 0 else 999

        # Score 1-5: 1 = highly liquid (<1 day), 5 = illiquid (>10 days)
        if days_to_exit < 0.5:
            score = 1
        elif days_to_exit < 1:
            score = 2
        elif days_to_exit < 3:
            score = 3
        elif days_to_exit < 7:
            score = 4
        else:
            score = 5

        flag = None
        if days_to_exit > 5:
            flag = f"Would take {days_to_exit:.0f} days to exit at {PARTICIPATION_RATE:.0%} of ADV"
        elif days_to_exit > 2:
            flag = f"{days_to_exit:.1f} days to exit"

        items.append({
            "ticker": ticker,
            "avg_daily_volume": round(adv),
            "avg_daily_dollar_volume": round(adv * price) if price else None,
            "days_to_exit": round(days_to_exit, 1),
            "liquidity_score": score,
            "portfolio_pct": round(pct, 1),
            "flag": flag,
        })

    items.sort(key=lambda x: -(x.get("days_to_exit") or 0))
    illiquid = [i for i in items if (i.get("days_to_exit") or 0) > 5]

    note = None
    if illiquid:
        names = ", ".join(i["ticker"] for i in illiquid[:3])
        note = f"{len(illiquid)} position{'s' if len(illiquid) != 1 else ''} would take >5 days to exit: {names}"

    return {
        "items": items,
        "illiquid_count": len(illiquid),
        "note": note,
    }
