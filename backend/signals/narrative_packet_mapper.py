"""
Maps our existing ticker-detail engine output onto narrative_waterfall.SignalPacket.

Source data (all already computed elsewhere — nothing here re-derives a signal,
it only translates field names/shapes):
    ticker_detail   full response dict from backend/api/ticker_detail.py::get_ticker_detail()
                    (has top-level current_price/rsi/pattern_score/regime_bull_pct/
                    cross_asset/confidence, plus the nested investor_summary dict)
    mode            "scout" | "swing" | "owner" — selects which horizon
                    (short/medium/long) and persona framing to build the packet for,
                    matching the scout->short / swing->medium / owner->long convention
                    already used by signal_reason_by_persona in ticker_detail.py.

See docs comment block at the top of narrative_waterfall.py for the gap list this
mapper resolves (gate id renaming, entry_mode disambiguation, invalidation
fallback, EV computation, trend derivation, asof).
"""
from __future__ import annotations

import re
from typing import Any

from signals.narrative_waterfall import Band, Gate, Scenario, SignalPacket, full_size_price_from_mos
from signals.retail_action_payload import (
    ST_ML_GATE,
    VALUATION_GATE_PASS_PCT,
    required_mos_pct as _ladder_mos_pct,
    tranche_idx_from_tier_id,
)
from signals.time_et import today_est

_HORIZON_BY_MODE = {"scout": "short", "swing": "medium", "owner": "long"}

# Our retail_action gate `id` -> the narrative packet's canonical gate name.
_GATE_ID_TO_CANONICAL = {
    "valuation": "valuation",
    "regime": "market_weather",
    "momentum": "momentum_chop",
    "ml": "ml_probability",
    "confidence": "confidence",
}

# Regime-weather bull-probability threshold used elsewhere in this app
# (CLAUDE.md: UP regime >= 60) — reused here only as narrative context, not
# to recompute the regime itself.
_MARKET_WEATHER_NEED_PCT = 60.0


def _band_from_entry_zone(entry_zone: dict | None) -> Band | None:
    if not isinstance(entry_zone, dict):
        return None
    lo, hi = entry_zone.get("low"), entry_zone.get("high")
    if lo is None or hi is None:
        return None
    return Band(float(lo), float(hi))


def _band_from_lo_hi(d: dict | None) -> Band | None:
    if not isinstance(d, dict):
        return None
    lo, hi = d.get("low"), d.get("high")
    if lo is None or hi is None:
        return None
    return Band(float(lo), float(hi))


def _catch_levels(entry_zone: dict | None) -> list[float]:
    if not isinstance(entry_zone, dict):
        return []
    levels = entry_zone.get("levels") or []
    return [float(lv["price"]) for lv in levels if isinstance(lv, dict) and lv.get("price") is not None]


def _bridge_band_and_levels(horizon: dict, mode: str) -> tuple[Band | None, list[float]]:
    """Bridge sleeve lives under entry_zone.spot_position (short/medium) or
    entry_tiers.spot_position (long/owner) — same shape, different parent key."""
    parent_key = "entry_tiers" if mode == "owner" else "entry_zone"
    spot_position = (horizon.get(parent_key) or {}).get("spot_position") or {}
    bridge = spot_position.get("bridge_band")
    if not bridge:
        cross_gap = spot_position.get("cross_gap") or {}
        bridge = cross_gap.get("bridge_band")
    band = _band_from_lo_hi(bridge)
    levels = []
    if isinstance(bridge, dict):
        for lv in bridge.get("levels") or []:
            if isinstance(lv, dict) and lv.get("price") is not None:
                levels.append(float(lv["price"]))
    return band, levels


def _usable_live_floor(
    candidate: float | None,
    *,
    spot: float,
    entry_floor: float | None,
) -> float | None:
    """A live invalidation/stop must sit below spot and below the add-zone floor."""
    if candidate is None:
        return None
    px = float(candidate)
    if px <= 0:
        return None
    if spot > 0 and px >= spot:
        return None
    if entry_floor is not None and px >= float(entry_floor):
        return None
    return px


