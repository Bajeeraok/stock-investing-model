"""
Retail action / trading-gate payloads for API responses.

Single source of truth for gate pass/fail, RSI heat, regime weather, and R:R bands.
Frontend maps visual_status tokens to Tailwind — no duplicate threshold math in React.
"""

from __future__ import annotations

from typing import Any, Literal

ST_ML_GATE = 25
REGIME_GATE = 60
CONFIDENCE_GATE = 55
PRIMARY_GATE_IDS = ("valuation", "regime", "momentum", "ml")

RsiStatus = Literal["hot", "neutral", "oversold"]
RegimeWeatherStatus = Literal["bull", "stormy", "mixed"]
RrStatus = Literal["tight", "balanced", "favorable"]
GateVisualStatus = Literal["cleared", "blocked"]
ActionLight = Literal["green", "yellow", "red"]


def rsi_status(rsi: float | None) -> RsiStatus:
    if rsi is None:
        return "neutral"
    if rsi >= 50:
        return "hot"
    if rsi <= 35:
        return "oversold"
    return "neutral"


def regime_weather_status(regime_bull_pct: float | None) -> RegimeWeatherStatus:
    if regime_bull_pct is None:
        return "mixed"
    if regime_bull_pct >= REGIME_GATE:
        return "bull"
    if regime_bull_pct < 42:
        return "stormy"
    return "mixed"


def rr_status(risk_reward: float | None) -> RrStatus | None:
    if risk_reward is None:
        return None
    if risk_reward < 0.6:
        return "tight"
    if risk_reward >= 1.0:
        return "favorable"
    return "balanced"


def _global_regime_bull_pct(global_market_regime: str | None) -> float | None:
    g = (global_market_regime or "").upper()
    if g in ("BULL", "STRONG_BULL"):
        return 68.0
    if g in ("BEAR", "STRONG_BEAR"):
        return 32.0
    if g == "NEUTRAL":
        return 50.0
    return None


def _assessment_pct(current_price: float | None, fair_value: float | None) -> float:
    if current_price is None or fair_value is None or current_price <= 0 or fair_value <= 0:
        return 0.0
    return 100.0 * (fair_value - current_price) / current_price


def _assessment_from_lt_band(current_price: float | None, lt_band: dict | None) -> float:
    if not lt_band or current_price is None or current_price <= 0:
        return 0.0
    lo = lt_band.get("low")
    hi = lt_band.get("high")
    if lo is None or hi is None:
        return 0.0
    fv = (float(lo) + float(hi)) / 2.0
    return 100.0 * (fv - current_price) / current_price


def _inside_st_band(current_price: float | None, st_band: dict | None) -> bool:
    if not st_band or current_price is None:
        return False
    lo = st_band.get("low")
    hi = st_band.get("high")
    if lo is None or hi is None:
        return False
    low, high = min(float(lo), float(hi)), max(float(lo), float(hi))
    return low <= float(current_price) <= high


