"""
Plain-language signal reasoning: contributing factors + wait timeframes.

Aggregates gates, confidence layers, market context, and triggers into a
retail-friendly summary for ticker detail and signals list.
"""

from __future__ import annotations

from typing import Any, Literal

from signals.retail_action_payload import (
    PRIMARY_GATE_IDS,
    REGIME_GATE,
    ST_ML_GATE,
    VALUATION_GATE_PASS_PCT,
)

Stance = Literal["helps", "hurts", "neutral"]
Persona = Literal["scout", "swing", "owner"]

_PERSONA_PREFIX: dict[str, str] = {
    "swing": "Swing view (weeks): ",
    "owner": "Owner view (long-term): ",
}

_LAYER_META: dict[str, tuple[str, str]] = {
    "regime_hmm": ("Market & regime", "market"),
    "pattern_technical": ("Chart & momentum", "technical"),
    "lgbm_probability": ("ML setup probability", "ml"),
    "options_sentiment": ("Options sentiment", "options"),
    "insider_signal": ("Insider activity", "insider"),
    "fundamental_score": ("Fundamentals & valuation", "fundamentals"),
    "nlp_sentiment": ("News & headlines", "news"),
}

_GATE_META: dict[str, tuple[str, str]] = {
    "valuation": ("Valuation", "fundamentals"),
    "regime": ("Market weather", "market"),
    "momentum": ("Momentum & chart", "technical"),
    "ml": ("ML probability", "ml"),
}


def _days_to_plain(days: int | float | None) -> str:
    if days is None:
        return "several weeks"
    try:
        d = int(round(float(days)))
    except (TypeError, ValueError):
        return "several weeks"
    if d <= 0:
        return "soon"
    if d <= 5:
        return "within about a week"
    if d <= 14:
        return "roughly 1–2 weeks"
    if d <= 30:
        return "about 2–4 weeks"
    if d <= 60:
        return "likely 1–2 months"
    return "several weeks to a few months"


def _stance_from_score(score: float | None, *, gate_pass: bool | None = None) -> Stance:
    if gate_pass is True:
        return "helps"
    if gate_pass is False:
        return "hurts"
    if score is None:
        return "neutral"
    if score >= 0.62:
        return "helps"
    if score <= 0.42:
        return "hurts"
    return "neutral"