def _invalidation(horizon: dict, mode: str, stop_loss: float | None, spot: float) -> float | None:
    """Thesis-broken floor. Must sit below spot (and below owner entry floor).

    Commodity/index structural invalidation can land above spot or above T1 —
    that is reference-only. The packet uses the tactical stop in those cases
    so Layer 3 cannot say 'close above $X negates' when price is already above X.
    """
    ez = horizon.get("entry_zone") or {}
    floor = ez.get("low")
    floor_f = float(floor) if floor is not None else None

    struct_inv: float | None = None
    if mode == "owner":
        struct = ((horizon.get("entry_tiers") or {}).get("structural_invalidation")) or {}
        if struct.get("price") is not None:
            struct_inv = float(struct["price"])
    stop_f = float(stop_loss) if stop_loss is not None else None

    inv = _usable_live_floor(struct_inv, spot=spot, entry_floor=floor_f)
    if inv is None:
        inv = _usable_live_floor(stop_f, spot=spot, entry_floor=floor_f)
    if inv is None and stop_f is not None and spot > 0 and stop_f < spot:
        # Last resort: still never publish a floor on the wrong side of spot.
        inv = stop_f if floor_f is None or stop_f < floor_f else None
    return inv



def _stop_below_entry_floor(
    stop_loss: float | None,
    entry_band,
    spot: float,
) -> float | None:
    """Tactical stop must sit below the add-zone floor (never inside the band).

    Skip when spot is already above the band (Owner wait-above / stretch): stop
    then legitimately sits between spot and a deeper harmonized floor.
    """
    if stop_loss is None:
        return None
    stop = float(stop_loss)
    if entry_band is None:
        return stop
    # Wait-above: do not yank stop under a deep Owner floor.
    if spot > float(entry_band.hi) + 1e-6:
        return stop
    floor = float(entry_band.lo)
    if stop < floor - 1e-9:
        return stop
    buf = max(spot * 0.015, floor * 0.008, 0.05) if spot > 0 else max(floor * 0.008, 0.05)
    return round(floor - buf, 2)


def _owner_entry_band(horizons: dict, long_h: dict) -> Band | None:
    """T1 ceiling + floor at least as deep as swing/scout add levels."""
    band = _band_from_entry_zone(long_h.get("entry_zone"))
    if band is None:
        tiers = ((long_h.get("entry_tiers") or {}).get("tiers")) or []
        t1 = next((t for t in tiers if str(t.get("id")) == "T1"), None)
        if isinstance(t1, dict) and t1.get("high") is not None:
            lo = float(t1.get("low") or t1["high"])
            band = Band(lo, float(t1["high"]))
    if band is None:
        return None
    floors = [band.lo]
    for key in ("medium", "short"):
        ez = (horizons.get(key) or {}).get("entry_zone") or {}
        if ez.get("low") is not None:
            floors.append(float(ez["low"]))
        for lv in ez.get("levels") or []:
            if isinstance(lv, dict) and lv.get("price") is not None:
                floors.append(float(lv["price"]))
    return Band(min(floors), band.hi)


def _entry_mode(retail_action: dict) -> str:
    raw = (retail_action.get("entry_mode") or "").lower()
    if raw == "full_go":
        return "FULL"
    if raw == "hard_lock":
        return "WAIT"
    if raw == "starter_only":
        zone = retail_action.get("zone_context") or {}
        return "BRIDGE_ONLY" if zone.get("in_bridge_band") else "STARTER_ONLY"
    return "WAIT"


def _verdict(retail_action: dict) -> str:
    title = (retail_action.get("action_title") or "").strip().upper()
    return title.replace(" ", "_") if title else "WATCH_ZONE"


def _trend(regime_bull_pct: float | None) -> str:
    """UP/DOWN simplification — SignalPacket.trend has no NEUTRAL slot, so this
    collapses the app's real 3-way regime (CLAUDE.md: UP >=60, DOWN <=40, else
    NEUTRAL) into two buckets. Uses the >=60 boundary (not a naive >=50 split)
    so a marginal/NEUTRAL regime (e.g. 55%) doesn't get misclassified as "UP" —
    that misclassification previously made validate()'s "target below spot on
    UP trend" check fire for tickers whose long-horizon target is a fair-value
    anchor (legitimately below spot when a stock trades above fair value),
    not a bullish upside number."""
    return "UP" if (regime_bull_pct or 0) >= 60 else "DOWN"