def build_trading_gates(
    *,
    assessment_pct: float,
    regime_bull_pct: float | None,
    pattern_score: float | None,
    short_ml_prob: float | None,
    rsi: float | None,
    confidence_mid: float | None,
    include_confidence: bool = True,
) -> list[dict[str, Any]]:
    """Primary + optional confidence gates with pass flags and visual_status tokens."""
    rb = regime_bull_pct if regime_bull_pct is not None else 50.0
    rsi_val = float(rsi) if rsi is not None else 50.0
    weather = regime_weather_status(regime_bull_pct)

    valuation_ok = assessment_pct >= 5
    regime_ok = regime_bull_pct is not None and regime_bull_pct >= REGIME_GATE
    momentum_ok = rsi_val < 50 and (pattern_score or 0) >= 45
    ml_ok = (short_ml_prob or 0) >= ST_ML_GATE
    conf_ok = (confidence_mid or 0) >= CONFIDENCE_GATE

    gates: list[dict[str, Any]] = [
        {
            "id": "valuation",
            "label": "VALUATION",
            "detail": (
                f"Deeply Undervalued (+{abs(assessment_pct):.1f}% Fair Value)"
                if valuation_ok
                else (
                    f"Modest discount (+{assessment_pct:.1f}% Fair Value)"
                    if assessment_pct >= 0
                    else f"Rich vs Fair Value ({assessment_pct:.1f}%)"
                )
            ),
            "pass": valuation_ok,
            "gate_cleared": valuation_ok,
            "visual_status": "cleared" if valuation_ok else "blocked",
            "icon": "✅" if valuation_ok else "❌",
            "blocker_weight": 0 if valuation_ok else 30,
        },
        {
            "id": "regime",
            "label": "MARKET WEATHER",
            "detail": (
                f"Bull tape · HMM bull {round(rb)}%"
                if regime_ok
                else f"Stormy Tape (HMM Regime Non-Bull · {round(rb)}%)"
            ),
            "pass": regime_ok,
            "gate_cleared": regime_ok,
            "visual_status": "bull" if regime_ok else "stormy",
            "regime_weather_status": weather,
            "icon": "☀️" if regime_ok else ("⚡" if weather == "stormy" else "🌧️"),
            "blocker_weight": 0 if regime_ok else 45,
        },
        {
            "id": "momentum",
            "label": "MOMENTUM CHOP",
            "detail": (
                f"RSI {rsi_val:.0f} · pattern {round(pattern_score or 0)}/100"
                if momentum_ok
                else (
                    f"RSI is Extended ({rsi_val:.0f}/100)"
                    if rsi_val >= 50
                    else f"Pattern weak ({round(pattern_score or 0)}/100)"
                )
            ),
            "pass": momentum_ok,
            "gate_cleared": momentum_ok,
            "visual_status": "cleared" if momentum_ok else "hot",
            "rsi_status": rsi_status(rsi),
            "icon": "📉" if momentum_ok else "📈",
            "blocker_weight": 0 if momentum_ok else (40 if rsi_val >= 50 else 25),
        },
        {
            "id": "ml",
            "label": "ML PROBABILITY",
            "detail": (
                f"Validated Setup ({round(short_ml_prob or 0)}% vs {ST_ML_GATE}% Threshold)"
                if ml_ok
                else f"Weak short ML ({round(short_ml_prob or 0)}% · need {ST_ML_GATE}%+)"
            ),
            "pass": ml_ok,
            "gate_cleared": ml_ok,
            "visual_status": "cleared" if ml_ok else "blocked",
            "icon": "🤖",
            "blocker_weight": 0 if ml_ok else 20,
        },
    ]

    if include_confidence:
        gates.append(
            {
                "id": "confidence",
                "label": "CONFIDENCE",
                "detail": (
                    f"{round(confidence_mid)}% fused confidence (gate {CONFIDENCE_GATE}%+)"
                    if confidence_mid is not None
                    else "Confidence not available"
                ),
                "pass": conf_ok,
                "gate_cleared": conf_ok,
                "visual_status": "cleared" if conf_ok else "blocked",
                "icon": "🎯",
                "blocker_weight": 0 if conf_ok else 15,
            }
        )

    return gates


