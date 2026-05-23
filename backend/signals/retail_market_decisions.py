"""
Retail market decisions — answers the five real trader questions using existing signals.

Institutional inputs → retail IF/THEN copy. No new data vendors required for P0.
"""
from __future__ import annotations

from typing import Any

# Maps internal actions to 3×3 matrix columns
_ACTION_BUY = "BUY"
_ACTION_HOLD = "HOLD"
_ACTION_REDUCE = "REDUCE"


def _matrix_action(score: float | None, regime: str | None, *, cautious: bool = False) -> str:
    """Map confluence/regime to BUY | HOLD | REDUCE."""
    r = (regime or "").upper()
    s = score if score is not None else 50.0
    if cautious or r == "DOWN" or "RISK-OFF" in r or "BEAR" in r:
        return _ACTION_REDUCE if s < 45 else _ACTION_HOLD
    if s >= 65 and r in ("UP", "RISK-ON", "BULL"):
        return _ACTION_BUY
    if s <= 35:
        return _ACTION_REDUCE
    return _ACTION_HOLD


def _market_temperature(
    vix: float | None,
    macro_regime: str | None,
    macro_bundle: dict | None,
) -> dict[str, Any]:
    """Cold / Warm / Hot from VIX + macro — single contextual dial."""
    vx = vix
    if vx is None and macro_bundle:
        factors = macro_bundle.get("factors") or {}
        vx = factors.get("vix")
    label = "WARM"
    level = "warm"
    if vx is not None:
        if vx >= 28:
            label, level = "COLD", "cold"
        elif vx >= 22:
            label, level = "COOL", "cool"
        elif vx <= 13:
            label, level = "HOT", "hot"
        elif vx <= 16:
            label, level = "WARM-HOT", "warm_hot"
    mr = (macro_regime or "").lower()
    if "risk-off" in mr or "bear" in mr:
        label, level = "COLD", "cold"
    elif "risk-on" in mr and vx is not None and vx < 18:
        label, level = "WARM-HOT", "warm_hot"

    if level in ("cold", "cool"):
        interp = (
            "Fear elevated — better entry zone forming for patient buyers. "
            "Don't panic sell core holdings; add only with tight risk."
        )
    elif level in ("hot", "warm_hot"):
        interp = (
            "Not the best time to chase new positions aggressively. "
            "Hold winners, trim extended names, wait for pullbacks to add."
        )
    else:
        interp = (
            "Normal conditions — stock picking matters. "
            "Hold core, add selectively on pullbacks, avoid FOMO entries."
        )

    drivers: list[str] = []
    if vx is not None:
        drivers.append(f"VIX {vx:.1f}")
    if macro_regime:
        drivers.append(f"Macro {macro_regime}")
    hy = (macro_bundle or {}).get("factors", {}).get("hy_oas_bp")
    if hy is not None:
        bp_pct = hy / 100 if hy > 20 else hy
        drivers.append(f"HY spread {bp_pct:.1f}%")

    return {
        "level": level,
        "label": label,
        "vix": vx,
        "drivers": drivers,
        "interpretation": interp,
        "buy_zone": level in ("cold", "cool"),
        "reduce_zone": level in ("hot", "warm_hot"),
    }


def _breadth_check(market_regime: dict | None) -> dict[str, Any]:
    mr = market_regime or {}
    breadth = mr.get("market_breadth") or "Neutral"
    narrow = mr.get("participation_narrow")
    tech = mr.get("tech_leadership") or "Flat"
    rotation = mr.get("rotation_risk") or "Medium"

    if breadth == "Strong" and narrow is not True:
        signal = "HEALTHY"
        plain = (
            "Broad participation — rally not just a handful of mega-caps. "
            "Moves tend to be more sustainable when equal-weight keeps up."
        )
    elif narrow is True or breadth == "Weak":
        signal = "NARROW"
        plain = (
            "Index may rise while many stocks lag — explains portfolios not keeping up with SPY. "
            "If SPY keeps climbing but breadth stays weak, reduce chase exposure."
        )
    else:
        signal = "MIXED"
        plain = "Mixed participation — be selective; index-level strength may not lift all holdings."

    watch = None
    if narrow is True and tech == "Rising":
        watch = "SPY up but equal-weight lagging — narrowing rally; trim extended tech if rotation risk rises."

    return {
        "signal": signal,
        "market_breadth": breadth,
        "tech_leadership": tech,
        "rotation_risk": rotation,
        "participation_narrow": narrow,
        "plain_english": plain,
        "watch": watch,
    }


