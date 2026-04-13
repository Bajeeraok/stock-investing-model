"""
Thrive Alpha — Signal Fusion Engine
Core scoring logic: divergence, blending, coherence, RSI direction,
transition bonus, regime transition probability, and conditional playbook.
"""

import math
from typing import Optional, Dict, Any
from datetime import datetime

from .constants import (
    AssetType, Thresholds, SignalMode, CoherenceLevel, RSISignal,
    WEIGHT_PROFILES
)
from .models import (
    SignalInput, ClassificationResult,
    DivergenceResult, BlendResult, RegimeTransitionResult,
    CoherenceResult, TransitionBonusResult, RSIDirectionResult,
    PlaybookScenario, FullEngineResult
)
from .asset_classifier import classify_asset


# ─────────────────────────────────────────────
# 1. SIGNAL DIVERGENCE SCORE
# ─────────────────────────────────────────────

def compute_signal_divergence(
    options_sentiment: Optional[float],
    ml_probability: Optional[float]
) -> Optional[DivergenceResult]:
    """
    Measures gap between options sentiment and ML probability.
    High score = smart money and model are strongly disagreeing.
    This is the key contrarian detection signal.

    WHERE TO INTEGRATE:
    Display as 'Signal Conflict Score' in the ticker card header.
    If is_high_conflict=True → trigger Contrarian Watch mode.
    Show direction label to explain which way the conflict runs.
    """
    if options_sentiment is None or ml_probability is None:
        return None

    score = abs(options_sentiment - ml_probability)

    if score >= 70:
        label = "EXTREME"
    elif score >= 50:
        label = "HIGH"
    elif score >= 30:
        label = "MODERATE"
    else:
        label = "LOW"

    direction = (
        "OPTIONS_BULLISH_ML_BEARISH"
        if options_sentiment > ml_probability
        else "ML_BULLISH_OPTIONS_BEARISH"
    )

    return DivergenceResult(
        score=round(score, 1),
        label=label,
        is_high_conflict=score >= Thresholds.DIVERGENCE_SCORE_MIN,
        direction=direction,
    )


# ─────────────────────────────────────────────
# 2. REGIME-WEIGHTED BLEND SCORE
# ─────────────────────────────────────────────

def compute_blended_score(
    signals: SignalInput,
    classification: ClassificationResult,
) -> BlendResult:
    """
    Replaces pure confidence suppression with a smart blend.
    In deep bear + high options sentiment → options gets elevated weight.
    Otherwise uses the asset-type-adjusted standard weights.

    WHERE TO INTEGRATE:
    Replace the existing ML Confidence gauge with this blended score.
    Show method label (CONTRARIAN_BLEND vs STANDARD_BLEND) as a subtext.
    Feed blended_score into the overall recommendation logic.
    """
    wp = classification.weight_profile
    s = signals

    is_contrarian = (
        s.hmm_bear_prob >= Thresholds.BEAR_REGIME_MIN
        and (s.options_sentiment or 0) >= Thresholds.OPTIONS_CONTRARIAN_MIN
    )

    if is_contrarian:
        # Contrarian blend: options gets 40% regardless of asset-type weight
        contrarian_weights = {
            "ml": 0.30, "options": 0.40,
            "pattern": 0.20, "fundamentals": 0.10,
        }
        blended = (
            (s.ml_probability or 0) * contrarian_weights["ml"] +
            (s.options_sentiment or 0) * contrarian_weights["options"] +
            (s.pattern_score or 0) * contrarian_weights["pattern"] +
            (s.fundamentals or 50) * contrarian_weights["fundamentals"]
        )
        return BlendResult(
            blended_score=round(blended, 1),
            method="CONTRARIAN_BLEND",
            weights_used=contrarian_weights,
            note="Deep bear + contrarian options: options sentiment elevated. ML weight reduced.",
        )

    # Standard asset-type blend
    active_score = 0.0
    active_weight = 0.0
    layer_map = {
        "regime":       (s.hmm_bull_prob,       wp.regime),
        "pattern":      (s.pattern_score,        wp.pattern),
        "ml":           (s.ml_probability,       wp.ml),
        "options":      (s.options_sentiment,    wp.options),
        "insider":      (s.insider_activity,     wp.insider),
        "fundamentals": (s.fundamentals,         wp.fundamentals),
    }
    for layer, (score, weight) in layer_map.items():
        if score is not None and weight > 0:
            active_score += score * weight
            active_weight += weight

    normalized = (active_score / active_weight * (1.0 / sum(
        w for _, w in layer_map.values() if w > 0
    ))) if active_weight > 0 else 0

    # Simpler: just normalize by active weight
    normalized = (active_score / active_weight) if active_weight > 0 else 0

    return BlendResult(
        blended_score=round(normalized, 1),
        method="STANDARD_BLEND",
        weights_used=wp.as_dict(),
        note=f"Standard {classification.weight_profile.label} weighting applied.",
    )