def build_dynamic_subtitle(
    gates: list[dict[str, Any]],
    assessment_pct: float,
    rsi: float | None,
    inside_buy_band: bool = False,
) -> str:
    primary = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS]
    failed = sorted([g for g in primary if not g.get("pass")], key=lambda x: -(x.get("blocker_weight") or 0))
    passed = sum(1 for g in primary if g.get("pass"))

    if not failed:
        return "All trading gates are green — confirm sizing on Roadmaps before adding risk."

    top = failed[0]
    tid = top.get("id")
    if tid == "momentum" and rsi is not None and rsi >= 50 and inside_buy_band:
        return f"Price is inside the buy band, but short-term RSI ({rsi:.0f}) is too hot to chase today."
    if tid == "regime":
        return (
            "Valuation is highly attractive, but market weather is stormy. Sit on your hands and wait for a cleaner dip."
            if assessment_pct >= 5
            else "Macro regime is risk-off — wait for bull tape before sizing new entries."
        )
    if tid == "valuation":
        return "Little margin of safety vs model fair value — patience beats forcing a trade here."
    if tid == "ml":
        return "ML has not validated the near-term setup yet — let probability catch up before entry."

    return (
        f"{passed} of {len(primary)} gates pass · top blocker: "
        f"{str(top.get('label', '')).lower()} ({top.get('detail', '')})."
    )


def derive_action_title(overall_verdict: str | None, gate_cleared: bool) -> tuple[str, ActionLight]:
    v = (overall_verdict or "WATCH").upper()
    if gate_cleared and v in ("BUY", "STRONG BUY"):
        return "TACTICAL ENTRY", "green"
    if v in ("STRONG BUY", "BUY"):
        return "TACTICAL ENTRY", "green"
    if v in ("AVOID", "REDUCE", "SELL", "WAIT"):
        return "DO NOT CHASE", "red"
    return "WATCH OR HOLD", "yellow"


def build_retail_action_payload(
    *,
    current_price: float | None,
    fair_value: float | None,
    regime_bull_pct: float | None,
    pattern_score: float | None,
    short_ml_prob: float | None,
    rsi: float | None,
    confidence_mid: float | None,
    overall_verdict: str | None = None,
    st_band: dict | None = None,
    risk_reward: float | None = None,
    include_confidence_gate: bool = True,
) -> dict[str, Any]:
    assessment_pct = _assessment_pct(current_price, fair_value)
    gates = build_trading_gates(
        assessment_pct=assessment_pct,
        regime_bull_pct=regime_bull_pct,
        pattern_score=pattern_score,
        short_ml_prob=short_ml_prob,
        rsi=rsi,
        confidence_mid=confidence_mid,
        include_confidence=include_confidence_gate,
    )
    primary = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS]
    locked = sum(1 for g in primary if not g.get("pass"))
    all_go = locked == 0
    inside_buy_band = _inside_st_band(current_price, st_band)
    subtitle = build_dynamic_subtitle(gates, assessment_pct, rsi, inside_buy_band)
    title, light = derive_action_title(overall_verdict, all_go)

    rr = rr_status(risk_reward)
    payload: dict[str, Any] = {
        "gate_cleared": all_go,
        "gates_locked_count": locked,
        "go_no_go": "go" if all_go else "no_go",
        "rsi_status": rsi_status(rsi),
        "regime_weather_status": regime_weather_status(regime_bull_pct),
        "inside_buy_band": inside_buy_band,
        "assessment_pct": round(assessment_pct, 1),
        "action_title": title,
        "action_light": light,
        "dynamic_subtitle": subtitle,
        "gates": gates,
        "primary_gate_ids": list(PRIMARY_GATE_IDS),
    }
    if rr is not None:
        payload["rr_status"] = rr
    if risk_reward is not None:
        payload["rr_ratio"] = round(float(risk_reward), 2)
    return payload


