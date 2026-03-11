"""
horizon_entry_calculator.py
============================
Calculates proper, anchor-based entry prices for all 3 investment horizons
in Thrive Alpha signal cards.

Each horizon uses a different anchor — not the naive "current price = entry":
  SHORT  (1m)     RSI state -> VWAP -> recent support + ATR stops
  MEDIUM (3m)     MA50 zone + earnings catalyst + fundamentals quality
  LONG   (6-18m)  MA200 + 25% MOS tiers + 52w low deep value

FastAPI integration:
    from horizon_entry_calculator import build_all_horizons_payload, estimate_fair_value
    response["horizons"] = build_all_horizons_payload(**signal_data)

Run standalone test:
    python horizon_entry_calculator.py
"""

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dataclasses import dataclass, asdict
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS  — tune these per your model calibration
# ══════════════════════════════════════════════════════════════════════════════

# Short-term
ST_RSI_OVERSOLD        = 35.0   # RSI below = oversold, ideal entry
ST_RSI_OVERBOUGHT      = 65.0   # RSI above = overbought, avoid entry
ST_MIN_ML_PROB         = 25.0   # minimum ML prob for short-term signal
ST_ATR_STOP_MULT       = 1.5    # stop = entry_low - (ATR * mult)
ST_ATR_TARGET_MULT     = 3.0    # target = entry_high + (ATR * mult)
ST_MIN_RR              = 1.5    # minimum acceptable risk/reward

# Medium-term
MT_MA50_BAND_PCT       = 4.0    # acceptable range above MA50 for entry
MT_MIN_ML_PROB         = 35.0   # minimum ML prob for medium-term signal
MT_EARNINGS_WINDOW     = 60     # days — earnings within this = catalyst flag
MT_STOP_BELOW_MA50_PCT = 6.0    # stop = MA50 * (1 - pct) — MA50 break invalidates
MT_MIN_RR              = 2.0    # minimum R/R enforced for medium-term

# Long-term
LT_REQUIRED_MOS_PCT    = 25.0   # minimum margin of safety for full buy
LT_PARTIAL_MOS_PCT     = 15.0   # partial position threshold
LT_MA200_BAND_PCT      = 5.0    # Tier 1: MA200 +- 5%
LT_TIER2_MOS_PCT       = 25.0   # Tier 2: fair_value * 0.75
LT_TIER2_BAND_PCT      = 3.0    # Tier 2: +- 3% around target
LT_TIER3_LOW_MULT      = 1.05   # Tier 3: 52w_low * 1.05
LT_TIER3_HIGH_MULT     = 1.15   # Tier 3: 52w_low * 1.15
LT_MAX_ABOVE_MA200_PCT = 15.0   # flag if price > MA200 by more than this


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EntryZone:
    low: float
    high: float
    anchor: str         # what this zone is based on (for display)
    quality: str        # Ideal | Acceptable | Stretched | Waiting | In Zone
    quality_color: str  # hex color for frontend badge


@dataclass
class EntryTier:
    """Long-term only — one of three tiered entry zones."""
    id: str                          # T1 | T2 | T3
    label: str
    description: str
    low: float
    high: float
    upside_to_fv_pct: float          # % upside from entry high to fair value
    margin_of_safety_pct: float
    estimated_rr: str                # e.g. "~2.5x"
    conviction: str                  # Medium | High | Highest
    color: str                       # hex
    reachable: bool                  # True = price still above tier, needs to fall
    drop_needed_pct: Optional[float] # how much price must fall to reach tier high


@dataclass
class HorizonSignal:
    label: str
    duration: str
    verdict: str        # WAIT | WATCH | BUY | STRONG BUY
    signal: str         # Weak | Cautious | Neutral | Moderate | Strong
    conviction: str     # Low | Medium | High
    ml_prob: float
    entry_zone: EntryZone
    target: float
    target_pct: float
    stop_loss: float
    stop_loss_pct: float
    risk_reward: float
    rationale: str
    trigger_buy: str
    warnings: list
    entry_tiers: Optional[dict] = None   # long-term only
    fair_value: Optional[float] = None   # long-term only


# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _r(value: float, decimals: int = 2) -> float:
    return round(value, decimals)


def _ml_to_signal(prob: float) -> str:
    if prob < 15:  return "Weak"
    if prob < 30:  return "Cautious"
    if prob < 50:  return "Neutral"
    if prob < 65:  return "Moderate"
    return "Strong"


# ══════════════════════════════════════════════════════════════════════════════
# SHORT-TERM CALCULATOR  (1 month)
# ──────────────────────────────────────────────────────────────────────────────
# Entry logic — RSI gates the anchor:
#   RSI < 35  (oversold)  → entry near lower of support or VWAP
#   RSI 35-50 (neutral)   → VWAP pullback zone
#   RSI > 50  (elevated)  → current price, flagged as stretched
#
# Stop:   entry_low  - (ATR × 1.5)
# Target: min(resistance × 0.98,  entry_high + ATR × 3.0)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ShortTermInputs:
    current_price: float
    ml_prob: float           # 1-month ML probability
    rsi: float               # 14-day RSI
    atr: float               # 14-day Average True Range
    vwap: float              # Volume Weighted Average Price
    support_level: float     # nearest technical support (recent swing low)
    resistance_level: float  # nearest resistance
    regime_bull_pct: float   # HMM bull regime probability
    pattern_score: float     # technical pattern score 0-100
    volume_ratio: float      # today's volume / 20-day avg volume


def compute_short_term_entry(inp: ShortTermInputs) -> HorizonSignal:
    warnings = []

    # ── Entry zone ───────────────────────────────────────────────────────
    if inp.rsi < ST_RSI_OVERSOLD:
        anchor = min(inp.support_level, inp.vwap)
        el, eh = _r(anchor * 0.99), _r(anchor * 1.01)
        quality, q_color = "Ideal", "#00e5a0"
        zone_anchor = "RSI oversold ({:.0f}) — entry near support ${:.2f}".format(
            inp.rsi, inp.support_level)

    elif inp.rsi < 50:
        el, eh = _r(inp.vwap * 0.985), _r(inp.vwap * 1.005)
        quality, q_color = "Acceptable", "#f5a623"
        zone_anchor = "VWAP pullback zone (RSI {:.0f})".format(inp.rsi)

    else:
        el, eh = _r(inp.current_price * 0.99), _r(inp.current_price * 1.005)
        quality, q_color = "Stretched", "#ff6b6b"
        zone_anchor = "Current price — RSI elevated ({:.0f}), not ideal".format(inp.rsi)
        warnings.append(
            "RSI {:.0f} is elevated — wait for pullback to VWAP (${:.2f}) for better entry".format(
                inp.rsi, inp.vwap))

    # ── Stop & target ────────────────────────────────────────────────────
    stop_loss     = _r(el - inp.atr * ST_ATR_STOP_MULT)
    stop_loss_pct = _r((stop_loss - eh) / eh * 100, 1)
    target        = _r(min(inp.resistance_level * 0.98, eh + inp.atr * ST_ATR_TARGET_MULT))
    target_pct    = _r((target - eh) / eh * 100, 1)
    risk          = eh - stop_loss
    rr            = _r((target - eh) / risk, 2) if risk > 0 else 0.0

    # ── Warnings ─────────────────────────────────────────────────────────
    if rr < ST_MIN_RR:
        warnings.append(
            "R/R {:.2f}x is below {:.1f}x minimum — consider tighter stop or skip".format(rr, ST_MIN_RR))
    if inp.volume_ratio < 0.7:
        warnings.append(
            "Low volume ({:.1f}x average) — conviction in move is weak".format(inp.volume_ratio))

    # ── Verdict ──────────────────────────────────────────────────────────
    all_clear = (inp.ml_prob >= ST_MIN_ML_PROB and inp.rsi < ST_RSI_OVERBOUGHT
                 and inp.regime_bull_pct >= 40 and inp.pattern_score >= 55 and rr >= ST_MIN_RR)
    if all_clear:
        verdict, conviction = "BUY", "Medium"
    elif inp.ml_prob >= ST_MIN_ML_PROB and rr >= 1.2:
        verdict, conviction = "WATCH", "Low"
    else:
        verdict, conviction = "WAIT", "Low"

    # ── Rationale & trigger ──────────────────────────────────────────────
    rsi_note = ("oversold — bounce setup" if inp.rsi < ST_RSI_OVERSOLD
                else "overbought — reversal risk" if inp.rsi > ST_RSI_OVERBOUGHT
                else "neutral")
    rationale = (
        "ML {:.0f}% ({} {:.0f}% threshold). "
        "RSI {:.0f} — {}. "
        "R/R {:.2f}x. Pattern score {:.0f}/100."
    ).format(
        inp.ml_prob, "above" if inp.ml_prob >= ST_MIN_ML_PROB else "below",
        ST_MIN_ML_PROB, inp.rsi, rsi_note, rr, inp.pattern_score)

    trigger = (
        "Price pulls back to ${el}–${eh} "
        "AND RSI < {rsi_thresh:.0f} "
        "AND ML prob > {ml_thresh:.0f}%"
    ).format(el=el, eh=eh, rsi_thresh=ST_RSI_OVERSOLD, ml_thresh=ST_MIN_ML_PROB)

    return HorizonSignal(
        label="Short-term", duration="1 month",
        verdict=verdict, signal=_ml_to_signal(inp.ml_prob), conviction=conviction,
        ml_prob=inp.ml_prob,
        entry_zone=EntryZone(el, eh, zone_anchor, quality, q_color),
        target=target, target_pct=target_pct,
        stop_loss=stop_loss, stop_loss_pct=stop_loss_pct,
        risk_reward=rr, rationale=rationale, trigger_buy=trigger, warnings=warnings,
    )