# ─────────────────────────────────────────────
# 3. REGIME TRANSITION PROBABILITY (forward-looking)
# ─────────────────────────────────────────────

def compute_regime_transition_probability(
    hmm_bear_prob: float,
    hmm_transition_prob: float,
    hmm_bull_prob: float,
    options_sentiment: Optional[float],
) -> RegimeTransitionResult:
    """
    Estimates forward probability of regime shifting from bear → transition.
    This is the missing forward-looking signal in the current model.

    WHERE TO INTEGRATE:
    Add as a new row in the signal layers section labeled 'Regime Shift Outlook'.
    Display as a percentage with a time estimate.
    If shift_probability > 30% → highlight in amber as WATCH_CLOSELY.
    """
    base_prob = hmm_transition_prob * 1.5  # amplify — transition > 0 is early signal
    base_prob += hmm_bull_prob * 0.5

    if options_sentiment is not None:
        if options_sentiment >= 70:
            base_prob += 15
        elif options_sentiment >= 55:
            base_prob += 8

    shift_probability = min(round(base_prob, 1), 95.0)

    if shift_probability >= 40:
        days_estimate = "5–10 days"
    elif shift_probability >= 20:
        days_estimate = "10–20 days"
    elif shift_probability >= 10:
        days_estimate = "20–40 days"
    else:
        days_estimate = "40+ days (uncertain)"

    label = "WATCH_CLOSELY" if shift_probability >= 30 else "EARLY_SIGNAL"

    return RegimeTransitionResult(
        shift_probability=shift_probability,
        days_estimate=days_estimate,
        label=label,
    )


# ─────────────────────────────────────────────
# 4. SIGNAL COHERENCE CHECK
# ─────────────────────────────────────────────