def _credit_pulse(macro_bundle: dict | None) -> dict[str, Any]:
    factors = (macro_bundle or {}).get("factors") or {}
    hy = factors.get("hy_oas_bp")
    yc = factors.get("yield_curve_2s10s")
    if hy is None:
        return {
            "signal": "UNKNOWN",
            "plain_english": "Credit spread data unavailable — treat macro caution as unconfirmed.",
        }
    bp = float(hy) / 100 if float(hy) > 20 else float(hy)
    if bp >= 7:
        signal, plain = "DANGER", "Stress in corporate bonds — recession risk elevated; reduce risk assets."
    elif bp >= 5:
        signal, plain = "WARNING", "Spreads widening — companies borrowing harder; tighten stops and avoid new leverage."
    elif bp >= 4:
        signal, plain = "CAUTION", "Spreads elevated but not crisis — stay invested, don't add aggressively."
    else:
        signal, plain = (
            "HEALTHY",
            "Corporate bond market calm — companies can borrow easily. Green light for stocks generally.",
        )
    yc_note = None
    if yc is not None:
        if yc < 0:
            yc_note = "Yield curve inverted — recession watch; favor quality and shorter duration risk."
        elif yc > 0.3:
            yc_note = "Yield curve normal/steepening — recession not imminent in bond market's read."
    return {
        "signal": signal,
        "hy_spread_pct": round(bp, 2),
        "yield_curve_2s10s": yc,
        "plain_english": plain,
        "yield_curve_note": yc_note,
    }


def _strategy_matrix(
    temperature: dict,
    breadth: dict,
    credit: dict,
    macro_regime: str | None,
    avg_score: float | None,
    catalysts: dict | None,
) -> dict[str, Any]:
    cautious_st = temperature.get("reduce_zone") or credit.get("signal") in ("WARNING", "DANGER")
    scheduled = (catalysts or {}).get("scheduled_today") or []
    has_macro_today = len(scheduled) > 0

    st_action = _ACTION_HOLD if cautious_st or has_macro_today else _matrix_action(avg_score, macro_regime)
    if has_macro_today and st_action == _ACTION_BUY:
        st_action = _ACTION_HOLD

    mt_action = _matrix_action(avg_score, macro_regime)
    if credit.get("signal") == "HEALTHY" and breadth.get("signal") == "HEALTHY":
        if mt_action == _ACTION_HOLD:
            mt_action = _ACTION_BUY if (avg_score or 0) >= 55 else _ACTION_HOLD
    if credit.get("signal") in ("WARNING", "DANGER"):
        mt_action = _ACTION_REDUCE if mt_action == _ACTION_BUY else _ACTION_HOLD

    lt_action = _ACTION_HOLD
    if credit.get("signal") == "HEALTHY" and (macro_regime or "").lower() in ("risk-on", "neutral", ""):
        lt_action = _ACTION_BUY
    if credit.get("signal") == "DANGER":
        lt_action = _ACTION_REDUCE

    st_bullets = []
    if has_macro_today:
        ev = scheduled[0]
        st_bullets.append(f"Macro today ({ev.get('event_type', 'release')}) — wait for reaction before new entries.")
    if cautious_st:
        st_bullets.append("Market warm/hot — no aggressive adds; keep stops tight on recent entries.")
    else:
        st_bullets.append("Can add small on pullbacks if your ticker is in entry zone.")
    st_bullets.append("Trim any single position with >10% unrealized gain before earnings this week.")

    mt_bullets = [
        "Hold core positions; add on 3–5% pullbacks in quality names you already trust.",
        f"Breadth: {breadth.get('signal', '—')} — "
        + ("broad rally" if breadth.get("signal") == "HEALTHY" else "be selective"),
    ]
    if credit.get("signal") == "HEALTHY":
        mt_bullets.append("Credit markets calm — medium-term trend intact unless spreads spike.")

    lt_bullets = [
        "Stay invested in core index allocation; don't reduce on short-term volatility alone.",
        "Add monthly if that's your plan — ignore daily noise.",
        "Rebalance if any single position exceeds your max weight (e.g. 8–10%).",
    ]
    lt_breakers = [
        {"label": "Credit spreads >6%", "triggered": (credit.get("hy_spread_pct") or 0) >= 6},
        {"label": "Earnings growth turns negative", "triggered": False},
        {"label": "Fed pivots to hiking again", "triggered": False},
    ]

    return {
        "short_term": {
            "horizon": "days–weeks",
            "stance": "CAUTIOUS" if st_action != _ACTION_BUY else "SELECTIVE",
            "action": st_action,
            "bullets": st_bullets[:4],
        },
        "medium_term": {
            "horizon": "weeks–months",
            "stance": "CONSTRUCTIVE" if mt_action == _ACTION_BUY else ("DEFENSIVE" if mt_action == _ACTION_REDUCE else "NEUTRAL"),
            "action": mt_action,
            "bullets": mt_bullets[:4],
        },
        "long_term": {
            "horizon": "months–years",
            "stance": "BULLISH" if lt_action == _ACTION_BUY else ("CAUTIOUS" if lt_action == _ACTION_REDUCE else "HOLD CORE"),
            "action": lt_action,
            "bullets": lt_bullets[:4],
            "thesis_breakers": lt_breakers,
        },
        "grid": {
            "short": st_action,
            "medium": mt_action,
            "long": lt_action,
        },
    }


