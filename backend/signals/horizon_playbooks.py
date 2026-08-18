"""
Horizon playbooks — swing (ST), position build (MT), thesis & tiers (LT).

Single orchestrator for ticker detail; levels from horizons.* (source of truth).
"""
from __future__ import annotations

from typing import Any

from signals.swing_setup import (
    _inside_band,
    _quality_label,
    _safe_float,
    build_swing_setup,
)


def _gate_summary(investor_out: dict[str, Any]) -> tuple[list[dict], int, int, str, bool]:
    retail = investor_out.get("retail_action") or {}
    gates = retail.get("gates") or []
    primary_ids = retail.get("primary_gate_ids") or ["valuation", "regime", "momentum", "ml"]
    primary = [g for g in gates if g.get("id") in primary_ids] or gates[:4]
    passed = sum(1 for g in primary if g.get("pass"))
    total = len(primary) or 4
    go_no_go = retail.get("go_no_go") or ("go" if passed == total else "no_go")
    return primary, passed, total, go_no_go, go_no_go == "go"


def _market_narrative(
    *,
    investor_out: dict[str, Any],
    response: dict[str, Any],
    market_context: dict | None,
    max_lines: int = 4,
) -> list[str]:
    cp = _safe_float(response.get("current_price")) or _safe_float(investor_out.get("current_price"))
    regime_bull = _safe_float(investor_out.get("regime_bull_pct"))
    fv = _safe_float(investor_out.get("fair_value"))
    high_52w = _safe_float(response.get("high_52w"))
    narrative: list[str] = []
    if cp and high_52w and high_52w > cp:
        pct_off = (high_52w - cp) / high_52w * 100
        if pct_off >= 3:
            narrative.append(f"Pulled back ~{pct_off:.0f}% from 52-week high — distinguish tape fear vs name-specific news.")
    if regime_bull is not None:
        if regime_bull >= 60:
            narrative.append(f"Bull regime intact (HMM ~{regime_bull:.0f}% bull) — supports building over weeks.")
        else:
            narrative.append(f"Regime cautious (HMM ~{regime_bull:.0f}% bull) — tranche slowly, keep reserve dry powder.")
    ctx = market_context or {}
    if ctx.get("quadrant") == "best_buy_zone":
        narrative.append("Market context: fear in a bull tape — historically a strong medium-term accumulation window.")
    elif ctx.get("primary_message"):
        narrative.append(str(ctx.get("primary_message")))
    if cp and fv and cp < fv:
        mos = (fv - cp) / cp * 100
        if mos >= 5:
            narrative.append(f"~{mos:.1f}% below model fair value — valuation supports patient adds.")
    return narrative[:max_lines]