def compute_signal_coherence(
    signals: SignalInput,
    classification: ClassificationResult,
) -> CoherenceResult:
    """
    Measures how much all active signal layers agree.
    High variance = incoherent output = do not trade on this.

    WHERE TO INTEGRATE:
    Display coherence level as a badge next to the ticker header.
    If INCOHERENT → block position sizing and show warning.
    If is_contrarian=True → auto-trigger Contrarian Watch mode UI.
    """
    wp = classification.weight_profile
    s = signals

    layer_map = {
        "Regime":       (s.hmm_bull_prob,    wp.regime),
        "Pattern":      (s.pattern_score,    wp.pattern),
        "ML":           (s.ml_probability,   wp.ml),
        "Options":      (s.options_sentiment, wp.options),
        "Insider":      (s.insider_activity, wp.insider),
        "Fundamentals": (s.fundamentals,     wp.fundamentals),
    }

    active = [
        {"layer": layer, "score": score, "weight": weight}
        for layer, (score, weight) in layer_map.items()
        if weight > 0 and score is not None
    ]

    if len(active) < 2:
        return CoherenceResult(
            level=CoherenceLevel.INCOHERENT,
            std_dev=None, mean=None, spread=None,
            active_layer_count=len(active),
            active_layers=active,
            tradeable=False,
            is_contrarian=False,
            message="Insufficient active layers to assess coherence.",
        )

    scores = [a["score"] for a in active]
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    std_dev = math.sqrt(variance)
    spread = max(scores) - min(scores)

    tradeable = True
    if std_dev < Thresholds.COHERENCE_HIGH:
        level = CoherenceLevel.HIGH
    elif std_dev < Thresholds.COHERENCE_MODERATE:
        level = CoherenceLevel.MODERATE
    elif std_dev < Thresholds.COHERENCE_LOW:
        level = CoherenceLevel.LOW
        tradeable = False
    else:
        level = CoherenceLevel.INCOHERENT
        tradeable = False

    # Contrarian detection
    ml_score = s.ml_probability
    opt_score = s.options_sentiment
    is_contrarian = (
        ml_score is not None
        and opt_score is not None
        and abs(ml_score - opt_score) > Thresholds.DIVERGENCE_SCORE_MIN
    )
    opt_ml_gap = abs(ml_score - opt_score) if ml_score and opt_score else 0

    messages = {
        CoherenceLevel.HIGH: "Signals broadly aligned — model output reliable.",
        CoherenceLevel.MODERATE: (
            f"Contrarian divergence: options vs ML gap {opt_ml_gap:.0f}pts — apply Contrarian Watch."
            if is_contrarian else
            "Moderate disagreement — reduce position sizing."
        ),
        CoherenceLevel.LOW: "Significant signal conflict — wait for confirmation before entry.",
        CoherenceLevel.INCOHERENT: "All layers disagree — no actionable signal. Stand down.",
    }

    return CoherenceResult(
        level=level,
        std_dev=round(std_dev, 1),
        mean=round(mean, 1),
        spread=round(spread, 1),
        active_layer_count=len(active),
        active_layers=active,
        tradeable=tradeable,
        is_contrarian=is_contrarian,
        message=messages[level],
    )


# ─────────────────────────────────────────────
# 5. TRANSITION MOMENTUM BONUS (BABA fix)
# ─────────────────────────────────────────────

def compute_transition_bonus(signals: SignalInput) -> TransitionBonusResult:
    """
    If HMM is in deep Transition + ML is strong → upgrade from HOLD/WATCH to ACCUMULATE.
    This fixes the BABA scenario where transition 88% + ML 70% was still showing HOLD.

    WHERE TO INTEGRATE:
    If bonus_active=True → override the recommendation badge to show ACCUMULATE.
    Show the upgrade arrow (HOLD/WATCH → ACCUMULATE) prominently in amber.
    Display rationale text below the main badge.
    Add position_bonus to the existing max position size.
    """
    t = signals.hmm_transition_prob
    ml = signals.ml_probability or 0
    bear = signals.hmm_bear_prob

    if (
        t >= Thresholds.TRANSITION_BONUS_HMM
        and ml >= Thresholds.TRANSITION_BONUS_ML
        and bear < Thresholds.TRANSITION_BONUS_BEAR
    ):
        # Estimate days to bull confirmation
        bull = signals.hmm_bull_prob
        days_to_confirm = max(1, round((100 - bull) / max(t * 0.1, 1)))

        return TransitionBonusResult(
            bonus_active=True,
            upgrade="HOLD/WATCH → ACCUMULATE",
            position_bonus=0.02,  # Allow +2% additional position
            rationale=(
                f"HMM Transition {t:.0f}% + ML {ml:.0f}% = bull confirmation imminent. "
                f"Regime flip expected within ~{days_to_confirm} days."
            ),
            days_to_confirm=days_to_confirm,
        )

    return TransitionBonusResult(bonus_active=False)


# ─────────────────────────────────────────────
# 6. RSI DIRECTION SIGNAL
# ─────────────────────────────────────────────

