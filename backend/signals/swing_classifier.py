"""
Swing setup classifier, score, and mechanical exit plan.

Swing trades are **technical-first** (trend, RSI, volume, MA structure, pattern).
Short-horizon ML probability is optional confirmation — not the primary swing gate.
Full 7-layer confidence + valuation gates remain for accumulation / long-term.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class SwingSetupType(str, Enum):
    DIP_TO_MA = "dip_to_ma"
    OVERSOLD_BOUNCE = "oversold_bounce"
    BREAKOUT = "breakout"
    MOMENTUM_CONT = "momentum_cont"
    NO_SETUP = "no_setup"


SETUP_LABELS = {
    SwingSetupType.DIP_TO_MA: "DIP TO MA21",
    SwingSetupType.OVERSOLD_BOUNCE: "OVERSOLD BOUNCE",
    SwingSetupType.BREAKOUT: "BREAKOUT",
    SwingSetupType.MOMENTUM_CONT: "MOMENTUM CONT",
    SwingSetupType.NO_SETUP: "NO SETUP",
}


def _sf(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def extract_swing_inputs(
    *,
    investor_out: dict[str, Any],
    response: dict[str, Any] | None,
    current_price: float | None,
) -> dict[str, Any]:
    """Map existing dashboard / ticker_detail fields into classifier inputs."""
    response = response or {}
    cp = _sf(current_price) or _sf(response.get("close"))
    ma20 = _sf(response.get("ma20"))
    ma50 = _sf(response.get("ma50"))
    ma200 = _sf(response.get("ma200"))
    rsi = _sf(investor_out.get("rsi"))
    pattern = _sf(investor_out.get("pattern_score"))
    vol_ratio = _sf(response.get("volume_ratio")) or 1.0
    atr = _sf(response.get("atr14"))
    high_52w = _sf(response.get("high_52w"))
    trend_strength = _sf(response.get("trend_score")) or _sf(investor_out.get("composite_buy"))
    if trend_strength is None:
        trend_strength = pattern or 50.0

    golden_cross = ma50 is not None and ma200 is not None and ma50 > ma200
    above_ma50 = cp is not None and ma50 is not None and cp > ma50

    # Momentum shift: pattern + volume surge + RSI building (not for pure dip setups)
    momentum_shift = pattern or 0.0
    if vol_ratio >= 1.3 and rsi is not None and 50 <= rsi <= 68:
        momentum_shift = min(100.0, momentum_shift + 15.0)

    resistance = high_52w
    near_resistance = False
    if cp and resistance and resistance > 0:
        near_resistance = (resistance - cp) / resistance <= 0.03

    recent_low = _sf(response.get("low_52w"))
    if recent_low is None and cp and ma50:
        recent_low = min(ma50 * 0.95, cp * 0.92)

    ema8 = _sf(response.get("ema8"))
    if ema8 is None and ma20:
        ema8 = ma20  # proxy when EMA8 not on wire

    ma21 = ma20  # entry anchor — MA20 as MA21 proxy

    return {
        "price": cp,
        "rsi": rsi,
        "vol_ratio": vol_ratio,
        "golden_cross": golden_cross,
        "above_ma50": above_ma50,
        "momentum_shift": momentum_shift,
        "trend_strength": trend_strength,
        "pattern_score": pattern,
        "ma20": ma20,
        "ma21": ma21,
        "ma50": ma50,
        "ma200": ma200,
        "atr": atr,
        "resistance": resistance,
        "near_resistance": near_resistance,
        "recent_low": recent_low,
        "ema8": ema8,
        "regime_bull_pct": _sf(investor_out.get("regime_bull_pct")),
        "ml_short_prob": _sf((investor_out.get("horizons") or {}).get("short", {}).get("ml_prob")),
        "overall_verdict": str(investor_out.get("overall_verdict") or ""),
    }


def classify_swing_setup(inp: dict[str, Any]) -> tuple[SwingSetupType, list[str]]:
    """
    Classify tactical setup from existing indicators.
    Priority order: DIP_TO_MA → OVERSOLD_BOUNCE → BREAKOUT → MOMENTUM_CONT.
    """
    reasons: list[str] = []
    rsi = inp.get("rsi")
    rsi_v = float(rsi) if rsi is not None else 50.0
    vol = float(inp.get("vol_ratio") or 1.0)
    ts = float(inp.get("trend_strength") or 0)
    ms = float(inp.get("momentum_shift") or 0)

    if (
        ts > 70
        and rsi_v < 55
        and vol < 0.8
        and inp.get("above_ma50")
    ):
        reasons.append(f"Trend strength {ts:.0f} with RSI reset to {rsi_v:.0f}")
        if vol < 0.7:
            reasons.append(f"Volume drying on pullback ({vol:.1f}× avg)")
        if inp.get("golden_cross"):
            reasons.append("Golden cross intact (MA50 > MA200)")
        return SwingSetupType.DIP_TO_MA, reasons

    if rsi_v < 40 and inp.get("golden_cross"):
        reasons.append(f"RSI oversold at {rsi_v:.0f} with golden cross support")
        return SwingSetupType.OVERSOLD_BOUNCE, reasons

    if ms > 60 and vol > 1.5 and inp.get("near_resistance"):
        reasons.append(f"Momentum shift {ms:.0f}/100 near resistance with volume {vol:.1f}×")
        return SwingSetupType.BREAKOUT, reasons

    if ts > 80 and 50 < rsi_v < 65 and vol > 1.2:
        reasons.append(f"Strong trend ({ts:.0f}) with sustained volume {vol:.1f}×")
        return SwingSetupType.MOMENTUM_CONT, reasons

    return SwingSetupType.NO_SETUP, ["No clean swing archetype — mixed or extended conditions"]


def compute_swing_score(
    inp: dict[str, Any],
    setup_type: SwingSetupType,
) -> dict[str, Any]:
    """
    Technical swing score (not 7-layer confidence).
    ≥70 + classified setup → SWING SIGNAL; 55–69 WATCH; else NO SIGNAL.
    """
    technical = _sf(inp.get("trend_strength")) or 50.0
    pattern = _sf(inp.get("pattern_score")) or 50.0
    base = round(0.55 * technical + 0.45 * pattern, 1)

    regime_bonus = 0.0
    rb = inp.get("regime_bull_pct")
    if rb is not None:
        if float(rb) >= 60:
            regime_bonus += 5.0
        elif float(rb) >= 50:
            regime_bonus += 2.0

    setup_bonus = 3.0 if setup_type != SwingSetupType.NO_SETUP else 0.0
    score = min(100.0, round(base + regime_bonus + setup_bonus, 1))

    if setup_type != SwingSetupType.NO_SETUP and score >= 70:
        verdict = "SWING_SIGNAL"
    elif score >= 55:
        verdict = "WATCH"
    else:
        verdict = "NO_SIGNAL"

    ml = inp.get("ml_short_prob")
    ml_note = None
    if ml is not None:
        ml_f = float(ml)
        if ml_f >= 25:
            ml_note = f"Short ML {ml_f:.0f}% confirms tactical bias (optional — not required for swing)."
        else:
            ml_note = f"Short ML {ml_f:.0f}% is weak — swing leans on structure, not ML."

    return {
        "score": score,
        "verdict": verdict,
        "technical_component": round(technical, 1),
        "pattern_component": round(pattern, 1),
        "regime_bonus": regime_bonus,
        "setup_bonus": setup_bonus,
        "signal_basis": "technical",
        "ml_confirmation_note": ml_note,
    }


def build_swing_exit_plan(
    setup_type: SwingSetupType,
    inp: dict[str, Any],
    *,
    entry_low: float | None = None,
    entry_high: float | None = None,
) -> dict[str, Any] | None:
    """Mechanical exit ladder per setup type (trim 1/3 at T1/T2, runner trails)."""
    cp = _sf(inp.get("price"))
    if cp is None:
        return None

    atr = _sf(inp.get("atr")) or max(cp * 0.025, 1.0)
    ma50 = _sf(inp.get("ma50"))
    ma21 = _sf(inp.get("ma21")) or _sf(inp.get("ma20"))
    resistance = _sf(inp.get("resistance"))
    recent_low = _sf(inp.get("recent_low"))
    ema8 = _sf(inp.get("ema8"))

    el = entry_low if entry_low is not None else (ma21 or cp * 0.99)
    eh = entry_high if entry_high is not None else (cp if cp else el * 1.01)
    entry_mid = (float(el) + float(eh)) / 2.0

    if setup_type == SwingSetupType.DIP_TO_MA:
        entry_anchor = ma21 or entry_mid
        stop = min(entry_anchor * 0.97, (ma50 * 0.98) if ma50 else entry_anchor * 0.97)
    elif setup_type == SwingSetupType.OVERSOLD_BOUNCE:
        entry_anchor = cp
        stop = (recent_low * 0.98) if recent_low else cp * 0.97
    elif setup_type == SwingSetupType.BREAKOUT:
        res = resistance or cp
        entry_anchor = res * 1.005
        stop = res * 0.97
    elif setup_type == SwingSetupType.MOMENTUM_CONT:
        entry_anchor = cp
        stop = (ema8 * 0.98) if ema8 else cp * 0.97
    else:
        entry_anchor = entry_mid
        stop = entry_anchor * 0.97

    risk = entry_anchor - stop
    if risk <= 0:
        risk = entry_anchor * 0.03
        stop = entry_anchor - risk

    t1 = entry_anchor + 1.5 * risk
    t2 = entry_anchor + 2.5 * risk
    runner = entry_anchor + 3.5 * risk
    trail_atr = round(2.0 * atr, 2)

    horizon_days = 15 if setup_type == SwingSetupType.DIP_TO_MA else 12
    horizon_label = "10–14 days" if setup_type in (SwingSetupType.DIP_TO_MA, SwingSetupType.MOMENTUM_CONT) else "7–12 days"

    rr = (t1 - entry_anchor) / risk if risk > 0 else None

    return {
        "setup_type": setup_type.value,
        "entry_low": round(min(el, eh), 2),
        "entry_high": round(max(el, eh), 2),
        "entry_anchor": round(entry_anchor, 2),
        "hard_stop": round(stop, 2),
        "stop_pct": round((entry_anchor - stop) / entry_anchor * 100, 1) if entry_anchor else None,
        "target_1": round(t1, 2),
        "target_2": round(t2, 2),
        "runner_target": round(runner, 2),
        "trim_pct_each": 33,
        "trail_atr_mult": 2.0,
        "trail_atr_usd": trail_atr,
        "time_stop_days": horizon_days,
        "horizon_label": horizon_label,
        "risk_reward_t1": round(rr, 2) if rr is not None else None,
        "exit_rules": [
            f"Target 1 ${t1:.2f} (+1.5R) → trim ~33%",
            f"Target 2 ${t2:.2f} (+2.5R) → trim ~33%",
            f"Runner: trail 2×ATR (~${trail_atr:.2f}) or ${runner:.2f} stretch goal",
            f"Time stop: exit by day {horizon_days} if not at 1R",
            f"Hard stop ${stop:.2f} — exit full position on close below",
        ],
    }


def build_swing_divergence_note(
    *,
    overall_verdict: str,
    swing_verdict: str,
    setup_type: SwingSetupType,
) -> str | None:
    """Long-term WAIT vs tactical swing — the key retail message."""
    ov = (overall_verdict or "").upper()
    if swing_verdict != "SWING_SIGNAL":
        return None
    if ov in ("WAIT", "WATCH", "REDUCE", "AVOID"):
        label = SETUP_LABELS.get(setup_type, setup_type.value)
        return (
            f"Full model says {ov} (valuation / long-term gates). "
            f"Technical setup says SWING ({label}). "
            "This is a tactical swing trade — not accumulation sizing."
        )
    return None


def build_swing_classification_bundle(
    *,
    investor_out: dict[str, Any],
    response: dict[str, Any] | None,
    current_price: float | None,
    entry_low: float | None = None,
    entry_high: float | None = None,
) -> dict[str, Any]:
    """Full classifier + score + exits for swing_setup integration."""
    inp = extract_swing_inputs(
        investor_out=investor_out,
        response=response,
        current_price=current_price,
    )
    setup_type, reasons = classify_swing_setup(inp)
    score_block = compute_swing_score(inp, setup_type)
    exits = build_swing_exit_plan(
        setup_type,
        inp,
        entry_low=entry_low,
        entry_high=entry_high,
    )
    divergence = build_swing_divergence_note(
        overall_verdict=inp.get("overall_verdict") or "",
        swing_verdict=score_block["verdict"],
        setup_type=setup_type,
    )
    return {
        "setup_type": setup_type.value,
        "setup_label": SETUP_LABELS.get(setup_type, setup_type.value),
        "setup_reasons": reasons,
        "inputs": {k: v for k, v in inp.items() if k not in ("overall_verdict",)},
        "swing_score": score_block,
        "exit_plan": exits,
        "divergence_note": divergence,
    }
