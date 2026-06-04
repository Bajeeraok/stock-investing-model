"""
Retail action / trading-gate payloads for API responses.

Single source of truth for gate pass/fail, RSI heat, regime weather, and R:R bands.
Frontend maps visual_status tokens to Tailwind — no duplicate threshold math in React.
"""

from __future__ import annotations

from typing import Any, Literal

ST_ML_GATE = 25
ML_MARGINAL_ABS = 55  # pass vs threshold but low absolute conviction
REGIME_GATE = 60
CONFIDENCE_GATE = 55
PRIMARY_GATE_IDS = ("valuation", "regime", "momentum", "ml")

RsiStatus = Literal["hot", "neutral", "oversold"]
RegimeWeatherStatus = Literal["bull", "stormy", "mixed"]
RrStatus = Literal["tight", "balanced", "favorable"]
GateVisualStatus = Literal["cleared", "blocked", "marginal"]
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


def _regime_gate_detail(
    *,
    ticker: str | None,
    stock_bull_pct: float,
    regime_ok: bool,
    regime_hmm_label: str | None = None,
    regime_transition_pct: float | None = None,
    market_bull_pct: float | None = None,
) -> str:
    if regime_ok:
        sym = ticker or "Stock"
        return f"Bull tape · {sym} HMM bull {round(stock_bull_pct)}%"

    sym = ticker or "This name"
    label = (regime_hmm_label or "non-bull").replace("_", " ").strip()
    trans = regime_transition_pct
    in_transition = trans is not None and trans >= 35
    if in_transition:
        line1 = (
            f"Stormy Tape — {sym} in transition regime "
            f"({round(stock_bull_pct)}% bull, {round(trans)}% transition)"
        )
    else:
        line1 = f"Stormy Tape — {sym} HMM non-bull ({round(stock_bull_pct)}% bull)"
        if label and label.lower() not in ("bull", "non-bull", "non bull"):
            line1 = f"Stormy Tape — {sym} in {label.lower()} regime ({round(stock_bull_pct)}% bull)"

    if market_bull_pct is not None and market_bull_pct >= REGIME_GATE and stock_bull_pct < REGIME_GATE:
        return f"{line1} · Market overall: {round(market_bull_pct)}% bull · → Stock lagging the broader market"
    return line1


def _momentum_gate_detail(
    *,
    rsi_val: float,
    pattern_score: float | None,
    momentum_ok: bool,
) -> str:
    if momentum_ok:
        return f"RSI {rsi_val:.0f} · pattern {round(pattern_score or 0)}/100"
    if rsi_val >= 70:
        return f"RSI extended ({rsi_val:.0f}/100) — overbought; wait for cooldown"
    if rsi_val >= 50:
        return (
            f"RSI above neutral ({rsi_val:.0f}/100) — model prefers RSI < 50 for optimal entry timing"
        )
    return f"Pattern weak ({round(pattern_score or 0)}/100)"


def _ml_gate_detail(short_ml_prob: float | None) -> tuple[str, str, bool]:
    """Return (detail, visual_status, pass)."""
    ml = float(short_ml_prob or 0)
    ml_ok = ml >= ST_ML_GATE
    if not ml_ok:
        return (
            f"Weak short ML ({round(ml)}% · need {ST_ML_GATE}%+)",
            "blocked",
            False,
        )
    if ml < ML_MARGINAL_ABS:
        return (
            f"Marginal pass ({round(ml)}% vs {ST_ML_GATE}% threshold) — "
            f"low absolute probability; setup exists but not high conviction",
            "marginal",
            True,
        )
    return (
        f"Validated setup ({round(ml)}% vs {ST_ML_GATE}% threshold)",
        "cleared",
        True,
    )