def _factors_from_confidence(confidence: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not confidence or not isinstance(confidence.get("breakdown"), dict):
        return []
    breakdown = confidence["breakdown"]
    labels = confidence.get("labels") or {}
    factors: list[dict[str, Any]] = []
    for layer_id, meta in _LAYER_META.items():
        row = breakdown.get(layer_id)
        if not isinstance(row, dict) or not row.get("available"):
            continue
        score = row.get("score")
        weight = float(row.get("weight") or 0)
        if weight <= 0:
            continue
        label_text = labels.get(layer_id) or row.get("label") or meta[0]
        score_f = float(score) if score is not None else None
        factors.append({
            "id": layer_id,
            "label": meta[0],
            "category": meta[1],
            "stance": _stance_from_score(score_f),
            "weight_pct": round(weight * 100, 1),
            "score_pct": round(score_f * 100, 1) if score_f is not None else None,
            "summary": str(label_text).strip()[:220],
        })
    factors.sort(key=lambda x: x["weight_pct"], reverse=True)
    return factors[:6]


def _factors_from_gates(
    gates: list[dict[str, Any]],
    *,
    assessment_pct: float,
    regime_bull_pct: float | None,
    market_regime_bull_pct: float | None,
    pattern_score: float | None,
    rsi: float | None,
    short_ml_prob: float | None,
    global_market_regime: str | None,
) -> list[dict[str, Any]]:
    factors: list[dict[str, Any]] = []
    primary = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS]

    for g in primary:
        gid = str(g.get("id") or "")
        meta = _GATE_META.get(gid)
        if not meta:
            continue
        passed = bool(g.get("pass"))
        bw = float(g.get("blocker_weight") or 0)
        weight = 25.0 if passed else max(15.0, bw if bw > 0 else 20.0)
        detail = str(g.get("detail") or "").strip()
        if gid == "valuation" and assessment_pct != 0:
            if assessment_pct >= VALUATION_GATE_PASS_PCT:
                detail = f"{assessment_pct:.0f}% margin of safety vs model fair value — full entry zone."
            elif assessment_pct >= 0:
                detail = f"+{assessment_pct:.0f}% vs fair value — need ~{VALUATION_GATE_PASS_PCT:.0f}% MOS for full size."
            else:
                detail = f"{assessment_pct:.0f}% vs fair value — price is rich relative to the model anchor."
        factors.append({
            "id": gid,
            "label": meta[0],
            "category": meta[1],
            "stance": _stance_from_score(None, gate_pass=passed),
            "weight_pct": weight,
            "score_pct": None,
            "summary": detail or meta[0],
        })

    gmr = (global_market_regime or "").upper()
    if gmr:
        if gmr in ("BULL", "STRONG_BULL"):
            factors.append({
                "id": "broad_market",
                "label": "Broad market tape",
                "category": "market",
                "stance": "helps",
                "weight_pct": 12.0,
                "score_pct": None,
                "summary": f"Macro regime reads {gmr.replace('_', ' ').title()} — tailwind for risk assets.",
            })
        elif gmr in ("BEAR", "STRONG_BEAR"):
            factors.append({
                "id": "broad_market",
                "label": "Broad market tape",
                "category": "market",
                "stance": "hurts",
                "weight_pct": 14.0,
                "score_pct": None,
                "summary": f"Macro regime reads {gmr.replace('_', ' ').title()} — headwind for new adds.",
            })

    if pattern_score is not None:
        ps = float(pattern_score)
        factors.append({
            "id": "pattern",
            "label": "Chart structure",
            "category": "technical",
            "stance": _stance_from_score(ps / 100.0 if ps > 1 else ps),
            "weight_pct": 10.0,
            "score_pct": round(ps, 0),
            "summary": f"Pattern score {ps:.0f}/100 — {'supportive base' if ps >= 45 else 'weak structure'}.",
        })

    ml = float(short_ml_prob or 0)
    if ml > 0:
        factors.append({
            "id": "ml_short",
            "label": "Short-horizon ML",
            "category": "ml",
            "stance": "helps" if ml >= ST_ML_GATE else "hurts",
            "weight_pct": 10.0,
            "score_pct": round(ml, 0),
            "summary": (
                f"Model sees {ml:.0f}% odds of a favorable short-term move (need {ST_ML_GATE}%+)."
            ),
        })

    if rsi is not None:
        rv = float(rsi)
        if rv >= 50:
            factors.append({
                "id": "rsi_heat",
                "label": "RSI heat",
                "category": "technical",
                "stance": "hurts",
                "weight_pct": 8.0,
                "score_pct": round(rv, 0),
                "summary": f"RSI {rv:.0f} — momentum is warm; better entries often come on a cooldown.",
            })

    mkt = market_regime_bull_pct if market_regime_bull_pct is not None else regime_bull_pct
    if mkt is not None and not any(f["id"] == "regime" for f in factors):
        factors.append({
            "id": "hmm_stock",
            "label": "Stock HMM regime",
            "category": "market",
            "stance": "helps" if float(mkt) >= REGIME_GATE else "hurts",
            "weight_pct": 11.0,
            "score_pct": round(float(mkt), 0),
            "summary": f"HMM bull probability ~{float(mkt):.0f}% (need {REGIME_GATE}%+ for full weather pass).",
        })

    total = sum(f["weight_pct"] for f in factors) or 1.0
    for f in factors:
        f["weight_pct"] = round(100.0 * f["weight_pct"] / total, 1)
    factors.sort(key=lambda x: x["weight_pct"], reverse=True)
    return factors[:6]