def compute_rsi_direction(
    rsi_current: Optional[float],
    rsi_previous: Optional[float],
) -> Optional[RSIDirectionResult]:
    """
    Tracks RSI direction rather than just level.
    RSI 30 turning UP is bullish. RSI 30 turning DOWN is bearish (falling knife).
    This is the BABA pattern score fix — adds direction to pattern scoring.

    WHERE TO INTEGRATE:
    Add as a sub-indicator under the Pattern Score layer.
    Apply pattern_bonus to the raw pattern score before composite calculation.
    Display signal label with color coding (green for OVERSOLD_REVERSAL, etc.).
    """
    if rsi_current is None:
        return None

    rsi_prev = rsi_previous if rsi_previous is not None else rsi_current
    delta = rsi_current - rsi_prev
    is_oversold = rsi_current <= Thresholds.RSI_OVERSOLD
    is_overbought = rsi_current >= Thresholds.RSI_OVERBOUGHT

    if is_oversold and delta > 0:
        signal = RSISignal.OVERSOLD_REVERSAL
        pattern_bonus = 20
    elif is_oversold and delta <= 0:
        signal = RSISignal.OVERSOLD_FALLING
        pattern_bonus = -5
    elif is_overbought and delta < 0:
        signal = RSISignal.OVERBOUGHT_REVERSAL
        pattern_bonus = -15
    elif is_overbought and delta >= 0:
        signal = RSISignal.OVERBOUGHT_MOMENTUM
        pattern_bonus = 5
    else:
        signal = RSISignal.NEUTRAL
        pattern_bonus = 0

    labels = {
        RSISignal.OVERSOLD_REVERSAL:   "Oversold Reversal ↑ — Bullish",
        RSISignal.OVERSOLD_FALLING:    "Oversold Falling ↓ — Falling Knife",
        RSISignal.OVERBOUGHT_REVERSAL: "Overbought Reversal ↓ — Trim Signal",
        RSISignal.OVERBOUGHT_MOMENTUM: "Overbought Momentum ↑ — Caution on Entry",
        RSISignal.NEUTRAL:             "Neutral — No RSI edge",
    }

    return RSIDirectionResult(
        signal=signal,
        label=labels[signal],
        rsi_current=rsi_current,
        delta=round(delta, 1),
        pattern_bonus=pattern_bonus,
        is_oversold=is_oversold,
        is_overbought=is_overbought,
    )


# ─────────────────────────────────────────────
# 7. CONDITIONAL PLAYBOOK ENGINE
# ─────────────────────────────────────────────

