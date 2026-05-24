"""
Per-ticker market context — maps global retail decisions to a single name.

Used in ticker detail Overview tab (compact card, not full dashboard panel).
"""
from __future__ import annotations

from typing import Any

_TECH_SECTORS = frozenset(
    {"technology", "communication services", "information technology"}
)
_RATE_SENSITIVE = frozenset({"financials", "real estate", "utilities", "financial services"})
_ENERGY = frozenset({"energy"})


def _is_tech(sector: str | None) -> bool:
    return (sector or "").lower() in _TECH_SECTORS or "tech" in (sector or "").lower()


def _benchmark_for_ticker(sector: str | None) -> str:
    return "QQQ" if _is_tech(sector) else "SPY"


def _ticker_horizon_overlay(
    *,
    score: float | None,
    regime: str | None,
    market_decisions: dict | None,
    sector: str | None,
    rotation: dict | None,
) -> dict[str, Any]:
    matrix = (market_decisions or {}).get("strategy_matrix") or {}
    grid = matrix.get("grid") or {}
    base_st = grid.get("short") or "HOLD"
    base_mt = grid.get("medium") or "HOLD"
    base_lt = grid.get("long") or "HOLD"

    s = score if score is not None else 50.0
    r = (regime or "").upper()

    def _nudge(action: str, down: bool = False) -> str:
        order = ["REDUCE", "HOLD", "BUY"]
        try:
            i = order.index(action)
        except ValueError:
            i = 1
        if down:
            return order[max(0, i - 1)]
        if s >= 68 and r in ("UP", "RISK-ON") and action == "HOLD":
            return "BUY"
        if s <= 32 or r == "DOWN":
            return "REDUCE" if action != "REDUCE" else "REDUCE"
        return action

    st = _nudge(base_st, down=_is_tech(sector) and (rotation or {}).get("tech_leadership") == "Falling")
    mt = _nudge(base_mt)
    lt = _nudge(base_lt, down=r == "DOWN")

    bullets: dict[str, str] = {}
    if s >= 65:
        bullets["short"] = "Score supports tactical adds on pullbacks if market matrix allows."
    elif s <= 35:
        bullets["short"] = "Weak score — align with REDUCE/HOLD; don't fight tape on this name."
    else:
        bullets["short"] = "Mixed score — wait for entry zone or catalyst before sizing up."

    if _is_tech(sector):
        bullets["medium"] = "Tech name — CPI/NFP and QQQ triggers matter for multiples."
    else:
        bullets["medium"] = "Follow sector rotation: add if your sector is leading vs SPY."

    bullets["long"] = "Core thesis unchanged unless credit pulse or earnings break the story."

    return {
        "short": {"action": st, "note": bullets["short"]},
        "medium": {"action": mt, "note": bullets["medium"]},
        "long": {"action": lt, "note": bullets["long"]},
    }


def _earnings_rule(ticker: str, earnings: dict | None, is_holding: bool) -> dict[str, Any] | None:
    if not earnings:
        return None
    days = earnings.get("days_until")
    if days is None:
        return None
    try:
        d = int(days)
    except (TypeError, ValueError):
        return None
    if d < 0:
        return {
            "days_until": d,
            "rule": f"{ticker} recently reported — wait for guidance reaction before adding size.",
            "urgency": "post_report",
        }
    if d <= 1:
        return {
            "days_until": d,
            "rule": (
                f"{ticker} reports {'today' if d == 0 else 'tomorrow'} — "
                + ("trim 15–20% before close if holding; no new buys." if is_holding else "avoid new entries until after print.")
            ),
            "urgency": "high",
        }
    if d <= 5:
        return {
            "days_until": d,
            "rule": f"{ticker} reports in {d}d — reduce size into event if holding; tighten stops.",
            "urgency": "medium",
        }
    return None


def _macro_watch(
    sector: str | None,
    market_decisions: dict | None,
) -> list[dict[str, str]]:
    scenarios = (market_decisions or {}).get("if_then_scenarios") or []
    if not scenarios:
        return []
    out: list[dict[str, str]] = []
    for s in scenarios[:3]:
        cond = s.get("condition") or ""
        if "No major" in cond:
            if _is_tech(sector):
                out.append({
                    "condition": "No macro today",
                    "impact": "Tape + sector RS drive this name more than headlines.",
                    "action": s.get("action") or "Follow entry zone and score.",
                })
            continue
        et = cond.upper()
        relevant = False
        if _is_tech(sector) and any(x in et for x in ("CPI", "NFP", "FOMC", "QQQ")):
            relevant = True
        if (sector or "").lower() in _RATE_SENSITIVE and any(x in et for x in ("CPI", "FOMC", "YIELD")):
            relevant = True
        if (sector or "").lower() in _ENERGY and "CPI" in et:
            relevant = True
        if relevant or len(out) == 0:
            out.append({
                "condition": cond,
                "impact": s.get("impact") or "",
                "action": s.get("action") or "",
            })
        if len(out) >= 2:
            break
    return out


