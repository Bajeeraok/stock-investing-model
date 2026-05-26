"""
Reconcile short-term temperature with longer-term regime into one retail message.

Temperature (days–weeks) and global/HMM regime (weeks–months) can disagree —
that is feature, not bug. This module produces a single quadrant playbook.
"""
from __future__ import annotations

from typing import Any

_ACTION_BUY = "BUY"
_ACTION_HOLD = "HOLD"
_ACTION_REDUCE = "REDUCE"
_ACTION_WAIT = "WAIT"


def _temp_level(temperature: dict | None) -> str:
    return (temperature or {}).get("level") or "warm"


def _regime_bucket(global_market_regime: str | None, macro_regime: str | None) -> str:
    g = (global_market_regime or "").upper().replace(" ", "_")
    if g in ("STRONG_BULL", "BULL"):
        return "bull"
    if g in ("STRONG_BEAR", "BEAR"):
        return "bear"
    m = (macro_regime or "").lower()
    if "risk-off" in m or "bear" in m:
        return "bear"
    if "risk-on" in m:
        return "bull"
    return "neutral"


def _hmm_bull_pct(global_market_regime: str | None, macro_regime_bundle: dict | None) -> float | None:
    bundle = macro_regime_bundle or {}
    bear = bundle.get("hmm_bear_pct_used")
    if bear is not None:
        try:
            return round(100.0 - float(bear), 1)
        except (TypeError, ValueError):
            pass
    fusion = bundle.get("fusion") or {}
    if fusion.get("hmm_score") is not None:
        try:
            return float(fusion["hmm_score"])
        except (TypeError, ValueError):
            pass
    g = (global_market_regime or "").upper()
    defaults = {
        "STRONG_BULL": 87.0,
        "BULL": 72.0,
        "NEUTRAL": 50.0,
        "BEAR": 28.0,
        "STRONG_BEAR": 12.0,
    }
    return defaults.get(g)


def _determine_quadrant(temp_level: str, regime_bucket: str, *, macro_regime: str | None = None) -> str:
    cold = temp_level in ("cold", "cool")
    hot = temp_level in ("hot", "warm_hot")
    # Macro Risk-Off in a bull tape = fear overlay (short-term) even if VIX is moderate
    if not cold and "risk-off" in (macro_regime or "").lower() and regime_bucket == "bull":
        cold = True

    if cold and regime_bucket == "bull":
        return "best_buy_zone"
    if hot and regime_bucket == "bull":
        return "hold_and_trim"
    if cold and regime_bucket == "bear":
        return "falling_knife"
    if hot and regime_bucket == "bear":
        return "dead_cat_bounce"
    if regime_bucket == "bear":
        return "bear_market_rally"
    if regime_bucket == "bull":
        return "selective_buy"
    if cold:
        return "cautious_neutral"
    if hot:
        return "cautious_neutral"
    return "selective_buy"