def run_conditional_playbook(
    signals: SignalInput,
    classification: ClassificationResult,
) -> tuple[SignalMode, str, float, list[PlaybookScenario]]:
    """
    The main decision engine.
    Returns current mode, action text, position multiplier, and full playbook.

    WHERE TO INTEGRATE:
    Replace the existing AVOID/BUY/HOLD badge logic with current_mode.
    Display the full playbook as collapsible scenarios below the main card.
    Highlight the active scenario (condition_met=True) in amber.
    Gray out pending scenarios but keep them visible.
    """
    s = signals
    pb = s.price_bands or {}

    # ── Evaluate conditions ──────────────────
    is_deep_bear        = s.hmm_bear_prob >= Thresholds.BEAR_REGIME_MIN
    is_contrarian_opts  = (s.options_sentiment or 0) >= Thresholds.OPTIONS_CONTRARIAN_MIN
    is_high_divergence  = (
        s.ml_probability is not None and s.options_sentiment is not None
        and abs(s.options_sentiment - s.ml_probability) >= Thresholds.DIVERGENCE_SCORE_MIN
    )
    is_ml_recovering    = (s.ml_probability or 0) >= Thresholds.ML_STAGE2_TRIGGER
    is_pattern_recover  = (s.pattern_score or 0) >= Thresholds.PATTERN_STAGE2_TRIGGER
    is_regime_shifting  = (
        s.hmm_bear_prob < Thresholds.HMM_BEAR_EXIT
        and s.hmm_transition_prob >= Thresholds.HMM_TRANSITION_MIN
    )
    is_options_fading   = (s.options_sentiment or 100) < Thresholds.OPTIONS_FADE_MAX

    # ── Determine current mode ───────────────
    if is_options_fading and not is_ml_recovering:
        mode = SignalMode.STAND_DOWN
        action = "Options thesis invalidated. Hold cash. Wait for MT band floor."
        pos_size = 0.0

    elif is_regime_shifting and (s.ml_probability or 0) >= Thresholds.ML_FULL_TRIGGER:
        mode = SignalMode.FULL_POSITION
        action = "Regime shifting + ML recovering. Deploy full position. Set trailing stop at MA50."
        pos_size = 1.0

    elif is_ml_recovering or is_pattern_recover:
        mode = SignalMode.STAGE_2_ACCUMULATE
        action = "ML/Pattern confirming. Deploy Stage 2 (additional 35%). Watch sell level."
        pos_size = 0.35

    elif is_deep_bear and is_contrarian_opts and is_high_divergence:
        mode = SignalMode.CONTRARIAN_WATCH
        action = "Deep bear + smart money divergence. Deploy Stage 1 (25%). Watch ML crossing 25%."
        pos_size = 0.25

    else:
        mode = SignalMode.AVOID
        action = "No contrarian confirmation. Stay out. Monitor daily."
        pos_size = 0.0

    # ── Build scenario tree ──────────────────
    scenarios = [
        PlaybookScenario(
            scenario_id=1,
            name="Bear + Contrarian Options",
            condition_desc="HMM Bear >80% AND Options >65% AND ML <20%",
            condition_met=is_deep_bear and is_contrarian_opts and not is_ml_recovering,
            mode=SignalMode.CONTRARIAN_WATCH,
            action="STAGE 1 — Deploy 25% of intended position",
            conflict_score="HIGH",
            details={
                "entry_zone":       pb.get("short_term_low", "ST band low"),
                "next_trigger":     "ML > 25% OR Pattern Score > 45%",
                "stop_condition":   f"Price breaks {pb.get('mt_band_low', '$272')} on volume → pause",
                "position_size":    "25%",
                "kelly_fraction":   "Kelly × 0.25",
                "note":             "Smart money positioning. Let price prove itself before committing more.",
            },
        ),
        PlaybookScenario(
            scenario_id=2,
            name="ML Probability Recovers",
            condition_desc="ML crosses 25% AND HMM still bearish AND Options still elevated",
            condition_met=is_ml_recovering and is_deep_bear and is_contrarian_opts,
            mode=SignalMode.STAGE_2_ACCUMULATE,
            action="STAGE 2 — Deploy additional 35% (60% total)",
            conflict_score="MODERATE",
            details={
                "entry_zone":       "Current price or MT band low on dip",
                "sell_alert":       pb.get("sell_level", "Model sell level"),
                "next_trigger":     "HMM Bear drops below 60%",
                "position_size":    "35% additional (60% total)",
                "kelly_fraction":   "Kelly × 0.50",
                "note":             "ML and options now aligned. Retain 40% dry powder for regime shift entry.",
            },
        ),
        PlaybookScenario(
            scenario_id=3,
            name="Regime Shifts to Transition",
            condition_desc="HMM Bear <60% AND Transition >30% AND Pattern Score >50%",
            condition_met=is_regime_shifting,
            mode=SignalMode.FULL_POSITION,
            action="STAGE 3 — Full position. Highest conviction.",
            conflict_score="LOW",
            details={
                "entry_zone":       "Any dip toward MA50",
                "trailing_stop":    "MA50 (dynamic)",
                "position_size":    "Remaining 40% (100% total)",
                "kelly_fraction":   "Full Kelly",
                "note":             "This is the signal you have been waiting for. Act decisively.",
            },
        ),
        PlaybookScenario(
            scenario_id=4,
            name="Options Fade Before ML Recovers",
            condition_desc="Options <50% AND ML still <20%",
            condition_met=is_options_fading and not is_ml_recovering,
            mode=SignalMode.STAND_DOWN,
            action="STAND DOWN — Contrarian thesis invalidated",
            conflict_score="N/A",
            details={
                "wait_for":         pb.get("mt_band_low", "MT band floor"),
                "position_size":    "0%",
                "kelly_fraction":   "0",
                "note":             "Smart money exited early. Do not chase. Patience is the position.",
            },
        ),
        PlaybookScenario(
            scenario_id=5,
            name="Earnings Catalyst",
            condition_desc="Within 5 days post-earnings AND price drops >5% on volume",
            condition_met=bool(
                (s.days_since_earnings is not None and s.days_since_earnings <= 5)
                and (s.post_earnings_return_pct is not None and s.post_earnings_return_pct <= -5.0)
                and (
                    s.post_earnings_volume_ratio is None
                    or s.post_earnings_volume_ratio >= 1.5
                )
            ),
            mode=SignalMode.HOLD_WATCH,
            action="Re-run full playbook with fresh signals on earnings+1",
            conflict_score="DYNAMIC",
            details={
                "bull_case":        "Strong earnings + ML recovers → accelerate to Stage 3",
                "bear_case":        f"Miss + ML stays low → wait for {pb.get('mt_band_low', 'MT floor')}",
                "position_size":    "Up to 40% of remaining dry powder",
                "note":             "Earnings reset all signals. Re-evaluate fresh on earnings+1 day.",
                "earnings_date":    s.earnings_date or "Unknown",
                "days_since_earnings": s.days_since_earnings,
                "post_earnings_return_pct": s.post_earnings_return_pct,
                "post_earnings_volume_ratio": s.post_earnings_volume_ratio,
            },
        ),
    ]

    # Exclude equity-only scenarios for commodity/volatility ETFs (no earnings)
    if classification.asset_type in (AssetType.ETF_COMMODITY, AssetType.ETF_VOLATILITY):
        scenarios = [sc for sc in scenarios if sc.name != "Earnings Catalyst"]

    # Deep bear: surface bear / earnings-adjacent scenarios first (display order only)
    if is_deep_bear:
        _order = {1: 0, 5: 1, 2: 2, 3: 3, 4: 4}
        scenarios = sorted(scenarios, key=lambda sc: _order.get(sc.scenario_id, 99))

    return mode, action, pos_size, scenarios


