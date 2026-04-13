"""
Retail trader value-add: daily briefing, portfolio heat, one-line actions, badges, nudges.
Consumes dashboard data (results, report, horizon_levels, tax, paper_trading) and returns
structured payload for the UI.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

REGIME_PLAIN_ENGLISH = {
    "Risk-On": "Favor small adds on pullbacks. Don't chase; use your levels.",
    "Neutral": "Hold core; skip big new buys until the trend is clearer.",
    "Risk-Off": "Tighten stops, trim size, no new YOLOs. Preserve capital.",
}

# Approx % of portfolio at risk if all stops hit (simplified: risk_per_position = value * stop_pct/100)
def _portfolio_heat_pct(per_holding: list[dict], total_value: float, stop_pct: float) -> float:
    if not total_value or total_value <= 0:
        return 0.0
    risk_sum = 0.0
    for h in per_holding or []:
        v = float(h.get("value") or 0)
        if v > 0:
            risk_sum += v * (stop_pct / 100.0)
    return round(100.0 * risk_sum / total_value, 1)


def _concentration_check(per_holding: list[dict], total_value: float, top_n: int = 3) -> dict:
    """Top positions and a short message if concentrated."""
    if not per_holding or not total_value:
        return {"top_positions": [], "message": None, "concentration_pct": 0.0}
    by_value = sorted(
        [h for h in per_holding if (h.get("value") or 0) > 0],
        key=lambda x: -(float(x.get("value") or 0)),
    )[:top_n]
    top_pct = sum(float(h.get("value") or 0) for h in by_value) / total_value * 100.0
    msg = None
    if top_pct > 50:
        msg = f"Top {top_n} positions are {top_pct:.0f}% of portfolio. Consider trimming if any thesis weakens."
    return {
        "top_positions": [{"ticker": h.get("ticker"), "pct": round(100 * float(h.get("value") or 0) / total_value, 1)} for h in by_value],
        "message": msg,
        "concentration_pct": round(top_pct, 1),
    }


def _regime_plain_english(macro_regime: str) -> str:
    return REGIME_PLAIN_ENGLISH.get(macro_regime) or REGIME_PLAIN_ENGLISH.get("Neutral")


def _in_entry_zone(price: float, entry_low: float, entry_high: float) -> bool:
    if entry_low is None or entry_high is None:
        return False
    return entry_low <= price <= entry_high


def _stops_near(price: float, stop_loss: float, pct_near: float = 2.0) -> bool:
    if stop_loss is None or stop_loss <= 0 or price <= 0:
        return False
    return price <= stop_loss * (1 + pct_near / 100.0)


def _target_hit(price: float, target: float) -> bool:
    if target is None or target <= 0:
        return False
    return price >= target


def _earnings_days_from_note(earnings_note: str | None) -> int | None:
    if not earnings_note:
        return None
    m = re.search(r"Earnings in (\d+) days", earnings_note)
    return int(m.group(1)) if m else None


def _one_liner(
    ticker: str,
    price: float,
    score: float | None,
    regime: str | None,
    entry_low: float | None,
    entry_high: float | None,
    stop_loss: float | None,
    target: float | None,
    earnings_note: str | None,
    is_holding: bool,
) -> str:
    """Single sentence: what to do and levels."""
    parts = []
    if is_holding:
        if stop_loss is not None and price > 0 and stop_loss > 0 and price <= stop_loss * 1.02:
            parts.append(f"Stop near ${stop_loss:.2f}. Decide: hold or trim.")
        elif target is not None and price >= target * 0.98:
            parts.append(f"Target ${target:.2f} reached. Consider trimming partial.")
        elif earnings_note:
            parts.append(f"{earnings_note}. Reduce size or wait for reaction.")
        elif score is not None and score < 35:
            parts.append(f"Score {score:.0f}. Consider trim on strength.")
        else:
            parts.append("Hold. No action needed.")
    else:
        if entry_low is not None and entry_high is not None and _in_entry_zone(price, entry_low, entry_high):
            parts.append(f"In entry zone ${entry_low:.2f}–${entry_high:.2f}. Add small.")
        elif entry_low is not None and entry_high is not None and price > entry_high:
            parts.append(f"Wait for pullback to ${entry_low:.2f}–${entry_high:.2f}.")
        elif score is not None and score >= 65:
            parts.append(f"Score {score:.0f}. Consider small add on pullback.")
        else:
            parts.append("Watch. No clear entry.")
    if stop_loss is not None and is_holding and "Stop" not in (parts[0] if parts else ""):
        parts.append(f"Stop below ${stop_loss:.2f}.")
    return " ".join(parts) if parts else "No action."


def _action_badge(
    ticker: str,
    price: float,
    score: float | None,
    entry_low: float | None,
    entry_high: float | None,
    stop_loss: float | None,
    target: float | None,
    earnings_days: int | None,
    is_holding: bool,
) -> str:
    """BUY | WAIT | TRIM | HOLD."""
    if is_holding:
        if stop_loss is not None and price > 0 and price <= stop_loss * 1.02:
            return "TRIM"
        if target is not None and price >= target * 0.98:
            return "TRIM"
        if earnings_days is not None and earnings_days <= 3:
            return "TRIM"
        if score is not None and score < 35:
            return "TRIM"
        return "HOLD"
    if entry_low is not None and entry_high is not None and _in_entry_zone(price, entry_low, entry_high):
        return "BUY"
    if score is not None and score >= 65:
        return "WAIT"
    return "WAIT"


def _plan_action_to_retail_badge(plan: str | None) -> str | None:
    """
    Map 7-layer confidence action (run_confidence) to the same BUY | WAIT | TRIM | HOLD
    chips as the rest of retail — keeps the signals row aligned with Roadmaps / ticker detail.
    """
    if not plan or not isinstance(plan, str):
        return None
    u = plan.upper().strip()
    if u == "INCOMPATIBLE":
        return "WAIT"
    if "STRONG BUY" in u or u == "BUY":
        return "BUY"
    if "BUY" in u and "WATCH" not in u:
        return "BUY"
    if "AVOID" in u:
        return "WAIT"
    if "REDUCE" in u:
        return "TRIM"
    if "HOLD" in u or "WATCH" in u:
        return "HOLD"
    return None


def build_retail_briefing(
    *,
    results: list[dict],
    report: dict,
    data_root: Path | None,
    opportunities: list[dict],
    tax_aware_exits: dict,
    earnings_risk_count: int,
    macro_regime: str,
    risk_pct: float,
    stop_pct: float,
    paper_trading: dict | None,
    thesis_check: list[dict],
    config: dict | None,
    plan_actions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Build daily briefing, portfolio heat, concentration, regime sentence,
    per-ticker actions and one-liners. Horizon levels (entry/stop/target) loaded from data_root when present.
    """
    config = config or {}
    per_holding = report.get("per_holding") or []
    total_value = float(report.get("total_value") or 0)
    results_by_ticker = {r["ticker"]: r for r in results if not r.get("error")}
    portfolio_tickers = {h.get("ticker") if isinstance(h, dict) else h for h in per_holding if (h.get("ticker") if isinstance(h, dict) else h)}

    horizon_levels = {}
    if data_root:
        try:
            from scanner.horizon_levels import read_horizon_levels
            horizon_levels = read_horizon_levels(data_root)
        except Exception:
            pass

    heat_pct = _portfolio_heat_pct(per_holding, total_value, stop_pct)
    concentration = _concentration_check(per_holding, total_value)
    regime_sentence = _regime_plain_english(macro_regime)

    in_entry_zone: list[dict] = []
    earnings_soon: list[dict] = []
    stops_near: list[dict] = []
    targets_hit: list[dict] = []
    suggested_actions: list[dict] = []

    for r in results:
        ticker = r.get("ticker")
        if not ticker or r.get("error"):
            continue
        price = float(r.get("close") or r.get("price") or 0)
        if price <= 0:
            continue
        levels = horizon_levels.get(ticker.upper(), {})
        el = levels.get("entry_low")
        eh = levels.get("entry_high")
        stop = levels.get("stop_loss")
        tgt = levels.get("target")
        score = r.get("composite_buy")
        earnings_note = r.get("earnings_note")
        er_days = _earnings_days_from_note(earnings_note)
        is_holding = ticker in portfolio_tickers

        if is_holding and stop is not None and _stops_near(price, stop):
            stops_near.append({"ticker": ticker, "price": price, "stop_loss": stop})
        if is_holding and tgt is not None and _target_hit(price, tgt):
            targets_hit.append({"ticker": ticker, "price": price, "target": tgt})
        if not is_holding and el is not None and eh is not None and _in_entry_zone(price, el, eh):
            in_entry_zone.append({"ticker": ticker, "price": price, "entry_low": el, "entry_high": eh})
        if er_days is not None and er_days <= 7 and ticker in portfolio_tickers:
            earnings_soon.append({"ticker": ticker, "days": er_days})

    priority_actions = []
    for x in stops_near:
        priority_actions.append({"ticker": x["ticker"], "action": "TRIM", "reason": f"Stop ${x['stop_loss']:.2f} within 2% of price."})
    for x in earnings_soon:
        if x["ticker"] not in [a["ticker"] for a in priority_actions]:
            priority_actions.append({"ticker": x["ticker"], "action": "TRIM", "reason": f"Earnings in {x['days']} days. Reduce or wait."})
    for x in in_entry_zone[:5]:
        priority_actions.append({"ticker": x["ticker"], "action": "BUY", "reason": f"In entry zone ${x['entry_low']:.2f}–${x['entry_high']:.2f}."})
    for x in targets_hit[:5]:
        if x["ticker"] not in [a["ticker"] for a in priority_actions]:
            priority_actions.append({"ticker": x["ticker"], "action": "TRIM", "reason": f"Target ${x['target']:.2f} reached."})
    suggested_actions = priority_actions[:10]

    summary_parts = []
    if stops_near:
        summary_parts.append(f"{len(stops_near)} near stop")
    if earnings_soon:
        summary_parts.append(f"{len(earnings_soon)} earnings soon")
    if in_entry_zone:
        summary_parts.append(f"{len(in_entry_zone)} in entry zone")
    if targets_hit:
        summary_parts.append(f"{len(targets_hit)} at target")
    summary_sentence = "Today: " + "; ".join(summary_parts) if summary_parts else "No urgent actions. " + regime_sentence

    ticker_actions: dict[str, dict] = {}
    for r in results:
        ticker = r.get("ticker")
        if not ticker or r.get("error"):
            continue
        price = float(r.get("close") or r.get("price") or 0)
        levels = horizon_levels.get(ticker.upper(), {})
        one = _one_liner(
            ticker,
            price,
            r.get("composite_buy"),
            r.get("regime"),
            levels.get("entry_low"),
            levels.get("entry_high"),
            levels.get("stop_loss"),
            levels.get("target"),
            r.get("earnings_note"),
            ticker in portfolio_tickers,
        )
        badge = _action_badge(
            ticker,
            price,
            r.get("composite_buy"),
            levels.get("entry_low"),
            levels.get("entry_high"),
            levels.get("stop_loss"),
            levels.get("target"),
            _earnings_days_from_note(r.get("earnings_note")),
            ticker in portfolio_tickers,
        )
        if plan_actions:
            pb = _plan_action_to_retail_badge(plan_actions.get(ticker))
            if pb:
                badge = pb
        ticker_actions[ticker] = {"action": badge, "one_liner": one}

    tax_approaching: list[dict] = []
    for item in (tax_aware_exits.get("items") or []):
        to_ltcg = item.get("days_to_ltcg")
        if to_ltcg is not None and 0 <= to_ltcg <= 90:
            tax_approaching.append({"ticker": item.get("ticker"), "days_to_ltcg": to_ltcg})

    win_loss: dict | None = None
    if paper_trading and isinstance(paper_trading.get("summary"), dict):
        s = paper_trading["summary"]
        completed = s.get("completed")
        win_loss = {
            "total_trades": completed,
            "wins": None,
            "losses": None,
            "win_rate_pct": s.get("win_rate_pct"),
            "net_pnl_pct": s.get("avg_return_pct"),
        }
        if completed is not None and s.get("win_rate_pct") is not None:
            w = round(completed * (s["win_rate_pct"] / 100.0))
            win_loss["wins"] = w
            win_loss["losses"] = completed - w

    overtrading_nudge: str | None = None
    if paper_trading and isinstance(paper_trading.get("recent"), list):
        recent = paper_trading["recent"]
        last_7 = [t for t in recent if t.get("open_date") or t.get("entry_date")][:20]
        if len(last_7) >= 10:
            overtrading_nudge = f"You have {len(last_7)} recent paper trades. Consider pausing new trades and reviewing stops."

    sector_gap: str | None = None
    sectors = {}
    for h in per_holding:
        s = (h.get("sector") or "Unknown").strip() or "Unknown"
        sectors[s] = sectors.get(s, 0) + 1
    if sectors and len(sectors) <= 2 and total_value > 0:
        sector_gap = "Portfolio is concentrated in few sectors. Consider 5–10% in a defensive sector (e.g. XLP) for diversification."

    drawdown_guard: str | None = None
    if heat_pct > 15:
        drawdown_guard = f"Portfolio heat is {heat_pct}%. If market drops, consider reducing size or tightening stops."

    return {
        "daily_briefing": {
            "summary_sentence": summary_sentence,
            "regime_plain_english": regime_sentence,
            "in_entry_zone": in_entry_zone,
            "earnings_soon": earnings_soon,
            "stops_near": stops_near,
            "targets_hit": targets_hit,
            "suggested_actions": suggested_actions,
            "earnings_risk_count": earnings_risk_count,
            "tax_approaching_ltcg": tax_approaching,
        },
        "portfolio_heat_pct": heat_pct,
        "concentration": concentration,
        "regime_plain_english": regime_sentence,
        "ticker_actions": ticker_actions,
        "tax_approaching_ltcg": tax_approaching,
        "win_loss_recap": win_loss,
        "overtrading_nudge": overtrading_nudge,
        "sector_gap": sector_gap,
        "drawdown_guard": drawdown_guard,
    }