# ══════════════════════════════════════════════════════════════════════════════
# MEDIUM-TERM CALCULATOR  (3 months)
# ──────────────────────────────────────────────────────────────────────────────
# Entry logic — anchored to MA50 (trend support):
#   Price at/below MA50          → Ideal zone  (MA50 × 0.97–1.01)
#   Price within 4% above MA50   → Acceptable  (MA50 × 0.99–1.04)
#   Price > 4% above MA50        → Stretched, flag and wait
#
# Stop:   MA50 × (1 − 6%)   — MA50 break invalidates medium-term thesis
# Target: ML-prob scaled 0–25%, amplified by quality multiplier
#         Minimum 2:1 R/R enforced (target bumped up if needed)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class MediumTermInputs:
    current_price: float
    ml_prob: float               # 3-month ML probability
    ma50: float                  # 50-day moving average
    ma200: float                 # 200-day moving average
    atr: float                   # ATR for context
    regime_bull_pct: float
    pattern_score: float
    days_to_earnings: Optional[int]
    options_sentiment_score: float   # 0-100, your existing options layer
    insider_activity_score: float    # 0-100, your existing insider layer
    fundamentals_score: float        # 0-100, your existing fundamentals layer


def compute_medium_term_entry(inp: MediumTermInputs) -> HorizonSignal:
    p = inp.current_price
    warnings = []
    pct_above_ma50 = (p - inp.ma50) / inp.ma50 * 100

    # ── Entry zone anchored to MA50 ──────────────────────────────────────
    if pct_above_ma50 <= 0:
        el, eh = _r(inp.ma50 * 0.97), _r(inp.ma50 * 1.01)
        quality, q_color = "Ideal", "#00e5a0"
        zone_anchor = "At/below MA50 (${:.2f}) — trend dip-buy zone".format(inp.ma50)

    elif pct_above_ma50 <= MT_MA50_BAND_PCT:
        el, eh = _r(inp.ma50 * 0.99), _r(inp.ma50 * (1 + MT_MA50_BAND_PCT / 100))
        quality, q_color = "Acceptable", "#f5a623"
        zone_anchor = "Within {:.0f}% above MA50 (${:.2f})".format(MT_MA50_BAND_PCT, inp.ma50)

    else:
        el, eh = _r(inp.ma50 * 0.99), _r(inp.ma50 * 1.04)
        quality, q_color = "Stretched", "#ff6b6b"
        zone_anchor = "Price {:.1f}% above MA50 — wait for pullback to ${:.2f}".format(
            pct_above_ma50, inp.ma50)
        warnings.append(
            "Price is {:.1f}% above MA50 (${:.2f}). "
            "Ideal medium-term entry: ${:.2f}–${:.2f}".format(
                pct_above_ma50, inp.ma50, el, eh))

    # ── Stop: below MA50 — break invalidates thesis ──────────────────────
    stop_loss     = _r(inp.ma50 * (1 - MT_STOP_BELOW_MA50_PCT / 100))
    stop_loss_pct = _r((stop_loss - eh) / eh * 100, 1)

    # ── Target: ML-scaled with quality multiplier ────────────────────────
    quality_mult = 1.0
    if inp.fundamentals_score >= 70:       quality_mult += 0.03
    if inp.options_sentiment_score >= 60:  quality_mult += 0.02
    if inp.insider_activity_score >= 60:   quality_mult += 0.02

    target_pct = _r(inp.ml_prob / 100 * 25 * quality_mult, 1)
    target     = _r(eh * (1 + target_pct / 100))
    risk       = eh - stop_loss
    rr         = _r((target - eh) / risk, 2) if risk > 0 else 0.0

    # Enforce minimum 2:1 R/R
    if rr < MT_MIN_RR:
        target     = _r(eh + risk * MT_MIN_RR)
        target_pct = _r((target - eh) / eh * 100, 1)
        rr         = MT_MIN_RR
        warnings.append(
            "Target adjusted upward to enforce minimum {:.1f}x R/R".format(MT_MIN_RR))

    # ── Earnings flag ────────────────────────────────────────────────────
    earnings_flag = bool(inp.days_to_earnings and inp.days_to_earnings <= MT_EARNINGS_WINDOW)
    if earnings_flag:
        warnings.append(
            "Earnings in {} days — position before for catalyst, "
            "or wait for post-earnings reaction to reduce binary risk".format(inp.days_to_earnings))

    # ── MA200 trend check ────────────────────────────────────────────────
    if p < inp.ma200:
        warnings.append(
            "Price (${:.2f}) is below MA200 (${:.2f}) — "
            "medium-term trend is bearish, reduce position size".format(p, inp.ma200))

    # ── Verdict ──────────────────────────────────────────────────────────
    if (inp.ml_prob >= MT_MIN_ML_PROB and quality in ("Ideal", "Acceptable")
            and inp.regime_bull_pct >= 45 and rr >= MT_MIN_RR):
        if inp.ml_prob >= 50:
            verdict, conviction = "BUY", "High"
        else:
            verdict, conviction = "WATCH", "Medium"
    elif inp.ml_prob >= 30 and quality != "Stretched":
        verdict, conviction = "WATCH", "Low"
    else:
        verdict, conviction = "WAIT", "Low"

    # ── Rationale & trigger ──────────────────────────────────────────────
    rationale = (
        "ML {ml:.0f}% ({dir} {thresh:.0f}% threshold). "
        "Price {pct:.1f}% {abv} MA50 (${ma:.2f}). "
        "{earn}"
        "Fundamentals {fund:.0f}/100. "
        "R/R {rr:.1f}x."
    ).format(
        ml=inp.ml_prob,
        dir="clears" if inp.ml_prob >= MT_MIN_ML_PROB else "below",
        thresh=MT_MIN_ML_PROB,
        pct=abs(pct_above_ma50),
        abv="above" if pct_above_ma50 > 0 else "below",
        ma=inp.ma50,
        earn="Earnings in {}d — catalyst. ".format(inp.days_to_earnings) if earnings_flag else "",
        fund=inp.fundamentals_score,
        rr=rr)

    trigger = (
        "Price pulls back to MA50 zone (${el}–${eh}) "
        "AND ML prob >= {ml:.0f}% "
        "AND regime Bull >= 45%"
        "{earn}"
    ).format(
        el=el, eh=eh, ml=MT_MIN_ML_PROB,
        earn=" — OR enter pre-earnings ({}d) with half position".format(
            inp.days_to_earnings) if earnings_flag else "")

    return HorizonSignal(
        label="Medium-term", duration="3 months",
        verdict=verdict, signal=_ml_to_signal(inp.ml_prob), conviction=conviction,
        ml_prob=inp.ml_prob,
        entry_zone=EntryZone(el, eh, zone_anchor, quality, q_color),
        target=target, target_pct=target_pct,
        stop_loss=stop_loss, stop_loss_pct=stop_loss_pct,
        risk_reward=rr, rationale=rationale, trigger_buy=trigger, warnings=warnings,
    )