def _sector_note(sector: str | None, rotation: dict | None) -> str | None:
    if not rotation or not sector:
        return None
    sec_lower = sector.lower()
    for s in rotation.get("leading") or []:
        if sec_lower in (s.get("name") or "").lower():
            return f"{sector} is leading vs SPY — favorable backdrop for holders; don't chase extended entries."
    for s in rotation.get("lagging") or []:
        if sec_lower in (s.get("name") or "").lower():
            return f"{sector} is lagging — need a strong thesis to add; consider smaller size."
    toward = rotation.get("rotate_toward") or []
    away = rotation.get("rotate_away") or []
    for t in toward:
        if t.lower() in sec_lower or sec_lower in t.lower():
            return f"Rotation favors {t} — aligns with this name's sector."
    for t in away:
        if t.lower() in sec_lower or sec_lower in t.lower():
            return f"Rotation away from {t} — headwind for new adds."
    return None


def _headline(
    ticker: str,
    temperature: dict | None,
    horizon: dict,
    earnings_rule: dict | None,
) -> str:
    temp_label = (temperature or {}).get("label") or "WARM"
    st = (horizon.get("short") or {}).get("action") or "HOLD"
    parts = [f"{ticker}: ST {st} in a {temp_label} market."]
    if earnings_rule and earnings_rule.get("urgency") in ("high", "medium"):
        parts.append(earnings_rule["rule"])
    elif (temperature or {}).get("reduce_zone"):
        parts.append("Market hot — prefer pullbacks over chasing.")
    elif (temperature or {}).get("buy_zone"):
        parts.append("Fear elevated — patient entries OK if score supports.")
    return " ".join(parts)


def build_ticker_market_context(
    ticker: str,
    *,
    sector: str | None = None,
    score: float | None = None,
    regime: str | None = None,
    rsi: float | None = None,
    earnings: dict | None = None,
    is_holding: bool = False,
    market_decisions: dict | None = None,
    investor_summary: dict | None = None,
) -> dict[str, Any]:
    """
    Compact per-ticker overlay from global retail_market_decisions + local signal.
    """
    md = market_decisions or {}
    temperature = md.get("market_temperature")
    rotation = md.get("sector_rotation")
    triggers = md.get("trigger_levels") or {}
    levels = triggers.get("levels") or {}

    bench = _benchmark_for_ticker(sector)
    bench_levels = levels.get(bench) or levels.get("SPY") or {}
    trigger_watch = None
    if bench_levels.get("primary_trigger"):
        trig = bench_levels["primary_trigger"]
        trigger_watch = {
            "benchmark": bench,
            "trigger_price": trig,
            "rule": (
                f"If {bench} breaks ${trig:.2f}, tighten risk on {ticker} "
                + ("(tech beta)" if bench == "QQQ" else "(broad market beta)")
            ),
        }

    horizon = _ticker_horizon_overlay(
        score=score,
        regime=regime,
        market_decisions=md,
        sector=sector,
        rotation=rotation,
    )
    earnings_rule = _earnings_rule(ticker, earnings, is_holding)
    macro_watch = _macro_watch(sector, md)
    sector_note = _sector_note(sector, rotation)

    crowd = md.get("crowd_positioning") or {}
    crowd_note = None
    fg = (crowd.get("fear_greed") or {}).get("score")
    if fg is not None and fg <= 30 and (score or 0) >= 55:
        crowd_note = "Extreme fear + decent score — contrarian add zone if thesis intact."
    elif fg is not None and fg >= 70 and (score or 0) < 50:
        crowd_note = "Greed + weak score — avoid catching falling knife in hot tape."

    personal_q = None
    if earnings_rule and earnings_rule.get("urgency") == "high":
        personal_q = {
            "question": f"Should I hold {ticker} through earnings?",
            "answer": earnings_rule["rule"],
        }
    elif is_holding and (score or 50) <= 35:
        personal_q = {
            "question": f"Should I trim {ticker}?",
            "answer": "Score weak — consider trim aligned with portfolio REDUCE stance.",
        }
    elif not is_holding and (score or 0) >= 65 and (horizon.get("short") or {}).get("action") == "BUY":
        personal_q = {
            "question": f"Should I buy {ticker} this week?",
            "answer": "Score + matrix support selective add — use entry zone, size small if macro event today.",
        }

    inv_verdict = None
    if investor_summary:
        inv_verdict = investor_summary.get("overall_verdict") or (investor_summary.get("one_answer") or {}).get("verdict")

    return {
        "headline": _headline(ticker, temperature, horizon, earnings_rule),
        "market_temperature_label": (temperature or {}).get("label"),
        "horizon_overlay": horizon,
        "earnings_rule": earnings_rule,
        "trigger_watch": trigger_watch,
        "macro_watch": macro_watch,
        "sector_rotation_note": sector_note,
        "crowd_note": crowd_note,
        "personal_question": personal_q,
        "investor_verdict": inv_verdict,
        "score": score,
        "regime": regime,
        "rsi": rsi,
        "disclaimer": "Ticker context maps global market read to this name — not a buy/sell order.",
    }