def build_coherent_setup_story(
    *,
    ticker: str | None,
    assessment_pct: float,
    stock_bull_pct: float | None,
    market_bull_pct: float | None,
    rsi: float | None,
    short_ml_prob: float | None,
    gates: list[dict[str, Any]],
    regime_transition_days: int | None = None,
) -> str:
    sym = ticker or "This name"
    parts: list[str] = []

    if assessment_pct >= 5:
        parts.append(f"{sym} is cheap (~{abs(assessment_pct):.0f}% below model fair value)")
    elif assessment_pct >= 0:
        parts.append(f"{sym} has modest valuation support (+{assessment_pct:.0f}% vs fair value)")
    else:
        parts.append(f"{sym} is rich vs model fair value ({assessment_pct:.0f}%)")

    if market_bull_pct is not None and market_bull_pct >= REGIME_GATE:
        parts.append("the broader market tape is bullish")
    elif market_bull_pct is not None:
        parts.append("the broader market backdrop is cautious")

    primary = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS]
    regime_gate = next((g for g in primary if g.get("id") == "regime"), None)
    if regime_gate and not regime_gate.get("pass"):
        if stock_bull_pct is not None and stock_bull_pct < REGIME_GATE:
            parts.append(f"but {sym}'s own HMM read has not confirmed bull yet")
        else:
            parts.append("but short-term weather on this name is not clear yet")
    elif stock_bull_pct is not None and stock_bull_pct >= REGIME_GATE:
        parts.append("and the stock's regime aligns with the tape")

    rsi_v = float(rsi) if rsi is not None else None
    if rsi_v is not None and rsi_v >= 50:
        parts.append(f"RSI is above neutral ({rsi_v:.0f}) — timing is not ideal for chasing")

    ml = float(short_ml_prob or 0)
    if ml >= ST_ML_GATE and ml < ML_MARGINAL_ABS:
        parts.append(f"ML sees a setup ({ml:.0f}%) but conviction is modest")

    story = ". ".join(parts[:4]).rstrip(".") + "."
    if regime_gate and not regime_gate.get("pass") and market_bull_pct and market_bull_pct >= REGIME_GATE:
        story += (
            f" Watch for {sym}'s Market Weather gate to flip PASS (HMM bull ≥ {REGIME_GATE}%) — "
            "that's your entry trigger."
        )
        if regime_transition_days:
            story += f" Model estimates resolution in ~{regime_transition_days} days."
    elif any(not g.get("pass") for g in primary):
        story += " Until more gates clear: watch, don't chase."
    else:
        story += " Gates align — confirm sizing on Roadmaps before adding."
    return story


def build_next_trigger(
    *,
    ticker: str | None,
    gates: list[dict[str, Any]],
    stock_bull_pct: float | None,
    market_bull_pct: float | None,
    regime_transition_days: int | None = None,
) -> dict[str, Any] | None:
    primary = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS]
    regime_gate = next((g for g in primary if g.get("id") == "regime"), None)
    if not regime_gate or regime_gate.get("pass"):
        failed = [g for g in primary if not g.get("pass")]
        if not failed:
            return None
        top = failed[0]
        return {
            "headline": f"Setup activates when {str(top.get('label', 'gate')).title()} clears",
            "detail": str(top.get("detail") or ""),
            "estimated_days": None,
        }

    sym = ticker or "This name"
    detail = (
        f"Watch for {sym} HMM bull ≥ {REGIME_GATE}% (stock-specific regime, not the market tape alone)."
    )
    if market_bull_pct is not None and market_bull_pct >= REGIME_GATE:
        detail += f" Market is already {round(market_bull_pct)}% bull — you're waiting on the name to catch up."
    est = regime_transition_days
    if est is not None:
        try:
            est_i = int(est)
        except (TypeError, ValueError):
            est_i = None
        if est_i is not None and est_i > 0:
            detail += f" Estimated resolution: ~{est_i} days based on transition regime read."
    return {
        "headline": "Setup activates when Market Weather gate flips PASS",
        "detail": detail,
        "estimated_days": regime_transition_days,
    }