def _merge_factors(
    conf_factors: list[dict[str, Any]],
    gate_factors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if conf_factors:
        by_id = {f["id"]: f for f in conf_factors}
        for gf in gate_factors:
            if gf["id"] in ("valuation", "regime", "momentum", "ml"):
                mapped = {
                    "valuation": "fundamental_score",
                    "regime": "regime_hmm",
                    "momentum": "pattern_technical",
                    "ml": "lgbm_probability",
                }.get(gf["id"])
                if mapped and mapped in by_id:
                    if gf["stance"] == "hurts":
                        by_id[mapped]["stance"] = "hurts"
                    by_id[mapped]["summary"] = gf["summary"]
                elif gf["stance"] == "hurts" and gf["id"] not in by_id:
                    by_id[gf["id"]] = gf
        out = list(by_id.values())
        out.sort(key=lambda x: x["weight_pct"], reverse=True)
        return out[:6]
    return gate_factors


def _gate_plain_blocker(gate: dict[str, Any]) -> str:
    gid = str(gate.get("id") or "")
    if gid == "valuation":
        return "price needs more margin of safety vs our fair-value model"
    if gid == "regime":
        return "market weather (HMM regime) has not confirmed a bull read on this name"
    if gid == "momentum":
        return "momentum is extended or chart structure is not ideal for chasing"
    if gid == "ml":
        return "short-horizon ML probability is below our minimum threshold"
    return str(gate.get("label") or "a gate").lower()


def _build_headline(
    *,
    gate_cleared: bool,
    entry_mode: str | None,
    factors: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    overall_verdict: str | None,
    persona: Persona = "scout",
) -> str:
    if gate_cleared or entry_mode == "full_go":
        helps = [f for f in factors if f.get("stance") == "helps"]
        top = helps[0]["label"] if helps else "Model checks"
        text = f"Model aligns — {top.lower()} leads, and all four entry gates are green for a staged add."
        return _PERSONA_PREFIX.get(persona, "") + text

    failed = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS and not g.get("pass")]
    top_fail = failed[0] if failed else None
    helps = [f for f in factors if f.get("stance") == "helps"]

    if entry_mode == "starter_only":
        blocker = _gate_plain_blocker(top_fail) if top_fail else "timing gates"
        support = helps[0]["label"].lower() if helps else "valuation"
        text = f"Starter size only — {support} supports the thesis, but {blocker}."
        return _PERSONA_PREFIX.get(persona, "") + text

    if entry_mode == "hard_lock":
        text = (
            "Hard lock — no margin of safety at this price; wait for the next tranche's discount."
            if persona == "owner"
            else "Hard lock — no margin of safety at this price; wait for a deeper discount or tier entry."
        )
        return _PERSONA_PREFIX.get(persona, "") + text

    ov = (overall_verdict or "").upper()
    if ov in ("REDUCE", "AVOID"):
        text = f"{ov.title()} — risk controls override the bullish case; trim or avoid new adds here."
        return _PERSONA_PREFIX.get(persona, "") + text

    if top_fail:
        blocker = _gate_plain_blocker(top_fail)
        if helps:
            text = f"Wait — {blocker}, even though {helps[0]['label'].lower()} still supports the longer thesis."
        else:
            text = f"Wait — mainly because {blocker}."
        return _PERSONA_PREFIX.get(persona, "") + text

    return _PERSONA_PREFIX.get(persona, "") + "Wait — not all model checks have cleared yet; see factors below."