def _playbook(quadrant: str, *, vix: float | None, hmm_bull: float | None, credit: dict | None) -> dict[str, Any]:
    hb = hmm_bull if hmm_bull is not None else 50.0
    vx = vix if vix is not None else 18.0
    credit_sig = (credit or {}).get("signal") or "UNKNOWN"

    playbooks: dict[str, dict[str, Any]] = {
        "best_buy_zone": {
            "primary_message": "FEAR IN A BULL MARKET — BEST BUY OPPORTUNITY",
            "explanation": (
                f"Short-term temperature is cool/cold (VIX {vx:.1f}) while the underlying regime stays "
                f"bullish (HMM ~{hb:.0f}% bull). Fear in a bull market historically produces strong forward returns — "
                f"institutions add on weakness, they don't panic sell core."
            ),
            "historical_analog": "Similar setups: Oct 2023, Aug 2024 — fear resolved with 8–15% rallies over ~6 weeks.",
            "short_action": _ACTION_BUY,
            "short_label": "ACCUMULATE DIPS",
            "short_guidance": "Add quality names at support; scale in, don't all-in at once.",
            "medium_action": _ACTION_BUY,
            "medium_label": "CORE BUILDER",
            "medium_guidance": "Best medium-term entry zone — add highest-conviction names on 3–5% pullbacks.",
            "long_action": _ACTION_HOLD,
            "long_label": "STAY INVESTED",
            "long_guidance": "Do not reduce long-term core on fear alone — bull regime intact.",
            "bull_case_trigger": "VIX < 15 + breadth expands → fear resolved, rally continuation likely.",
            "bear_case_trigger": "Credit spreads >4% or HMM bull < 50% → regime change warning; reduce exposure.",
        },
        "hold_and_trim": {
            "primary_message": "GREED IN A BULL MARKET — HOLD, DON'T CHASE",
            "explanation": (
                f"Bull regime intact (HMM ~{hb:.0f}% bull) but sentiment is extended. "
                "Chasing here risks buying a short-term top — trim extended winners, wait for pullbacks."
            ),
            "historical_analog": "Jul 2023, Feb 2024 — brief 3–5% pullbacks before resuming higher.",
            "short_action": _ACTION_REDUCE,
            "short_label": "TRIM EXTENDED",
            "short_guidance": "Trim positions up >15–20% from entry; no new FOMO adds at highs.",
            "medium_action": _ACTION_HOLD,
            "medium_label": "HOLD CORE",
            "medium_guidance": "Keep core; set alerts 3–5% below spot for next add.",
            "long_action": _ACTION_HOLD,
            "long_label": "STAY INVESTED",
            "long_guidance": "Bull intact — don't cut long-term allocation on greed alone.",
            "bull_case_trigger": "3–5% pullback + VIX spike that fades → next add zone.",
            "bear_case_trigger": "Breadth narrows + greed extreme → trim growth 15%.",
        },
        "falling_knife": {
            "primary_message": "FEAR IN A BEAR MARKET — DON'T CATCH THE KNIFE",
            "explanation": (
                f"Cold tape (VIX {vx:.1f}) AND bearish regime (HMM ~{hb:.0f}% bull). "
                "Unlike bull-market fear, bear-market fear often worsens before stabilizing."
            ),
            "historical_analog": "Oct 2022, Mar 2020 early — felt like bottom but wasn't immediately.",
            "short_action": _ACTION_WAIT,
            "short_label": "STAY FLAT",
            "short_guidance": "No new entries until regime confirms turn — wait for HMM improvement.",
            "medium_action": _ACTION_REDUCE,
            "medium_label": "DEFENSIVE",
            "medium_guidance": "Reduce growth; rotate defensive; target higher cash.",
            "long_action": _ACTION_HOLD,
            "long_label": "CORE ONLY",
            "long_guidance": "Keep only highest-conviction long-term names.",
            "bull_case_trigger": "HMM bull > 55% for 2+ weeks + credit calms → re-enter carefully.",
            "bear_case_trigger": "Credit spreads >6% → raise cash aggressively.",
        },
        "dead_cat_bounce": {
            "primary_message": "GREED IN A BEAR MARKET — SELL INTO STRENGTH",
            "explanation": "Bear regime with temporarily hot sentiment — historically a relief rally, not a new bull leg.",
            "historical_analog": "Aug 2022 bear rally — +17% then new lows.",
            "short_action": _ACTION_REDUCE,
            "short_label": "SELL STRENGTH",
            "short_guidance": "Use strength to trim 20–30% of growth exposure.",
            "medium_action": _ACTION_REDUCE,
            "medium_label": "RAISE CASH",
            "medium_guidance": "Target 30–40% cash; bear regimes can persist months.",
            "long_action": _ACTION_HOLD,
            "long_label": "CORE ONLY",
            "long_guidance": "Keep index core; exit speculative bucket if thesis broken.",
            "bull_case_trigger": "HMM bull > 60% and holds 2+ weeks → regime change.",
            "bear_case_trigger": "Rally fades + VIX spikes → add to cash.",
        },
        "bear_market_rally": {
            "primary_message": "BEAR REGIME RALLY — STAY CAUTIOUS",
            "explanation": f"Regime still bearish (HMM ~{hb:.0f}% bull) — rallies may be temporary.",
            "historical_analog": "Multiple 2022 bear rallies failed at resistance.",
            "short_action": _ACTION_HOLD,
            "short_label": "NEUTRAL",
            "short_guidance": "Tight stops only; don't add size into bear regime.",
            "medium_action": _ACTION_REDUCE,
            "medium_label": "CAUTIOUS",
            "medium_guidance": "Use strength to trim weak names; raise cash 15–25%.",
            "long_action": _ACTION_HOLD,
            "long_label": "CORE ONLY",
            "long_guidance": "Index core OK; no new speculative adds.",
            "bull_case_trigger": "HMM bull > 55% for 2 weeks → regime shift.",
            "bear_case_trigger": "Break below prior lows → new leg down.",
        },
        "selective_buy": {
            "primary_message": "NORMAL BULL MARKET — BE SELECTIVE",
            "explanation": f"Bull regime (HMM ~{hb:.0f}% bull) with balanced sentiment — stock picking matters most.",
            "historical_analog": "Most of 2023–2024 productive tape looked like this.",
            "short_action": _ACTION_HOLD,
            "short_label": "SELECTIVE",
            "short_guidance": "Add only names in entry zone with strong score — no FOMO.",
            "medium_action": _ACTION_BUY,
            "medium_label": "ACCUMULATE",
            "medium_guidance": "Normal accumulation — add quality on 3–5% dips.",
            "long_action": _ACTION_HOLD,
            "long_label": "STAY INVESTED",
            "long_guidance": "Stay fully invested in core; rebalance quarterly.",
            "bull_case_trigger": "Breadth expands + earnings beats accelerate.",
            "bear_case_trigger": "VIX > 25 + credit stress → shift to cautious playbook.",
        },
        "cautious_neutral": {
            "primary_message": "MIXED TAPE — PATIENCE OVER PREDICTION",
            "explanation": "Regime neutral/mixed — neither strong buy nor strong sell zone.",
            "historical_analog": "Chop regimes — levels matter more than directional calls.",
            "short_action": _ACTION_HOLD,
            "short_label": "PATIENT",
            "short_guidance": "Wait for clearer edge; follow trigger levels.",
            "medium_action": _ACTION_HOLD,
            "medium_label": "NEUTRAL",
            "medium_guidance": "Hold core; add only on defined pullbacks.",
            "long_action": _ACTION_HOLD,
            "long_label": "STAY INVESTED",
            "long_guidance": "Long-term plan unchanged.",
            "bull_case_trigger": "Regime upgrades to bull + credit healthy.",
            "bear_case_trigger": "Regime downgrades + credit stress.",
        },
    }

    pb = dict(playbooks.get(quadrant, playbooks["selective_buy"]))
    if credit_sig in ("WARNING", "DANGER"):
        for key in ("short_action", "medium_action"):
            if pb[key] == _ACTION_BUY:
                pb[key] = _ACTION_HOLD
        pb["credit_override"] = "Credit stress caps aggressive adds despite quadrant read."
    return pb