def build_trading_gates(
    *,
    assessment_pct: float,
    regime_bull_pct: float | None,
    pattern_score: float | None,
    short_ml_prob: float | None,
    rsi: float | None,
    confidence_mid: float | None,
    include_confidence: bool = True,
    ticker: str | None = None,
    regime_hmm_label: str | None = None,
    regime_transition_pct: float | None = None,
    market_regime_bull_pct: float | None = None,
) -> list[dict[str, Any]]:
    """Primary + optional confidence gates with pass flags and visual_status tokens."""
    rb = regime_bull_pct if regime_bull_pct is not None else 50.0
    rsi_val = float(rsi) if rsi is not None else 50.0
    weather = regime_weather_status(regime_bull_pct)

    valuation_ok = assessment_pct >= 5
    regime_ok = regime_bull_pct is not None and regime_bull_pct >= REGIME_GATE
    momentum_ok = rsi_val < 50 and (pattern_score or 0) >= 45
    ml_detail, ml_visual, ml_ok = _ml_gate_detail(short_ml_prob)
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
            "detail": _regime_gate_detail(
                ticker=ticker,
                stock_bull_pct=rb,
                regime_ok=regime_ok,
                regime_hmm_label=regime_hmm_label,
                regime_transition_pct=regime_transition_pct,
                market_bull_pct=market_regime_bull_pct,
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
            "detail": _momentum_gate_detail(
                rsi_val=rsi_val,
                pattern_score=pattern_score,
                momentum_ok=momentum_ok,
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
            "detail": ml_detail,
            "pass": ml_ok,
            "gate_cleared": ml_ok,
            "visual_status": ml_visual,
            "icon": "🤖" if ml_visual != "marginal" else "⚠️",
            "blocker_weight": 0 if ml_ok else 20,
            "marginal_pass": ml_visual == "marginal",
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
    market_regime_bull_pct: float | None = None,
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
        if assessment_pct >= 5 and market_regime_bull_pct and market_regime_bull_pct >= REGIME_GATE:
            return (
                "Valuation is attractive and the market tape is bullish, but this stock's own HMM regime "
                "has not confirmed yet — wait for Market Weather to flip PASS before sizing."
            )
        return (
            "Valuation is highly attractive, but market weather on this name is stormy. "
            "Sit on your hands and wait for a cleaner dip."
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


def derive_zone_aware_action_title(
    overall_verdict: str | None,
    gate_cleared: bool,
    *,
    long_spot: dict | None = None,
    short_spot: dict | None = None,
    in_bridge_band: bool = False,
) -> tuple[str, ActionLight]:
    """Price-zone-aware headline — updates with spot vs tiers (per request snapshot)."""
    spot = long_spot or short_spot or {}
    state = (spot.get("state") or "").lower()
    tier_id = spot.get("tier_id") or spot.get("active_tier_id") or spot.get("next_add_tier_id")

    if state == "in_tier" and tier_id:
        tier = str(tier_id).upper()
        if gate_cleared:
            return f"ACCUMULATE · {tier}", "green"
        return f"ACCUMULATE · {tier} (partial)", "yellow"

    if state in ("in_band",) and gate_cleared:
        return "TACTICAL ENTRY", "green"
    if state in ("in_band",):
        return "IN BUY BAND · WAIT FOR GATES", "yellow"

    if in_bridge_band or (state in ("between_tiers", "between_horizon_bands") and spot.get("in_bridge_band")):
        return "BRIDGE ONLY · PARTIAL", "yellow"

    if state in ("between_tiers", "between_horizon_bands"):
        return "WATCH ZONE", "yellow"

    return derive_action_title(overall_verdict, gate_cleared)


def build_zone_context(
    investor_out: dict[str, Any],
    current_price: float | None,
) -> dict[str, Any] | None:
    """Named zone + bridge band for Watch Zone UI."""
    if current_price is None or current_price <= 0:
        return None
    horizons = investor_out.get("horizons") or {}
    long_h = horizons.get("long") or {}
    long_spot = ((long_h.get("entry_tiers") or {}).get("spot_position")) or {}
    short_ez = (horizons.get("short") or {}).get("entry_zone") or {}
    st_spot = short_ez.get("spot_position") or {}

    spot = long_spot if long_spot.get("state") in ("between_tiers", "in_tier") else st_spot
    if not spot:
        cross = st_spot.get("cross_gap") or {}
        if cross.get("state") == "between_horizon_bands":
            spot = {**st_spot, **cross}

    state = spot.get("state")
    if state not in ("between_tiers", "between_horizon_bands", "in_tier", "in_band"):
        return None

    bridge = spot.get("bridge_band") or {}
    bridge_lo = bridge.get("low")
    bridge_hi = bridge.get("high")
    gap_lo = spot.get("floor_band_high") or spot.get("band_low")
    gap_hi = spot.get("ceiling_band_low") or spot.get("band_high")

    in_watch = state in ("between_tiers", "between_horizon_bands")
    zone_name = "Watch Zone" if in_watch else f"Inside {spot.get('active_tier_id') or spot.get('tier_id') or 'tier'}"

    return {
        "zone_name": zone_name,
        "state": state,
        "in_watch_zone": in_watch,
        "in_bridge_band": bool(spot.get("in_bridge_band")),
        "gap_low": gap_lo,
        "gap_high": gap_hi,
        "bridge_low": bridge_lo,
        "bridge_high": bridge_hi,
        "bridge_rationale": (
            "Bridge zone — partial starter if regime improves; not full position sizing."
        ),
        "catch_levels": bridge.get("levels") or spot.get("catch_levels") or [],
        "floor_tier_id": spot.get("floor_tier_id"),
        "ceiling_tier_id": spot.get("ceiling_tier_id"),
        "next_add_tier_id": spot.get("next_add_tier_id"),
    }


def build_unlock_summary(
    gates: list[dict[str, Any]],
    *,
    stock_bull_pct: float | None,
    zone_context: dict[str, Any] | None = None,
    st_band: dict | None = None,
) -> str | None:
    """One-line 'what flips WAIT → BUY' for Today tab."""
    parts: list[str] = []
    primary = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS]
    regime_gate = next((g for g in primary if g.get("id") == "regime"), None)
    if regime_gate and not regime_gate.get("pass"):
        bull = round(float(stock_bull_pct or 0))
        parts.append(f"HMM bull ≥{REGIME_GATE}% (now {bull}%)")

    failed = [g for g in primary if not g.get("pass") and g.get("id") != "regime"]
    if failed:
        top = sorted(failed, key=lambda x: -(x.get("blocker_weight") or 0))[0]
        label = str(top.get("label") or "gate").title()
        parts.append(f"{label} clears")

    zc = zone_context or {}
    if zc.get("in_bridge_band") and zc.get("bridge_low") is not None:
        parts.append(
            f"price in bridge ${float(zc['bridge_low']):.0f}–${float(zc['bridge_high']):.0f}"
        )
    elif zc.get("gap_low") is not None and zc.get("gap_high") is not None:
        parts.append(
            f"price enters ${float(zc['gap_low']):.0f}–${float(zc['gap_high']):.0f}"
        )
    elif st_band and st_band.get("low") is not None:
        lo, hi = float(st_band["low"]), float(st_band["high"])
        parts.append(f"price in ST band ${lo:.0f}–${hi:.0f}")

    if not parts:
        return None
    return "Unlocks when: " + " + ".join(parts)


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
    ticker: str | None = None,
    regime_hmm_label: str | None = None,
    regime_transition_pct: float | None = None,
    market_regime_bull_pct: float | None = None,
    regime_transition_days: int | None = None,
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
        ticker=ticker,
        regime_hmm_label=regime_hmm_label,
        regime_transition_pct=regime_transition_pct,
        market_regime_bull_pct=market_regime_bull_pct,
    )
    primary = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS]
    locked = sum(1 for g in primary if not g.get("pass"))
    all_go = locked == 0
    inside_buy_band = _inside_st_band(current_price, st_band)
    subtitle = build_dynamic_subtitle(
        gates,
        assessment_pct,
        rsi,
        inside_buy_band,
        market_regime_bull_pct=market_regime_bull_pct,
    )
    title, light = derive_action_title(overall_verdict, all_go)

    rr = rr_status(risk_reward)
    coherent_story = build_coherent_setup_story(
        ticker=ticker,
        assessment_pct=assessment_pct,
        stock_bull_pct=regime_bull_pct,
        market_bull_pct=market_regime_bull_pct,
        rsi=rsi,
        short_ml_prob=short_ml_prob,
        gates=gates,
        regime_transition_days=regime_transition_days,
    )
    next_trigger = build_next_trigger(
        ticker=ticker,
        gates=gates,
        stock_bull_pct=regime_bull_pct,
        market_bull_pct=market_regime_bull_pct,
        regime_transition_days=regime_transition_days,
    )
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
        "coherent_story": coherent_story,
        "next_trigger": next_trigger,
        "gates": gates,
        "primary_gate_ids": list(PRIMARY_GATE_IDS),
        "stock_regime_bull_pct": round(float(regime_bull_pct), 1) if regime_bull_pct is not None else None,
        "market_regime_bull_pct": round(float(market_regime_bull_pct), 1) if market_regime_bull_pct is not None else None,
    }
    if rr is not None:
        payload["rr_status"] = rr
    if risk_reward is not None:
        payload["rr_ratio"] = round(float(risk_reward), 2)
    return payload


