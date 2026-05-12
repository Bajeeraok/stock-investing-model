"""
Priority action queue — "What do I do this week / this month?"

Ranks actions by urgency:
  - THIS WEEK: urgent (earnings in <8d, concentration > 25%, regime flip, stop hit)
  - THIS MONTH: conditional (entry zone, pattern score trigger, rebalance)

Each action has: ticker, action, reasoning, tags, dollar amount.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_priority_actions(
    per_holding: list[dict],
    total_value: float,
    *,
    trim_list: list[dict] | None = None,
    add_list: list[dict] | None = None,
    correlation_alerts: list[str] | None = None,
    earnings_calendar: list[dict] | None = None,
    mctr: dict | None = None,
    tax_exits: dict | None = None,
    concentration_threshold_pct: float = 20.0,
) -> dict[str, Any]:
    """
    Build prioritized action list: this_week (urgent) + this_month (conditional).
    """
    this_week: list[dict] = []
    this_month: list[dict] = []

    # --- Earnings risk: positions reporting in next 8 days ---
    if earnings_calendar:
        for ec in earnings_calendar:
            days = ec.get("days_until")
            ticker = ec.get("ticker")
            if days is not None and days <= 8 and ticker:
                holding = next((h for h in per_holding if h.get("ticker") == ticker), None)
                pct = holding.get("pct", 0) if holding else 0
                action_text = f"Set {ticker} hard stop before earnings"
                reason = (
                    f"Earnings in ~{days} days. {ticker} is {pct:.1f}% of portfolio. "
                    f"Stop protects unrealized gain if earnings disappoint."
                )
                this_week.append({
                    "ticker": ticker,
                    "action": action_text,
                    "reason": reason,
                    "tags": ["Earnings risk"],
                    "urgency": "high",
                    "days_until_event": days,
                })

    # --- Correlation-driven trims (effectively one position) ---
    if correlation_alerts:
        for alert in correlation_alerts[:2]:
            parts = alert.split(":")
            pair = parts[0].strip() if parts else ""
            corr_val = parts[1].strip() if len(parts) > 1 else ""
            tickers_in_pair = [t.strip() for t in pair.split("-")]
            if len(tickers_in_pair) == 2:
                t1, t2 = tickers_in_pair
                h1 = next((h for h in per_holding if h.get("ticker") == t1), None)
                h2 = next((h for h in per_holding if h.get("ticker") == t2), None)
                if h1 and h2:
                    trim_ticker = t2 if (h1.get("pct") or 0) >= (h2.get("pct") or 0) else t1
                    keep_ticker = t1 if trim_ticker == t2 else t2
                    pct1 = h1.get("pct") or 0
                    pct2 = h2.get("pct") or 0
                    this_week.append({
                        "ticker": trim_ticker,
                        "action": f"Trim {trim_ticker} — {corr_val} correlated with {keep_ticker}",
                        "reason": (
                            f"{corr_val} correlated with {keep_ticker} — you effectively hold one position, not two. "
                            f"Combined {pct1 + pct2:.1f}% of portfolio."
                        ),
                        "tags": ["Urgent"],
                        "urgency": "high",
                    })

    # --- Concentration trims ---
    if trim_list:
        for tr in trim_list:
            pct = tr.get("current_pct", 0)
            conf = tr.get("confidence")
            ticker = tr.get("ticker")
            if pct > concentration_threshold_pct:
                this_week.append({
                    "ticker": ticker,
                    "action": f"Reduce {ticker} to {concentration_threshold_pct:.0f}% max — trim ${tr.get('suggest_trim_dollars', 0):,.0f}",
                    "reason": tr.get("reason", ""),
                    "tags": ["Regime conflict", "Taxable trim"] if conf and conf < 40 else ["Concentration"],
                    "urgency": "high",
                    "dollars": tr.get("suggest_trim_dollars"),
                })
            elif conf is not None and conf < 35:
                this_month.append({
                    "ticker": ticker,
                    "action": f"Reassess {ticker} — confidence {conf:.0f}%",
                    "reason": tr.get("reason", ""),
                    "tags": ["Watch"],
                    "urgency": "medium",
                })

    # --- Tax-aware actions ---
    if tax_exits:
        items = tax_exits.get("items") or tax_exits.get("exits") or []
        for item in items:
            if item.get("status") == "approaching_ltcg":
                days_to = item.get("days_to_ltcg", 0)
                ticker = item.get("ticker")
                if days_to <= 30 and ticker:
                    this_month.append({
                        "ticker": ticker,
                        "action": f"Hold {ticker} — LTCG in {days_to} days",
                        "reason": f"Holding {days_to} more days qualifies for long-term rate.",
                        "tags": ["Tax optimal"],
                        "urgency": "low",
                    })
            if item.get("has_loss") and not item.get("is_long_term"):
                ticker = item.get("ticker")
                gain_loss = item.get("gain_loss")
                if ticker and gain_loss and gain_loss < 0:
                    this_month.append({
                        "ticker": ticker,
                        "action": f"Harvest {ticker} loss to offset gains",
                        "reason": f"Short-term loss of ${abs(gain_loss):,.0f} can offset taxable gains.",
                        "tags": ["Tax"],
                        "urgency": "medium",
                        "dollars": round(gain_loss, 0),
                    })

    # --- Conditional adds ---
    if add_list:
        for add in add_list[:3]:
            ticker = add.get("ticker")
            conf = add.get("confidence")
            buy_price = add.get("buy_price")
            this_month.append({
                "ticker": ticker,
                "action": f"Add {ticker} if holds ${buy_price:.2f} entry zone" if buy_price else f"Add {ticker}",
                "reason": (
                    f"{'BUY signal triggered' if add.get('action') == 'BUY' else 'Signal constructive'}. "
                    f"{'Confidence ' + str(round(conf)) + '%.' if conf else ''}"
                ),
                "tags": ["Conditional"],
                "urgency": "medium",
            })

    # --- MCTR-driven rebalance ---
    if mctr and mctr.get("positions"):
        top_risk = mctr["positions"][0]
        if top_risk["risk_pct"] > top_risk["value_pct"] * 1.8:
            # Only add if not already in this_week
            already = {a.get("ticker") for a in this_week}
            if top_risk["ticker"] not in already:
                this_month.append({
                    "ticker": top_risk["ticker"],
                    "action": (
                        f"Rebalance {top_risk['ticker']} — "
                        f"{top_risk['risk_pct']:.0f}% of risk vs {top_risk['value_pct']:.0f}% of value"
                    ),
                    "reason": "Disproportionate risk contribution. Consider trimming to reduce portfolio volatility.",
                    "tags": ["Rebalance"],
                    "urgency": "medium",
                })

    # Sort by urgency and limit
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    this_week.sort(key=lambda x: urgency_order.get(x.get("urgency", "medium"), 1))
    this_month.sort(key=lambda x: urgency_order.get(x.get("urgency", "medium"), 1))

    return {
        "this_week": this_week[:5],
        "this_month": this_month[:6],
        "total_actions": len(this_week) + len(this_month),
    }


def build_earnings_calendar_portfolio(
    per_holding: list[dict],
    total_value: float,
    config: dict | None = None,
    days_ahead: int = 30,
) -> dict[str, Any]:
    """
    Portfolio-level earnings calendar: which holdings report in next N days.
    """
    config = config or {}
    items: list[dict] = []
    total_at_risk_pct = 0.0

    for h in per_holding:
        ticker = h.get("ticker")
        pct = h.get("pct") or 0
        if not ticker or pct <= 0:
            continue

        try:
            from signals.providers import get_next_earnings
            e = get_next_earnings(ticker, config)
            if e and e.get("days_until") is not None:
                days = int(e["days_until"])
                if 0 <= days <= days_ahead:
                    items.append({
                        "ticker": ticker,
                        "earnings_date": e.get("date"),
                        "days_until": days,
                        "portfolio_pct": round(pct, 1),
                    })
                    total_at_risk_pct += pct
        except Exception:
            pass

    items.sort(key=lambda x: x.get("days_until", 999))

    return {
        "items": items,
        "total_at_risk_pct": round(total_at_risk_pct, 1),
        "count": len(items),
        "note": (
            f"{len(items)} position{'s' if len(items) != 1 else ''} reporting in {days_ahead} days "
            f"— {total_at_risk_pct:.1f}% of portfolio at event risk"
        ) if items else None,
    }