def reconcile_market_context(
    *,
    temperature: dict | None,
    macro_regime: str | None,
    global_market_regime: str | None,
    macro_regime_bundle: dict | None = None,
    credit: dict | None = None,
    breadth: dict | None = None,
    market_catalysts: dict | None = None,
) -> dict[str, Any]:
    """Unified market context — single message retail traders act on."""
    temp_level = _temp_level(temperature)
    regime_bucket = _regime_bucket(global_market_regime, macro_regime)
    quadrant = _determine_quadrant(temp_level, regime_bucket, macro_regime=macro_regime)
    vix = (temperature or {}).get("vix")
    if vix is None and macro_regime_bundle:
        vix = (macro_regime_bundle.get("factors") or {}).get("vix")
    hmm_bull = _hmm_bull_pct(global_market_regime, macro_regime_bundle)
    pb = _playbook(quadrant, vix=vix, hmm_bull=hmm_bull, credit=credit)

    temp_label = (temperature or {}).get("label") or "WARM"
    regime_display = (global_market_regime or macro_regime or "NEUTRAL").replace("_", " ")

    coexistence = (
        f"Short-term: {temp_label} (sentiment/fear) · Long-term regime: {regime_display}. "
        "These measure different timeframes — not a contradiction."
    )
    if quadrant == "best_buy_zone":
        coexistence += " Fear in a bull market = historically the best dip-buying setup."
    elif "risk-off" in (macro_regime or "").lower() and regime_bucket == "bull":
        coexistence += " Macro Risk-Off reflects yields/credit caution; SPY regime can still be bull — reconcile both."

    scheduled = (market_catalysts or {}).get("scheduled_today") or []
    if scheduled and pb["short_action"] == _ACTION_BUY:
        pb = dict(pb)
        pb["short_action"] = _ACTION_HOLD
        pb["short_label"] = "WAIT FOR RELEASE"
        pb["short_guidance"] = (
            f"Macro today ({scheduled[0].get('event_type', 'release')}) — wait for reaction before sizing up."
        )

    return {
        "quadrant": quadrant,
        "primary_message": pb["primary_message"],
        "explanation": pb["explanation"],
        "historical_analog": pb.get("historical_analog"),
        "coexistence_note": coexistence,
        "temperature_label": temp_label,
        "temperature_level": temp_level,
        "regime_label": regime_display,
        "regime_bucket": regime_bucket,
        "hmm_bull_pct": hmm_bull,
        "is_contradictory": False,
        "contradiction_explanation": None,
        "short_term": {
            "action": pb["short_action"],
            "stance": pb["short_label"],
            "bullets": [pb["short_guidance"]],
        },
        "medium_term": {
            "action": pb["medium_action"],
            "stance": pb["medium_label"],
            "bullets": [pb["medium_guidance"]],
        },
        "long_term": {
            "action": pb["long_action"],
            "stance": pb["long_label"],
            "bullets": [pb["long_guidance"]],
        },
        "grid": {
            "short": pb["short_action"],
            "medium": pb["medium_action"],
            "long": pb["long_action"],
        },
        "bull_case_trigger": pb.get("bull_case_trigger"),
        "bear_case_trigger": pb.get("bear_case_trigger"),
        "credit_override": pb.get("credit_override"),
        "breadth_note": (breadth or {}).get("plain_english"),
    }


def matrix_from_context(context: dict[str, Any]) -> dict[str, Any]:
    """Strategy matrix shaped for existing UI from reconciled context."""
    lt_breakers = [
        {"label": "Credit spreads >4%", "triggered": False},
        {"label": "HMM bull drops below 50%", "triggered": False},
        {"label": "Earnings growth turns negative", "triggered": False},
    ]
    return {
        "short_term": {
            "horizon": "days–weeks",
            "stance": context["short_term"]["stance"],
            "action": context["short_term"]["action"],
            "bullets": context["short_term"]["bullets"],
        },
        "medium_term": {
            "horizon": "weeks–months",
            "stance": context["medium_term"]["stance"],
            "action": context["medium_term"]["action"],
            "bullets": context["medium_term"]["bullets"],
        },
        "long_term": {
            "horizon": "months–years",
            "stance": context["long_term"]["stance"],
            "action": context["long_term"]["action"],
            "bullets": context["long_term"]["bullets"],
            "thesis_breakers": lt_breakers,
        },
        "grid": context.get("grid") or {},
        "reconciled": True,
    }