def _unlock_conditions(gates: list[Gate]) -> list[str]:
    """Built from the final canonical gate list (post confidence-synthesis) —
    not just the primary 4 — because SignalPacket.validate() requires
    unlock_conditions to cover every failed gate in p.gates, confidence
    included. Sourcing this from only the primary raw gates left the
    synthesized confidence gate uncovered, so any ticker whose confidence
    gate failed got wrongly rejected as "blocked" (unlock_conditions missing
    failed gate 'confidence') even though nothing else was wrong."""
    out = []
    for g in gates:
        if not g.passed:
            label = g.name.replace("_", " ").title()
            out.append(f"{label} clears")
    return out


def _gate_detail(canonical: str, gate: dict, *, rsi, hmm_bull_pct, ml_prob_pct,
                  fused_confidence_pct, mos_pct=None, required_mos_pct=None) -> dict:
    """Structured numeric fields where cheaply available (renders the nicer
    GATE_TEMPLATES copy); `text` is always present as a safe fallback
    (narrative_waterfall.render_explanations degrades to it gracefully)."""
    detail: dict[str, Any] = {"text": gate.get("detail") or ""}
    if canonical == "momentum_chop" and rsi is not None:
        detail["rsi"] = float(rsi)
    elif canonical == "valuation":
        if mos_pct is not None:
            detail["mos_pct"] = float(mos_pct)
        if required_mos_pct is not None:
            detail["required_pct"] = float(required_mos_pct)
    elif canonical == "market_weather" and hmm_bull_pct is not None:
        detail["hmm_bull_pct"] = float(hmm_bull_pct)
        detail["need_pct"] = _MARKET_WEATHER_NEED_PCT
        detail["tape"] = "Bull" if hmm_bull_pct >= _MARKET_WEATHER_NEED_PCT else "Mixed"
    elif canonical == "ml_probability" and ml_prob_pct is not None:
        detail["ml_prob_pct"] = float(ml_prob_pct)
        # The real pass/fail bar (retail_action_payload.ST_ML_GATE) — NOT the
        # per-horizon ml_horizons[...].threshold_pct, which is a different
        # concept (the ML model's target gain threshold, not a probability
        # bar) and was previously mistakenly reused here, producing a
        # nonsensical "clears the 3% threshold" instead of the real ~25%.
        detail["threshold_pct"] = ST_ML_GATE
    elif canonical == "confidence" and fused_confidence_pct is not None:
        detail["conf_pct"] = float(fused_confidence_pct)
    return detail


def _earnings_card_from_detail(ticker_detail: dict) -> dict | None:
    """Always surface next/last earnings when the calendar says it matters."""
    earnings = ticker_detail.get("earnings")
    if not isinstance(earnings, dict):
        return None
    try:
        from signals.catalyst_detector import build_earnings_event_card
    except Exception:
        build_earnings_event_card = None
    if build_earnings_event_card is not None:
        card = build_earnings_event_card(
            ticker=str(ticker_detail.get("ticker") or ""),
            days_until=earnings.get("days_until"),
            days_since=earnings.get("days_since"),
            report_date=earnings.get("date") or earnings.get("report_date"),
        )
        if isinstance(card, dict) and card:
            card = dict(card)
            card.setdefault("source", "earnings_calendar")
            return card
    # Fallback when detector is unavailable
    days = earnings.get("days_until")
    try:
        d = int(days) if days is not None else None
    except (TypeError, ValueError):
        d = None
    if d is None or d < 0 or d > 21:
        return None
    when = "today" if d == 0 else f"in {d} day{'s' if d != 1 else ''}"
    date_bit = earnings.get("date") or earnings.get("report_date") or ""
    mech = f"Earnings {when}" + (f" ({date_bit})" if date_bit else "")
    return {
        "name": "Earnings",
        "event_type": "EARNINGS_CALENDAR",
        "direction": "neutral",
        "mechanism": mech,
        "watch": "Size down into the print",
        "horizon": "days",
        "source": "earnings_calendar",
        "date": date_bit or None,
    }