def _if_then_scenarios(catalysts: dict | None, flip_stats: dict | None = None) -> list[dict[str, Any]]:
    """Conditional clarity around today's key catalyst — institutional morning playbook."""
    scheduled = (catalysts or {}).get("scheduled_today") or []
    if not scheduled:
        return [{
            "condition": "No major US macro release today",
            "impact": "Tape-driven session — watch SPY support/resistance and sector rotation.",
            "action": "Follow ST/MT matrix; no binary event to wait for.",
            "probability_pct": None,
        }]

    ev = scheduled[0]
    et = ev.get("event_type") or "Macro"
    gf = None
    scenario = ev.get("scenario") or {}
    if scenario.get("pct_gap_fade") is not None:
        gf = scenario["pct_gap_fade"]
    elif flip_stats:
        st = (flip_stats.get("events") or {}).get(et)
        if isinstance(st, dict):
            gf = st.get("pct_gap_fade")

    scenarios: list[dict[str, Any]] = []
    if et == "CPI":
        scenarios = [
            {
                "condition": "CPI cooler than expected (< ~2.4% YoY core)",
                "impact": "QQQ likely +0.8–1.5%; rate-cut hopes rise",
                "action": "Can add small growth positions after first hour stabilizes",
                "probability_pct": 30,
            },
            {
                "condition": "CPI in-line (~2.4–2.8%)",
                "impact": "Muted reaction — chop around open",
                "action": "Stay flat until direction clears; no new size before 10am ET",
                "probability_pct": 45,
            },
            {
                "condition": "CPI hot (> ~2.8%)",
                "impact": "QQQ likely -1 to -2%; yields up, multiples compress",
                "action": "Do not add; wait for support test — trim extended tech if breaks",
                "probability_pct": 25,
            },
        ]
    elif et == "NFP":
        scenarios = [
            {
                "condition": "Weak jobs + soft wages",
                "impact": "Rate-cut bid — growth rallies, yields fall",
                "action": "Can add on confirmation after 10am ET",
                "probability_pct": 25,
            },
            {
                "condition": "In-line report",
                "impact": "Limited surprise — range session",
                "action": "Hold plan; no hero trades into the number",
                "probability_pct": 50,
            },
            {
                "condition": "Strong jobs + hot wages",
                "impact": "Higher-for-longer fear — pressure on multiples",
                "action": "Reduce new buys; tighten stops on recent entries",
                "probability_pct": 25,
            },
        ]
    elif et == "FOMC":
        scenarios = [
            {
                "condition": "Dovish hold / cut hint",
                "impact": "Yields drop — risk-on continuation",
                "action": "Hold growth; add on dips if breadth healthy",
                "probability_pct": 35,
            },
            {
                "condition": "Neutral hold",
                "impact": "Limited move — focus on dots language",
                "action": "Wait for press conference before sizing up",
                "probability_pct": 40,
            },
            {
                "condition": "Hawkish surprise",
                "impact": "Yields spike — growth sells",
                "action": "Trim extended positions; no new leverage",
                "probability_pct": 25,
            },
        ]
    else:
        scenarios = [{
            "condition": f"{ev.get('name', et)} release",
            "impact": "Volatility around headline vs consensus",
            "action": "Stay flat until after release; use ST matrix",
            "probability_pct": None,
        }]

    if gf is not None:
        for s in scenarios:
            s["gap_fade_note"] = f"Historically gap faded {gf}% on past {et} days — don't chase opening spike blindly."
    return scenarios


