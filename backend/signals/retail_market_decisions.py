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
_ACTION_WAIT = "WAIT"


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
    # Macro Risk-Off/On is a separate overlay — do NOT force temperature cold/hot from it.
    # Reconciler combines temperature (short-term) with global regime (long-term).
    macro_overlay = None
    if "risk-off" in mr:
        macro_overlay = "Macro overlay: Risk-Off (yields/VIX/credit caution) — see unified context below."
        # Fear overlay on tape — not the same as bear regime (reconciler handles ST/MT/LT actions).
        if level in ("warm", "warm_hot") and vx is not None and vx < 22:
            label, level = "COOL", "cool"
            interp = (
                "Short-term fear/caution (macro Risk-Off) while longer-term bull regime may stay intact. "
                "Often a better dip-buying zone — see unified market context above."
            )
    elif "risk-on" in mr:
        macro_overlay = "Macro overlay: Risk-On — tailwind for risk assets if regime agrees."

    if level in ("cold", "cool"):
        interp = (
            "Fear elevated — better entry zone forming for patient buyers. "
            "Don't panic sell core holdings; add only with tight risk."
        )
    elif level in ("hot", "warm_hot"):
        interp = (
            "Not the best time to chase new positions aggressively. "
            "Hold winners and add in stages rather than all at once."
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
        "macro_overlay": macro_overlay,
        "timeframe_note": "Short-term sentiment (days–weeks) — not the same as bull/bear regime.",
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


def _sell_guidance(
    st_action: str | None,
    *,
    portfolio_risk: dict | None = None,
    portfolio_doctor_v2: dict | None = None,
    per_holding: list[dict] | None = None,
) -> str:
    lines = ["No blanket sell today.", "", "Trim if:"]
    trim_rules = [
        "Any position up >20% from entry",
        "Any position below your stop level",
    ]
    earnings_trim: list[str] = []
    pd = portfolio_doctor_v2 or {}
    for item in (pd.get("earnings_calendar") or {}).get("items") or []:
        try:
            days = int(item.get("days_until", 99))
        except (TypeError, ValueError):
            continue
        if days <= 2:
            t = item.get("ticker")
            if t:
                earnings_trim.append(str(t))
    if earnings_trim:
        names = ", ".join(earnings_trim[:3])
        trim_rules.append(f"Earnings in next 48hrs ({names}) AND position up >10%")
    else:
        trim_rules.append("Earnings in next 48hrs AND position up >10%")

    for rule in trim_rules:
        lines.append(f"→ {rule}")

    weak = [
        h.get("ticker")
        for h in (per_holding or [])
        if h.get("ticker") and (h.get("score") is not None and float(h.get("score")) < 35)
    ]
    if weak:
        lines.append(f"→ Weak scores (<35): {', '.join(str(t) for t in weak[:3])} — review thesis")

    lines.extend(["", "Hold everything else."])
    if st_action == _ACTION_REDUCE:
        lines[0] = "Selective trim day — no panic selling."
    elif st_action == _ACTION_WAIT:
        lines[0] = "No new buys today — hold unless stops hit."
    if portfolio_risk and (portfolio_risk.get("score") or 10) >= 7:
        lines.append("Portfolio risk elevated — prioritize largest earnings names this week.")
    return "\n".join(lines)


def _holdings_alignment_answer(
    *,
    retail_briefing: dict | None,
    portfolio_doctor_v2: dict | None,
    per_holding: list[dict] | None,
    sector_rotation: dict | None,
    breadth: dict,
) -> str:
    conc = (retail_briefing or {}).get("concentration") or {}
    conc_pct = conc.get("concentration_pct")
    top = conc.get("top_positions") or []
    pd = portfolio_doctor_v2 or {}
    sector_alloc = pd.get("sector_allocation") or []

    tech_pct = None
    tech_sector = None
    for row in sector_alloc:
        sec = str(row.get("sector") or "")
        if "tech" in sec.lower() or sec.lower() in ("information technology", "technology"):
            tech_pct = float(row.get("pct") or 0)
            tech_sector = sec
            break

    weak = [
        h.get("ticker")
        for h in (per_holding or [])
        if h.get("ticker") and (h.get("score") is not None and float(h.get("score")) < 40)
    ]

    if tech_pct is not None and tech_pct > 50:
        return (
            f"Your {tech_sector or 'tech'} concentration: {tech_pct:.0f}%. "
            "Recommended max: 50%. Consider: trim 1 extended tech position or add a diversifier (e.g. XLP, XLV)."
        )

    if conc_pct and conc_pct > 45 and top:
        names = ", ".join(f"{x.get('ticker')} ({x.get('pct', 0):.0f}%)" for x in top[:3] if x.get("ticker"))
        msg = f"Top 3 = {conc_pct:.0f}% ({names}). Consider trimming one extended name or adding a diversifier."
        if weak:
            msg += f" Weak scores: {', '.join(str(t) for t in weak[:3])}."
        return msg

    if sector_rotation and sector_rotation.get("rotate_away"):
        away = ", ".join(sector_rotation["rotate_away"][:2])
        return f"Rotation lagging in {away} — check if you're overweight there vs leading sectors."

    if breadth.get("signal") == "NARROW":
        return (
            "Breadth narrow — mega-cap leaders vs rest. "
            "Ensure you're not in lagging small names; portfolio may trail SPY even in up tapes."
        )

    if weak:
        return (
            f"Concentration OK, but weak scores: {', '.join(str(t) for t in weak[:4])}. "
            "Review thesis — trim laggards before adding new names."
        )

    if conc_pct and conc_pct <= 45:
        return "Portfolio looks balanced — no concentration alerts. Hold quality names aligned with the matrix."

    return "Portfolio looks balanced — no concentration alerts. Hold quality names aligned with the matrix."


def _five_questions(
    context: dict | None,
    matrix: dict,
    temperature: dict,
    breadth: dict,
    credit: dict,
    portfolio_risk: dict | None,
    catalysts: dict | None,
    *,
    trigger_levels: dict | None = None,
    sector_rotation: dict | None = None,
    per_holding: list[dict] | None = None,
    retail_briefing: dict | None = None,
    portfolio_doctor_v2: dict | None = None,
) -> list[dict[str, str]]:
    st = matrix.get("short_term", {})
    mt = matrix.get("medium_term", {})
    scheduled = (catalysts or {}).get("scheduled_today") or []

    spy_trig = ((trigger_levels or {}).get("levels") or {}).get("SPY") or {}
    primary = spy_trig.get("primary_trigger")
    last_close = spy_trig.get("last_close")

    buy_answer = (context or {}).get("short_term", {}).get("bullets", [""])[0] if context else ""
    if not buy_answer:
        buy_answer = "Selectively — small adds on pullbacks only." if st.get("action") == _ACTION_BUY else "Wait for a clearer edge."
    if scheduled:
        buy_answer = f"Wait until after today's {scheduled[0].get('event_type', 'macro')} release, then reassess."
    elif primary and last_close and st.get("action") in (_ACTION_BUY, _ACTION_HOLD):
        buy_answer = (
            f"Scale in: part now, optional limit near SPY ${primary:.0f} support (last ${last_close:.0f}) "
            "for the rest."
        )

    sell_answer = _sell_guidance(
        st.get("action"),
        portfolio_risk=portfolio_risk,
        portfolio_doctor_v2=portfolio_doctor_v2,
        per_holding=per_holding,
    )

    crash_answer = "No crash signal — credit and breadth not in danger zone."
    if credit.get("signal") in ("WARNING", "DANGER"):
        crash_answer = "Credit stress rising — not a crash call, but reduce risk and raise cash slowly."
    elif (context or {}).get("quadrant") == "best_buy_zone":
        crash_answer = (
            "High fear in a bull regime — volatility yes, crash unlikely unless credit breaks. "
            "Often a better entry zone for patient holders."
        )
    elif temperature.get("level") == "cold" and temperature.get("vix") and temperature["vix"] >= 28:
        crash_answer = "VIX elevated — spike risk, but often marks better entries for long-term holders if regime stays bull."

    holdings_answer = _holdings_alignment_answer(
        retail_briefing=retail_briefing,
        portfolio_doctor_v2=portfolio_doctor_v2,
        per_holding=per_holding,
        sector_rotation=sector_rotation,
        breadth=breadth,
    )

    hold_answer = "Core thesis: months–years. Tactical adds: days–weeks with stops."
    if mt.get("action") == _ACTION_BUY:
        hold_answer = "Core: hold months–years. Tactical: add on dips over days–weeks with defined stops."
    if (context or {}).get("quadrant") == "best_buy_zone":
        hold_answer = "Long-term bull intact — hold core through fear; add tactically on weakness."

    return [
        {"question": "Should I buy more this week?", "answer": buy_answer},
        {"question": "Should I sell anything?", "answer": sell_answer},
        {"question": "Is the market about to crash?", "answer": crash_answer},
        {"question": "Am I in the right stuff?", "answer": holdings_answer},
        {"question": "How long should I hold this?", "answer": hold_answer},
    ]


def _morning_checklist(context: dict | None, trigger_levels: dict | None, portfolio_risk: dict | None) -> list[dict[str, str]]:
    items: list[dict[str, str]] = [
        {"time": "Before open", "task": "Review earnings in next 48h — trim 15–20% if up >10% gain."},
        {"time": "9:30–10:00 ET", "task": "Don't hero-trade the open — let direction confirm."},
    ]
    spy = ((trigger_levels or {}).get("levels") or {}).get("SPY") or {}
    trig = spy.get("primary_trigger")
    if trig:
        items.append({"time": "If SPY holds", "task": f"Above ${trig:.0f} — selective adds OK per matrix."})
        items.append({"time": "If SPY breaks", "task": f"Below ${trig:.0f} — pause new entries; tighten stops."})
    items.append({"time": "End of day", "task": "Update stops on any position up >8% from entry."})
    if portfolio_risk and (portfolio_risk.get("adjustments") or []):
        adj = portfolio_risk["adjustments"][0]
        items.insert(1, {"time": "Priority", "task": adj})
    if (context or {}).get("quadrant") == "best_buy_zone":
        items.insert(0, {"time": "Setup", "task": "Fear in bull market — prioritize watchlist entries at support, not chase."})
    return items[:6]


def _hold_vs_trade_answer(context: dict | None) -> dict[str, Any]:
    q = (context or {}).get("quadrant")
    if q == "best_buy_zone":
        return {
            "headline": "Long-term hold vs tactical trim?",
            "answer": "Core thesis names vs swing trades — different rules apply in a fear-in-bull setup.",
            "bullets": [
                "Core thesis names (5–10 yr): hold through fear if thesis intact — this is often the best add zone.",
                "Tactical trades: buy dips with stops; trim only if up >20% or thesis breaks.",
                "Don't panic-sell quality compounders because macro overlay says Risk-Off short term.",
            ],
        }
    if q == "hold_and_trim":
        return {
            "headline": "Long-term hold vs tactical trim?",
            "answer": "Sentiment extended in a bull tape — protect gains on trades, keep compounders.",
            "bullets": [
                "Hold long-term core compounders — don't sell quality for short-term greed.",
                "Trim 20% of extended tactical positions now.",
                "Re-add on 3–5% pullbacks with defined stops.",
            ],
        }
    return {
        "headline": "Long-term hold vs tactical trim?",
        "answer": "Match your time horizon to the action — long-term plan vs short-term tactics differ.",
        "bullets": [
            "Long-term (5–10+ yr): hold quality if thesis + regime support intact.",
            "Short-term / trading: use sell roadmap stops and targets.",
            "Trim tactical positions on rules; don't apply trade stops to compounders blindly.",
        ],
    }


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


def _breadth_panel(market_regime: dict | None, breadth: dict) -> dict[str, Any]:
    """Participation proxy until constituent % above MA50/200 is available."""
    mr = market_regime or {}
    rsp_trend = mr.get("rsp_spy_trend") or "Flat"
    return {
        "proxy": "RSP/SPY equal-weight vs cap-weight",
        "market_breadth": breadth.get("market_breadth"),
        "rsp_spy_trend": rsp_trend,
        "participation_narrow": breadth.get("participation_narrow"),
        "plain_english": breadth.get("plain_english"),
        "data_note": "Full % above MA50/200 requires constituent feed — using RS proxy today.",
    }


def _personal_earnings_calendar(portfolio_doctor: dict | None) -> dict[str, Any] | None:
    pd = portfolio_doctor or {}
    earnings = pd.get("earnings_calendar") or {}
    items = earnings.get("items") or []
    if not items:
        return None
    rules: list[dict[str, Any]] = []
    for item in items[:8]:
        t = item.get("ticker")
        d = item.get("days_until")
        if t is None or d is None:
            continue
        try:
            di = int(d)
        except (TypeError, ValueError):
            continue
        if di < 0 or di > 14:
            continue
        rule = f"{t} in {di}d"
        if di <= 1:
            action = "Trim 15–20% before close prior day if holding."
        elif di <= 5:
            action = "Reduce size into report; no new buys."
        else:
            action = "On calendar — plan trim if extended."
        rules.append({"ticker": t, "days_until": di, "action": action})
    if not rules:
        return None
    return {
        "items": rules,
        "plain_english": f"{len(rules)} portfolio holding(s) report in next 2 weeks — earnings dominate risk.",
    }


def build_retail_market_decisions(
    *,
    config: dict | None = None,
    macro_regime: str | None = None,
    global_market_regime: str | None = None,
    macro_regime_bundle: dict | None = None,
    market_regime: dict | None = None,
    market_catalysts: dict | None = None,
    portfolio_doctor_v2: dict | None = None,
    retail_briefing: dict | None = None,
    per_holding: list[dict] | None = None,
    avg_portfolio_score: float | None = None,
    flip_stats: dict | None = None,
    cross_asset: list | None = None,
    premarket: dict | None = None,
    data_root=None,
    include_p1: bool = True,
) -> dict[str, Any]:
    """
    Single retail decision payload: temperature, reconciled context, matrix, IF/THEN, five questions.
    """
    vix = None
    if macro_regime_bundle:
        vix = (macro_regime_bundle.get("factors") or {}).get("vix")

    temperature = _market_temperature(vix, macro_regime, macro_regime_bundle)
    breadth = _breadth_check(market_regime)
    credit = _credit_pulse(macro_regime_bundle)

    trigger_levels = None
    sector_rotation = None
    crowd = None
    if include_p1:
        try:
            from signals.trigger_levels import build_trigger_levels

            trigger_levels = build_trigger_levels()
        except Exception:
            pass
        try:
            from signals.sector_rotation_tilt import build_sector_rotation_tilt

            sector_rotation = build_sector_rotation_tilt()
        except Exception:
            pass
        try:
            from signals.sentiment_positioning import get_crowd_positioning

            crowd = get_crowd_positioning(config)
            fg = (crowd.get("fear_greed") or {}).get("score")
            if fg is not None and fg <= 30 and temperature.get("level") not in ("cold", "cool"):
                temperature = dict(temperature)
                temperature["label"] = "COLD"
                temperature["level"] = "cold"
                temperature["buy_zone"] = True
        except Exception:
            pass

    from signals.market_context_reconciler import reconcile_market_context, matrix_from_context

    market_context = reconcile_market_context(
        temperature=temperature,
        macro_regime=macro_regime,
        global_market_regime=global_market_regime,
        macro_regime_bundle=macro_regime_bundle,
        credit=credit,
        breadth=breadth,
        market_catalysts=market_catalysts,
    )
    matrix = matrix_from_context(market_context)
    scenarios = _if_then_scenarios(market_catalysts, flip_stats)
    portfolio_risk = _portfolio_risk_block(portfolio_doctor_v2, retail_briefing, per_holding)
    questions = _five_questions(
        market_context,
        matrix,
        temperature,
        breadth,
        credit,
        portfolio_risk,
        market_catalysts,
        trigger_levels=trigger_levels,
        sector_rotation=sector_rotation,
        per_holding=per_holding,
        retail_briefing=retail_briefing,
        portfolio_doctor_v2=portfolio_doctor_v2,
    )

    overnight_delta = None
    if data_root is not None:
        try:
            from pathlib import Path
            from signals.overnight_delta import build_overnight_delta

            overnight_delta = build_overnight_delta(
                data_root=Path(data_root) if not isinstance(data_root, Path) else data_root,
                cross_asset=cross_asset,
                macro_regime_bundle=macro_regime_bundle,
                premarket=premarket,
            )
        except Exception:
            pass

    out: dict[str, Any] = {
        "five_questions": questions,
        "market_context": market_context,
        "market_temperature": temperature,
        "strategy_matrix": matrix,
        "if_then_scenarios": scenarios,
        "breadth_check": breadth,
        "breadth_panel": _breadth_panel(market_regime, breadth),
        "credit_pulse": credit,
        "portfolio_risk": portfolio_risk,
        "morning_checklist": _morning_checklist(market_context, trigger_levels, portfolio_risk),
        "hold_vs_trade": _hold_vs_trade_answer(market_context),
        "overnight_delta": overnight_delta,
        "disclaimer": "Decision support only — conditional guidance, not a guarantee. Confirm with your plan.",
    }

    if include_p1:
        out["crowd_positioning"] = crowd
        try:
            from signals.earnings_season_pulse import get_earnings_season_pulse

            out["earnings_season_pulse"] = get_earnings_season_pulse(config)
        except Exception:
            out["earnings_season_pulse"] = None
        out["trigger_levels"] = trigger_levels
        out["sector_rotation"] = sector_rotation
        out["personal_earnings_calendar"] = _personal_earnings_calendar(portfolio_doctor_v2)

    return out