# ══════════════════════════════════════════════════════════════════════════════
# LONG-TERM CALCULATOR  (6–18 months)
# ──────────────────────────────────────────────────────────────────────────────
# Three tiered entry zones — NONE anchored to current price.
#
#   T1  MA200 ± 5%          → 25% allocation  starter position  ~2.5x R/R
#   T2  Fair Value × 0.75   → 50% allocation  core position     ~3.5x R/R
#   T3  52w_low × 1.05–1.15 → 25% allocation  max conviction    ~5x+  R/R
#
# Stop:   5% below 52w low (structural invalidation level)
# Target: Fair value (primary) → Tier 1 entry used for R/R calc
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LongTermInputs:
    current_price: float
    fair_value: float
    ma200: float
    week52_low: float
    ml_prob: float          # 6-month ML probability
    regime_bull_pct: float
    fundamentals_score: float


def compute_long_term_entry(inp: LongTermInputs) -> HorizonSignal:
    p, fv = inp.current_price, inp.fair_value
    warnings = []

    # ── Current price MOS assessment ─────────────────────────────────────
    mos_pct          = _r((fv - p) / p * 100, 1)
    pct_above_ma200  = _r((p - inp.ma200) / inp.ma200 * 100, 1)
    min_price_to_buy = _r(fv * (1 - LT_REQUIRED_MOS_PCT / 100))

    if mos_pct >= LT_REQUIRED_MOS_PCT:
        assess_verdict = "BUY"
        assess_label   = "Sufficient MOS ({:.1f}%) — entry justified".format(mos_pct)
        assess_color   = "#00e5a0"
    elif mos_pct >= LT_PARTIAL_MOS_PCT:
        assess_verdict = "PARTIAL"
        assess_label   = "Marginal discount ({:.1f}%) — partial position only".format(mos_pct)
        assess_color   = "#f5a623"
    else:
        assess_verdict = "WAIT"
        assess_label   = "Only {:.1f}% discount — need {:.0f}% MOS for long-term entry".format(
            mos_pct, LT_REQUIRED_MOS_PCT)
        assess_color   = "#ff6b6b"
        warnings.append(
            "Need price <= ${:.2f} for {:.0f}% margin of safety. "
            "Currently only {:.1f}% discount.".format(
                min_price_to_buy, LT_REQUIRED_MOS_PCT, mos_pct))

    if pct_above_ma200 > LT_MAX_ABOVE_MA200_PCT:
        warnings.append(
            "Price is {:.1f}% above MA200 (${:.2f}). "
            "Long-term investors target entries near or below MA200.".format(
                pct_above_ma200, inp.ma200))

    # ── Build entry tiers ────────────────────────────────────────────────
    def make_tier(tid, label, description, low, high, rr_str, conviction, color):
        return EntryTier(
            id=tid, label=label, description=description,
            low=low, high=high,
            upside_to_fv_pct=_r((fv - high) / high * 100, 1),
            margin_of_safety_pct=_r((fv - high) / fv * 100, 1),
            estimated_rr=rr_str, conviction=conviction, color=color,
            reachable=p > high,
            drop_needed_pct=_r((p - high) / p * 100, 1) if p > high else None,
        )

    tier1 = make_tier(
        "T1", "Tier 1 — MA200 Zone",
        "Near 200-day moving average — medium conviction starter",
        _r(inp.ma200 * (1 - LT_MA200_BAND_PCT / 100)),
        _r(inp.ma200 * (1 + LT_MA200_BAND_PCT / 100)),
        "~2.5x", "Medium", "#f5a623")

    t2_center = fv * (1 - LT_TIER2_MOS_PCT / 100)
    tier2 = make_tier(
        "T2", "Tier 2 — 25% Margin of Safety",
        "Fair value × 0.75 — strong conviction core position",
        _r(t2_center * (1 - LT_TIER2_BAND_PCT / 100)),
        _r(t2_center * (1 + LT_TIER2_BAND_PCT / 100)),
        "~3.5x", "High", "#00e5a0")

    tier3 = make_tier(
        "T3", "Tier 3 — Deep Value",
        "Near 52-week low — maximum conviction, rare opportunity",
        _r(inp.week52_low * LT_TIER3_LOW_MULT),
        _r(inp.week52_low * LT_TIER3_HIGH_MULT),
        "~5x+", "Highest", "#7ec8e3")

    # ── Entry zone for HorizonSignal (T1 as primary display) ─────────────
    entry_zone = EntryZone(
        low=tier1.low, high=tier1.high,
        anchor="MA200 zone (${:.2f}) — Tier 1 entry".format(inp.ma200),
        quality="In Zone" if not tier1.reachable else "Waiting",
        quality_color="#f5a623",
    )

    # ── Stop / target using T1 as entry reference ────────────────────────
    stop_loss     = _r(inp.week52_low * 0.95)   # 5% below 52w low
    stop_loss_pct = _r((stop_loss - tier1.high) / tier1.high * 100, 1)
    target        = fv
    target_pct    = _r((fv - tier1.high) / tier1.high * 100, 1)
    risk          = tier1.high - stop_loss
    rr            = _r((fv - tier1.high) / risk, 2) if risk > 0 else 0.0

    # ── Verdict ──────────────────────────────────────────────────────────
    if assess_verdict == "BUY" and inp.ml_prob >= 40 and inp.regime_bull_pct >= 50:
        verdict, conviction = "BUY", "High"
    elif assess_verdict in ("BUY", "PARTIAL") and inp.ml_prob >= 25:
        verdict, conviction = "WATCH", "Medium"
    else:
        verdict, conviction = "WAIT", "Low"

    # ── Rationale & trigger ──────────────────────────────────────────────
    parts = []
    if assess_verdict == "WAIT":
        parts.append("Only {:.1f}% MOS — need {:.0f}%.".format(mos_pct, LT_REQUIRED_MOS_PCT))
        if inp.ml_prob >= 60:
            parts.append("ML {:.0f}% supports entry; MOS requirement ({:.0f}%) overrides for long-term.".format(inp.ml_prob, LT_REQUIRED_MOS_PCT))
    if pct_above_ma200 > LT_MAX_ABOVE_MA200_PCT:
        parts.append("Price {:.1f}% above MA200 (${:.2f}).".format(pct_above_ma200, inp.ma200))
    if inp.ml_prob < 25:
        parts.append("ML {:.0f}% below 25% confirmation threshold.".format(inp.ml_prob))
    if inp.regime_bull_pct < 50:
        parts.append("Regime {:.0f}% non-bull — wait for HMM confirmation.".format(
            100 - inp.regime_bull_pct))
    rationale = " ".join(parts) or "Conditions approaching entry. Monitor tier levels closely."

    trigger = (
        "Price enters Tier 1 zone (${low}–${high}) near MA200 "
        "AND HMM Bull >= 60% "
        "AND ML prob > 25%"
    ).format(low=tier1.low, high=tier1.high)

    return HorizonSignal(
        label="Long-term", duration="6–18 months",
        verdict=verdict, signal=_ml_to_signal(inp.ml_prob), conviction=conviction,
        ml_prob=inp.ml_prob,
        entry_zone=entry_zone, target=target, target_pct=target_pct,
        stop_loss=stop_loss, stop_loss_pct=stop_loss_pct,
        risk_reward=rr, rationale=rationale, trigger_buy=trigger, warnings=warnings,
        fair_value=fv,
        entry_tiers={
            "current_assessment": {
                "verdict":              assess_verdict,
                "label":               assess_label,
                "color":               assess_color,
                "margin_of_safety_pct": mos_pct,
                "pct_above_ma200":     pct_above_ma200,
                "min_price_to_buy":    min_price_to_buy,
            },
            "tiers": [asdict(tier1), asdict(tier2), asdict(tier3)],
            "position_sizing": [
                {"tier": "T1 (MA200)",      "allocation_pct": 25, "note": "starter position"},
                {"tier": "T2 (25% MOS)",    "allocation_pct": 50, "note": "core position"},
                {"tier": "T3 (Deep value)", "allocation_pct": 25, "note": "if triggered"},
            ],
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# FAIR VALUE — delegated to multi-method estimator
# ══════════════════════════════════════════════════════════════════════════════

def estimate_fair_value(
    current_price: float,
    pe_ratio: float,
    sector_pe: float,
    revenue_growth_pct: float,
    net_margin_pct: float,
    de_ratio: float,
    **kwargs: object,
) -> float:
    """
    Backward-compatible wrapper: delegates to fair_value_estimator.estimate_fair_value_simple.
    Pass forward_pe, sector_forward_pe, earnings_growth_pct, fcf_per_share, analyst_target
    for better accuracy on growth/high-growth stocks.
    """
    from signals.fair_value_estimator import estimate_fair_value_simple
    return estimate_fair_value_simple(
        current_price=current_price,
        ttm_pe=pe_ratio,
        sector_pe=sector_pe,
        revenue_growth_pct=revenue_growth_pct,
        net_margin_pct=net_margin_pct,
        de_ratio=de_ratio,
        **{k: v for k, v in kwargs.items() if k in ("forward_pe", "sector_forward_pe", "fcf_per_share", "analyst_target", "earnings_growth_pct")},
    )


# ══════════════════════════════════════════════════════════════════════════════
# MASTER BUILDER
# ──────────────────────────────────────────────────────────────────────────────
# Call this from your FastAPI signal route:
#
#   from horizon_entry_calculator import build_all_horizons_payload
#   response["horizons"] = build_all_horizons_payload(**signal_data)
# ══════════════════════════════════════════════════════════════════════════════

def build_all_horizons_payload(
    # Price & technical inputs
    current_price: float,
    rsi: float,
    atr: float,
    vwap: float,
    support_level: float,
    resistance_level: float,
    ma50: float,
    ma200: float,
    week52_low: float,
    volume_ratio: float,
    # ML probabilities per horizon
    st_ml_prob: float,          # short-term  (1m)
    mt_ml_prob: float,          # medium-term (3m)
    lt_ml_prob: float,          # long-term   (6m)
    # Regime & pattern
    regime_bull_pct: float,
    pattern_score: float,
    # Valuation
    fair_value: float,
    # Fundamental scores (0-100) from your existing signal layers
    options_sentiment_score: float,
    insider_activity_score: float,
    fundamentals_score: float,
    # Optional
    days_to_earnings: Optional[int] = None,
) -> dict:
    """
    Builds all three horizon signals and returns a dict ready to attach
    to your existing signal card API response.
    """
    short = compute_short_term_entry(ShortTermInputs(
        current_price=current_price,
        ml_prob=st_ml_prob,
        rsi=rsi, atr=atr, vwap=vwap,
        support_level=support_level,
        resistance_level=resistance_level,
        regime_bull_pct=regime_bull_pct,
        pattern_score=pattern_score,
        volume_ratio=volume_ratio,
    ))

    medium = compute_medium_term_entry(MediumTermInputs(
        current_price=current_price,
        ml_prob=mt_ml_prob,
        ma50=ma50, ma200=ma200, atr=atr,
        regime_bull_pct=regime_bull_pct,
        pattern_score=pattern_score,
        days_to_earnings=days_to_earnings,
        options_sentiment_score=options_sentiment_score,
        insider_activity_score=insider_activity_score,
        fundamentals_score=fundamentals_score,
    ))

    long_term = compute_long_term_entry(LongTermInputs(
        current_price=current_price,
        fair_value=fair_value,
        ma200=ma200,
        week52_low=week52_low,
        ml_prob=lt_ml_prob,
        regime_bull_pct=regime_bull_pct,
        fundamentals_score=fundamentals_score,
    ))

    return {
        "short":  asdict(short),
        "medium": asdict(medium),
        "long":   asdict(long_term),
    }


# ══════════════════════════════════════════════════════════════════════════════
# QUICK TEST  —  python horizon_entry_calculator.py
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    # GOOGL — matches live signal card data from screenshots
    fair_value = estimate_fair_value(
        current_price=299.86,
        pe_ratio=22.4,
        sector_pe=28.5,
        revenue_growth_pct=18,
        net_margin_pct=32.8,
        de_ratio=0.2,
    )
    print("Fair Value Estimate: ${}\n".format(fair_value))

    result = build_all_horizons_payload(
        current_price       = 299.86,
        rsi                 = 48.0,
        atr                 = 8.50,
        vwap                = 295.40,
        support_level       = 288.00,
        resistance_level    = 315.00,
        ma50                = 320.05,
        ma200               = 250.82,
        week52_low          = 144.30,
        volume_ratio        = 0.95,
        st_ml_prob          = 2.0,
        mt_ml_prob          = 41.0,
        lt_ml_prob          = 24.0,
        regime_bull_pct     = 26.0,
        pattern_score       = 42.0,
        fair_value          = fair_value,
        options_sentiment_score = 48.0,
        insider_activity_score  = 50.0,
        fundamentals_score      = 78.0,
        days_to_earnings        = 51,
    )

    divider = "=" * 52
    for horizon, data in result.items():
        ez = data["entry_zone"]
        print(divider)
        print("  {} | {} | {} ({})".format(
            horizon.upper(), data["label"],
            data["verdict"], data["conviction"]))
        print(divider)
        print("  Entry Zone : ${} – ${}".format(ez["low"], ez["high"]))
        print("  Anchor     : {}".format(ez["anchor"]))
        print("  Quality    : {}".format(ez["quality"]))
        print("  Target     : ${} (+{}%)".format(data["target"], data["target_pct"]))
        print("  Stop Loss  : ${} ({}%)".format(data["stop_loss"], data["stop_loss_pct"]))
        print("  R/R        : {}x".format(data["risk_reward"]))
        print("  ML Prob    : {}%".format(data["ml_prob"]))
        print("  Signal     : {}".format(data["signal"]))
        if data.get("warnings"):
            print("  Warnings:")
            for w in data["warnings"]:
                print("    ⚠  {}".format(w))
        print("  Rationale  : {}".format(data["rationale"]))
        print("  Trigger    : {}".format(data["trigger_buy"]))

        if horizon == "long" and data.get("entry_tiers"):
            ca = data["entry_tiers"]["current_assessment"]
            print("\n  -- Long-Term Entry Tiers --")
            print("  Assessment : {}".format(ca["label"]))
            print("  Min Buy Px : ${}".format(ca["min_price_to_buy"]))
            print("  MOS now    : {}%".format(ca["margin_of_safety_pct"]))
            print("  Above MA200: {}%".format(ca["pct_above_ma200"]))
            for t in data["entry_tiers"]["tiers"]:
                status = ("IN ZONE" if not t["reachable"]
                          else "needs -{:.1f}% drop".format(t["drop_needed_pct"] or 0))
                print("  {} : ${} – ${}  |  +{}% upside  |  {}% MOS  |  {}  [{}]".format(
                    t["id"], t["low"], t["high"],
                    t["upside_to_fv_pct"], t["margin_of_safety_pct"],
                    t["estimated_rr"], status))
            print("\n  Position Sizing:")
            for ps in data["entry_tiers"]["position_sizing"]:
                print("    {}  →  {}%  ({})".format(
                    ps["tier"], ps["allocation_pct"], ps["note"]))
        print()
