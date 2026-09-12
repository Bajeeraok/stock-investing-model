"""
Retail action / trading-gate payloads for API responses.

Single source of truth for gate pass/fail, RSI heat, regime weather, and R:R bands.
Frontend maps visual_status tokens to Tailwind — no duplicate threshold math in React.
"""

from __future__ import annotations

from typing import Any, Literal


def _retail_gates_config() -> dict[str, Any]:
    """config.yaml `retail_gates` section — loaded once, with hardcoded fallbacks below.

    Previously these thresholds were pure Python constants with no config path, so
    editing config.yaml's `retail_gates` block (which documented itself as the tunable
    source) had zero effect. Load once at import; a bad/missing config.yaml falls back
    to the same numbers this module always shipped with.
    """
    try:
        from config_loader import load_config

        return dict(load_config().get("retail_gates") or {})
    except Exception:
        return {}


_RG_CFG = _retail_gates_config()

ST_ML_GATE = float(_RG_CFG.get("ml_short_prob_min", 25))
ML_MARGINAL_ABS = float(_RG_CFG.get("ml_marginal_abs_pct", 55))  # pass vs threshold but low absolute conviction
REGIME_GATE = float(_RG_CFG.get("regime_bull_pct_min", 60))
CONFIDENCE_GATE = float(_RG_CFG.get("confidence_gate_pct", 55))
# pattern_signals.py::_bullish_trend_score treats RSI 55-70 as the "strong trend zone"
# (its single largest bonus) and only starts discounting RSI above 70 ("overbought but in
# momentum range"). A flat momentum_rsi_max of 50 directly contradicted that — it hard-
# failed every genuine trend-continuation setup (which by definition tends to sit at
# RSI 50-70) regardless of how strong pattern_score was. 70 now matches where this
# module's own _momentum_gate_detail already called RSI "extended/overbought"; 65-70 is
# a marginal pass instead of a clean one.
MOMENTUM_RSI_MAX = float(_RG_CFG.get("momentum_rsi_max", 70))
MOMENTUM_RSI_MARGINAL_MIN = float(_RG_CFG.get("momentum_rsi_marginal_min", 65))
# pattern_score's 27-43 range is the documented-normal band for a stock that isn't in a
# near-bottom reversal setup (see near_bottom_score/_bullish_trend_score in pattern_signals.py) —
# a single hard floor at the old 45 sat inside that normal band and made the gate nearly
# unreachable for any non-bottom setup, the same "flat threshold => 0% pass rate" failure
# already fixed once for the valuation gate (see comment on retail_gates in config.yaml).
# 35-43 now passes but is flagged marginal instead of a clean pass.
MOMENTUM_PATTERN_MIN = float(_RG_CFG.get("momentum_pattern_min", 35))
MOMENTUM_PATTERN_MARGINAL_MAX = float(_RG_CFG.get("momentum_pattern_marginal_max", 43))
# OBV 10d trend thresholds — accumulation/distribution confirmation for the momentum gate.
# A single day's volume_ratio can't tell "nobody's interested" from "sellers dried up";
# a multi-day OBV slope can. Kept as soft (visual_status only, not pass/fail) since this
# hasn't been backtested against the RSI/pattern rule the way momentum_ok itself has.
MOMENTUM_OBV_ACCUMULATION_PCT = float(_RG_CFG.get("momentum_obv_accumulation_pct", 5.0))
MOMENTUM_OBV_DISTRIBUTION_PCT = float(_RG_CFG.get("momentum_obv_distribution_pct", -8.0))

# Tranche-tiered MOS ladder: required valuation discount scales with tranche depth
# (T1 = first dollar in, T3 = final/deepest tranche) instead of one flat number applied
# to every entry regardless of context. A flat 25% requirement made "full GO" nearly
# unreachable for list-level rows (no tranche context => implicitly held to the T3 bar).
_ladder_cfg = _RG_CFG.get("valuation_mos_ladder_pct")
VALUATION_MOS_LADDER_PCT: tuple[float, ...] = (
    tuple(float(x) for x in _ladder_cfg) if isinstance(_ladder_cfg, (list, tuple)) and _ladder_cfg
    else (10.0, 18.0, 25.0)
)
_addon_cfg = _RG_CFG.get("valuation_regime_addon_pct") or {}
VALUATION_REGIME_ADDON_PCT: dict[str, float] = {
    "bull": float(_addon_cfg.get("bull", 0.0)),
    "mixed": float(_addon_cfg.get("mixed", 3.0)),
    "stormy": float(_addon_cfg.get("stormy", 7.0)),
}
VALUATION_GATE_PASS_PCT = VALUATION_MOS_LADDER_PCT[-1]   # deepest-tranche ceiling; align with House LT_REQUIRED_MOS_PCT
VALUATION_GATE_PARTIAL_PCT = float(_RG_CFG.get("valuation_partial_mos_pct", 15.0))
PRIMARY_GATE_IDS = ("valuation", "regime", "momentum", "ml")

