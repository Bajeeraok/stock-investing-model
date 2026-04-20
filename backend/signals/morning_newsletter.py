"""
Morning newsletter: one-place brief built from macro, regime, retail briefing, and forward tracking.
Consumed by the dashboard and displayed in the Pre-market / Markets area.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


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
) -> dict[str, Any]:
    """
    Build a morning brief for the newsletter section.
    Returns { headline, date, three_line_brief, sections, action_items }.
    """
    REGIME_PLAIN: dict[str, str] = {
        "Risk-On": "Favor small adds on pullbacks. Don't chase; use your levels.",
        "Neutral": "Hold core; skip big new buys until the trend is clearer.",
        "Risk-Off": "Tighten stops, trim size, no new YOLOs. Preserve capital.",
    }

    date_str = as_of_date or datetime.now().strftime("%Y-%m-%d")
    sections: list[dict[str, Any]] = []
    action_items: list[str] = []
    mr = model_rules or {}
    add_pct = int(float(mr.get("add_min_confidence", 70)))
    trim_pct = int(float(mr.get("trim_max_confidence", 30)))

    # —— Compressed 3-line decision UX (regime → actions → risk) ——
    three_line: list[str] = []
    # Line 1: regime + validation status
    rv = regime_validation or {}
    rv_summary = ""
    if rv.get("validated") is True:
        rv_summary = f" ✓ validated ({rv.get('consensus_score', 0):.0%} consensus, {rv.get('days_stable', 0)}d stable)"
    elif rv.get("validated") is False:
        div = rv.get("divergence_severity", "")
        days = rv.get("days_stable", 0)
        rv_summary = f" ⚠ unconfirmed ({days}d stable" + (f", {div.lower()} divergence" if div and div != "NONE" else "") + ")"
    if macro_regime:
        three_line.append(f"Regime — {macro_regime}{rv_summary}: {REGIME_PLAIN.get(macro_regime, '')}")
    elif macro_analog and macro_analog.get("plain_language"):
        three_line.append(f"Context — {macro_analog['plain_language'][:140]}")
    else:
        three_line.append("Regime — check macro and breadth before sizing up.")
    line2_parts: list[str] = []
    # Pre-market bias is the most time-sensitive morning signal — lead with it
    pm = premarket_report or {}
    pm_bias = pm.get("bias")
    pm_score = pm.get("composite_score")
    pm_conf = pm.get("confidence")
    if pm_bias and pm_score is not None:
        conf_str = f", conf {pm_conf:.0%}" if pm_conf is not None else ""
        line2_parts.append(f"Pre-market {pm_bias} ({pm_score:+.2f}{conf_str})")
    tc = trim_candidates or []
    if tc:
        tickers = [h.get("ticker") for h in tc[:4] if h.get("ticker")]
        if tickers:
            line2_parts.append(f"Trim watch: {', '.join(tickers)}")
    if earnings_risk_count and earnings_risk_count > 0:
        line2_parts.append(f"{earnings_risk_count} holding(s) report this week — avoid new adds there")
    db0 = (retail_briefing or {}).get("daily_briefing") or {}
    if db0.get("summary_sentence") and not line2_parts:
        line2_parts.append(db0["summary_sentence"][:160])
    if not line2_parts:
        line2_parts.append(f"Follow model rules: add ≥{add_pct}% confidence & UP regime; trim ≤{trim_pct}% or REDUCE/AVOID.")
    three_line.append("Today — " + " · ".join(line2_parts[:3]))
    risk_bits: list[str] = []
    if market_regime and market_regime.get("rotation_risk") == "High":
        risk_bits.append("Rotation risk elevated — favor holds over new tech adds")
    if macro_regime == "Risk-Off":
        risk_bits.append("Risk-off backdrop — tighten risk; no YOLOs")
    ft0 = forward_tracking or {}
    sb0 = ft0.get("summary_by_signal") or {}
    ha0 = sb0.get("HOLD/ADD")
    if isinstance(ha0, dict) and ha0.get("hit_rate_pct") is not None and ha0.get("n_observations"):
        risk_bits.append(
            f"Forward 20d ADD hit rate {ha0['hit_rate_pct']:.0f}% (n={ha0['n_observations']})"
        )
    # VIX from pre-market report
    vix_sig = next((s for s in (pm.get("signals") or []) if "VIX" in s.get("name", "")), None)
    if vix_sig and vix_sig.get("raw_value") and vix_sig.get("raw_value") != "N/A":
        vix_dir = vix_sig.get("direction", "")
        risk_bits.append(f"VIX {vix_sig['raw_value']} — {vix_dir.lower()}")
    if not risk_bits:
        risk_bits.append("Risk — use stops and position caps from Portfolio Doctor.")
    three_line.append(" · ".join(risk_bits) if len(risk_bits) > 1 else risk_bits[0])

    # —— Market pulse ——
    pulse_items: list[str] = []
    if macro_regime:
        pulse_items.append(f"Macro: {macro_regime} — {REGIME_PLAIN.get(macro_regime, '')}")
    if macro_analog and macro_analog.get("plain_language"):
        pulse_items.append(macro_analog["plain_language"])
    if market_regime:
        rot = market_regime.get("rotation_risk")
        if rot:
            pulse_items.append(f"Rotation risk: {rot}. High = step down tech adds, favor holds.")
    if pulse_items:
        sections.append({"title": "Market pulse", "items": pulse_items})

    # —— Pre-market engine snapshot ——
    if pm_bias and pm_score is not None:
        pm_items: list[str] = []
        pm_items.append(f"Composite: {pm_bias} ({pm_score:+.2f})" + (f" — confidence {pm_conf:.0%}" if pm_conf is not None else ""))
        for label_key, items_key in [("↑ Bullish drivers", "top_bullish"), ("↓ Bearish drivers", "top_bearish")]:
            items_list = pm.get(items_key) or []
            if items_list:
                pm_items.append(f"{label_key}: {' · '.join(items_list[:2])}")
        for risk in (pm.get("key_risks") or [])[:2]:
            pm_items.append(f"⚠ {risk}")
        sections.append({"title": "Pre-market", "items": pm_items})

    # —— Key levels (SPY / QQQ from results) ——
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

    # —— Today's focus ——
    focus_items: list[str] = []
    if earnings_risk_count and earnings_risk_count > 0:
        focus_items.append(f"{earnings_risk_count} holding(s) with earnings in the next 7 days — reduce size or wait for reaction.")
    db = (retail_briefing or {}).get("daily_briefing") or {}
    if db.get("summary_sentence"):
        focus_items.append(db["summary_sentence"])
    if db.get("in_entry_zone"):
        for e in db["in_entry_zone"][:3]:
            focus_items.append(f"{e.get('ticker', '')} in entry zone ${e.get('entry_low', 0):.2f}–${e.get('entry_high', 0):.2f}.")
    if db.get("stops_near"):
        for s in db["stops_near"][:2]:
            focus_items.append(f"{s.get('ticker', '')} near stop ${s.get('stop_loss', 0):.2f} — decide hold or trim.")
    if focus_items:
        sections.append({"title": "Today's focus", "items": focus_items})

    # —— Model view (forward tracking hit rate) ——
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
                    model_items.append(f"{sig}: {hr:.0f}% hit rate (20d, n={n})" + (f", avg {avg:+.2f}%" if avg is not None else ""))
        if model_items:
            sections.append({"title": "Signal accuracy (20d)", "items": model_items})

    # —— Action items (crisp bullets) ——
    if macro_regime == "Risk-Off":
        action_items.append("Reduce new buys; tighten stops. No YOLOs.")
    if market_regime and market_regime.get("rotation_risk") == "High":
        action_items.append("Tech stepped down — favor holds over new adds.")
    if earnings_risk_count and earnings_risk_count > 0:
        action_items.append("Avoid new entries in names with earnings this week.")
    if retail_briefing and (retail_briefing.get("drawdown_guard") or retail_briefing.get("concentration", {}).get("message")):
        if retail_briefing.get("drawdown_guard"):
            action_items.append(retail_briefing["drawdown_guard"])
        conc = retail_briefing.get("concentration") or {}
        if conc.get("message"):
            action_items.append(conc["message"])
    if not action_items:
        action_items.append(
            f"Add only when confidence ≥ {add_pct} and regime UP. "
            f"Trim when confidence ≤ {trim_pct} or regime DOWN."
        )

    # Retail: same theme as ticker One answer — teaser in newsletter UI + full panel in ticker detail
    hold_teaser = (
        "Unsure trim-and-rebuy vs hold 5–10 years? Tactics (targets, sell roadmap) differ from "
        "long-term strategy (tiers, fair value) — open any ticker for the full framework."
    )
    hold_more = (
        "Signals → pick a ticker → One answer → expand “Hold for years vs take profits”."
    )

    return {
        "headline": f"Morning brief · {date_str}",
        "date": date_str,
        "three_line_brief": three_line[:3],
        "sections": sections,
        "action_items": action_items[:6],
        "hold_vs_trade_teaser": hold_teaser,
        "hold_vs_trade_more": hold_more,
    }