def _normalize_news_card(card: dict, *, source: str = "catalyst_card") -> dict:
    return {
        "name": card.get("name") or card.get("title"),
        "event_type": card.get("event_type") or card.get("type"),
        "direction": card.get("direction"),
        "mechanism": card.get("mechanism") or card.get("title") or card.get("headline"),
        "title": card.get("title") or card.get("headline"),
        "watch": card.get("watch"),
        "horizon": card.get("horizon"),
        "source": card.get("source") or source,
        "published_at": card.get("published_at") or card.get("asof") or card.get("date"),
        "age_hours": card.get("age_hours"),
        "date": card.get("date"),
    }


def _news_events_from_detail(ticker_detail: dict, investor: dict) -> list[dict]:
    """Advisory catalysts: earnings calendar + catalyst cards + headlines."""
    roadmap = investor.get("trade_roadmap") or {}
    layer = roadmap.get("news_sentiment_layer") or {}
    if not isinstance(layer, dict):
        layer = {}

    out: list[dict] = []
    seen: set[str] = set()

    def _add(card: dict | None) -> None:
        if not isinstance(card, dict):
            return
        row = _normalize_news_card(card, source=str(card.get("source") or "catalyst_card"))
        key = f"{row.get('event_type')}|{str(row.get('mechanism') or '')[:80].lower()}"
        if key in seen:
            return
        seen.add(key)
        out.append(row)

    _add(_earnings_card_from_detail(ticker_detail))

    cards = layer.get("catalyst_cards")
    if not isinstance(cards, list) or not cards:
        cards = ticker_detail.get("catalyst_cards")
    if isinstance(cards, list):
        for card in cards[:6]:
            _add(card if isinstance(card, dict) else None)

    headlines = layer.get("headlines") or ticker_detail.get("headlines") or []
    if isinstance(headlines, list):
        for h in headlines[:4]:
            if isinstance(h, dict):
                title = h.get("title") or h.get("headline")
                if not title:
                    continue
                _add({
                    "name": title,
                    "title": title,
                    "mechanism": title,
                    "event_type": h.get("event_type"),
                    "direction": h.get("direction") or h.get("label"),
                    "published_at": h.get("published_at") or h.get("date"),
                    "source": "headline",
                })
            elif isinstance(h, str) and h.strip():
                _add({
                    "name": h.strip()[:180],
                    "title": h.strip()[:180],
                    "mechanism": h.strip()[:180],
                    "source": "headline",
                })

    return out[:8]


def _driver_context_from_detail(ticker_detail: dict, conf: dict) -> dict:
    """Attach insider / short-interest / light macro hooks for catalyst matrix."""
    ctx: dict = {}
    if not isinstance(conf, dict):
        conf = {}

    # Live confidence payload uses short_interest + penalty_audit + breakdown.
    si = conf.get("short_interest") or ticker_detail.get("short_interest")
    if isinstance(si, dict) and si:
        ctx["short_interest"] = si

    insider: dict = {}
    pa = conf.get("penalty_audit") or conf.get("penalty_audit") or {}
    sell_pen = {}
    if isinstance(pa, dict):
        sell_pen = (
            pa.get("insider_sell_penalty")
            or pa.get("insider_sell_penalty")
            or {}
        )
    if isinstance(sell_pen, dict) and sell_pen.get("triggered"):
        insider = {"signal": "selling", "sell_count": 3}
    else:
        bd = (
            (conf.get("breakdown") or {}).get("insider_signal")
            or (conf.get("breakdown") or {}).get("insider_signal")
            or {}
        )
        label = str(bd.get("label") or "").lower()
        if "net selling" in label or ("selling" in label and "buying" not in label):
            sells = None
            m = re.search(r"([\d,]+)\s+shares\s+sold", label)
            if m:
                try:
                    sells = int(m.group(1).replace(",", ""))
                except ValueError:
                    sells = None
            insider = {
                "signal": "selling",
                "sell_count": 3 if sells is None else max(3, 1),
                "label": bd.get("label"),
            }
    stats = (
        ticker_detail.get("insider_stats")
        or ticker_detail.get("insider_stats")
        or {}
    )
    if isinstance(stats, dict) and not insider:
        sell_ratio = stats.get("sell_ratio") or stats.get("totalSellRatio")
        try:
            sr = float(sell_ratio) if sell_ratio is not None else None
        except (TypeError, ValueError):
            sr = None
        if sr is not None and sr > 1.0:
            sr = sr / 100.0
        if sr is not None and sr >= 0.6:
            insider = {"signal": "selling", "sell_count": 3}
    if insider:
        ctx["insider"] = insider

    macro = ticker_detail.get("macro") if isinstance(ticker_detail.get("macro"), dict) else {}
    if macro:
        ctx["macro"] = macro

    cal = (
        ticker_detail.get("economic_calendar")
        or ticker_detail.get("macro_events")
        or ticker_detail.get("economic_calendar")
    )
    if isinstance(cal, list) and cal:
        ctx["economic_calendar"] = cal[:6]

    return ctx