RsiStatus = Literal["hot", "neutral", "oversold"]
RegimeWeatherStatus = Literal["bull", "stormy", "mixed", "extended"]
RrStatus = Literal["tight", "balanced", "favorable"]
GateVisualStatus = Literal["cleared", "blocked", "marginal"]
ActionLight = Literal["green", "yellow", "red"]
EntryMode = Literal["hard_lock", "starter_only", "full_go"]

BRIDGE_MAX_SIZING_PCT = 10
STARTER_MAX_SIZING_PCT = 25


def rsi_status(rsi: float | None) -> RsiStatus:
    if rsi is None:
        return "neutral"
    if rsi >= 50:
        return "hot"
    if rsi <= 35:
        return "oversold"
    return "neutral"


def regime_weather_status(
    regime_bull_pct: float | None,
    *,
    momentum_extended: bool = False,
) -> RegimeWeatherStatus:
    if momentum_extended:
        return "extended"
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


def _assessment_from_lt_band(
    current_price: float | None,
    lt_band: dict | None,
    fair_value_mid: float | None = None,
) -> float:
    """
    % gap between current price and long-term fair value (positive = cheap).

    Prefers ``fair_value_mid`` (target_bands' uncapped fair-value/consensus midpoint,
    ``row["lt_fair_value_mid"]``) over the ``lt_band`` midpoint — ``lt_band`` is capped
    to +/-35% of spot purely so the UI stays readable (see
    ``target_bands._cap_band_width_for_display``), and that capped high/low pair
    understates upside for any name where the true fair-value range is wider, which
    silently biases this gate more negative as spot runs up. Falls back to the
    (capped) lt_band midpoint for legacy rows saved before ``lt_fair_value_mid`` existed.
    """
    if current_price is None or current_price <= 0:
        return 0.0
    if fair_value_mid is not None:
        try:
            fv = float(fair_value_mid)
            if fv > 0:
                return 100.0 * (fv - current_price) / current_price
        except (TypeError, ValueError):
            pass
    if not lt_band:
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


# Matches pattern_signals.near_bottom_score's own "within 5% of 52w low" component — reused
# here for consistency rather than inventing a separate proximity cutoff.
_NEAR_52W_LOW_PCT = 5.0


def _price_anchor_clause(
    *,
    close: float | None,
    ma50: float | None,
    high_52w: float | None,
    low_52w: float | None,
    momentum_extended: bool,
    regime_ok: bool,
) -> str:
    """Ties the bull/bear percentage split to an actual price level — 'what would need to
    happen', not just the raw split. Reuses the exact thresholds validate_regime() /
    detect_momentum_extended() (hmm_regime.py) already trust internally for overriding a
    stale HMM read, rather than inventing a new cutoff. Returns "" (no clause) when close
    isn't available, so callers degrade to exactly today's text.
    """
    if close is None or close <= 0:
        return ""

    near_low = (
        low_52w is not None and low_52w > 0
        and (close - low_52w) / low_52w * 100.0 <= _NEAR_52W_LOW_PCT
    )
    near_high = high_52w is not None and high_52w > 0 and close >= high_52w * 0.94

    if momentum_extended and near_high:
        return (
            f". Trading near its 52-week high (${high_52w:,.2f}) — the model flags "
            f"mean-reversion risk here, not a broken trend; a pullback wouldn't invalidate "
            f"the bigger picture."
        )
    if not regime_ok and ma50 is not None and ma50 > 0:
        gap_ma50_pct = (close - ma50) / ma50 * 100.0
        if gap_ma50_pct < 0:
            low_note = f", and is near its 52-week low (${low_52w:,.2f})" if near_low else ""
            return (
                f". Trading {abs(gap_ma50_pct):.1f}% below its 50-day average (${ma50:,.2f})"
                f"{low_note} — a close back above that level is what the model would need "
                f"to call this confirmed."
            )
    if near_low and not momentum_extended:
        return f". Trading within {_NEAR_52W_LOW_PCT:.0f}% of its 52-week low (${low_52w:,.2f})."
    return ""


def _regime_gate_detail(
    *,
    ticker: str | None,
    stock_bull_pct: float,
    regime_ok: bool,
    regime_hmm_label: str | None = None,
    regime_transition_pct: float | None = None,
    market_bull_pct: float | None = None,
    momentum_extended: bool = False,
    close: float | None = None,
    ma50: float | None = None,
    high_52w: float | None = None,
    low_52w: float | None = None,
) -> str:
    anchor = _price_anchor_clause(
        close=close,
        ma50=ma50,
        high_52w=high_52w,
        low_52w=low_52w,
        momentum_extended=momentum_extended,
        regime_ok=regime_ok,
    )

    if regime_ok:
        sym = ticker or "Stock"
        return f"Bull tape · {sym} HMM bull {round(stock_bull_pct)}%{anchor}"

    sym = ticker or "This name"
    if momentum_extended:
        line1 = (
            f"Extended tape — {sym} near highs with aligned MAs; "
            f"HMM bull {round(stock_bull_pct)}% (pullback-risk signal, not structural bear)"
        )
        if market_bull_pct is not None and market_bull_pct >= REGIME_GATE:
            return f"{line1} · Broader market {round(market_bull_pct)}% bull{anchor}"
        return f"{line1}{anchor}"

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
        return f"{line1} · Market overall: {round(market_bull_pct)}% bull · → Stock lagging the broader market{anchor}"
    return f"{line1}{anchor}"