# ─────────────────────────────────────────────
# 8. MASTER ENGINE — full pipeline
# ─────────────────────────────────────────────

def run_full_engine(signals: SignalInput) -> FullEngineResult:
    """
    Master function. Runs the complete pre-flight + signal fusion pipeline.
    Call this from your API endpoint / backend route.

    WHERE TO INTEGRATE IN THRIVE ALPHA:
    Replace existing scoring function with this.
    Map FullEngineResult fields to existing UI component props.
    See UI_INTEGRATION_MAP below for exact field mappings.

    INTEGRATION ORDER:
    1. classify_asset()        → determines weight profile + flags
    2. compute_signal_coherence() → coherence check, may block scoring
    3. compute_transition_bonus() → BABA-type upgrade check
    4. compute_rsi_direction()    → RSI direction for pattern adjustment
    5. compute_signal_divergence() → contrarian detection
    6. compute_blended_score()     → composite score
    7. compute_regime_transition() → forward regime outlook
    8. run_conditional_playbook()  → mode + action + scenarios
    """
    # Step 1: Classify asset
    classification = classify_asset(signals.ticker)

    # Step 2: Early exit for incompatible instruments
    if not classification.is_scoreable:
        return FullEngineResult(
            ticker=signals.ticker,
            timestamp=datetime.utcnow().isoformat(),
            classification=classification,
            pre_flight_flags=classification.flags,
            is_scoreable=False,
            current_mode=SignalMode.INCOMPATIBLE,
            current_action="Standard equity model not applicable for this instrument type.",
            position_size_multiplier=0.0,
            divergence=None, blend=None, regime_transition=None,
            coherence=None, transition_bonus=None, rsi_signal=None,
            playbook=[],
            summary={
                "signal_conflict":  "N/A",
                "blended_score":    None,
                "blend_method":     "INCOMPATIBLE",
                "regime_shift_prob": "N/A",
                "recommendation":   "Use dedicated instrument-type model",
                "flag_count":       len(classification.flags),
            },
        )

    # Step 3: Run all analyses
    coherence        = compute_signal_coherence(signals, classification)
    transition_bonus = compute_transition_bonus(signals)
    rsi_signal       = compute_rsi_direction(signals.rsi_current, signals.rsi_previous)
    divergence       = compute_signal_divergence(signals.options_sentiment, signals.ml_probability)
    blend            = compute_blended_score(signals, classification)
    regime_trans     = compute_regime_transition_probability(
                           signals.hmm_bear_prob, signals.hmm_transition_prob,
                           signals.hmm_bull_prob, signals.options_sentiment)
    mode, action, pos_size, playbook = run_conditional_playbook(signals, classification)

    # Apply RSI pattern bonus to adjust pattern score context
    effective_pattern = (signals.pattern_score or 0)
    if rsi_signal:
        effective_pattern = min(100, max(0, effective_pattern + rsi_signal.pattern_bonus))

    # Override mode if transition bonus active
    if transition_bonus.bonus_active and mode in (SignalMode.AVOID, SignalMode.HOLD_WATCH):
        mode = SignalMode.STAGE_1_ACCUMULATE
        action = f"Transition Bonus Active: {transition_bonus.upgrade}. {transition_bonus.rationale}"
        pos_size = 0.02  # Start with bonus position size

    return FullEngineResult(
        ticker=signals.ticker,
        timestamp=datetime.utcnow().isoformat(),
        classification=classification,
        pre_flight_flags=classification.flags,
        is_scoreable=True,
        current_mode=mode,
        current_action=action,
        position_size_multiplier=pos_size,
        divergence=divergence,
        blend=blend,
        regime_transition=regime_trans,
        coherence=coherence,
        transition_bonus=transition_bonus,
        rsi_signal=rsi_signal,
        playbook=playbook,
        summary={
            "signal_conflict":  divergence.label if divergence else "N/A",
            "divergence_score": divergence.score if divergence else None,
            "blended_score":    blend.blended_score,
            "blend_method":     blend.method,
            "coherence_level":  coherence.level.value,
            "coherence_tradeable": coherence.tradeable,
            "regime_shift_prob": f"{regime_trans.shift_probability}% within {regime_trans.days_estimate}",
            "transition_bonus_active": transition_bonus.bonus_active,
            "rsi_signal":       rsi_signal.signal.value if rsi_signal else None,
            "pattern_bonus":    rsi_signal.pattern_bonus if rsi_signal else 0,
            "effective_pattern": effective_pattern,
            "recommendation":   action,
            "position_size":    f"{round(pos_size * 100)}%",
            "flag_count":       len(classification.flags),
            "asset_type":       classification.asset_type.value,
        },
    )