def enrich_investor_summary_retail_action(
    investor_out: dict[str, Any],
    current_price: float | None,
) -> dict[str, Any]:
    """Attach retail_action block to investor_summary dict (mutates copy)."""
    horizons = investor_out.get("horizons") or {}
    short = horizons.get("short") or {}
    band = None
    tr = investor_out.get("trade_roadmap") or {}
    tldr = tr.get("tldr") or {}
    conf_band = tldr.get("model_confidence_band")
    confidence_mid = investor_out.get("model_confidence_pct")
    if isinstance(conf_band, str):
        import re

        m = re.match(r"(\d+)\s*-\s*(\d+)", conf_band)
        if m:
            confidence_mid = (float(m.group(1)) + float(m.group(2))) / 2.0

    st_band = None
    ez = short.get("entry_zone") or {}
    if ez.get("low") is not None and ez.get("high") is not None:
        st_band = {"low": ez["low"], "high": ez["high"]}

    rr = short.get("risk_reward")
    if rr is None and short.get("stop_loss") and short.get("target") and current_price:
        stop = float(short["stop_loss"])
        tgt = float(short["target"])
        cp = float(current_price)
        if cp > stop and tgt > cp:
            rr = (tgt - cp) / (cp - stop)

    investor_out["retail_action"] = build_retail_action_payload(
        current_price=current_price,
        fair_value=investor_out.get("fair_value"),
        regime_bull_pct=investor_out.get("regime_bull_pct"),
        pattern_score=investor_out.get("pattern_score"),
        short_ml_prob=short.get("ml_prob"),
        rsi=investor_out.get("rsi"),
        confidence_mid=confidence_mid,
        overall_verdict=investor_out.get("overall_verdict"),
        st_band=st_band,
        risk_reward=float(rr) if rr is not None else None,
    )
    return investor_out


def enrich_dashboard_signal_row(
    row: dict[str, Any],
    *,
    regime_bull_pct: float | None = None,
) -> dict[str, Any]:
    """Light retail_status for signals table rows (no full investor_summary)."""
    cp = row.get("close")
    rb = regime_bull_pct
    if rb is None:
        rb = _global_regime_bull_pct(row.get("_global_market_regime"))

    ml_pct = row.get("ml_short_prob")
    if ml_pct is not None and ml_pct <= 1:
        ml_pct = float(ml_pct) * 100.0

    conf = row.get("plan_confidence")
    conf_mid = float(conf) * 100.0 if conf is not None and conf <= 1 else conf

    assessment = _assessment_from_lt_band(cp, row.get("lt_band"))
    st_band = row.get("st_band")

    payload = build_retail_action_payload(
        current_price=float(cp) if cp is not None else None,
        fair_value=None,
        regime_bull_pct=rb,
        pattern_score=row.get("confluence_score") or row.get("composite_buy"),
        short_ml_prob=ml_pct,
        rsi=row.get("rsi"),
        confidence_mid=conf_mid,
        overall_verdict=row.get("plan_action") or row.get("signal"),
        st_band=st_band,
        risk_reward=None,
        include_confidence_gate=False,
    )
    # List view uses LT band proxy — override valuation detail when no FV
    if assessment != 0:
        for g in payload["gates"]:
            if g["id"] == "valuation":
                ok = assessment >= 5
                g["pass"] = ok
                g["gate_cleared"] = ok
                g["visual_status"] = "cleared" if ok else "blocked"
                g["icon"] = "✅" if ok else "❌"
                g["detail"] = (
                    f"Deeply Undervalued (+{abs(assessment):.1f}% vs LT band)"
                    if ok
                    else f"LT band discount (+{assessment:.1f}%)"
                    if assessment >= 0
                    else f"Above LT band ({assessment:.1f}%)"
                )

    primary = [g for g in payload["gates"] if g["id"] in PRIMARY_GATE_IDS]
    locked = sum(1 for g in primary if not g["pass"])
    payload["gate_cleared"] = locked == 0
    payload["gates_locked_count"] = locked
    payload["go_no_go"] = "go" if payload["gate_cleared"] else "no_go"
    payload["dynamic_subtitle"] = build_dynamic_subtitle(
        payload["gates"],
        assessment,
        row.get("rsi"),
        payload.get("inside_buy_band", False),
    )
    title, light = derive_action_title(row.get("plan_action") or row.get("signal"), payload["gate_cleared"])
    payload["action_title"] = title
    payload["action_light"] = light

    row["retail_status"] = payload
    row["rsi_status"] = payload["rsi_status"]
    row["gate_cleared"] = payload["gate_cleared"]
    return row