def _build_wait_plain(
    *,
    gate_cleared: bool,
    entry_mode: str | None,
    one_answer_action_today: str | None,
    next_trigger: dict[str, Any] | None,
    regime_transition_days: int | None,
    assessment_pct: float,
    gates: list[dict[str, Any]],
    rsi: float | None,
    st_band: dict | None,
    current_price: float | None,
    trigger_buy: str | None,
    earnings_days: int | None,
    catalyst: dict[str, Any] | None,
    persona: Persona = "scout",
    required_mos_pct_value: float | None = None,
) -> str | None:
    if gate_cleared and entry_mode == "full_go":
        return None
    action = (one_answer_action_today or "").lower()
    if action == "enter_now" and gate_cleared:
        return None

    parts: list[str] = []

    est = None
    if isinstance(next_trigger, dict):
        est = next_trigger.get("estimated_days")
        headline = str(next_trigger.get("headline") or "").strip()
        if headline:
            parts.append(headline.rstrip(".") + ".")
        if est is not None:
            parts.append(f"Model estimate: {_days_to_plain(est)}.")

    if regime_transition_days and (est is None or int(regime_transition_days) < int(est or 999)):
        parts.append(f"Regime shift may take {_days_to_plain(regime_transition_days)}.")

    val_gate = next((g for g in gates if g.get("id") == "valuation"), None)
    val_req = required_mos_pct_value if required_mos_pct_value is not None else VALUATION_GATE_PASS_PCT
    if val_gate and not val_gate.get("pass") and assessment_pct < val_req:
        gap = max(0.0, val_req - assessment_pct)
        if gap >= 3:
            if persona == "owner":
                parts.append(
                    f"This tranche needs ~{gap:.0f}% more discount to fair value — deploy the next dollar there, not before."
                )
            else:
                parts.append(
                    f"Full-size entry needs ~{gap:.0f}% more discount — that is a deeper "
                    "price than the nearby buy zone, which is a starter watch at most."
                )

    mom_gate = next((g for g in gates if g.get("id") == "momentum"), None)
    rv = float(rsi) if rsi is not None else None
    if persona != "owner" and ((mom_gate and not mom_gate.get("pass")) or (rv is not None and rv >= 50)):
        parts.append("Momentum usually cools within 1–2 weeks on a small dip or sideways chop.")
    elif persona == "owner" and mom_gate and not mom_gate.get("pass"):
        parts.append("Near-term momentum is hot, but that's noise for a multi-year hold — valuation is what matters here.")

    if st_band and current_price:
        lo, hi = st_band.get("low"), st_band.get("high")
        try:
            lo_f, hi_f, cp = float(lo), float(hi), float(current_price)
            if lo_f > 0 and hi_f > 0:
                if persona == "owner":
                    if cp > hi_f:
                        parts.append(
                            f"Planned add ceiling ≤ ${hi_f:.2f} — any print at or below that level counts (gaps through the window included)."
                        )
                    else:
                        parts.append(
                            f"Price is at or below the T1 ceiling ${hi_f:.2f} — waiting on gates, not a tighter band window."
                        )
                elif cp > hi_f:
                    parts.append(
                        f"Planned entry zone ${lo_f:.2f}–${hi_f:.2f} — reach it on a normal pullback (often days to a few weeks)."
                    )
                elif lo_f <= cp <= hi_f:
                    parts.append(
                        f"Price is already in the entry band ${lo_f:.2f}–${hi_f:.2f} — waiting on gates, not price."
                    )
                elif cp < lo_f:
                    parts.append(
                        f"Spot is below the entry band ${lo_f:.2f}–${hi_f:.2f} — first add is at/through the floor, not a bounce back into the window."
                    )
        except (TypeError, ValueError):
            pass

    if trigger_buy and trigger_buy.strip():
        tb = trigger_buy.strip()
        if len(tb) < 120:
            parts.append(f"Trigger: {tb}.")

    if earnings_days is not None and 0 < int(earnings_days) <= 21:
        d = int(earnings_days)
        parts.append(
            f"Earnings in {d} day{'s' if d != 1 else ''} — many traders wait for the report before sizing up."
        )

    if isinstance(catalyst, dict) and catalyst.get("active"):
        note = catalyst.get("override_note") or catalyst.get("headline")
        if isinstance(note, str) and note.strip():
            parts.append(note.strip())

    if not parts:
        if action in ("wait_for_pullback", "hold", "trim", "no_new_position") or not gate_cleared:
            return "No fixed calendar date — watch gate status daily; setups like this often resolve within 2–4 weeks."
        return None

    seen: set[str] = set()
    deduped: list[str] = []
    for p in parts:
        key = p.lower()[:60]
        if key not in seen:
            seen.add(key)
            deduped.append(p)
    return " ".join(deduped[:4])