def to_packet(ticker_detail: dict, mode: str, scenarios_raw: list[dict] | None = None) -> SignalPacket:
    """Build a SignalPacket for one persona (`mode`) from an already-computed
    ticker_detail response, plus the scenario list from price_targets.py's
    `_build_scenarios()` output (not part of the ticker_detail payload itself —
    pass `run_price_targets(...)["scenarios"]` in, or omit for no scenario data).
    Raises only on truly malformed input (missing ticker/current_price) —
    everything else degrades to None/[] so validate() (not an exception) is
    what flags a bad packet."""
    ticker = ticker_detail["ticker"]
    investor = ticker_detail.get("investor_summary") or {}
    retail_action = investor.get("retail_action") or {}
    conf = ticker_detail.get("confidence") or {}
    hmm = conf.get("hmm") or {}
    options = conf.get("options") or {}
    nlp = conf.get("nlp") or {}
    ml_horizons = conf.get("ml_horizons") or {}
    valuation_deck = investor.get("valuation_deck") or {}
    street = valuation_deck.get("street") or {}
    cross_asset = ticker_detail.get("cross_asset") or {}

    horizon_key = _HORIZON_BY_MODE.get(mode, "short")
    horizon = (investor.get("horizons") or {}).get(horizon_key) or {}

    spot = float(ticker_detail.get("current_price") or 0)
    regime_bull_pct = investor.get("regime_bull_pct")
    rsi = ticker_detail.get("rsi")
    fused_confidence_pct = (
        round(float(conf["confidence"]) * 100, 1) if conf.get("confidence") is not None else None
    )
    ml_prob_pct = horizon.get("ml_prob")
    ml_threshold_pct = (ml_horizons.get(horizon_key) or {}).get("threshold_pct")
    hmm_bull_pct = round(float(regime_bull_pct or 0.0), 1)
    mos_pct = retail_action.get("assessment_pct")
    if mos_pct is not None:
        mos_pct = float(mos_pct)
    fair_value = investor.get("fair_value")
    if fair_value is not None:
        fair_value = float(fair_value)

    if mode == "owner":
        long_spot = ((horizon.get("entry_tiers") or {}).get("spot_position")) or {}
        tranche_idx = tranche_idx_from_tier_id(
            long_spot.get("active_tier_id") or long_spot.get("tier_id") or long_spot.get("next_add_tier_id")
        )
        required_mos = float(_ladder_mos_pct(tranche_idx, regime_bull_pct))
    else:
        # Swing/scout "full-size" copy uses the historical 25% bar (same as
        # signal_reason_summary when required_mos_pct_value is omitted).
        required_mos = float(VALUATION_GATE_PASS_PCT)

    full_size_price = full_size_price_from_mos(fair_value, required_mos)

    # ── gates: rename ids to canonical names, synthesize confidence gate ──
    raw_gates = list(retail_action.get("gates") or [])
    gates: list[Gate] = []
    seen_canonical: set[str] = set()
    for g in raw_gates:
        canonical = _GATE_ID_TO_CANONICAL.get(g.get("id"))
        if not canonical:
            continue
        gates.append(Gate(
            name=canonical,
            passed=bool(g.get("pass")),
            detail=_gate_detail(
                canonical, g, rsi=rsi, hmm_bull_pct=hmm_bull_pct,
                ml_prob_pct=ml_prob_pct, fused_confidence_pct=fused_confidence_pct,
                mos_pct=mos_pct, required_mos_pct=required_mos,
            ),
        ))
        seen_canonical.add(canonical)
    if "confidence" not in seen_canonical and fused_confidence_pct is not None:
        gates.append(Gate(
            name="confidence",
            passed=fused_confidence_pct >= 50.0,
            detail={"conf_pct": fused_confidence_pct,
                    "text": f"Fused model confidence {fused_confidence_pct:.0f}%"},
        ))

    entry_band = _band_from_entry_zone(horizon.get("entry_zone"))
    if mode == "owner":
        entry_band = _owner_entry_band(investor.get("horizons") or {}, horizon) or entry_band
    short_h = (investor.get("horizons") or {}).get("short") or {}
    st_band = _band_from_entry_zone(short_h.get("entry_zone"))
    if mode == "scout":
        st_band = entry_band or st_band
    bridge_band, bridge_levels = _bridge_band_and_levels(horizon, mode)
    stop_loss = horizon.get("stop_loss")
    if stop_loss is not None:
        stop_loss = _stop_below_entry_floor(float(stop_loss), entry_band, spot)
    inv = _invalidation(horizon, mode, stop_loss, spot)
    rr = None
    if horizon.get("risk_reward") is not None:
        rr = float(horizon["risk_reward"])
    if stop_loss is not None and horizon.get("target") is not None and spot > float(stop_loss):
        tgt = float(horizon["target"])
        if tgt > spot:
            computed_rr = (tgt - spot) / (spot - float(stop_loss))
            rr = round(computed_rr, 2)

    scenarios = [
        Scenario(
            name=s.get("name") or s.get("scenario_type") or "Scenario",
            ret_pct=float(s.get("return_pct") or 0.0),
            prob_pct=round(float(s.get("probability") or 0.0) * 100, 1),
        )
        for s in (scenarios_raw or [])
        if isinstance(s, dict)
    ]

    return SignalPacket(
        ticker=ticker,
        mode=mode,
        asof=today_est(),
        spot=spot,
        trend=_trend(regime_bull_pct),
        verdict=_verdict(retail_action),
        score=int(round(investor.get("pattern_score") or 0)),
        gates=gates,
        entry_band=entry_band,
        stop=float(stop_loss) if stop_loss is not None else None,
        invalidation=inv,
        target=float(horizon["target"]) if horizon.get("target") is not None else None,
        rr=rr,
        st_band=st_band,
        bridge_band=bridge_band,
        bridge_levels=bridge_levels,
        catch_levels=_catch_levels(horizon.get("entry_zone")),
        entry_mode=_entry_mode(retail_action),
        max_tranche_pct=float(retail_action.get("max_sizing_pct") or 0.0),
        sector=str(ticker_detail.get("sector") or ""),
        fair_value=fair_value,
        mos_pct=mos_pct,
        required_mos_pct=required_mos,
        full_size_price=full_size_price,
        hmm_bull_pct=hmm_bull_pct,
        hmm_transition_pct=round(float(hmm.get("transition_probability") or 0.0) * 100, 1),
        rsi=float(rsi) if rsi is not None else None,
        ml_prob_pct=float(ml_prob_pct) if ml_prob_pct is not None else None,
        ml_threshold_pct=float(ml_threshold_pct) if ml_threshold_pct is not None else None,
        fused_confidence_pct=fused_confidence_pct,
        options_pc=options.get("pc_ratio"),
        options_class=((options.get("asset_narrative_meta") or {}).get("verdict") or options.get("options_label") or ""),
        options_score_pct=round(float(options["options_score"]) * 100, 1) if options.get("options_score") is not None else None,
        unlock_conditions=_unlock_conditions(gates),
        scenarios=scenarios,
        expected_value_pct=None,
        sensitivities=list(cross_asset.get("badges") or []),
        street_median=street.get("median_usd"),
        street_analysts=street.get("analyst_count"),
        street_bullish_pct=(street.get("ratings") or {}).get("bullish_pct"),
        news_sentiment=nlp.get("sentiment_label") or "",
        news_events=_news_events_from_detail(ticker_detail, investor),
        driver_context=_driver_context_from_detail(ticker_detail, conf),
    )