def _five_questions(
    temperature: dict,
    matrix: dict,
    breadth: dict,
    credit: dict,
    portfolio_risk: dict | None,
    catalysts: dict | None,
) -> list[dict[str, str]]:
    st = matrix.get("short_term", {})
    mt = matrix.get("medium_term", {})
    scheduled = (catalysts or {}).get("scheduled_today") or []

    buy_answer = "Not aggressively this week." if st.get("action") != _ACTION_BUY else "Selectively — small adds on pullbacks only."
    if scheduled:
        buy_answer = f"Wait until after today's {scheduled[0].get('event_type', 'macro')} release, then reassess."

    sell_answer = "No blanket sell." if st.get("action") != _ACTION_REDUCE else "Trim extended names and tighten stops."
    if portfolio_risk and (portfolio_risk.get("score") or 10) >= 7:
        sell_answer = "Consider trimming ahead of earnings on your largest positions."

    crash_answer = "No crash signal — credit and breadth not in danger zone."
    if credit.get("signal") in ("WARNING", "DANGER"):
        crash_answer = "Credit stress rising — not a crash call, but reduce risk and raise cash slowly."
    elif temperature.get("level") == "cold" and temperature.get("vix") and temperature["vix"] >= 28:
        crash_answer = "High fear (VIX elevated) — volatility spike possible, but often marks better entries for long-term holders."

    holdings_answer = "Mixed — check your Portfolio tab for weak scores and concentration."
    if breadth.get("signal") == "NARROW":
        holdings_answer = "You may be in the right sectors but breadth is narrow — mega-cap leaders vs rest; review if you're overweight lagging names."

    hold_answer = "Short term: days–weeks (trade the setup). Medium: months (core thesis). Long: years (ignore daily noise)."
    if mt.get("action") == _ACTION_BUY:
        hold_answer = "Core positions: months to years. Tactical adds: days to weeks with stops."

    return [
        {"question": "Should I buy more this week?", "answer": buy_answer},
        {"question": "Should I sell anything?", "answer": sell_answer},
        {"question": "Is the market about to crash?", "answer": crash_answer},
        {"question": "Am I in the right stuff?", "answer": holdings_answer},
        {"question": "How long should I hold this?", "answer": hold_answer},
    ]


def _portfolio_risk_block(
    portfolio_doctor: dict | None,
    retail_briefing: dict | None,
    per_holding: list[dict] | None,
) -> dict[str, Any] | None:
    pd = portfolio_doctor or {}
    health = pd.get("health") or {}
    score = health.get("score")
    if score is None:
        rb = retail_briefing or {}
        heat = rb.get("portfolio_heat_pct")
        if heat is None:
            return None
        score = min(10.0, max(1.0, heat / 2.5))

    score_f = float(score)
    if score_f > 10:
        score_f = score_f / 10.0

    adjustments: list[str] = []
    earnings = pd.get("earnings_calendar") or {}
    for item in (earnings.get("items") or [])[:3]:
        t = item.get("ticker")
        d = item.get("days_until")
        if t and d is not None and d <= 5:
            adjustments.append(f"{t} reports in {d}d — consider trimming 15–20% before close prior day.")

    conc = (retail_briefing or {}).get("concentration") or {}
    if (conc.get("concentration_pct") or 0) > 50:
        adjustments.append("Top 3 holdings >50% — add diversifier or trim largest if thesis weakens.")

    sub = health.get("sub_scores") or {}
    if sub.get("concentration", 100) < 50:
        adjustments.append("Concentration score low — spread risk across sectors.")

    return {
        "score": round(score_f, 1),
        "score_scale": "1-10 (higher = more risk)",
        "trend": health.get("biggest_drag"),
        "adjustments": adjustments[:5],
        "do_nothing_if": [
            "You're a long-term investor with target allocation intact",
            "You can handle -20% without panic selling",
        ],
    }


def build_retail_market_decisions(
    *,
    macro_regime: str | None = None,
    macro_regime_bundle: dict | None = None,
    market_regime: dict | None = None,
    market_catalysts: dict | None = None,
    portfolio_doctor_v2: dict | None = None,
    retail_briefing: dict | None = None,
    per_holding: list[dict] | None = None,
    avg_portfolio_score: float | None = None,
    flip_stats: dict | None = None,
) -> dict[str, Any]:
    """
    Single retail decision payload: temperature, 3×3 matrix, IF/THEN, five questions.
    """
    vix = None
    if macro_regime_bundle:
        vix = (macro_regime_bundle.get("factors") or {}).get("vix")

    temperature = _market_temperature(vix, macro_regime, macro_regime_bundle)
    breadth = _breadth_check(market_regime)
    credit = _credit_pulse(macro_regime_bundle)
    matrix = _strategy_matrix(
        temperature, breadth, credit, macro_regime, avg_portfolio_score, market_catalysts
    )
    scenarios = _if_then_scenarios(market_catalysts, flip_stats)
    portfolio_risk = _portfolio_risk_block(portfolio_doctor_v2, retail_briefing, per_holding)
    questions = _five_questions(temperature, matrix, breadth, credit, portfolio_risk, market_catalysts)

    return {
        "five_questions": questions,
        "market_temperature": temperature,
        "strategy_matrix": matrix,
        "if_then_scenarios": scenarios,
        "breadth_check": breadth,
        "credit_pulse": credit,
        "portfolio_risk": portfolio_risk,
        "disclaimer": "Decision support only — conditional guidance, not a guarantee. Confirm with your plan.",
    }