def build_signal_reason_summary(
    *,
    ticker: str | None = None,
    gates: list[dict[str, Any]],
    assessment_pct: float,
    current_price: float | None = None,
    fair_value: float | None = None,
    regime_bull_pct: float | None = None,
    market_regime_bull_pct: float | None = None,
    pattern_score: float | None = None,
    rsi: float | None = None,
    short_ml_prob: float | None = None,
    overall_verdict: str | None = None,
    entry_mode: str | None = None,
    gate_cleared: bool = False,
    next_trigger: dict[str, Any] | None = None,
    regime_transition_days: int | None = None,
    st_band: dict | None = None,
    trigger_buy: str | None = None,
    confidence: dict[str, Any] | None = None,
    catalyst: dict[str, Any] | None = None,
    earnings_days: int | None = None,
    global_market_regime: str | None = None,
    one_answer_action_today: str | None = None,
    persona: Persona = "scout",
    required_mos_pct_value: float | None = None,
    near_bottom: dict[str, Any] | None = None,
    move_narrative: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build retail signal reasoning payload.

    persona tailors headline/wait_plain phrasing for the Scout (tactical),
    Swing (few-week), or Owner (long-term accumulate) view of the same ticker —
    the underlying gates are shared, but the framing and time horizon differ.
    near_bottom / move_narrative are optional pass-throughs (signals.pattern_signals
    near_bottom_score and signals.price_move_narrative) folded into the payload so
    ticker detail has one place to read "is this near a bottom" and "why did it move."
    """
    conf_factors = _factors_from_confidence(confidence)
    gate_factors = _factors_from_gates(
        gates,
        assessment_pct=assessment_pct,
        regime_bull_pct=regime_bull_pct,
        market_regime_bull_pct=market_regime_bull_pct,
        pattern_score=pattern_score,
        rsi=rsi,
        short_ml_prob=short_ml_prob,
        global_market_regime=global_market_regime,
    )
    factors = _merge_factors(conf_factors, gate_factors)

    helps = [f for f in factors if f.get("stance") == "helps"]
    hurts = [f for f in factors if f.get("stance") == "hurts"]

    headline = _build_headline(
        gate_cleared=gate_cleared,
        entry_mode=entry_mode,
        factors=factors,
        gates=gates,
        overall_verdict=overall_verdict,
        persona=persona,
    )
    wait_plain = _build_wait_plain(
        gate_cleared=gate_cleared,
        entry_mode=entry_mode,
        one_answer_action_today=one_answer_action_today,
        next_trigger=next_trigger,
        regime_transition_days=regime_transition_days,
        assessment_pct=assessment_pct,
        gates=gates,
        rsi=rsi,
        st_band=st_band,
        current_price=current_price,
        trigger_buy=trigger_buy,
        earnings_days=earnings_days,
        catalyst=catalyst,
        persona=persona,
        required_mos_pct_value=required_mos_pct_value,
    )

    sym = (ticker or "This name").upper()
    supporting: list[str] = []
    if helps:
        supporting.append(
            f"{helps[0]['label']}: {helps[0]['summary']}"
        )
    if len(helps) > 1:
        supporting.append(f"Also positive: {helps[1]['label'].lower()}.")
    blocking: list[str] = []
    for g in gates:
        if g.get("id") in PRIMARY_GATE_IDS and not g.get("pass"):
            blocking.append(f"{g.get('label', g.get('id'))}: {g.get('detail', '')}")
    if hurts and not blocking:
        blocking.append(f"{hurts[0]['label']}: {hurts[0]['summary']}")

    # Near-bottom/breakout reversal signal (signals.pattern_signals.near_bottom_score) —
    # a genuinely strong read (score >= 50) is worth surfacing alongside the gate factors.
    nb_signals = (near_bottom or {}).get("signals") or []
    if isinstance(near_bottom, dict) and (near_bottom.get("score") or 0) >= 50 and nb_signals:
        label = "Reversal setup" if near_bottom.get("mode") == "bottom_reversal" else "Trend continuation"
        supporting.insert(0, f"{label}: {nb_signals[0]}")

    return {
        "ticker": sym if ticker else None,
        "persona": persona,
        "headline": headline,
        "wait_plain": wait_plain,
        "factors": factors,
        "supporting": supporting[:3],
        "blocking": blocking[:3],
        "top_driver": helps[0]["id"] if helps else None,
        "top_blocker": (
            next((g.get("id") for g in gates if g.get("id") in PRIMARY_GATE_IDS and not g.get("pass")), None)
            or (hurts[0]["id"] if hurts else None)
        ),
        "fair_value": round(float(fair_value), 2) if fair_value else None,
        "assessment_pct": round(float(assessment_pct), 1),
        "near_bottom": near_bottom,
        "move_narrative": move_narrative,
    }
