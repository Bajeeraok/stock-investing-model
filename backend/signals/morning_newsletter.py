"""
Morning newsletter: one-place brief built from reconciled market context, macro, and portfolio.
Consumed by the dashboard and displayed in the Pre-market / Markets area.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

REGIME_PLAIN: dict[str, str] = {
    "Risk-On": "Favor small adds on pullbacks. Don't chase; use your levels.",
    "Neutral": "Hold core; skip big new buys until the trend is clearer.",
    "Risk-Off": "Tighten stops, trim size. Avoid new speculative entries — preserve capital.",
}


def _human_et_timestamp(iso_or_date: str | None) -> str:
    """Retail-friendly timestamp: Sunday May 25, 2026 · 10:08 PM ET."""
    if not iso_or_date:
        dt = datetime.now(_ET)
    else:
        try:
            dt = datetime.fromisoformat(str(iso_or_date).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_ET)
            dt = dt.astimezone(_ET)
        except (TypeError, ValueError):
            return str(iso_or_date)
    day = dt.strftime("%A %B %d, %Y")
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{day} · {hour12}:{dt.strftime('%M')} {ampm} ET"


def _spy_key_level_line(trigger_levels: dict | None, results: list[dict] | None) -> str:
    spy = ((trigger_levels or {}).get("levels") or {}).get("SPY") or {}
    trig = spy.get("primary_trigger")
    if trig is not None:
        try:
            p = float(trig)
            return f"Key level — SPY ${p:.0f} pivot: holds = add, breaks = pause entries."
        except (TypeError, ValueError):
            pass
    if results:
        by_ticker = {r.get("ticker"): r for r in results if not r.get("error") and r.get("ticker")}
        r = by_ticker.get("SPY")
        if r:
            support = r.get("support_level")
            st = r.get("st_band") if isinstance(r.get("st_band"), dict) else None
            if support is None and st:
                support = st.get("low")
            if support is not None:
                try:
                    p = float(support)
                    return f"Key level — SPY ${p:.0f} support: holds = add, breaks = pause entries."
                except (TypeError, ValueError):
                    pass
    return "Key level — watch SPY/QQQ support from Key levels below before sizing up."


def _portfolio_line(
    *,
    trim_candidates: list[dict] | None,
    earnings_risk_count: int,
    retail_briefing: dict | None,
    premarket_report: dict | None,
) -> str:
    parts: list[str] = []
    tc = trim_candidates or []
    if tc:
        tickers = [h.get("ticker") for h in tc[:4] if h.get("ticker")]
        if tickers:
            parts.append(f"Trim watch: {', '.join(tickers)} — weak scores; review before adding more")
    if earnings_risk_count and earnings_risk_count > 0:
        parts.append(
            f"{earnings_risk_count} holding(s) report this week — trim extended names before their reports"
        )
    pm = premarket_report or {}
    pm_bias = pm.get("bias")
    pm_score = pm.get("composite_score")
    if pm_bias and pm_score is not None and not tc:
        conf = pm.get("confidence")
        conf_str = f", conf {conf:.0%}" if conf is not None else ""
        parts.append(f"Pre-market {pm_bias} ({pm_score:+.2f}{conf_str})")
    db0 = (retail_briefing or {}).get("daily_briefing") or {}
    if db0.get("summary_sentence") and len(parts) < 2:
        parts.append(db0["summary_sentence"][:160])
    if not parts:
        return "Portfolio — follow model rules: add quality in entry zones; trim weak scores."
    return "Watch — " + " · ".join(parts[:2])


def _horizon_guidance(horizon: dict | None) -> str:
    if not horizon:
        return ""
    bullets = horizon.get("bullets") or []
    if bullets and bullets[0]:
        return str(bullets[0])
    return str(horizon.get("stance") or "")


def _regime_line_from_context(market_context: dict) -> str:
    quadrant = market_context.get("quadrant")
    primary = market_context.get("primary_message") or "Unified market read"
    guidance = _horizon_guidance(market_context.get("short_term"))

    if quadrant == "best_buy_zone":
        base = "Setup — Fear in bull market: best dip-buying zone historically."
        add = guidance or "Add quality at support; scale in, don't chase."
        return f"{base} {add}"
    if quadrant == "hold_and_trim":
        return f"Setup — {primary}. {guidance or 'Trim extended trades; hold core compounders.'}"
    if quadrant == "falling_knife":
        return f"Setup — {primary}. {guidance or 'Wait for stabilization before new entries.'}"
    if guidance:
        return f"Setup — {primary}. {guidance}"
    expl = (market_context.get("explanation") or "")[:140]
    return f"Setup — {primary}" + (f". {expl}" if expl else "")


def _regime_line_fallback(
    *,
    macro_regime: str | None,
    macro_analog: dict | None,
    regime_validation: dict | None,
) -> str:
    rv = regime_validation or {}
    rv_summary = ""
    if rv.get("validated") is True:
        rv_summary = f" ✓ validated ({rv.get('consensus_score', 0):.0%} consensus, {rv.get('days_stable', 0)}d stable)"
    elif rv.get("validated") is False:
        div = rv.get("divergence_severity", "")
        days = rv.get("days_stable", 0)
        rv_summary = (
            f" ⚠ unconfirmed ({days}d stable"
            + (f", {div.lower()} divergence" if div and div != "NONE" else "")
            + ")"
        )
    if macro_regime:
        return f"Regime — {macro_regime}{rv_summary}: {REGIME_PLAIN.get(macro_regime, '')}"
    if macro_analog and macro_analog.get("plain_language"):
        return f"Context — {macro_analog['plain_language'][:140]}"
    return "Regime — check macro and breadth before sizing up."


def _build_three_line_brief(
    *,
    market_context: dict | None,
    macro_regime: str | None,
    macro_analog: dict | None,
    regime_validation: dict | None,
    trim_candidates: list[dict] | None,
    earnings_risk_count: int,
    retail_briefing: dict | None,
    premarket_report: dict | None,
    trigger_levels: dict | None,
    results: list[dict] | None,
    forward_tracking: dict | None,
    market_regime: dict | None,
) -> list[str]:
    """Three distinct lines: regime/setup · portfolio · key level."""
    if market_context:
        line1 = _regime_line_from_context(market_context)
    else:
        line1 = _regime_line_fallback(
            macro_regime=macro_regime,
            macro_analog=macro_analog,
            regime_validation=regime_validation,
        )

    line2 = _portfolio_line(
        trim_candidates=trim_candidates,
        earnings_risk_count=earnings_risk_count,
        retail_briefing=retail_briefing,
        premarket_report=premarket_report,
    )

    line3 = _spy_key_level_line(trigger_levels, results)
    if market_context and market_context.get("quadrant") != "best_buy_zone":
        risk_bits: list[str] = []
        if market_regime and market_regime.get("rotation_risk") == "High":
            risk_bits.append("Rotation risk elevated — favor holds over new tech adds")
        ft0 = forward_tracking or {}
        sb0 = ft0.get("summary_by_signal") or {}
        ha0 = sb0.get("HOLD/ADD")
        if isinstance(ha0, dict) and ha0.get("hit_rate_pct") is not None and ha0.get("n_observations"):
            risk_bits.append(
                f"Forward 20d ADD hit rate {ha0['hit_rate_pct']:.0f}% (n={ha0['n_observations']})"
            )
        if risk_bits and line3.startswith("Key level"):
            line3 = line3 + " · " + risk_bits[0]

    return [line1, line2, line3]


def _build_market_pulse(
    *,
    market_context: dict | None,
    macro_regime: str | None,
    macro_analog: dict | None,
    market_regime: dict | None,
) -> list[str]:
    if market_context:
        items: list[str] = []
        # Master context banner covers primary/explanation — pulse only adds net-new detail.
        coexist = market_context.get("coexistence_note")
        if coexist and coexist not in (market_context.get("explanation") or ""):
            items.append(str(coexist))
        st = market_context.get("short_term") or {}
        st_guidance = _horizon_guidance(st)
        line1_hint = _regime_line_from_context(market_context)
        if st_guidance and st_guidance not in line1_hint:
            items.append(f"Short-term: {st_guidance}")
        if market_regime and market_regime.get("rotation_risk") == "High":
            items.append("Rotation risk elevated — step down aggressive tech adds.")
        return items

    pulse_items: list[str] = []
    if macro_regime:
        pulse_items.append(f"Macro: {macro_regime} — {REGIME_PLAIN.get(macro_regime, '')}")
    if macro_analog and macro_analog.get("plain_language"):
        pulse_items.append(macro_analog["plain_language"])
    if market_regime:
        rot = market_regime.get("rotation_risk")
        if rot:
            pulse_items.append(f"Rotation risk: {rot}. High = step down tech adds, favor holds.")
    return pulse_items


def _build_action_items(
    *,
    market_context: dict | None,
    macro_regime: str | None,
    market_regime: dict | None,
    earnings_risk_count: int,
    retail_briefing: dict | None,
    model_rules: dict | None,
) -> list[str]:
    mr = model_rules or {}
    add_pct = int(float(mr.get("add_min_confidence", 70)))
    trim_pct = int(float(mr.get("trim_max_confidence", 30)))
    items: list[str] = []

    if market_context:
        quadrant = market_context.get("quadrant")
        st = market_context.get("short_term") or {}
        mt = market_context.get("medium_term") or {}
        st_guidance = _horizon_guidance(st)
        mt_guidance = _horizon_guidance(mt)
        if st_guidance:
            items.append(st_guidance)
        if mt_guidance and mt_guidance != st_guidance:
            items.append(f"Medium-term: {mt_guidance}")
        if quadrant == "best_buy_zone":
            items.append("New positions: quality names at support only — avoid speculative entries.")
        elif macro_regime == "Risk-Off":
            items.append("Avoid new speculative entries; tighten stops on tactical trades.")
    else:
        if macro_regime == "Risk-Off":
            items.append("Reduce new buys; tighten stops. Avoid speculative new entries.")

    if market_regime and market_regime.get("rotation_risk") == "High":
        items.append("Tech stepped down — favor holds over new adds.")
    if earnings_risk_count and earnings_risk_count > 0:
        items.append("Avoid new entries in names with earnings this week.")
    if retail_briefing and (retail_briefing.get("drawdown_guard") or retail_briefing.get("concentration", {}).get("message")):
        if retail_briefing.get("drawdown_guard"):
            items.append(retail_briefing["drawdown_guard"])
        conc = retail_briefing.get("concentration") or {}
        if conc.get("message"):
            items.append(conc["message"])
    if not items:
        items.append(
            f"Add only when confidence ≥ {add_pct} and regime UP. "
            f"Trim when confidence ≤ {trim_pct} or regime DOWN."
        )
    return items[:6]


def _format_hold_vs_trade(hold_vs_trade: dict | None) -> tuple[str, str | None]:
    if not hold_vs_trade:
        return (
            "Fear in bull market = hold core.\n"
            "Trim only: positions up >20%, weak scores, or pre-earnings.",
            None,
        )
    lines = [hold_vs_trade.get("headline") or "Hold or trim?"]
    bullets = [str(b) for b in (hold_vs_trade.get("bullets") or [])[:3] if b]
    if bullets:
        lines.extend(bullets)
    elif hold_vs_trade.get("answer"):
        lines.append(str(hold_vs_trade["answer"]))
    return "\n".join(lines), None


def build_morning_newsletter(
    *,
    as_of_date: str | None = None,
    macro_regime: str | None = None,
    macro_analog: dict | None = None,
    market_regime: dict | None = None,
    retail_briefing: dict | None = None,
    earnings_risk_count: int = 0,
    forward_tracking: dict | None = None,
    results: list[dict] | None = None,
    model_rules: dict | None = None,
    trim_candidates: list[dict] | None = None,
    regime_validation: dict | None = None,
    premarket_report: dict | None = None,
    market_context: dict | None = None,
    hold_vs_trade: dict | None = None,
    trigger_levels: dict | None = None,
) -> dict[str, Any]:
    """
    Build a morning brief for the newsletter section.
    When market_context is provided (reconciled quadrant), all copy aligns with the hero panel.
    Returns { headline, date, date_display, three_line_brief, sections, action_items }.
    """
    date_str = as_of_date or datetime.now(_ET).strftime("%Y-%m-%d")
    date_display = _human_et_timestamp(as_of_date)
    sections: list[dict[str, Any]] = []
    pm = premarket_report or {}

    three_line = _build_three_line_brief(
        market_context=market_context,
        macro_regime=macro_regime,
        macro_analog=macro_analog,
        regime_validation=regime_validation,
        trim_candidates=trim_candidates,
        earnings_risk_count=earnings_risk_count,
        retail_briefing=retail_briefing,
        premarket_report=premarket_report,
        trigger_levels=trigger_levels,
        results=results,
        forward_tracking=forward_tracking,
        market_regime=market_regime,
    )

    pulse_items = _build_market_pulse(
        market_context=market_context,
        macro_regime=macro_regime,
        macro_analog=macro_analog,
        market_regime=market_regime,
    )
    if pulse_items:
        sections.append({"title": "Market pulse", "items": pulse_items})

    pm_bias = pm.get("bias")
    pm_score = pm.get("composite_score")
    pm_conf = pm.get("confidence")
    if pm_bias and pm_score is not None:
        pm_items: list[str] = []
        if market_context and market_context.get("coexistence_note"):
            pm_items.append(f"How to read pre-market vs regime: {market_context['coexistence_note']}")
        pm_items.append(
            f"Composite: {pm_bias} ({pm_score:+.2f})"
            + (f" — confidence {pm_conf:.0%}" if pm_conf is not None else "")
        )
        for label_key, items_key in [("↑ Bullish drivers", "top_bullish"), ("↓ Bearish drivers", "top_bearish")]:
            items_list = pm.get(items_key) or []
            if items_list:
                pm_items.append(f"{label_key}: {' · '.join(items_list[:2])}")
        for risk in (pm.get("key_risks") or [])[:2]:
            pm_items.append(f"⚠ {risk}")
        sections.append({"title": "Pre-market", "items": pm_items})

    mc = pm.get("market_catalysts") if isinstance(pm.get("market_catalysts"), dict) else {}
    if mc.get("summary_line"):
        cat_items: list[str] = [str(mc["summary_line"])]
        for ev in (mc.get("scheduled_today") or [])[:2]:
            if isinstance(ev, dict) and ev.get("name"):
                time_s = f"{ev['time_et']} ET · " if ev.get("time_et") else ""
                cat_items.append(f"{time_s}{ev['name']} ({ev.get('event_type', 'Macro')})")
        for t in (mc.get("tensions") or [])[:2]:
            if isinstance(t, dict) and t.get("message"):
                cat_items.append(f"⚠ {t['message']}")
        sections.append({"title": "Market catalysts", "items": cat_items[:5]})

    key_levels: list[str] = []
    if results:
        by_ticker = {r.get("ticker"): r for r in results if not r.get("error") and r.get("ticker")}
        for ticker in ("SPY", "QQQ"):
            r = by_ticker.get(ticker)
            if not r:
                continue
            try:
                close = r.get("close")
                if close is None:
                    continue
                line = f"{ticker}: ${float(close):.2f}"
                st = r.get("st_band") if isinstance(r.get("st_band"), dict) else None
                support = r.get("support_level")
                if support is None and st:
                    support = st.get("low")
                target = st.get("high") if st else None
                if support is not None:
                    line += f" · support ${float(support):.2f}"
                if target is not None:
                    line += f" · ST target ${float(target):.2f}"
                key_levels.append(line)
            except (TypeError, ValueError):
                continue
    if key_levels:
        sections.append({"title": "Key levels", "items": key_levels})

    focus_items: list[str] = []
    if earnings_risk_count and earnings_risk_count > 0:
        focus_items.append(
            f"{earnings_risk_count} holding(s) with earnings in the next 7 days — reduce size or wait for reaction."
        )
    db = (retail_briefing or {}).get("daily_briefing") or {}
    if db.get("summary_sentence"):
        focus_items.append(db["summary_sentence"])
    if db.get("in_entry_zone"):
        for e in db["in_entry_zone"][:3]:
            focus_items.append(
                f"{e.get('ticker', '')} in entry zone ${e.get('entry_low', 0):.2f}–${e.get('entry_high', 0):.2f}."
            )
    if db.get("stops_near"):
        for s in db["stops_near"][:2]:
            focus_items.append(
                f"{s.get('ticker', '')} near stop ${s.get('stop_loss', 0):.2f} — decide hold or trim."
            )
    if focus_items:
        sections.append({"title": "Today's focus", "items": focus_items})

    ft = forward_tracking or {}
    sb = ft.get("summary_by_signal") or {}
    if sb:
        model_items: list[str] = []
        for sig, data in list(sb.items())[:4]:
            if isinstance(data, dict):
                hr = data.get("hit_rate_pct")
                n = data.get("n_observations")
                avg = data.get("avg_return_20d_pct")
                if hr is not None and n is not None:
                    model_items.append(
                        f"{sig}: {hr:.0f}% hit rate (20d, n={n})"
                        + (f", avg {avg:+.2f}%" if avg is not None else "")
                    )
        if model_items:
            sections.append({"title": "Signal accuracy (20d)", "items": model_items})

    action_items = _build_action_items(
        market_context=market_context,
        macro_regime=macro_regime,
        market_regime=market_regime,
        earnings_risk_count=earnings_risk_count,
        retail_briefing=retail_briefing,
        model_rules=model_rules,
    )

    hold_teaser, hold_more = _format_hold_vs_trade(hold_vs_trade)

    master_context = None
    if market_context:
        master_context = {
            "quadrant": market_context.get("quadrant"),
            "primary_message": market_context.get("primary_message"),
            "explanation": market_context.get("explanation"),
            "coexistence_note": market_context.get("coexistence_note"),
            "temperature_label": market_context.get("temperature_label"),
            "regime_label": market_context.get("regime_label"),
            "hmm_bull_pct": market_context.get("hmm_bull_pct"),
        }

    return {
        "headline": f"Morning brief · {date_display}",
        "date": date_str,
        "date_display": date_display,
        "quadrant": (market_context or {}).get("quadrant"),
        "master_context": master_context,
        "three_line_brief": three_line[:3],
        "sections": sections,
        "action_items": action_items,
        "hold_vs_trade_teaser": hold_teaser,
        "hold_vs_trade_more": hold_more,
    }