def enrich_investor_summary_retail_action(
    investor_out: dict[str, Any],
    current_price: float | None,
    *,
    ticker: str | None = None,
    market_regime_bull_pct: float | None = None,
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
        ticker=ticker,
        regime_hmm_label=investor_out.get("regime_hmm_label"),
        regime_transition_pct=investor_out.get("regime_transition_pct"),
        market_regime_bull_pct=market_regime_bull_pct
        if market_regime_bull_pct is not None
        else investor_out.get("market_regime_bull_pct"),
        regime_transition_days=investor_out.get("regime_transition_days_estimate"),
    )

    long_h = horizons.get("long") or {}
    long_spot = ((long_h.get("entry_tiers") or {}).get("spot_position")) or {}
    short_spot = (short.get("entry_zone") or {}).get("spot_position") or {}
    zone_ctx = build_zone_context(investor_out, current_price)
    ra = investor_out["retail_action"]
    if zone_ctx:
        ra["zone_context"] = zone_ctx
        title, light = derive_zone_aware_action_title(
            investor_out.get("overall_verdict"),
            ra.get("gate_cleared", False),
            long_spot=long_spot,
            short_spot=short_spot,
            in_bridge_band=bool(zone_ctx.get("in_bridge_band")),
        )
        ra["action_title"] = title
        ra["action_light"] = light
    unlock = build_unlock_summary(
        ra.get("gates") or [],
        stock_bull_pct=investor_out.get("regime_bull_pct"),
        zone_context=zone_ctx,
        st_band=st_band,
    )
    if unlock:
        ra["unlock_summary"] = unlock

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