# ─────────────────────────────────────────────
# UI INTEGRATION MAP (reference for developers)
# ─────────────────────────────────────────────

UI_INTEGRATION_MAP = """
THRIVE ALPHA UI — WHERE EACH OUTPUT MAPS

FullEngineResult field               → UI Component / Location
─────────────────────────────────────────────────────────────
current_mode                         → Main badge (AVOID/BUY/CONTRARIAN_WATCH etc.)
current_action                       → Action description text below badge
position_size_multiplier             → Position size chip (e.g. "25%")
summary.blended_score                → ML Confidence gauge (replace raw ML %)
summary.blend_method                 → Subtext under gauge ("CONTRARIAN_BLEND")
summary.divergence_score             → New "Signal Conflict" row in layers
divergence.label                     → Conflict badge (HIGH/MODERATE/LOW)
coherence.level                      → Coherence badge in ticker card header
coherence.message                    → Tooltip on coherence badge
coherence.tradeable                  → If False, disable position size inputs
transition_bonus.bonus_active        → Show amber "TRANSITION BONUS" banner
transition_bonus.upgrade             → Upgrade arrow text in banner
transition_bonus.rationale           → Banner explanation text
rsi_signal.signal                    → Sub-indicator under Pattern Score row
rsi_signal.pattern_bonus             → "+20pts" label next to Pattern Score
rsi_signal.label                     → Tooltip on RSI direction indicator
regime_transition.shift_probability  → New row "Regime Shift Outlook X%"
regime_transition.days_estimate      → Time estimate next to probability
classification.flags                 → Warning icons in ticker header
classification.asset_type            → Asset type tag (ADR, ETF, etc.)
classification.weight_profile        → "How is X% calculated?" breakdown table
playbook                             → Collapsible "Conditional Playbook" section
playbook[n].condition_met            → Highlights active scenario in amber
playbook[n].condition_desc           → Scenario condition text
playbook[n].action                   → Scenario action text
playbook[n].details                  → Scenario detail rows
"""
