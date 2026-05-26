"""
Composed swing-trade play sheet for ticker detail — levels from horizons.short (source of truth).
"""
from __future__ import annotations

from typing import Any


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _quality_label(passed: int, total: int) -> str:
    if total <= 0:
        return "UNKNOWN"
    if passed >= total:
        return "HIGH"
    if passed >= total - 1:
        return "MEDIUM-HIGH"
    if passed >= total - 2:
        return "MIXED"
    return "LOW"


def _inside_band(price: float | None, lo: float | None, hi: float | None) -> bool:
    if price is None or lo is None or hi is None:
        return False
    low, high = min(lo, hi), max(lo, hi)
    return low <= price <= high


def build_swing_setup(
    *,
    ticker: str,
    investor_out: dict[str, Any],
    current_price: float | None,
    response: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """
    Retail swing play sheet — narrative + trade/wait plan from existing investor_summary fields.
    Returns None when short horizon levels are unavailable.
    """
    response = response or {}
    config = config or {}
    horizons = investor_out.get("horizons") or {}
    short = horizons.get("short") or {}
    medium = horizons.get("medium") or {}

    ez = short.get("entry_zone") or {}
    el, eh = _safe_float(ez.get("low")), _safe_float(ez.get("high"))
    stop = _safe_float(short.get("stop_loss"))
    target1 = _safe_float(short.get("target"))
    target2 = _safe_float(medium.get("target")) if medium else None
    if target2 is not None and target1 is not None and target2 <= target1:
        target2 = round(target1 * 1.06, 2)

    cp = _safe_float(current_price)
    if stop is None or target1 is None or cp is None:
        return None

    # Fallback band when spot is extended above ST entry (WATCH) — still show wait/trade plan
    if el is None or eh is None:
        tr = investor_out.get("trader_roadmap") or {}
        tr_short = tr.get("short") or {}
        tr_ez = tr_short.get("entry_zone") or {}
        el = _safe_float(tr_ez.get("low"))
        eh = _safe_float(tr_ez.get("high"))
    if (el is None or eh is None) and stop < cp:
        el = round(stop, 2)
        eh = round(min(cp * 0.995, (stop + cp) / 2.0), 2)
    if el is None or eh is None:
        return None

    cp = float(cp)
    retail = investor_out.get("retail_action") or {}
    gates = retail.get("gates") or []
    primary_ids = retail.get("primary_gate_ids") or ["valuation", "regime", "momentum", "ml"]
    primary = [g for g in gates if g.get("id") in primary_ids]
    if not primary:
        primary = gates[:4]

    passed = sum(1 for g in primary if g.get("pass"))
    total = len(primary) or 4
    go_no_go = retail.get("go_no_go") or ("go" if passed == total else "no_go")
    all_go = go_no_go == "go"

    regime_bull = _safe_float(investor_out.get("regime_bull_pct"))
    rsi = _safe_float(investor_out.get("rsi"))
    pattern = _safe_float(investor_out.get("pattern_score"))
    fv = _safe_float(investor_out.get("fair_value"))
    high_52w = _safe_float(response.get("high_52w"))

    narrative: list[str] = []
    if high_52w and high_52w > cp:
        pct_off = (high_52w - cp) / high_52w * 100
        if pct_off >= 3:
            narrative.append(
                f"Pulled back ~{pct_off:.0f}% from 52-week high — check if move is tape-wide fear vs name-specific news."
            )
    if rsi is not None:
        if rsi >= 50:
            narrative.append(f"Short-term RSI {rsi:.0f} — momentum extended; gates may block chasing even inside the band.")
        elif rsi <= 45:
            narrative.append(f"RSI cooled to {rsi:.0f} — less chase risk if other gates clear.")
    if regime_bull is not None:
        if regime_bull >= 60:
            narrative.append(f"Bull regime intact (HMM ~{regime_bull:.0f}% bull).")
        else:
            narrative.append(f"Regime cautious (HMM ~{regime_bull:.0f}% bull) — size down or wait for tape improvement.")
    ctx = market_context or {}
    if ctx.get("quadrant") == "best_buy_zone":
        narrative.append("Market context: fear in a bull tape — historically a better dip-buy zone if gates allow.")
    elif ctx.get("primary_message"):
        narrative.append(str(ctx.get("primary_message")))
    if fv and cp < fv:
        mos = (fv - cp) / cp * 100
        if mos >= 5:
            narrative.append(f"~{mos:.1f}% below model fair value — valuation gate supportive.")

    failed = [g for g in primary if not g.get("pass")]
    top_blocker = failed[0] if failed else None

    wait_triggers: list[str] = []
    if top_blocker:
        wait_triggers.append(f"Wait until {str(top_blocker.get('label', 'gate')).title()} clears — {top_blocker.get('detail', '')}")
    if rsi is not None and rsi >= 50:
        wait_triggers.append("RSI cools below 50 before adding size.")
    if not _inside_band(cp, el, eh):
        wait_triggers.append(f"Price returns to entry band ${min(el, eh):.2f}–${max(el, eh):.2f}.")
    wait_triggers.append("All four primary gates show Go in the header above.")

    risk_per_share = cp - stop if cp > stop else None
    rr_t1 = None
    if risk_per_share and risk_per_share > 0 and target1 > cp:
        rr_t1 = round((target1 - cp) / risk_per_share, 2)

    risk_cfg = (config.get("risk_sizing") or {}) if isinstance(config.get("risk_sizing"), dict) else {}
    risk_pct = float(risk_cfg.get("risk_pct") or 2.0)
    example_portfolio = 50_000.0
    sizing_block: dict[str, Any] | None = None
    if all_go and risk_per_share and risk_per_share > 0:
        max_loss = example_portfolio * (risk_pct / 100.0)
        shares = int(max_loss / risk_per_share)
        entry_mid = (el + eh) / 2.0
        notional = shares * entry_mid
        sizing_block = {
            "rule": f"Risk max {risk_pct:.0f}% of portfolio on stop hit.",
            "example_portfolio_usd": example_portfolio,
            "max_loss_usd": round(max_loss, 0),
            "risk_per_share_usd": round(risk_per_share, 2),
            "shares_example": shares,
            "notional_usd": round(notional, 0),
            "scale_in": [
                f"Day 1: buy ~50% (~{max(1, shares // 2)} shares) if gates stay Go.",
                f"If price dips toward ${min(el, eh):.2f}–${(el + eh) / 2:.2f}, add remaining half.",
            ],
        }

    exit_triggers = [
        f"Close below stop ${stop:.2f} — exit; don't average down.",
    ]
    if target1 > cp:
        exit_triggers.append(f"At target 1 ${target1:.2f}: trim ~50%; move stop on rest toward breakeven.")
    if target2 and target2 > target1:
        exit_triggers.append(f"At target 2 ${target2:.2f}: exit remaining tactical size.")

    add_triggers: list[str] = []
    if all_go:
        add_triggers.append(
            f"Scale in inside ${min(el, eh):.2f}–${max(el, eh):.2f} while gates stay Go."
        )
        if rsi is not None:
            add_triggers.append(f"RSI holds above 40 on pullback adds.")
    else:
        add_triggers.append("Do not add until header shows Go — see wait plan below.")

    reduce_triggers: list[str] = []
    earnings = response.get("earnings") if isinstance(response.get("earnings"), dict) else None
    earnings_block: dict[str, Any] | None = None
    if earnings:
        days = earnings.get("days_until")
        date_s = earnings.get("date") or earnings.get("report_date")
        try:
            di = int(days) if days is not None else None
        except (TypeError, ValueError):
            di = None
        if di is not None and di <= 14:
            reduce_triggers.append(
                f"{ticker} reports in {di}d — reduce tactical size into the event if already extended."
            )
        if date_s or di is not None:
            earnings_block = {
                "report_date": date_s,
                "days_until": di,
                "action_plan": [
                    "Pre-earnings swing: exit tactical size before binary if up >10% from entry.",
                    "If not profitable 5 sessions before report — exit anyway; don't hold a losing swing through earnings.",
                    "This is a structure trade — not an earnings bet.",
                ],
            }

    thesis_breaks = [
        "HMM bull regime drops below 50% (regime flip).",
        f"{ticker}-specific guidance cut or material negative news.",
        "Credit/market stress overrides individual setup (dashboard Risk-Off + failing gates).",
    ]

    rr_note = (
        "Edge comes from structure + gate alignment more than raw R/R on target 1 alone."
        if rr_t1 is not None and rr_t1 < 1.2
        else "Risk/reward aligns with tactical swing — still size to your stop."
    )

    quality_label = _quality_label(passed, total)
    headline = (
        "Gates clear — structured swing entry"
        if all_go
        else "Setup forming — do not initiate until gates clear"
    )

    return {
        "active": True,
        "ticker": ticker,
        "go_no_go": go_no_go,
        "setup_quality": {
            "passed": passed,
            "total": total,
            "label": quality_label,
        },
        "headline": headline,
        "setup_narrative": narrative[:5],
        "inside_entry_band": _inside_band(cp, el, eh),
        "trade": {
            "entry_low": round(min(el, eh), 2),
            "entry_high": round(max(el, eh), 2),
            "stop": round(stop, 2),
            "target_1": round(target1, 2),
            "target_2": round(target2, 2) if target2 else None,
            "timeline_weeks": "3–6",
            "current_price": round(cp, 2),
        },
        "sizing": sizing_block,
        "triggers": {
            "add": add_triggers,
            "exit": exit_triggers,
            "reduce": reduce_triggers,
            "wait": wait_triggers if not all_go else [],
        },
        "earnings_caveat": earnings_block,
        "thesis_breaks": thesis_breaks,
        "risk_reward": {
            "ratio_target_1": rr_t1,
            "risk_pct": round((cp - stop) / cp * 100, 1) if cp > stop else None,
            "honest_note": rr_note,
        },
        "disclaimer": "Decision support only — educational swing framework, not financial advice.",
    }