def _obv_divergence_note(volume_ratio: float | None, obv_trend_pct: float | None, rsi_val: float) -> str:
    """Disambiguate a low volume_ratio: OBV rising = lack of sellers, OBV falling = lack of interest."""
    if obv_trend_pct is None:
        return ""
    if volume_ratio is not None and volume_ratio < 0.75 and rsi_val < 50:
        if obv_trend_pct >= MOMENTUM_OBV_ACCUMULATION_PCT:
            return " · but OBV rising (accumulation — lack of sellers, not lack of interest)"
        if obv_trend_pct <= MOMENTUM_OBV_DISTRIBUTION_PCT:
            return " · OBV falling too (lack of interest — chop likely genuine exhaustion)"
        return ""
    if obv_trend_pct <= MOMENTUM_OBV_DISTRIBUTION_PCT:
        return " · OBV distribution over 10d (quiet selling beneath the price)"
    return ""


def _momentum_gate_detail(
    *,
    rsi_val: float,
    pattern_score: float | None,
    momentum_ok: bool,
    volume_ratio: float | None = None,
    obv_trend_pct: float | None = None,
) -> str:
    vol_note = ""
    if volume_ratio is not None and volume_ratio > 0:
        if volume_ratio < 0.75 and rsi_val < 50:
            vol_note = " · volume drying up (participation low — chop may be exhaustion)"
        elif volume_ratio >= 1.5 and rsi_val >= 45:
            vol_note = " · high-volume chop (distribution risk if support breaks)"
        elif volume_ratio >= 2.0:
            vol_note = " · unusual volume (≥2× 20d avg — confirm direction)"
    vol_note += _obv_divergence_note(volume_ratio, obv_trend_pct, rsi_val)
    if momentum_ok:
        base = f"RSI {rsi_val:.0f} · pattern {round(pattern_score or 0)}/100"
        notes = []
        if rsi_val >= MOMENTUM_RSI_MARGINAL_MIN:
            notes.append("RSI getting extended")
        if (pattern_score or 0) < MOMENTUM_PATTERN_MARGINAL_MAX:
            notes.append("pattern modest — normal range for a non-bottom setup")
        if notes:
            base += " (" + "; ".join(notes) + ")"
        return base + vol_note if vol_note else base
    if rsi_val >= MOMENTUM_RSI_MAX:
        return f"RSI extended ({rsi_val:.0f}/100) — overbought; wait for cooldown{vol_note}"
    return f"Pattern weak ({round(pattern_score or 0)}/100){vol_note}"


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


def _regime_bucket(regime_bull_pct: float | None) -> str:
    if regime_bull_pct is None:
        return "mixed"
    if regime_bull_pct >= REGIME_GATE:
        return "bull"
    if regime_bull_pct < 42:
        return "stormy"
    return "mixed"


def required_mos_pct(tranche_idx: int, regime_bull_pct: float | None = None) -> float:
    """Required valuation discount for this tranche depth, tightened (never loosened) by regime.

    tranche_idx 0 = first dollar in (loosest rung); the last rung matches the historical
    flat 25% "full GO" bar — that discipline still applies, just to the deepest tranche
    rather than to every entry regardless of how much has already been bought.
    """
    idx = max(0, min(int(tranche_idx), len(VALUATION_MOS_LADDER_PCT) - 1))
    base = VALUATION_MOS_LADDER_PCT[idx]
    addon = VALUATION_REGIME_ADDON_PCT[_regime_bucket(regime_bull_pct)]
    return base + addon


def tranche_idx_from_tier_id(tier_id: str | None) -> int:
    """Map a long-horizon entry tier ("T1"/"T2"/"T3") to a 0-based MOS ladder index.

    Defaults to 0 (T1, the loosest rung) when no tier context is available — e.g. the
    list-row / daily-batch path (enrich_dashboard_signal_row) has no entry-tier data,
    so it should be judged against the first-tranche bar, not implicitly held to the
    deepest tranche's 25% requirement.
    """
    s = str(tier_id or "").strip().upper()
    if s.startswith("T") and s[1:].isdigit():
        return max(0, int(s[1:]) - 1)
    return 0