def build_medium_setup(
    *,
    ticker: str,
    investor_out: dict[str, Any],
    current_price: float | None,
    response: dict[str, Any] | None = None,
    market_context: dict | None = None,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """Position build play sheet — levels from horizons.medium."""
    response = response or {}
    config = config or {}
    medium = (investor_out.get("horizons") or {}).get("medium") or {}
    ez = medium.get("entry_zone") or {}
    el, eh = _safe_float(ez.get("low")), _safe_float(ez.get("high"))
    stop = _safe_float(medium.get("stop_loss"))
    target = _safe_float(medium.get("target"))
    if el is None or eh is None or stop is None or target is None or current_price is None:
        return None

    cp = float(current_price)
    verdict = str(medium.get("verdict") or investor_out.get("overall_verdict") or "WATCH").upper()
    _, passed, total, go_no_go, all_go = _gate_summary(investor_out)
    inside = _inside_band(cp, el, eh)

    narrative = _market_narrative(
        investor_out=investor_out,
        response={**response, "current_price": cp},
        market_context=market_context,
    )
    ml = _safe_float(medium.get("ml_prob"))
    if ml is not None and ml >= 30:
        narrative.insert(0, f"Medium-term ML read ~{ml:.0f}% — position-build window if gates allow.")

    wait_triggers: list[str] = []
    if verdict in ("WAIT", "WATCH") and not inside:
        wait_triggers.append(f"Price inside entry band ${min(el, eh):.2f}–${max(el, eh):.2f} before tranche 1.")
    if not all_go:
        wait_triggers.append("At least 3 of 4 primary gates green — see header.")
    if not wait_triggers and verdict == "WAIT":
        wait_triggers.append("Medium verdict WAIT — build only on defined pullbacks, not chase.")

    can_build = verdict in ("BUY", "STRONG BUY", "WATCH") and passed >= max(2, total - 1)
    if verdict == "WAIT":
        can_build = False

    risk_cfg = (config.get("risk_sizing") or {}) if isinstance(config.get("risk_sizing"), dict) else {}
    position_pct = float(risk_cfg.get("medium_position_pct") or 8.0)
    example_portfolio = 50_000.0
    sizing_block: dict[str, Any] | None = None
    if can_build:
        notional = example_portfolio * (position_pct / 100.0)
        entry_mid = (el + eh) / 2.0
        shares = int(notional / entry_mid) if entry_mid > 0 else 0
        sizing_block = {
            "rule": f"Target ~{position_pct:.0f}% of portfolio for this name over 3–6 months (tranche in).",
            "example_portfolio_usd": example_portfolio,
            "max_loss_usd": round(notional * 0.15, 0),
            "risk_per_share_usd": round(max(cp - stop, 0), 2),
            "shares_example": shares,
            "notional_usd": round(notional, 0),
            "scale_in": [
                f"Tranche 1 (~40%): ~{max(1, int(shares * 0.4))} shares inside ${min(el, eh):.2f}–${max(el, eh):.2f}.",
                f"Tranche 2 (~30%): add on 3–5% pullback toward ${min(el, eh):.2f}.",
                f"Tranche 3 (~30%): reserve — deploy only if gates stay constructive.",
            ],
        }

    add_triggers = [
        f"Scale inside ${min(el, eh):.2f}–${max(el, eh):.2f} over weeks — not one shot.",
        "Medium ML and regime stay constructive on each tranche.",
    ]
    exit_triggers = [
        f"Close below stop ${stop:.2f} — pause new tranches; review thesis.",
        f"At target ${target:.2f}: trim 25–40% of tactical build; hold core if invest intent.",
    ]
    reduce_triggers: list[str] = []
    earnings = response.get("earnings") if isinstance(response.get("earnings"), dict) else None
    earnings_block: dict[str, Any] | None = None
    if earnings:
        days = earnings.get("days_until")
        try:
            di = int(days) if days is not None else None
        except (TypeError, ValueError):
            di = None
        if di is not None and di <= 21:
            reduce_triggers.append(f"{ticker} reports in {di}d — slow tranche 2/3 until after reaction.")
        if di is not None or earnings.get("date"):
            earnings_block = {
                "report_date": earnings.get("date") or earnings.get("report_date"),
                "days_until": di,
                "action_plan": [
                    "Position build is structural — not an earnings bet.",
                    "Pause new tranches 5 sessions before report if already extended.",
                    "Resume build only if post-earnings gates still pass.",
                ],
            }

    rr = None
    if cp > stop and target > cp:
        rr = round((target - cp) / (cp - stop), 2)

    headline = (
        "Position build — scale in over 3–6 months"
        if can_build
        else "Build plan forming — wait for band + gates"
    )

    return {
        "active": True,
        "horizon": "medium",
        "kind": "position_build",
        "title": "Position build",
        "ticker": ticker,
        "go_no_go": go_no_go if can_build else "no_go",
        "setup_quality": {"passed": passed, "total": total, "label": _quality_label(passed, total)},
        "headline": headline,
        "setup_narrative": narrative,
        "inside_entry_band": inside,
        "trade": {
            "entry_low": round(min(el, eh), 2),
            "entry_high": round(max(el, eh), 2),
            "stop": round(stop, 2),
            "target_1": round(target, 2),
            "target_2": None,
            "timeline_weeks": "12–26",
            "current_price": round(cp, 2),
        },
        "sizing": sizing_block,
        "triggers": {
            "add": add_triggers if can_build else [],
            "exit": exit_triggers,
            "reduce": reduce_triggers,
            "wait": wait_triggers if not can_build else [],
        },
        "earnings_caveat": earnings_block,
        "thesis_breaks": [
            "Medium verdict flips to WAIT with failing gates for 2+ weeks.",
            f"{ticker} guidance cut or sector rotation away from your thesis.",
            "Dashboard credit stress + regime flip — pause tranches.",
        ],
        "risk_reward": {
            "ratio_target_1": rr,
            "risk_pct": round((cp - stop) / cp * 100, 1) if cp > stop else None,
            "honest_note": "Position build favors time + tranches over perfect entry timing.",
        },
        "disclaimer": "Decision support only — educational position-build framework, not financial advice.",
    }


def build_long_setup(
    *,
    ticker: str,
    investor_out: dict[str, Any],
    current_price: float | None,
    response: dict | None = None,
    market_context: dict | None = None,
) -> dict[str, Any] | None:
    """Thesis & tiers compact card — long horizon entry tiers + hold-vs-trade."""
    response = response or {}
    long_h = (investor_out.get("horizons") or {}).get("long") or {}
    tiers_data = long_h.get("entry_tiers") or {}
    tiers = tiers_data.get("tiers") or []
    if not tiers or current_price is None:
        return None

    cp = float(current_price)
    fv = _safe_float(investor_out.get("fair_value")) or _safe_float(long_h.get("fair_value"))
    verdict = str(long_h.get("verdict") or "WATCH").upper()
    assessment = tiers_data.get("current_assessment") or {}
    active_id = tiers_data.get("active_tier_id")
    target_id = tiers_data.get("target_tier_id")

    compact_tiers: list[dict[str, Any]] = []
    for t in tiers[:4]:
        if not isinstance(t, dict):
            continue
        lo = _safe_float(t.get("low"))
        hi = _safe_float(t.get("high"))
        if lo is None or hi is None:
            continue
        compact_tiers.append(
            {
                "id": t.get("id"),
                "label": t.get("label"),
                "low": round(min(lo, hi), 2),
                "high": round(max(lo, hi), 2),
                "allocation_pct": t.get("allocation_pct") or (tiers_data.get("position_sizing") or [{}])[0].get("allocation_pct"),
                "conviction": t.get("conviction"),
                "active": t.get("id") == active_id,
                "target": t.get("id") == target_id,
            }
        )

    inv = tiers_data.get("structural_invalidation") or {}
    inv_price = _safe_float(inv.get("price"))
    mos = _safe_float(assessment.get("margin_of_safety_pct"))

    narrative: list[str] = []
    if fv and cp < fv:
        narrative.append(f"Model fair value ~${fv:.2f} — spot has margin of safety for patient accumulation.")
    elif fv and cp > fv:
        premium = (cp - fv) / fv * 100
        if premium >= 8:
            narrative.append(f"Spot ~{premium:.0f}% above model FV — prefer tier adds on pullbacks, not chase.")
    if assessment.get("label"):
        narrative.append(f"Accumulation mode: {assessment.get('label')}.")
    narrative.extend(
        _market_narrative(
            investor_out=investor_out,
            response={**response, "current_price": cp},
            market_context=market_context,
            max_lines=2,
        )
    )

    one = investor_out.get("one_answer") or {}
    hvt = one.get("hold_vs_trade") or {}
    hold_block: dict[str, Any] | None = None
    if hvt:
        long_snip = (hvt.get("long_term") or "")[:160]
        if len(hvt.get("long_term") or "") > 160:
            long_snip += "…"
        short_snip = (hvt.get("short_term") or "")[:160]
        if len(hvt.get("short_term") or "") > 160:
            short_snip += "…"
        hold_block = {
            "title": hvt.get("title") or "Hold for years vs take profits",
            "long_term": hvt.get("long_term"),
            "short_term": hvt.get("short_term"),
            "signal_bridge": hvt.get("signal_bridge"),
            "bullets": [b for b in [long_snip, short_snip] if b][:2],
        }

    add_triggers = [
        "Add at active tier band — scale over quarters, not days.",
        "Rebalance from extended positions into lower tiers when price allows.",
    ]
    if active_id:
        active_t = next((t for t in compact_tiers if t.get("id") == active_id), None)
        if active_t:
            add_triggers.insert(
                0,
                f"Active tier {active_t.get('label')}: ≤ ${active_t['high']:.2f} (threshold — gaps below still count).",
            )
    t1 = next((t for t in compact_tiers if t.get("id") == "T1"), None)
    if t1 and not active_id:
        add_triggers.insert(
            0,
            f"T1 ceiling ≤ ${t1['high']:.2f} — owner trigger is at-or-below, not a ${t1['low']:.2f}–${t1['high']:.2f} window.",
        )

    exit_triggers = []
    if inv_price and current_price is not None and inv_price < float(current_price):
        exit_triggers.append(
            f"Structural invalidation below ${inv_price:.2f} — a close BELOW that floor reviews the long-term thesis."
        )
    elif inv_price:
        exit_triggers.append(
            f"Structural reference ${inv_price:.2f} is not below spot — use the tactical stop, not this level, as live invalidation."
        )
    exit_triggers.append("Trim tactical slice only on extended moves + weak scores — not core on volatility alone.")

    stance = "accumulate" if verdict in ("BUY", "STRONG BUY") else "watch" if verdict == "WATCH" else "wait"
    headline = {
        "STRONG BUY": "Thesis intact — accumulate at tiers",
        "BUY": "Long-term buy zone — build at tiers",
        "WATCH": "Hold core — add only at lower tiers",
        "WAIT": "Patience — wait for tier bands",
    }.get(verdict, "Thesis & tiers — match horizon to action")

    return {
        "active": True,
        "horizon": "long",
        "kind": "thesis_tiers",
        "title": "Thesis & tiers",
        "ticker": ticker,
        "stance": stance,
        "headline": headline,
        "setup_narrative": narrative[:5],
        "fair_value": round(fv, 2) if fv else None,
        "margin_of_safety_pct": round(mos, 1) if mos is not None else None,
        "tiers": compact_tiers,
        "hold_vs_trade": hold_block,
        "triggers": {
            "add": add_triggers,
            "exit": exit_triggers,
            "reduce": ["Trim extended tactical slice >20% gain pre-earnings if not core thesis."],
            "wait": [
                f"Wait for price ≤ ${t1['high']:.2f} (T1 ceiling) before sizing up."
            ] if stance == "wait" and t1 else (
                ["Wait for price inside target tier before sizing up."] if stance == "wait" else []
            ),
        },
        "thesis_breaks": [
            f"{ticker} thesis broken: guidance cut, moat erosion, or sector obsolescence.",
            (
                f"Close BELOW structural invalidation ${inv_price:.2f} (a floor, not a ceiling)."
                if inv_price and current_price is not None and inv_price < float(current_price)
                else (
                    f"Structural reference ${inv_price:.2f} is not below spot — do not treat a close above it as invalidation."
                    if inv_price
                    else "Structural invalidation level breached."
                )
            ),
            "Regime shifts to sustained bear + credit stress — reduce concentration.",
        ],
        "disclaimer": "Decision support only — long-term framework; not personalized financial advice.",
    }


def _tag_playbook(payload: dict[str, Any] | None, *, horizon: str, kind: str, title: str) -> dict[str, Any] | None:
    if not payload:
        return None
    return {**payload, "horizon": horizon, "kind": kind, "title": title}


def build_horizon_playbooks(
    *,
    ticker: str,
    investor_out: dict[str, Any],
    current_price: float | None,
    response: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Build all horizon playbooks; default_primary is swing until client intent overrides."""
    swing = build_swing_setup(
        ticker=ticker,
        investor_out=investor_out,
        current_price=current_price,
        response=response,
        market_context=market_context,
        config=config,
    )
    medium = build_medium_setup(
        ticker=ticker,
        investor_out=investor_out,
        current_price=current_price,
        response=response,
        market_context=market_context,
        config=config,
    )
    long_pb = build_long_setup(
        ticker=ticker,
        investor_out=investor_out,
        current_price=current_price,
        response=response,
        market_context=market_context,
    )

    return {
        "default_primary": "short",
        "intent_map": {
            "trade": "short",
            "invest": "long",
            "unset": "short",
        },
        "swing": _tag_playbook(swing, horizon="short", kind="swing", title="Swing setup"),
        "medium": _tag_playbook(medium, horizon="medium", kind="position_build", title="Position build"),
        "long": _tag_playbook(long_pb, horizon="long", kind="thesis_tiers", title="Thesis & tiers"),
    }