def _valuation_gate_detail(
    assessment_pct: float,
    *,
    tranche_idx: int = 0,
    regime_bull_pct: float | None = None,
) -> tuple[bool, str]:
    """Valuation gate — required MOS scales with tranche depth (see required_mos_pct)."""
    full_req = required_mos_pct(tranche_idx, regime_bull_pct)
    partial_req = max(0.0, full_req - 10.0)
    tier_note = f"T{tranche_idx + 1}"
    if assessment_pct >= full_req:
        return True, f"Sufficient MOS (+{assessment_pct:.1f}% vs required {full_req:.0f}%, {tier_note})"
    if assessment_pct >= partial_req:
        return False, (
            f"Partial MOS (+{assessment_pct:.1f}% — need {full_req:.0f}% for full entry, {tier_note})"
        )
    if assessment_pct >= 0:
        return False, (
            f"Modest discount (+{assessment_pct:.1f}% — need {full_req:.0f}% MOS, {tier_note})"
        )
    return False, f"Rich vs fair value ({assessment_pct:.1f}%)"


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
    volume_ratio: float | None = None,
    obv_trend_pct: float | None = None,
    momentum_extended: bool = False,
    tranche_idx: int = 0,
    close: float | None = None,
    ma50: float | None = None,
    high_52w: float | None = None,
    low_52w: float | None = None,
) -> list[dict[str, Any]]:
    """Primary + optional confidence gates with pass flags and visual_status tokens."""
    rb = regime_bull_pct if regime_bull_pct is not None else 50.0
    rsi_val = float(rsi) if rsi is not None else 50.0
    weather = regime_weather_status(regime_bull_pct, momentum_extended=momentum_extended)

    valuation_ok, valuation_detail = _valuation_gate_detail(
        assessment_pct, tranche_idx=tranche_idx, regime_bull_pct=regime_bull_pct
    )
    regime_ok = regime_bull_pct is not None and regime_bull_pct >= REGIME_GATE
    momentum_ok = rsi_val < MOMENTUM_RSI_MAX and (pattern_score or 0) >= MOMENTUM_PATTERN_MIN
    # Momentum passes the RSI/pattern check but one of: (a) OBV shows quiet distribution
    # underneath, (b) pattern score is only in the 35-43 "normal for a non-bottom setup"
    # band rather than clearly strong, or (c) RSI is in the 65-70 "getting extended" band —
    # flag it as a marginal pass (still tradeable, still counts toward gate_cleared) rather
    # than silently treating it the same as a clean pass. Not applied to a failing gate:
    # none of these can rescue a fail here, they only temper confidence in a pass.
    momentum_pattern_marginal = momentum_ok and (pattern_score or 0) < MOMENTUM_PATTERN_MARGINAL_MAX
    momentum_rsi_marginal = momentum_ok and rsi_val >= MOMENTUM_RSI_MARGINAL_MIN
    momentum_marginal = (
        momentum_ok
        and (
            momentum_pattern_marginal
            or momentum_rsi_marginal
            or (obv_trend_pct is not None and obv_trend_pct <= MOMENTUM_OBV_DISTRIBUTION_PCT)
        )
    )
    ml_detail, ml_visual, ml_ok = _ml_gate_detail(short_ml_prob)
    conf_ok = (confidence_mid or 0) >= CONFIDENCE_GATE

    gates: list[dict[str, Any]] = [
        {
            "id": "valuation",
            "label": "VALUATION",
            "detail": valuation_detail,
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
                momentum_extended=momentum_extended,
                close=close,
                ma50=ma50,
                high_52w=high_52w,
                low_52w=low_52w,
            ),
            "pass": regime_ok,
            "gate_cleared": regime_ok,
            "visual_status": "bull" if regime_ok else ("extended" if momentum_extended else "stormy"),
            "regime_weather_status": weather,
            "icon": "☀️" if regime_ok else ("🔥" if momentum_extended else ("⚡" if weather == "stormy" else "🌧️")),
            "blocker_weight": 0 if regime_ok else 45,
        },
        {
            "id": "momentum",
            "label": "MOMENTUM CHOP",
            "detail": _momentum_gate_detail(
                rsi_val=rsi_val,
                pattern_score=pattern_score,
                momentum_ok=momentum_ok,
                volume_ratio=volume_ratio,
                obv_trend_pct=obv_trend_pct,
            ),
            "pass": momentum_ok,
            "gate_cleared": momentum_ok,
            "visual_status": "marginal" if momentum_marginal else ("cleared" if momentum_ok else "hot"),
            "rsi_status": rsi_status(rsi),
            "icon": "📉" if momentum_ok else "📈",
            "blocker_weight": 0 if momentum_ok else (40 if rsi_val >= 50 else 25),
            "marginal_pass": momentum_marginal,
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


def _gate_pass(gates: list[dict[str, Any]], gate_id: str) -> bool:
    g = next((x for x in gates if x.get("id") == gate_id), None)
    return bool(g and g.get("pass"))


def _tech_gates_pass(gates: list[dict[str, Any]]) -> bool:
    return all(_gate_pass(gates, gid) for gid in ("regime", "momentum", "ml"))


def _spot_in_actionable_zone(
    *,
    zone_context: dict[str, Any] | None,
    inside_buy_band: bool,
    long_spot: dict[str, Any] | None,
) -> bool:
    if inside_buy_band:
        return True
    if long_spot and long_spot.get("state") == "in_tier":
        return True
    if not zone_context:
        return False
    if zone_context.get("in_bridge_band"):
        return True
    return zone_context.get("state") in ("in_tier", "in_band")


def derive_entry_mode(
    *,
    gates: list[dict[str, Any]],
    assessment_pct: float,
    gate_cleared: bool,
    overall_verdict: str | None = None,
    zone_context: dict[str, Any] | None = None,
    inside_buy_band: bool = False,
    long_spot: dict[str, Any] | None = None,
    institutional_conviction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Conditional sizing from gate matrix (valuation × tech × zone).

    hard_lock     — no new entries (rich / no MOS / stormy + no value support)
    starter_only  — bridge or tier starter (~10–25% max) when value OK but tech gates fail
    full_go       — all primary gates pass → roadmap tranche sizing unlocked
    """
    val_full = _gate_pass(gates, "valuation")
    val_starter = assessment_pct >= VALUATION_GATE_PARTIAL_PCT
    tech_ok = _tech_gates_pass(gates)
    in_zone = _spot_in_actionable_zone(
        zone_context=zone_context,
        inside_buy_band=inside_buy_band,
        long_spot=long_spot,
    )
    verdict = (overall_verdict or "").upper()

    if assessment_pct < 0 or verdict in ("AVOID", "REDUCE", "SELL"):
        mode: EntryMode = "hard_lock"
    elif not val_starter and not in_zone:
        mode = "hard_lock"
    elif gate_cleared and val_full and tech_ok:
        mode = "full_go"
    elif val_starter or val_full or in_zone:
        mode = "starter_only"
    else:
        mode = "hard_lock"

    if mode == "full_go":
        max_pct = 100
        label = "FULL GO"
        headline = "All gates clear — roadmap sizing unlocked"
        detail = "Confirm tranche plan on Roadmaps before adding risk."
        light: ActionLight = "green"
    elif mode == "starter_only":
        in_bridge = bool(zone_context and zone_context.get("in_bridge_band"))
        in_tier = bool(
            (long_spot and long_spot.get("state") == "in_tier")
            or (zone_context and zone_context.get("state") == "in_tier")
        )
        if in_bridge:
            max_pct = BRIDGE_MAX_SIZING_PCT
            headline = f"Bridge / starter only (~{max_pct}% max)"
        elif in_tier or inside_buy_band:
            max_pct = STARTER_MAX_SIZING_PCT
            headline = f"Starter sizing only (~{max_pct}% max tranche)"
        else:
            max_pct = BRIDGE_MAX_SIZING_PCT
            headline = f"Patience phase — starter only when price reaches band (~{max_pct}% max)"
        label = "STARTER ONLY"
        failed = [g for g in gates if g.get("id") in PRIMARY_GATE_IDS and not g.get("pass")]
        top = sorted(failed, key=lambda x: -(x.get("blocker_weight") or 0))[0] if failed else None
        blocker = str(top.get("label") or "tech gates").title() if top else "tech gates"
        detail = (
            f"Value supports a small sleeve, but {blocker} still blocks full size. "
            "Use bridge/tier plan — not roadmap cumulative %."
        )
        light = "yellow"
    else:
        max_pct = 0
        label = "HARD LOCK"
        headline = "No new entries"
        if assessment_pct < 0:
            detail = "Rich vs model fair value — hold or trim only; no adds at this price."
        else:
            detail = (
                "Insufficient margin of safety and no actionable band at spot — "
                "wait for pullback or better MOS."
            )
        light = "red"

    inst = institutional_conviction or {}
    inst_verdict = str(inst.get("verdict") or "unknown")
    inst_note = ""
    if inst_verdict == "supports" and mode in ("starter_only", "full_go"):
        inst_note = (
            " Active-manager 13F delta supports the valuation floor "
            "(quarterly snapshot, ~45d lag — conviction filter, not a timing trigger)."
        )
        if inst.get("buy_the_dip"):
            inst_note = (
                " Active managers accumulated during a down quarter (buy-the-dip on 13F) — "
                "strong conviction filter; still wait for Market Weather / Momentum gates."
            )
    elif inst_verdict == "concerns" and mode == "starter_only":
        inst_note = (
            " Active-manager 13F delta is distributing — cap starter size; "
            "do not treat as a full-size signal."
        )
        max_pct = min(max_pct, BRIDGE_MAX_SIZING_PCT)
    if inst_note:
        detail = detail.rstrip(".") + "." + inst_note

    return {
        "entry_mode": mode,
        "entry_mode_label": label,
        "entry_mode_headline": headline,
        "entry_mode_detail": detail,
        "max_sizing_pct": max_pct,
        "action_light": light,
        "valuation_tier": (
            "full_mos" if val_full else "partial_mos" if val_starter else "none"
        ),
        "tech_gates_pass": tech_ok,
        "institutional_conviction_verdict": inst_verdict if inst else None,
    }


def build_unlock_sequence(
    gates: list[dict[str, Any]],
    *,
    stock_bull_pct: float | None,
) -> str:
    """Ordered unlock path for full-size entry."""
    steps: list[str] = []
    if not _gate_pass(gates, "regime"):
        bull = round(float(stock_bull_pct or 0))
        steps.append(f"Market Weather ≥{REGIME_GATE}% (now {bull}%)")
    if not _gate_pass(gates, "momentum"):
        steps.append(f"Momentum Chop pass (RSI <50, pattern ≥45)")
    if not _gate_pass(gates, "ml"):
        steps.append(f"ML probability ≥{ST_ML_GATE}%")
    if not _gate_pass(gates, "valuation"):
        steps.append(f"Valuation MOS ≥{VALUATION_GATE_PASS_PCT:.0f}%")
    if not steps:
        return "Full size unlocked — confirm roadmap tranches before adding."
    numbered = " → ".join(f"({i + 1}) {s}" for i, s in enumerate(steps))
    return f"Unlock full size when: {numbered}"


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

    if state in ("in_tier", "at_or_below_ceiling") and tier_id:
        tier = str(tier_id).upper()
        if gate_cleared:
            return f"ACCUMULATE · {tier}", "green"
        # Failed gates: still in the add zone, but do not advertise Accumulate vs Hold.
        return f"{tier} IN RANGE · WAIT FOR GATES", "yellow"

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
    current_price: float | None = None,
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

    def _in_range(lo: float | None, hi: float | None) -> bool:
        if current_price is None or lo is None or hi is None:
            return False
        return float(min(lo, hi)) <= float(current_price) <= float(max(lo, hi))

    zc = zone_context or {}
    st_lo = (st_band or {}).get("low")
    st_hi = (st_band or {}).get("high")
    in_st = _in_range(
        float(st_lo) if st_lo is not None else None,
        float(st_hi) if st_hi is not None else None,
    )
    in_bridge = bool(zc.get("in_bridge_band")) and _in_range(
        float(zc["bridge_low"]) if zc.get("bridge_low") is not None else None,
        float(zc["bridge_high"]) if zc.get("bridge_high") is not None else None,
    )
    in_gap = _in_range(
        float(zc["gap_low"]) if zc.get("gap_low") is not None else None,
        float(zc["gap_high"]) if zc.get("gap_high") is not None else None,
    )
    in_band_state = (zc.get("state") or "") == "in_band"

    if in_st or in_bridge or in_gap or in_band_state:
        if st_lo is not None and st_hi is not None:
            band_note = f"in ST band ${float(st_lo):.0f}–${float(st_hi):.0f}"
        elif in_bridge and zc.get("bridge_low") is not None:
            band_note = (
                f"in bridge ${float(zc['bridge_low']):.0f}–${float(zc['bridge_high']):.0f}"
            )
        elif zc.get("gap_low") is not None and zc.get("gap_high") is not None:
            band_note = (
                f"in zone ${float(zc['gap_low']):.0f}–${float(zc['gap_high']):.0f}"
            )
        else:
            band_note = "in entry band"
        if parts:
            return f"Already {band_note} — unlock when: " + " + ".join(parts)
        return f"Already {band_note} — waiting on gate confirmation."
    elif zc.get("in_bridge_band") and zc.get("bridge_low") is not None:
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
    volume_ratio: float | None = None,
    obv_trend_pct: float | None = None,
    institutional_conviction: dict[str, Any] | None = None,
    momentum_extended: bool = False,
    tranche_idx: int = 0,
    ma50: float | None = None,
    high_52w: float | None = None,
    low_52w: float | None = None,
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
        volume_ratio=volume_ratio,
        obv_trend_pct=obv_trend_pct,
        momentum_extended=momentum_extended,
        tranche_idx=tranche_idx,
        close=current_price,
        ma50=ma50,
        high_52w=high_52w,
        low_52w=low_52w,
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
        "regime_weather_status": regime_weather_status(regime_bull_pct, momentum_extended=momentum_extended),
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
    if institutional_conviction:
        payload["institutional_conviction"] = institutional_conviction

    try:
        from signals.signal_reason_summary import build_signal_reason_summary

        payload["signal_reason"] = build_signal_reason_summary(
            ticker=ticker,
            gates=gates,
            assessment_pct=assessment_pct,
            current_price=current_price,
            fair_value=fair_value,
            regime_bull_pct=regime_bull_pct,
            market_regime_bull_pct=market_regime_bull_pct,
            pattern_score=pattern_score,
            rsi=rsi,
            short_ml_prob=short_ml_prob,
            overall_verdict=overall_verdict,
            entry_mode=None,
            gate_cleared=all_go,
            next_trigger=next_trigger,
            regime_transition_days=regime_transition_days,
            st_band=st_band,
        )
    except Exception:
        pass

    return payload


def enrich_investor_summary_retail_action(
    investor_out: dict[str, Any],
    current_price: float | None,
    *,
    ticker: str | None = None,
    market_regime_bull_pct: float | None = None,
    volume_ratio: float | None = None,
    obv_trend_pct: float | None = None,
    institutional_conviction: dict[str, Any] | None = None,
    real_st_band: dict[str, Any] | None = None,
    ma50: float | None = None,
    high_52w: float | None = None,
    low_52w: float | None = None,
) -> dict[str, Any]:
    """Attach retail_action block to investor_summary dict (mutates copy).

    Ticker-detail copy (unlock line, wait_plain, inside-band chip) must cite the
    same horizon `entry_zone` the levels panel paints. The scanner `st_band`
    (`real_st_band`) is a different pipeline — using it here recreated the
    sticky-footer mismatch (narrative 43.96–45.77 vs ENTRY $44.90–$47.16).
    Fall back to the scanner band only when the horizon zone is missing.
    """
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
    elif real_st_band and real_st_band.get("low") is not None and real_st_band.get("high") is not None:
        st_band = {"low": real_st_band["low"], "high": real_st_band["high"]}

    long_h = horizons.get("long") or {}
    rr = long_h.get("risk_reward")
    if rr is None and long_h.get("stop_loss") and long_h.get("target") and current_price:
        stop = float(long_h["stop_loss"])
        tgt = float(long_h["target"])
        cp = float(current_price)
        if cp > stop and tgt > cp:
            rr = (tgt - cp) / (cp - stop)
    if rr is None:
        rr = short.get("risk_reward")
    if rr is None and short.get("stop_loss") and short.get("target") and current_price:
        stop = float(short["stop_loss"])
        tgt = float(short["target"])
        cp = float(current_price)
        if cp > stop and tgt > cp:
            rr = (tgt - cp) / (cp - stop)

    long_spot = ((long_h.get("entry_tiers") or {}).get("spot_position")) or {}
    tranche_idx = tranche_idx_from_tier_id(
        long_spot.get("active_tier_id") or long_spot.get("tier_id") or long_spot.get("next_add_tier_id")
    )

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
        volume_ratio=volume_ratio,
        obv_trend_pct=obv_trend_pct,
        institutional_conviction=institutional_conviction,
        momentum_extended=bool(investor_out.get("regime_momentum_extended")),
        tranche_idx=tranche_idx,
        ma50=ma50,
        high_52w=high_52w,
        low_52w=low_52w,
    )

    short_spot = (short.get("entry_zone") or {}).get("spot_position") or {}
    medium_spot = (horizons.get("medium") or {}).get("entry_zone", {}).get("spot_position") or {}
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

        # Mode-aware variants: the flat action_title above always prefers long_spot
        # (owner's T1/T2/T3 tier language) whenever long-term tiers exist — which is
        # basically every ticker — so a Scout/Swing user saw "T2 IN RANGE" language
        # that only means anything in Owner mode. Each persona gets only its own
        # horizon's zone here instead of the long-biased fallback chain. Mirrors the
        # signal_reason_by_persona pattern (ticker_detail.py) for the same class of
        # "one field, three personas" problem.
        scout_title, scout_light = derive_zone_aware_action_title(
            investor_out.get("overall_verdict"),
            ra.get("gate_cleared", False),
            long_spot=None,
            short_spot=short_spot,
            in_bridge_band=bool(zone_ctx.get("in_bridge_band")),
        )
        swing_title, swing_light = derive_zone_aware_action_title(
            investor_out.get("overall_verdict"),
            ra.get("gate_cleared", False),
            long_spot=None,
            short_spot=medium_spot,
            in_bridge_band=bool(zone_ctx.get("in_bridge_band")),
        )
        ra["action_title_by_mode"] = {
            "scout": {"title": scout_title, "light": scout_light},
            "swing": {"title": swing_title, "light": swing_light},
            "owner": {"title": title, "light": light},
        }

    assessment_pct = float(ra.get("assessment_pct") or 0)
    entry = derive_entry_mode(
        gates=ra.get("gates") or [],
        assessment_pct=assessment_pct,
        gate_cleared=bool(ra.get("gate_cleared")),
        overall_verdict=investor_out.get("overall_verdict"),
        zone_context=zone_ctx,
        inside_buy_band=bool(ra.get("inside_buy_band")),
        long_spot=long_spot,
        institutional_conviction=institutional_conviction or ra.get("institutional_conviction"),
    )
    ra.update(entry)
    if entry["entry_mode"] == "full_go":
        ra["action_light"] = entry["action_light"]
    elif entry["entry_mode"] == "hard_lock" and not zone_ctx:
        ra["action_title"] = entry["entry_mode_headline"]
        ra["action_light"] = entry["action_light"]

    ra["unlock_sequence"] = build_unlock_sequence(
        ra.get("gates") or [],
        stock_bull_pct=investor_out.get("regime_bull_pct"),
    )
    unlock = build_unlock_summary(
        ra.get("gates") or [],
        stock_bull_pct=investor_out.get("regime_bull_pct"),
        zone_context=zone_ctx,
        st_band=st_band,
        current_price=float(current_price) if current_price is not None else None,
    )
    if unlock:
        ra["unlock_summary"] = unlock
    elif ra.get("entry_mode") != "full_go":
        ra["unlock_summary"] = ra["unlock_sequence"]

    try:
        from signals.signal_reason_summary import build_signal_reason_summary

        short = horizons.get("short") or {}
        oa = investor_out.get("one_answer") or {}
        ra["signal_reason"] = build_signal_reason_summary(
            ticker=ticker,
            gates=ra.get("gates") or [],
            assessment_pct=float(ra.get("assessment_pct") or 0),
            current_price=current_price,
            fair_value=investor_out.get("fair_value"),
            regime_bull_pct=investor_out.get("regime_bull_pct"),
            market_regime_bull_pct=market_regime_bull_pct or investor_out.get("market_regime_bull_pct"),
            pattern_score=investor_out.get("pattern_score"),
            rsi=investor_out.get("rsi"),
            short_ml_prob=short.get("ml_prob"),
            overall_verdict=investor_out.get("overall_verdict"),
            entry_mode=ra.get("entry_mode"),
            gate_cleared=bool(ra.get("gate_cleared")),
            next_trigger=ra.get("next_trigger"),
            regime_transition_days=investor_out.get("regime_transition_days_estimate"),
            st_band=st_band,
            trigger_buy=short.get("trigger_buy"),
            one_answer_action_today=oa.get("action_today"),
        )
        investor_out["signal_reason"] = ra["signal_reason"]
    except Exception:
        pass

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

    assessment = _assessment_from_lt_band(cp, row.get("lt_band"), row.get("lt_fair_value_mid"))
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
        volume_ratio=row.get("volume_ratio"),
        obv_trend_pct=row.get("obv_trend_10d_pct"),
        ma50=row.get("ma50"),
        high_52w=row.get("high_52w"),
        low_52w=row.get("low_52w"),
    )
    # List view uses LT band proxy — override valuation detail when no FV.
    # tranche_idx defaults to 0 (T1, first-dollar rung) — this path has no entry-tier
    # context, so it must not be implicitly held to the T3/deepest-tranche 25% bar.
    if assessment != 0:
        for g in payload["gates"]:
            if g["id"] == "valuation":
                ok, detail = _valuation_gate_detail(assessment, regime_bull_pct=rb)
                g["pass"] = ok
                g["gate_cleared"] = ok
                g["visual_status"] = "cleared" if ok else "blocked"
                g["icon"] = "✅" if ok else "❌"
                g["detail"] = detail.replace("fair value", "LT band")

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
    entry = derive_entry_mode(
        gates=payload.get("gates") or [],
        assessment_pct=assessment,
        gate_cleared=bool(payload.get("gate_cleared")),
        overall_verdict=row.get("plan_action") or row.get("signal"),
        inside_buy_band=bool(payload.get("inside_buy_band")),
    )
    payload.update(entry)
    payload["unlock_sequence"] = build_unlock_sequence(
        payload.get("gates") or [],
        stock_bull_pct=rb,
    )
    try:
        from signals.signal_reason_summary import build_signal_reason_summary

        payload["signal_reason"] = build_signal_reason_summary(
            ticker=row.get("ticker"),
            gates=payload.get("gates") or [],
            assessment_pct=assessment,
            current_price=float(cp) if cp is not None else None,
            regime_bull_pct=rb,
            market_regime_bull_pct=rb,
            pattern_score=row.get("confluence_score") or row.get("composite_buy"),
            rsi=row.get("rsi"),
            short_ml_prob=ml_pct,
            overall_verdict=row.get("plan_action") or row.get("signal"),
            entry_mode=entry["entry_mode"],
            gate_cleared=bool(payload.get("gate_cleared")),
            next_trigger=payload.get("next_trigger"),
            st_band=st_band if isinstance(st_band, dict) else None,
            global_market_regime=row.get("_global_market_regime"),
            earnings_days=int(row.get("earnings_days_until") or row.get("days_to_earnings"))
            if row.get("earnings_days_until") is not None or row.get("days_to_earnings") is not None
            else None,
        )
    except Exception:
        pass

    row["retail_status"] = payload
    row["rsi_status"] = payload["rsi_status"]
    row["gate_cleared"] = payload["gate_cleared"]
    row["entry_mode"] = entry["entry_mode"]
    row["max_sizing_pct"] = entry["max_sizing_pct"]
    align_ml_signal_with_retail_gates(row)
    try:
        from signals.trim_gates import attach_trim_gates_to_row

        attach_trim_gates_to_row(row, regime_bull_pct=rb)
    except Exception:
        pass
    return row


def align_ml_signal_with_retail_gates(row: dict[str, Any]) -> None:
    """
    Downgrade ML `signal` when retail gates block a full entry.

    BUY/STRONG BUY without full_go inflates audit win rate (technical BUY but gates say wait).
    Preserves ``signal_uncapped`` so paper trading can still log starter_only at partial size.
    """
    sig = str(row.get("signal") or "").strip().upper()
    if sig not in ("BUY", "STRONG BUY"):
        return
    em = str(row.get("entry_mode") or "").lower()
    # Only full_go unlocks BUY/STRONG BUY — 4/4 gates with starter/hard_lock is not a full entry.
    if em == "full_go":
        return
    row["signal_uncapped"] = sig
    if em == "starter_only":
        row["signal"] = "WATCH"
        row["signal_gate_capped"] = "starter_only"
        return
    row["signal"] = "WATCH" if sig == "BUY" else "HOLD"
    row["signal_gate_capped"] = em or "hard_lock"
