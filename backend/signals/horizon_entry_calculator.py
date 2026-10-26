"""
horizon_entry_calculator.py
============================
Calculates proper, anchor-based entry prices for all 3 investment horizons
in Thrive Alpha signal cards.

Each horizon uses a different anchor — not the naive "current price = entry":
  SHORT  (1m)     RSI state -> VWAP -> recent support + ATR stops; band capped vs fair value so we do not imply buying above intrinsic
  MEDIUM (3m)     MA50 zone + earnings catalyst + fundamentals quality
  LONG   (6-18m)  MA200 + quality-based Tier 2 MOS + 52w tail-risk band

FastAPI integration:
    from horizon_entry_calculator import build_all_horizons_payload, estimate_fair_value
    response["horizons"] = build_all_horizons_payload(**signal_data)

Run standalone test:
    python horizon_entry_calculator.py
"""

import math
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dataclasses import dataclass, asdict, replace
from typing import Any, Dict, Optional

from signals.providers import MAJOR_INDEX_ETFS
from signals.structural_invalidation import structural_invalidation_below

_BROAD_INDEX_ETF_TICKERS = frozenset(MAJOR_INDEX_ETFS) | frozenset({"VOO", "VTI"})
# Match api.ticker_detail metal sanity set — deep 52w min can mis-state structural risk
_COMMODITY_METAL_ETFS = frozenset(
    {"GLD", "IAU", "SGOL", "GLDM", "BAR", "OUNZ", "SLV", "SIL", "PSLV", "USO", "GDX", "GDXJ"}
)
_STRUCTURAL_TAIL_ETFS = _BROAD_INDEX_ETF_TICKERS | _COMMODITY_METAL_ETFS


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS  — tune these per your model calibration
# ══════════════════════════════════════════════════════════════════════════════

# Short-term
ST_RSI_OVERSOLD        = 35.0   # RSI below = oversold, ideal entry
ST_RSI_OVERBOUGHT      = 65.0   # RSI above = overbought, avoid entry
ST_MIN_ML_PROB         = 30.0   # minimum ML prob for short-term signal (raised from 25 to reduce noise)
ST_ATR_STOP_MULT       = 1.5    # stop = entry_low - (ATR * mult)
ST_ATR_TARGET_MULT     = 3.0    # target = entry_high + (ATR * mult)
ST_MIN_RR              = 1.5    # minimum acceptable risk/reward
# Ignore support levels far below spot (e.g. 52w low) for 1-month entry — those belong in long-term tiers
ST_SUPPORT_MAX_DEPTH_PCT = 22.0
# If the oversold anchor is deeper than this vs spot, 1m "buy zone" is a crash scenario — use VWAP band instead
ST_MAX_NEAR_TERM_ZONE_DEPTH_PCT = 10.0
# On low-ATR% days, avoid stops that are unrealistically tight vs spot (semis / high-beta)
ST_MIN_STOP_DISTANCE_PCT_OF_SPOT = 4.0
# Short-term target vs entry_zone.high — HMM non-bull dampening (ATR×3 + resistance can imply 6–10% tactical
# upside that is mis-stated as a base case when tape is risk-off; long-horizon already warns on similar skew).
ST_ST_REGIME_CAP_RB48 = 48.0   # at/above: no upside cap (bullish-enough backdrop)
ST_ST_REGIME_CAP_RB42 = 42.0   # [42, 48): max upside % vs eh
ST_ST_UPSIDE_CAP_RB42_TO_48 = 6.5
ST_ST_REGIME_CAP_RB35 = 35.0   # [35, 42)
ST_ST_UPSIDE_CAP_RB35_TO_42 = 5.0
ST_ST_UPSIDE_CAP_BELOW_RB35 = 4.0  # regime_bull < 35


def _short_term_regime_cap_upside_pct(regime_bull_pct: float) -> Optional[float]:
    """
    Max upside % above short-term entry_zone.high when HMM skews non-bull.
    None = keep raw min(resistance×0.98, ATR target).
    """
    rb = float(regime_bull_pct)
    if rb >= ST_ST_REGIME_CAP_RB48:
        return None
    if rb >= ST_ST_REGIME_CAP_RB42:
        return ST_ST_UPSIDE_CAP_RB42_TO_48
    if rb >= ST_ST_REGIME_CAP_RB35:
        return ST_ST_UPSIDE_CAP_RB35_TO_42
    return ST_ST_UPSIDE_CAP_BELOW_RB35


# Medium-term
MT_MA50_BAND_PCT       = 4.0    # acceptable range above MA50 for entry
MT_MIN_ML_PROB         = 35.0   # minimum ML prob for medium-term signal
MT_EARNINGS_WINDOW     = 60     # days — earnings within this = catalyst flag
MT_STOP_BELOW_MA50_PCT = 6.0    # stop = MA50 * (1 - pct) — MA50 break invalidates
MT_MIN_RR              = 2.0    # minimum R/R enforced for medium-term
# P1 Fix: Relaxed regime threshold for swing from 45 to 40 to reduce false negatives
MT_REGIME_BULL_MIN     = 40.0   # minimum regime bull % for swing signal

# Plan-quality gates (applied after all three horizons are built)
PLAN_MIN_RR_FROM_ENTRY = 1.5    # R:R from entry midpoint — plans below this are "No setup"
PLAN_MIN_EDGE_PCT      = 2.0    # target must clear entry_high by at least this %
EXTENDED_ABOVE_FV_PCT  = 8.0    # spot > FV by this → DO NOT CHASE / pullback-conditional mode
FV_STALE_ATR_SIGMA     = 2.0    # |spot − FV| / ATR above this → flag FV as possibly stale
LT_FORWARD_YEARS       = 1.0    # grow today's FV by expected EPS growth over this horizon
LT_DEFAULT_GROWTH_PCT  = 8.0    # used when earnings growth is unavailable
# Cap on the growth rate used for the forward-FV lift specifically (see _forward_fair_value) —
# deliberately lower than fair_value_estimator's own growth cap (up to ~65% for high-growth
# names via its PEG/forward-PE methods). Those methods already price growth INTO fv (that's
# the "G" in PEG) — growing that already-growth-priced number by the model's own growth rate
# again for the 1-year lift double-counts it. Confirmed across GOOGL (fv $474.73 -> forward FV
# $664.62 at the old 40% cap, i.e. +40% on top of a valuation that already assumed 42% growth),
# MSFT, and AMD (all high-growth names hitting or near the old 40% cap) — while value/slow-
# growth names (PG, TTD; growth 1.5-3%) and the no-data default (8%) are well under 15% and are
# unaffected by this change.
LT_FORWARD_GROWTH_CAP_PCT = 15.0
TOUCH_SUPPRESS_PCT     = 15.0   # suppress pullback plans with very low historical touch odds
TOUCH_SUPPRESS_DROP_PCT = 10.0  # only suppress when band is this far below spot

# Long-term
LT_REQUIRED_MOS_PCT    = 25.0   # minimum margin of safety for full buy
LT_PARTIAL_MOS_PCT     = 15.0   # partial position threshold
LT_MA200_BAND_PCT      = 5.0    # Tier 1: MA200 +- 5%
LT_TIER2_MOS_PCT       = 25.0   # Default Tier 2 MOS when quality class is unknown (see resolve_tier2_mos_pct)
LT_TIER2_BAND_PCT      = 3.0    # Tier 2: +- 3% around target
# Per-quality Tier 2 MOS (% discount from fair value). Override via config horizons.tier2_mos_pct.
DEFAULT_TIER2_MOS_PCT_BY_CLASS: dict[str, float] = {
    "high_quality_defensive": 10.0,
    "large_cap_growth": 15.0,
    "high_volatility": 25.0,
    "speculative": 30.0,
}
# Known tickers → class (everything else: classify from fundamentals_score)
_HIGH_QUALITY_DEFENSIVE = frozenset({
    "BLK", "JPM", "WFC", "BAC", "C", "GS", "MS", "USB", "PNC", "TFC", "SCHW", "BK", "STT", "NTRS",
    "TROW", "BEN", "IVZ", "AMG", "JNJ", "PG", "KO", "PEP", "WMT", "COST", "MCD", "PM", "MO", "MRK",
    "ABBV", "PFE", "UNH", "CI", "HUM", "CVX", "XOM",
})
_LARGE_CAP_GROWTH = frozenset({
    "MSFT", "GOOGL", "GOOG", "AAPL", "AMZN", "NFLX", "ADBE", "CRM", "ORCL", "NOW", "INTU", "CSCO",
})
_HIGH_VOLATILITY = frozenset({
    "NVDA", "AMD", "TSLA", "META", "COIN", "MSTR", "SMCI", "AVGO", "PLTR", "CRWD", "PANW", "SHOP",
    "SQ", "HOOD", "RIVN",
})


def _norm_ticker_sym(ticker: str) -> str:
    if not ticker:
        return ""
    u = str(ticker).strip().upper().replace(".", "-")
    return u.split("-")[0]


def classify_mos_class(ticker: str, fundamentals_score: float) -> str:
    """
    Map symbol + fundamentals to a Tier 2 MOS profile.
    Known lists first; then weak fundamentals → speculative; strong → large-cap growth; else high-vol band.
    Fixed: Added dynamic fallback for fundamentals-based classification to catch new quality stocks not in hardcoded lists.
    """
    t = _norm_ticker_sym(ticker)
    if t in _HIGH_QUALITY_DEFENSIVE:
        return "high_quality_defensive"
    if t in _LARGE_CAP_GROWTH:
        return "large_cap_growth"
    if t in _HIGH_VOLATILITY:
        return "high_volatility"
    if fundamentals_score < 45:
        return "speculative"
    if fundamentals_score >= 65:
        return "large_cap_growth"
    # Fixed: Added dynamic fallback ranges to improve classification for stocks not in hardcoded lists
    if fundamentals_score >= 60 and fundamentals_score < 65:
        return "large_cap_growth"
    if fundamentals_score >= 40 and fundamentals_score < 60:
        return "high_quality_defensive"
    return "high_volatility"


def resolve_tier2_mos_pct(
    ticker: str,
    fundamentals_score: float,
    explicit_pct: Optional[float] = None,
    tier2_mos_by_class: Optional[dict[str, Any]] = None,
    ticker_overrides: Optional[dict[str, Any]] = None,
) -> tuple[float, str]:
    """
    Returns (mos_pct, class_key) for long-term Tier 2 band center = fair_value * (1 - mos_pct/100).
    explicit_pct wins; then per-ticker override; then merged class table + classify_mos_class.
    """
    if explicit_pct is not None and float(explicit_pct) > 0:
        return float(explicit_pct), "explicit"

    t = _norm_ticker_sym(ticker)
    ov = ticker_overrides or {}
    if t and t in ov and ov[t] is not None:
        try:
            v = float(ov[t])
            if v > 0:
                return v, "ticker_override"
        except (TypeError, ValueError):
            pass

    merged = dict(DEFAULT_TIER2_MOS_PCT_BY_CLASS)
    if tier2_mos_by_class:
        for k, v in tier2_mos_by_class.items():
            if v is None:
                continue
            try:
                merged[str(k)] = float(v)
            except (TypeError, ValueError):
                continue

    cls = classify_mos_class(ticker, fundamentals_score)
    pct = merged.get(cls, LT_TIER2_MOS_PCT)
    return float(pct), cls


def tier2_human_class_label(class_key: str) -> str:
    return {
        "high_quality_defensive": "high-quality defensive",
        "large_cap_growth": "large-cap growth",
        "high_volatility": "high volatility",
        "speculative": "speculative / weak fundamentals",
        "explicit": "custom MOS",
        "ticker_override": "per-ticker override",
    }.get(class_key, class_key)
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
    # Long-term: structural invalidation near 52w — not a tight trailing stop
    stop_loss_kind: str = "trailing"
    stop_loss_framing: Optional[str] = None


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


def resolve_active_tier(tiers: list[EntryTier], price: float) -> EntryTier | None:
    """Tier band containing current price (T2 preferred over T1 over T3 if overlapping)."""
    if not tiers or price <= 0:
        return None
    for tid in ("T2", "T1", "T3"):
        t = next((x for x in tiers if x.id == tid), None)
        if t is not None and t.low <= price <= t.high:
            return t
    return None


def resolve_target_tier_id(tiers: list[EntryTier], price: float) -> str | None:
    """Nearest accumulation tier when spot is outside all bands (not the lowest stress tier).

    Between-tier gaps: next add is the floor (don't chase the ceiling), unless
    spot is already within 1.5% of the ceiling band — then the ceiling is the
    imminent add, not a chase.
    """
    active = resolve_active_tier(tiers, price)
    if active:
        return active.id
    if not tiers or price <= 0:
        return None
    spot = classify_spot_tier_position(tiers, price)
    if spot.get("state") == "between_tiers" and spot.get("next_add_tier_id"):
        ceiling_lo = spot.get("ceiling_band_low")
        ceiling_id = spot.get("ceiling_tier_id")
        if (
            ceiling_lo is not None
            and ceiling_id
            and (float(ceiling_lo) - price) / price <= 0.015
        ):
            return str(ceiling_id)
        return spot["next_add_tier_id"]
    best = tiers[0]
    best_dist = float("inf")
    for t in tiers:
        lo, hi = min(t.low, t.high), max(t.low, t.high)
        if lo <= price <= hi:
            return t.id
        dist = (lo - price) if price < lo else (price - hi)
        if dist < best_dist:
            best_dist = dist
            best = t
    return best.id


def classify_spot_tier_position(tiers: list[EntryTier], price: float) -> dict[str, Any]:
    """
    Classify spot vs tier ladder — especially the 'between tiers' gap when MA200 (T1)
    sits well below FV-based T2 (common on extended large-cap growth names).
    """
    if not tiers or price <= 0:
        return {"state": "unknown"}
    active = resolve_active_tier(tiers, price)
    if active:
        return {
            "state": "in_tier",
            "active_tier_id": active.id,
            "next_add_tier_id": active.id,
        }
    t1 = next((t for t in tiers if str(t.id).upper() == "T1"), None)
    if t1 is not None:
        t1_hi = max(t1.low, t1.high)
        if price <= t1_hi + 1e-6:
            return {
                "state": "at_or_below_ceiling",
                "ceiling_tier_id": "T1",
                "ceiling": _r(t1_hi),
                "next_add_tier_id": "T1",
                "label": "At or below T1 ceiling ${:.2f}".format(t1_hi),
                "detail": (
                    "Owner trigger is threshold-based (price ≤ T1 high ${:.2f}). "
                    "Gaps through the narrow T1 window still count — scale at spot, "
                    "do not wait for a bounce back into the rectangle."
                ).format(t1_hi),
            }
    floor_tier: EntryTier | None = None
    for t in sorted(tiers, key=lambda x: x.high):
        if price > t.high:
            floor_tier = t
    ceiling_tier: EntryTier | None = None
    for t in sorted(tiers, key=lambda x: x.low):
        if price < t.low:
            ceiling_tier = t
            break
    if floor_tier and ceiling_tier and floor_tier.high < ceiling_tier.low - 1e-6:
        return {
            "state": "between_tiers",
            "floor_tier_id": floor_tier.id,
            "ceiling_tier_id": ceiling_tier.id,
            "floor_band_high": _r(floor_tier.high),
            "ceiling_band_low": _r(ceiling_tier.low),
            "gap_width_pct_of_spot": _r((ceiling_tier.low - floor_tier.high) / price * 100, 1),
            "next_add_tier_id": floor_tier.id,
            "label": "Between {} and {} — no new long-term adds at spot".format(
                floor_tier.id, ceiling_tier.id
            ),
            "detail": (
                "Spot ${:.2f} is above {} (${:.2f}–${:.2f}) but below {} (${:.2f}–${:.2f}). "
                "Hold existing size; next adds on pullback to {}, not chasing up into {}."
            ).format(
                price,
                floor_tier.id,
                floor_tier.low,
                floor_tier.high,
                ceiling_tier.id,
                ceiling_tier.low,
                ceiling_tier.high,
                floor_tier.id,
                ceiling_tier.id,
            ),
        }
    if ceiling_tier and floor_tier is None:
        return {"state": "below_all", "next_add_tier_id": ceiling_tier.id}
    if floor_tier and ceiling_tier is None:
        return {"state": "above_all", "next_add_tier_id": floor_tier.id}
    best = tiers[0]
    best_dist = float("inf")
    for t in tiers:
        lo, hi = min(t.low, t.high), max(t.low, t.high)
        dist = (lo - price) if price < lo else (price - hi)
        if dist < best_dist:
            best_dist = dist
            best = t
    return {"state": "unknown", "next_add_tier_id": best.id}


def classify_spot_band_position(
    price: float,
    band_low: float,
    band_high: float,
    *,
    band_label: str = "entry band",
    threshold_ceiling: bool = False,
) -> dict[str, Any]:
    """Spot vs a single horizon entry band (short / swing / long primary zone).

    threshold_ceiling: owner/long T1 — in-band if price ≤ high (gaps through the
    window still count). Range-gated bands keep lo ≤ price ≤ hi.
    """
    if not (price > 0 and band_low > 0 and band_high > 0):
        return {"state": "unknown"}
    lo, hi = min(band_low, band_high), max(band_low, band_high)
    if hi <= lo:
        return {"state": "unknown"}
    if threshold_ceiling:
        if price <= hi + 1e-6:
            return {
                "state": "in_band",
                "band_low": _r(lo),
                "band_high": _r(hi),
                "trigger_kind": "at_or_below",
                "label": f"At or below {band_label} ceiling",
                "detail": (
                    f"Spot ${price:.2f} ≤ ceiling ${hi:.2f} — owner trigger is threshold-based. "
                    f"Scale toward ${lo:.2f}; do not wait for a bounce into a narrow window."
                ),
            }
        gap_pct = _r((price - hi) / hi * 100, 1)
        return {
            "state": "above_band",
            "band_low": _r(lo),
            "band_high": _r(hi),
            "gap_pct": gap_pct,
            "next_add_at": _r(hi),
            "trigger_kind": "at_or_below",
            "label": f"{gap_pct:.1f}% above {band_label} ceiling",
            "detail": (
                f"Wait for price ≤ ${hi:.2f} (T1 ceiling). "
                f"Any print at or below that level counts — including gaps through ${lo:.2f}–${hi:.2f}."
            ),
        }
    if lo <= price <= hi:
        return {
            "state": "in_band",
            "band_low": _r(lo),
            "band_high": _r(hi),
            "label": f"Inside {band_label}",
            "detail": f"Spot ${price:.2f} is inside ${lo:.2f}–${hi:.2f} — use catch levels below for staged adds.",
        }
    if price > hi:
        gap_pct = _r((price - hi) / hi * 100, 1)
        return {
            "state": "above_band",
            "band_low": _r(lo),
            "band_high": _r(hi),
            "gap_pct": gap_pct,
            "next_add_at": _r(hi),
            "label": f"{gap_pct:.1f}% above {band_label}",
            "detail": (
                f"Trend intact. Optional limit in ${lo:.2f}–${hi:.2f} for a cheaper fill. "
                f"First limit near band high ${hi:.2f}, scale toward ${lo:.2f}."
            ),
        }
    gap_pct = _r((lo - price) / lo * 100, 1)
    return {
        "state": "below_band",
        "band_low": _r(lo),
        "band_high": _r(hi),
        "gap_pct": gap_pct,
        "next_add_at": _r(lo),
        "label": f"{gap_pct:.1f}% below {band_label} low",
        "detail": (
            f"Spot has not reached ${lo:.2f} yet — alert at band low, scale through mid/high."
        ),
    }


def build_entry_band_levels(
    band_low: float,
    band_high: float,
    *,
    anchors: list[tuple[str, str, float]] | None = None,
) -> list[dict[str, Any]]:
    """
    Actionable prices inside an entry band for limit orders / alerts.
    anchors: (id, label, price) — included when price falls inside the band.
    """
    lo, hi = min(band_low, band_high), max(band_low, band_high)
    if not (lo > 0 and hi > lo):
        return []
    mid = _r((lo + hi) / 2)
    span = hi - lo
    levels: list[dict[str, Any]] = [
        {"id": "band_low", "label": "Band low · first add", "price": _r(lo), "role": "entry", "sort": 1},
        {"id": "q25", "label": "25% into band", "price": _r(lo + span * 0.25), "role": "entry", "sort": 2},
        {"id": "band_mid", "label": "Band mid · scale", "price": mid, "role": "entry", "sort": 3},
        {"id": "q75", "label": "75% into band", "price": _r(lo + span * 0.75), "role": "entry", "sort": 4},
        {"id": "band_high", "label": "Band high · last add", "price": _r(hi), "role": "entry", "sort": 5},
    ]
    for aid, alabel, apx in anchors or []:
        if apx > 0 and lo - 1e-6 <= apx <= hi + 1e-6:
            levels.append(
                {"id": aid, "label": alabel, "price": _r(apx), "role": "anchor", "sort": 0}
            )
    # Dedupe prices within $0.02
    seen: set[float] = set()
    out: list[dict[str, Any]] = []
    for row in sorted(levels, key=lambda x: (x["sort"], x["price"])):
        key = round(float(row["price"]), 2)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return sorted(out, key=lambda x: x["price"])


def _refresh_tier_fv_metrics(tier: EntryTier, fv: float, price: float) -> EntryTier:
    return replace(
        tier,
        upside_to_fv_pct=_r((fv - tier.high) / tier.high * 100, 1),
        margin_of_safety_pct=_r((fv - tier.high) / fv * 100, 1),
        reachable=price > tier.high,
        drop_needed_pct=_r((price - tier.high) / price * 100, 1) if price > tier.high else None,
    )


def _enrich_mos_ceiling_context(
    spot_position: dict[str, Any],
    *,
    price: float,
    min_price_to_buy: float,
    assess_verdict: str,
    all_tiers: list[EntryTier],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    When spot is at/below the full-size MOS ceiling, tiers are NOT recomputed from spot —
    they stay MA200 / FV×MOS / 52w-low anchors. This clarifies the common case where spot
    sits below tier bands but still qualifies for full allocation on valuation.
    """
    sp = dict(spot_position)
    flags: dict[str, Any] = {
        "full_size_ceiling_label": "Full-size ceiling (25% MOS to fair value)",
    }
    if not (min_price_to_buy > 0 and price > 0):
        return sp, flags

    within = price <= min_price_to_buy + 1e-6
    flags["within_full_mos_ceiling"] = within
    if within:
        flags["above_full_mos_ceiling"] = False
        if assess_verdict == "BUY":
            flags["full_size_eligible_at_spot"] = True
            flags["position_mode"] = "full_size_ok"
        elif assess_verdict == "PARTIAL":
            flags["position_mode"] = "partial_ok"

    if within and sp.get("state") in ("below_all", "at_or_below_ceiling"):
        # "at_or_below_ceiling" (spot <= T1's high, classified before the floor/ceiling-tier
        # scan below ever runs) covers the same "off the bottom of the ladder" ground
        # "below_all" used to own on its own — T1 is always the lowest-anchored tier, so
        # reaching this state already implies spot is below every tier's low in practice.
        # Enrich both alike so a deep crash still gets "full MOS met at spot" framing
        # instead of only the generic T1-window copy.
        ceiling_tier = next(
            (t for t in sorted(all_tiers, key=lambda x: x.low) if price < t.low),
            all_tiers[0] if all_tiers else None,
        )
        sp["below_all_within_mos"] = True
        sp["label"] = "Below tier bands — full MOS met at spot"
        tid = ceiling_tier.id if ceiling_tier else "T2"
        tlo = ceiling_tier.low if ceiling_tier else 0.0
        thi = ceiling_tier.high if ceiling_tier else 0.0
        sp["detail"] = (
            "Spot ${:.2f} is below structural tier bands but at/below the full-size ceiling "
            "${:.2f}. Full allocation is valuation-justified; tiers (MA200 / FV MOS / 52w stress) "
            "are scale-in guides — not a higher minimum price. Nearest band: {} (${:.2f}–${:.2f})."
        ).format(price, min_price_to_buy, tid, tlo, thi)
        sp["next_add_tier_id"] = tid
    elif within and sp.get("state") == "in_tier":
        sp.setdefault(
            "detail",
            "Spot is inside a tier band and at/below the full-size ceiling ${:.2f} — scale per tier plan."
            .format(min_price_to_buy),
        )

    return sp, flags


def _enforce_strict_tier_ladder(
    tier1: EntryTier,
    tier2: EntryTier,
    tier3: EntryTier,
    fv: float,
    price: float,
    week52_low: float,
) -> tuple[EntryTier, EntryTier, EntryTier]:
    """
    T3 (52w stress tail) must sit entirely below T2 (MOS band).
    When 52w stress math lands above the MOS zone, pull T3 down under T2.
    """
    t1, t2, t3 = tier1, tier2, tier3
    if t3.high >= t2.low - 1e-6:
        new_hi = _r(t2.low * 0.97)
        tail_anchor = _r(week52_low * LT_TIER3_LOW_MULT) if week52_low > 0 else t3.low
        new_lo = _r(min(t3.low, tail_anchor, new_hi * 0.92))
        if new_lo >= new_hi:
            new_lo = _r(new_hi * 0.90)
        t3 = _refresh_tier_fv_metrics(replace(t3, low=new_lo, high=new_hi), fv, price)
    return t1, t2, t3


def _tier_catch_levels(
    tier: EntryTier,
    fv: float,
    mos_pct: float,
    *,
    anchors: list[tuple[str, str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Limit-order levels inside a tier — never imply buying at/near FV without MOS."""
    cap = tier.high
    if mos_pct < LT_PARTIAL_MOS_PCT:
        cap = min(cap, fv * (1 - LT_PARTIAL_MOS_PCT / 100))
    elif mos_pct < LT_REQUIRED_MOS_PCT:
        cap = min(cap, fv * (1 - LT_REQUIRED_MOS_PCT / 100))
    levels = build_entry_band_levels(tier.low, tier.high, anchors=anchors)
    capped = [row for row in levels if float(row["price"]) <= cap + 0.02]
    if capped:
        return capped
    return [
        {
            "id": "mos_cap",
            "label": f"MOS cap · max add ${cap:.2f}",
            "price": _r(cap),
            "role": "entry",
            "sort": 1,
        }
    ]


def _compute_long_tactical_stop(
    *,
    current_price: float,
    tier_ref: EntryTier,
    atr: float | None,
    structural_stop: float,
    entry_floor: float | None = None,
) -> tuple[float, str]:
    """
    Actionable stop for long accumulate — always below spot and the owner add floor.
    Structural invalidation (often MA200×0.97 on ETFs) is reference-only.
    """
    p = float(current_price)
    lo = float(tier_ref.low)
    if entry_floor is not None and entry_floor > 0:
        lo = min(lo, float(entry_floor))
    atr_buf = (float(atr) if atr and atr > 0 else p * 0.02) * ST_ATR_STOP_MULT
    min_buf = p * (ST_MIN_STOP_DISTANCE_PCT_OF_SPOT / 100.0)
    buf = max(atr_buf, min_buf, lo * 0.025)
    tactical = _r(lo - buf)
    max_tactical = _r(p * (1 - 0.005))
    if tactical >= p - 1e-6:
        tactical = _r(min(lo * 0.97, p * 0.97))
    tactical = min(tactical, max_tactical)
    if entry_floor is not None and entry_floor > 0 and tactical >= float(entry_floor) - 1e-6:
        tactical = _r(min(tactical, float(entry_floor) * 0.995, float(entry_floor) - max(buf * 0.25, 0.05)))
    if tactical <= 0:
        tactical = _r(p * 0.95)
    dist_pct = abs((p - tactical) / p * 100)
    framing = (
        f"Tactical stop ${tactical:.2f} (~{dist_pct:.1f}% below spot) under "
        f"{tier_ref.id} support ${lo:.2f}. Structural invalidation ${structural_stop:.2f} "
        f"is thesis-broken only — not a day-to-day stop."
    )
    return tactical, framing


def build_bridge_band(
    floor_high: float,
    ceiling_low: float,
    center: float | None = None,
    *,
    band_label: str = "Bridge band",
) -> dict[str, Any] | None:
    """
    Thin actionable sleeve inside a tier/horizon gap (T1→T2 or short→swing).
    Partial size only — not a substitute for core MOS / lower-tier adds.
    """
    if not (floor_high > 0 and ceiling_low > floor_high + 1e-6):
        return None
    gap_mid = (floor_high + ceiling_low) / 2.0
    anchor = center if center and floor_high < center < ceiling_low else gap_mid
    gap_width = ceiling_low - floor_high
    half = min(gap_width * 0.18, max(anchor * 0.012, 0.5), gap_width / 2.0 - 0.01)
    half = max(half, gap_width * 0.08)
    lo = max(floor_high, anchor - half)
    hi = min(ceiling_low, anchor + half)
    if hi <= lo + 1e-6:
        hi = min(ceiling_low, floor_high + max(gap_width * 0.22, 0.5))
        lo = floor_high
    levels = build_entry_band_levels(lo, hi)
    return {
        "low": _r(lo),
        "high": _r(hi),
        "center": _r(anchor),
        "gap_low": _r(floor_high),
        "gap_high": _r(ceiling_low),
        "label": band_label,
        "max_allocation_pct": 10,
        "detail": (
            f"Thin extension sleeve ${lo:.2f}–${hi:.2f} inside the ${floor_high:.2f}–${ceiling_low:.2f} gap — "
            "partial starter only (≈10% max), not core MOS. Prefer lower-tier retest for real adds."
        ),
        "levels": levels,
    }


def _attach_bridge_to_spot_position(
    spot_position: dict[str, Any],
    *,
    center: float | None,
    band_label: str,
) -> dict[str, Any]:
    if spot_position.get("state") not in ("between_tiers", "between_horizon_bands"):
        return spot_position
    floor_hi = spot_position.get("floor_band_high")
    ceil_lo = spot_position.get("ceiling_band_low")
    if floor_hi is None or ceil_lo is None:
        cross = spot_position.get("cross_gap") or {}
        floor_hi = cross.get("floor_band_high")
        ceil_lo = cross.get("ceiling_band_low")
    if floor_hi is None or ceil_lo is None:
        return spot_position
    bridge = build_bridge_band(float(floor_hi), float(ceil_lo), center, band_label=band_label)
    if bridge:
        spot_position = dict(spot_position)
        spot_position["bridge_band"] = bridge
        if floor_hi <= (center or 0) <= ceil_lo or (
            bridge["low"] <= (center or 0) <= bridge["high"]
        ):
            spot_position["in_bridge_band"] = (
                bridge["low"] <= (center or 0) <= bridge["high"]
            )
    return spot_position


def _enrich_horizon_entry_zone_extras(
    payload: dict[str, Any],
    *,
    current_price: float,
    vwap: float,
    support_level: float,
    ma50: float,
) -> None:
    """Attach spot_position + catch levels to short/medium entry zones; cross-horizon gap detection."""
    short_ez = payload.get("short", {}).get("entry_zone") or {}
    medium_ez = payload.get("medium", {}).get("entry_zone") or {}
    if not short_ez or not medium_ez or not (current_price > 0):
        return

    st_lo = min(float(short_ez["low"]), float(short_ez["high"]))
    st_hi = max(float(short_ez["low"]), float(short_ez["high"]))
    mt_lo = min(float(medium_ez["low"]), float(medium_ez["high"]))
    mt_hi = max(float(medium_ez["low"]), float(medium_ez["high"]))

    short_ez["levels"] = build_entry_band_levels(
        st_lo,
        st_hi,
        anchors=[
            ("vwap", "VWAP", float(vwap)),
            ("support", "Support", float(support_level)),
        ],
    )
    medium_ez["levels"] = build_entry_band_levels(
        mt_lo,
        mt_hi,
        anchors=[("ma50", "MA50", float(ma50))],
    )

    st_spot = classify_spot_band_position(current_price, st_lo, st_hi, band_label="short-term band")
    mt_spot = classify_spot_band_position(current_price, mt_lo, mt_hi, band_label="swing band")

    between_st_mt = st_hi < current_price < mt_lo - 1e-6
    between_mt_st = mt_hi < current_price < st_lo - 1e-6  # rare after harmonization

    if between_st_mt:
        cross = {
            "state": "between_horizon_bands",
            "floor_horizon": "short",
            "ceiling_horizon": "medium",
            "floor_band_high": _r(st_hi),
            "ceiling_band_low": _r(mt_lo),
            "gap_width_pct": _r((mt_lo - st_hi) / current_price * 100, 1),
            "label": "Between short & swing bands — no man's land",
            "detail": (
                f"Spot ${current_price:.2f} cleared short band top ${st_hi:.2f} "
                f"but is ${(mt_lo - current_price):.2f} below swing band low ${mt_lo:.2f}. "
                f"Hold — next scout add on short retest (${st_lo:.2f}–${st_hi:.2f}); "
                f"swing adds wait for ${mt_lo:.2f}–${mt_hi:.2f}."
            ),
            "next_scout_add_at": _r(st_hi),
            "next_swing_add_at": _r(mt_lo),
        }
        bridge = build_bridge_band(
            st_hi,
            mt_lo,
            ma50 if ma50 > 0 else vwap,
            band_label="ST–Swing bridge",
        )
        if bridge:
            cross["bridge_band"] = bridge
        st_spot = {**st_spot, "cross_gap": cross, "state": "between_horizon_bands", "floor_band_high": _r(st_hi), "ceiling_band_low": _r(mt_lo)}
        mt_spot = {**mt_spot, "cross_gap": cross, "state": "between_horizon_bands", "floor_band_high": _r(st_hi), "ceiling_band_low": _r(mt_lo)}
        if bridge:
            st_spot["bridge_band"] = bridge
            mt_spot["bridge_band"] = bridge
            st_spot["in_bridge_band"] = bridge["low"] <= current_price <= bridge["high"]
            mt_spot["in_bridge_band"] = st_spot["in_bridge_band"]
    elif between_mt_st:
        cross = {
            "state": "between_horizon_bands",
            "floor_horizon": "medium",
            "ceiling_horizon": "short",
            "floor_band_high": _r(mt_hi),
            "ceiling_band_low": _r(st_lo),
            "label": "Between swing & short bands",
            "detail": (
                f"Spot sits above swing top but below short band — unusual after harmonization; "
                f"prefer swing levels ${mt_lo:.2f}–${mt_hi:.2f} for 3–6m adds."
            ),
        }
        st_spot = {**st_spot, "cross_gap": cross}
        mt_spot = {**mt_spot, "cross_gap": cross}

    short_ez["spot_position"] = st_spot
    medium_ez["spot_position"] = mt_spot

    # Long primary entry zone catch levels (display tier band)
    long_h = payload.get("long") or {}
    long_ez = long_h.get("entry_zone") or {}
    if long_ez:
        lt_lo = min(float(long_ez["low"]), float(long_ez["high"]))
        lt_hi = max(float(long_ez["low"]), float(long_ez["high"]))
        fv = float(long_h.get("fair_value") or long_h.get("target") or 0)
        ca = (long_h.get("entry_tiers") or {}).get("current_assessment") or {}
        mos_pct = float(ca.get("margin_of_safety_pct") or 0)
        cap = lt_hi
        if fv > 0 and mos_pct < LT_PARTIAL_MOS_PCT:
            cap = min(lt_hi, fv * (1 - LT_PARTIAL_MOS_PCT / 100))
        elif fv > 0 and mos_pct < LT_REQUIRED_MOS_PCT:
            cap = min(lt_hi, fv * (1 - LT_REQUIRED_MOS_PCT / 100))
        levels = build_entry_band_levels(lt_lo, lt_hi)
        capped = [row for row in levels if float(row["price"]) <= cap + 0.02]
        long_ez["levels"] = capped or [
            {"id": "mos_cap", "label": f"MOS cap · max add ${cap:.2f}", "price": round(cap, 2), "role": "entry", "sort": 1}
        ]
        long_ez["spot_position"] = classify_spot_band_position(
            current_price, lt_lo, lt_hi, band_label="long-term band",
            threshold_ceiling=True,
        )
        long_ez["trigger_kind"] = "at_or_below"
        long_ez["trigger_ceiling"] = _r(lt_hi)
        long_h["entry_zone"] = long_ez
        payload["long"] = long_h


def _rr_from_entry_mid(entry_low: float, entry_high: float, stop: float, target: float) -> float:
    """R:R from the entry midpoint (pullback-plan quality), not from extended spot."""
    mid = (float(entry_low) + float(entry_high)) / 2.0
    risk = mid - float(stop)
    reward = float(target) - mid
    if risk > 0 and reward > 0:
        return _r(reward / risk, 2)
    return 0.0


def _forward_fair_value(fv: float, earnings_growth_pct: float | None, years: float = LT_FORWARD_YEARS) -> float:
    """Grow today's FV by expected EPS growth so long targets are not stuck at spot-date intrinsic."""
    if fv <= 0:
        return fv
    g = earnings_growth_pct if earnings_growth_pct is not None else LT_DEFAULT_GROWTH_PCT
    try:
        g = float(g)
    except (TypeError, ValueError):
        g = LT_DEFAULT_GROWTH_PCT
    # Cap the lift's own growth rate — separate from, and tighter than, fair_value_estimator's
    # growth cap on fv itself (see LT_FORWARD_GROWTH_CAP_PCT).
    g = max(-20.0, min(LT_FORWARD_GROWTH_CAP_PCT, g))
    y = max(0.25, float(years))
    return _r(fv * ((1.0 + g / 100.0) ** y))


def _mark_horizon_no_setup(h: dict[str, Any], reason: str) -> None:
    """Force WAIT and surface an explicit no-setup state (levels kept for context)."""
    warns = list(h.get("warnings") or [])
    if reason not in warns:
        warns.append(reason)
    h["warnings"] = warns
    h["setup_viable"] = False
    h["setup_status"] = "no_setup"
    h["verdict"] = "WAIT"
    if h.get("conviction") in ("High", "Medium"):
        h["conviction"] = "Low"


# Plausibility cap constants for medium/long targets (see _plausibility_cap): a target must
# be reachable within a bounded, roughly-2-sigma move from spot AND not run far past what
# analysts already publish as their high estimate — guards against a target compounding past
# any sane bound when fair_value itself is elevated (e.g. an EPS data artifact) and the
# forward-FV lift / cross-horizon monotonicity steps push it even higher.
_PLAUSIBILITY_SIGMA_MULT = 2.0
_PLAUSIBILITY_ANALYST_HIGH_BUFFER = 1.15  # allow the model to see 15% past the published Street high
_MT_TRADING_DAYS = 63    # ~3 months
_LT_TRADING_DAYS = 252   # ~12 months

# Threshold for the (non-blocking) street-divergence disclosure note — not a cap.
STREET_DIVERGENCE_NOTE_PCT = 15.0


def _plausibility_cap(
    current_price: float,
    atr: float | None,
    analyst_high: float | None,
    trading_days: int,
) -> float | None:
    """Lower of a volatility-implied ceiling (~sigma_mult * daily-vol-proxy over the horizon)
    and a buffered analyst-consensus-high ceiling — whichever constrains the target more.
    None (no cap) only when neither input is available."""
    caps: list[float] = []
    if atr and atr > 0 and current_price > 0:
        daily_vol_pct = atr / current_price
        move_pct = daily_vol_pct * _PLAUSIBILITY_SIGMA_MULT * math.sqrt(trading_days)
        caps.append(current_price * (1 + move_pct))
    if analyst_high and analyst_high > 0:
        caps.append(analyst_high * _PLAUSIBILITY_ANALYST_HIGH_BUFFER)
    return min(caps) if caps else None


def _apply_horizon_plan_invariants(
    payload: dict[str, Any],
    *,
    current_price: float,
    fair_value: float | None,
    atr: float | None = None,
    earnings_growth_pct: float | None = None,
    analyst_target_high: float | None = None,
    analyst_target_median: float | None = None,
) -> None:
    """
    Hard plan-quality gates before UI render:
      - Long target uses forward FV (grown by expected EPS), not today's FV alone
      - Targets non-decreasing short → medium → long
      - Medium/long targets capped by volatility-implied plausibility and analyst high
      - Medium/long targets that still diverge far from street consensus get a disclosure
        note (not a clamp — see STREET_DIVERGENCE_NOTE_PCT)
      - Per-horizon: min edge above entry_high + R:R ≥ 1.5 from entry mid
      - Low historical touch odds + deep pullback → no setup
      - Extended above FV → DO NOT CHASE / pullback-conditional mode
      - Large |spot−FV|/ATR → FV staleness flag
    """
    short = payload.get("short") if isinstance(payload.get("short"), dict) else None
    medium = payload.get("medium") if isinstance(payload.get("medium"), dict) else None
    long_h = payload.get("long") if isinstance(payload.get("long"), dict) else None
    if not short or not medium or not long_h:
        return

    fv = float(fair_value) if fair_value and float(fair_value) > 0 else None
    px = float(current_price) if current_price and current_price > 0 else 0.0

    # ── 1) Long target = forward FV (horizon-specific anchor) ─────────────
    if fv is not None:
        fwd = _forward_fair_value(fv, earnings_growth_pct)
        prev_t = float(long_h.get("target") or 0)
        if fwd > prev_t + 1e-6:
            long_h["target"] = fwd
            long_h["target_basis"] = "forward_fv"
            long_h["fair_value"] = fv
            long_h["forward_fair_value"] = fwd
            warns = list(long_h.get("warnings") or [])
            note = (
                f"Long target uses forward FV ${fwd:.2f} "
                f"(today's FV ${fv:.2f} grown over ~{LT_FORWARD_YEARS:.0f}y) — "
                "not today's intrinsic as a 12-month ceiling."
            )
            if note not in warns:
                warns.append(note)
            long_h["warnings"] = warns
            refresh_horizon_rr_from_levels(long_h, px or None)

    # ── 2) Monotonic targets across horizons ──────────────────────────────
    st_t = float(short.get("target") or 0)
    mt_t = float(medium.get("target") or 0)
    lt_t = float(long_h.get("target") or 0)
    if st_t > 0 and mt_t > 0 and mt_t + 1e-6 < st_t:
        medium["target"] = _r(st_t)
        warns = list(medium.get("warnings") or [])
        note = (
            f"Medium target lifted to ${st_t:.2f} so the 3m plan does not undercut the 1m target "
            "(cross-horizon monotonicity)."
        )
        if note not in warns:
            warns.append(note)
        medium["warnings"] = warns
        refresh_horizon_rr_from_levels(medium, px or None)
        mt_t = st_t
    if mt_t > 0 and lt_t > 0 and lt_t + 1e-6 < mt_t:
        long_h["target"] = _r(mt_t)
        warns = list(long_h.get("warnings") or [])
        note = (
            f"Long target lifted to ${mt_t:.2f} so the 6–18m thesis does not shrink vs the 3m plan."
        )
        if note not in warns:
            warns.append(note)
        long_h["warnings"] = warns
        refresh_horizon_rr_from_levels(long_h, px or None)

    # ── 2b) Plausibility cap — target must be reachable within a bounded move from spot
    # AND not run far past the published analyst high. Applied after the forward-FV lift
    # and monotonicity steps above, since either can push a target past a sane bound when
    # fair_value itself is elevated (a bad EPS input, a stale estimate, etc.).
    if px > 0:
        mt_cap = _plausibility_cap(px, atr, analyst_target_high, _MT_TRADING_DAYS)
        if mt_cap is not None:
            mt_t = float(medium.get("target") or 0)
            if mt_t > mt_cap + 1e-6:
                medium["target"] = _r(mt_cap)
                warns = list(medium.get("warnings") or [])
                note = (
                    f"Medium target capped to ${mt_cap:.2f} — the uncapped target implied a move "
                    "beyond plausible 3-month volatility and/or well past the analyst consensus high."
                )
                if note not in warns:
                    warns.append(note)
                medium["warnings"] = warns
                refresh_horizon_rr_from_levels(medium, px or None)
        lt_cap = _plausibility_cap(px, atr, analyst_target_high, _LT_TRADING_DAYS)
        if lt_cap is not None:
            lt_t = float(long_h.get("target") or 0)
            if lt_t > lt_cap + 1e-6:
                long_h["target"] = _r(lt_cap)
                warns = list(long_h.get("warnings") or [])
                note = (
                    f"Long target capped to ${lt_cap:.2f} — the uncapped target implied a move "
                    "beyond plausible 12-month volatility and/or well past the analyst consensus high."
                )
                if note not in warns:
                    warns.append(note)
                long_h["warnings"] = warns
                refresh_horizon_rr_from_levels(long_h, px or None)

    # ── 2c) Street-divergence disclosure (no clamp) ────────────────────────
    # Deliberately not a cap: a model that can never diverge from analyst consensus can
    # never show a genuine high-conviction call ahead of the street — that's sometimes the
    # whole point of running a model. Surface the gap instead, the same way fair_value's
    # own divergence-from-street note already works, so the user can judge the conviction
    # themselves rather than have it silently clamped away.
    if analyst_target_median and analyst_target_median > 0:
        for h in (medium, long_h):
            t = float(h.get("target") or 0)
            if t <= 0:
                continue
            div_pct = _r((t - analyst_target_median) / analyst_target_median * 100, 1)
            if abs(div_pct) >= STREET_DIVERGENCE_NOTE_PCT:
                warns = list(h.get("warnings") or [])
                note = (
                    f"Target is {div_pct:+.0f}% vs street consensus (${analyst_target_median:.2f}) — "
                    "model conviction beyond current analyst estimates, not blended or capped to them."
                )
                if note not in warns:
                    warns.append(note)
                h["warnings"] = warns

    # ── 3) Per-horizon edge + R:R from entry mid ──────────────────────────
    for key in ("short", "medium", "long"):
        h = payload.get(key)
        if not isinstance(h, dict):
            continue
        ez = h.get("entry_zone") or {}
        try:
            el = float(ez.get("low") or 0)
            eh = float(ez.get("high") or 0)
            stop = float(h.get("stop_loss") or 0)
            target = float(h.get("target") or 0)
        except (TypeError, ValueError):
            continue
        if not (el > 0 and eh >= el and stop > 0 and target > 0):
            continue
        edge_ok = target > eh * (1.0 + PLAN_MIN_EDGE_PCT / 100.0)
        rr_entry = _rr_from_entry_mid(el, eh, stop, target)
        h["risk_reward_from_entry"] = rr_entry
        h.setdefault("setup_viable", True)
        h.setdefault("setup_status", "ok")
        if not edge_ok:
            _mark_horizon_no_setup(
                h,
                f"No setup at this horizon — target ${target:.2f} lacks ≥{PLAN_MIN_EDGE_PCT:.0f}% "
                f"edge above entry high ${eh:.2f}.",
            )
        elif rr_entry < PLAN_MIN_RR_FROM_ENTRY:
            _mark_horizon_no_setup(
                h,
                f"No setup at this horizon — R:R from entry mid is {rr_entry:.2f}x "
                f"(need ≥{PLAN_MIN_RR_FROM_ENTRY:.1f}x).",
            )

        # Soft suppress: deep pullback + low historical touch odds
        fc = h.get("entry_touch_forecast") if isinstance(h.get("entry_touch_forecast"), dict) else {}
        touch = fc.get("touch_probability_pct") if fc else None
        if (
            px > 0
            and eh > 0
            and px > eh * (1.0 + TOUCH_SUPPRESS_DROP_PCT / 100.0)
            and touch is not None
            and float(touch) < TOUCH_SUPPRESS_PCT
            and h.get("setup_viable", True)
        ):
            _mark_horizon_no_setup(
                h,
                f"No setup at this horizon — entry needs ~{((px - eh) / px * 100):.0f}% pullback "
                f"with only ~{float(touch):.0f}% historical touch odds in-window.",
            )

    # ── 4) Extended above FV → DO NOT CHASE / pullback-conditional ───────
    if fv is not None and px > 0 and px > fv * (1.0 + EXTENDED_ABOVE_FV_PCT / 100.0):
        gap = _r((px - fv) / fv * 100, 1)
        payload["plan_mode"] = "pullback_conditional"
        payload["chase_banner"] = "ABOVE FAIR VALUE"
        payload["chase_detail"] = (
            f"Spot ${px:.2f} is ~{gap:.0f}% above model FV ${fv:.2f}. Bands below are optional "
            "cheaper-fill levels; stocks trading above their bands have not done worse on average."
        )
        for key in ("short", "medium", "long"):
            h = payload.get(key)
            if isinstance(h, dict):
                h["plan_mode"] = "pullback_conditional"

    # ── 5) FV staleness when price has run far from the estimate ─────────
    if fv is not None and atr and float(atr) > 0 and px > 0:
        sigma = abs(px - fv) / float(atr)
        if sigma >= FV_STALE_ATR_SIGMA:
            payload["fv_staleness"] = {
                "flagged": True,
                "sigma_vs_atr": _r(sigma, 2),
                "spot": _r(px),
                "fair_value": _r(fv),
                "note": (
                    f"Price is {sigma:.1f}σ(ATR) from model FV ${fv:.2f} — "
                    "recompute or flag when consensus revises; FV may lag a fast tape."
                ),
            }
            warns = list(long_h.get("warnings") or [])
            note = payload["fv_staleness"]["note"]
            if note not in warns:
                warns.append(note)
            long_h["warnings"] = warns

    payload["short"] = short
    payload["medium"] = medium
    payload["long"] = long_h


def _flag_cross_horizon_invariants(payload: dict[str, Any]) -> None:
    """Packet-time check: owner floor must not sit above swing/scout add levels."""
    medium = payload.get("medium") or {}
    long_h = payload.get("long") or {}
    mt_ez = medium.get("entry_zone") or {}
    lt_ez = long_h.get("entry_zone") or {}
    mt_lo = mt_ez.get("low")
    lt_lo = lt_ez.get("low")
    mt_levels = mt_ez.get("levels") or []
    swing_floor = mt_lo
    for row in mt_levels:
        if isinstance(row, dict) and row.get("price") is not None:
            px = float(row["price"])
            if swing_floor is None or px < float(swing_floor):
                swing_floor = px
    if swing_floor is None or lt_lo is None:
        return
    if float(lt_lo) > float(swing_floor) + 0.02:
        warns = list(long_h.get("warnings") or [])
        warns.append(
            f"INVARIANT: owner entry floor ${float(lt_lo):.2f} sits above swing add "
            f"${float(swing_floor):.2f} — long-term capital would skip a print the swing trader takes."
        )
        long_h["warnings"] = warns
        long_h["cross_horizon_invariant_ok"] = False
        payload["long"] = long_h
    else:
        long_h["cross_horizon_invariant_ok"] = True
        payload["long"] = long_h


def entry_zone_from_tier(tier: EntryTier, *, inside: bool) -> EntryZone:
    """Build horizon card entry_zone from a tier row."""
    if inside:
        quality, color = "In Zone", tier.color
        anchor = "{} (${:.2f}–${:.2f}) — active accumulation band".format(
            tier.label.split("—")[0].strip() if "—" in tier.label else tier.label,
            tier.low,
            tier.high,
        )
    else:
        quality, color = "Waiting", tier.color
        anchor = "{} — target pullback band (${:.2f}–${:.2f})".format(
            tier.label.split("—")[0].strip() if "—" in tier.label else tier.label,
            tier.low,
            tier.high,
        )
    return EntryZone(
        low=tier.low,
        high=tier.high,
        anchor=anchor,
        quality=quality,
        quality_color=color,
    )


def _short_term_effective_support(support_level: float, current_price: float) -> float:
    """Raise deep historical lows so the 1m zone stays in plausible pullback range, not 52w crash levels."""
    if current_price <= 0:
        return support_level
    floor = current_price * (1 - ST_SUPPORT_MAX_DEPTH_PCT / 100.0)
    return max(float(support_level), floor)


def _cap_short_entry_zone_vs_fair_value(
    el: float,
    eh: float,
    *,
    fair_value: Optional[float],
    current_price: float,
) -> tuple[float, float, bool, str]:
    """
    If the technical band sits above model fair value, do not label a 'buy' above intrinsic.
    Pull the band so its ceiling is at most fair value (with tiny tolerance for rounding).
    """
    if fair_value is None or fair_value <= 0:
        return el, eh, False, ""
    tol = max(0.2, 0.001 * fair_value)
    if eh <= fair_value + tol:
        return el, eh, False, ""
    new_eh = min(eh, fair_value)
    new_el = min(el, new_eh * 0.985, fair_value * 0.97)
    if new_el >= new_eh - 1e-6:
        new_el = new_eh * 0.97
    new_el = max(0.01, new_el)
    note = (
        "Aligned to model fair value (${:.2f}) — near-term zone was above intrinsic; "
        "prefer adds here or lower, not chasing spot/VWAP."
    ).format(fair_value)
    return _r(new_el), _r(new_eh), True, note


def _compress_entry_zone_for_display(
    *,
    band_key: str,
    low: float,
    high: float,
    current_price: float,
) -> tuple[float, float, bool]:
    """
    Keep entry zones actionable for UI/alerts.
    Very wide zones read as low precision and become "always in zone".
    P1 Fix: Adjusted compression thresholds for better accuracy:
    - Short: tighter (0.12) for precise tactical entries
    - Medium: looser (0.35) to accommodate swing ranges
    - Long: looser (0.50) for owner accumulation zones
    """
    if not (low > 0 and high > low and current_price > 0):
        return low, high, False
    width_pct = (high - low) / current_price
    max_pct_by_band = {
        "short": 0.12,  # tightened from 0.14 for better tactical precision
        "medium": 0.35,  # loosened from 0.30 for swing flexibility
        "long": 0.50,   # loosened from 0.45 for owner accumulation
    }
    max_pct = max_pct_by_band.get(str(band_key).lower(), 0.30)
    if width_pct <= max_pct:
        return low, high, False
    new_high = low + current_price * max_pct
    min_pad = max(0.01, current_price * 0.002)
    new_high = max(min(new_high, high), low + min_pad)
    return _r(low), _r(new_high), True


def _clamp_entry_high_to_spot(
    el: float,
    eh: float,
    spot: float,
) -> tuple[float, float, bool]:
    """Pullback / wait bands must not have a ceiling above spot (that would buy a rally)."""
    if not (spot > 0 and eh > spot + 1e-6):
        return el, eh, False
    new_eh = _r(spot)
    new_el = min(el, new_eh * 0.995)
    if new_el >= new_eh - 1e-6:
        new_el = _r(max(0.01, new_eh * 0.99))
    return _r(new_el), new_eh, True


def _rr_from_displayed_levels(spot: float, stop: float, target: float) -> float:
    """R:R from the same stop/target/spot the UI paints — not a stale floor like 2.0x."""
    risk = spot - stop
    reward = target - spot
    if risk > 0 and reward > 0:
        return _r(reward / risk, 2)
    return 0.0


def refresh_horizon_rr_from_levels(horizon: dict, spot: float | None) -> None:
    """Keep risk_reward / target_pct / stop_loss_pct in lockstep with painted levels.

    Call after any mutation of stop or target (e.g. scenario-target sync).
    """
    if not isinstance(horizon, dict):
        return
    try:
        px = float(spot) if spot is not None else None
        stop = float(horizon["stop_loss"]) if horizon.get("stop_loss") is not None else None
        target = float(horizon["target"]) if horizon.get("target") is not None else None
    except (TypeError, ValueError):
        return
    if px is None or not (px > 0) or stop is None or target is None:
        return
    horizon["risk_reward"] = _rr_from_displayed_levels(px, stop, target)
    horizon["target_pct"] = _r((target - px) / px * 100, 1)
    horizon["stop_loss_pct"] = _r((stop - px) / px * 100, 1)
    # risk_reward_from_entry is set once in the per-horizon edge pass; a later stop/target
    # mutation (e.g. scenario-target sync) must re-derive it too, or the Verdict R:R tile
    # (from entry mid) and the painted levels row disagree — e.g. HAL 3.1 vs 11.7.
    if "risk_reward_from_entry" in horizon:
        ez = horizon.get("entry_zone") or {}
        try:
            el = float(ez.get("low") or 0)
            eh = float(ez.get("high") or 0)
        except (TypeError, ValueError):
            el = eh = 0.0
        if el > 0 and eh >= el and stop > 0 and target > 0:
            horizon["risk_reward_from_entry"] = _rr_from_entry_mid(el, eh, stop, target)


# ══════════════════════════════════════════════════════════════════════════════
# SHORT-TERM CALCULATOR  (1 month)
# ──────────────────────────────────────────────────────────────────────────────
# Entry logic — RSI gates the anchor:
#   RSI < 35  (oversold)  → entry near lower of support or VWAP
#   RSI 35-50 (neutral)   → VWAP pullback zone
#   RSI > 50  (elevated)  → current price, flagged as stretched
#
# Stop:   entry_low  - (ATR × 1.5)
# Target: min(resistance × 0.98,  entry_high + ATR × 3.0), then optional cap vs entry_high
#         when HMM bull % is below 48% — keeps 1m upside from implying 6–10% base-case bounces in non-bull tape.
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
    fair_value: Optional[float] = None  # caps ST band so we do not imply buying above intrinsic
    horizon_confidence_pct: Optional[float] = None  # 0-100, per-horizon 7-layer fused score


def compute_short_term_entry(inp: ShortTermInputs) -> HorizonSignal:
    warnings = []

    # ── Entry zone ───────────────────────────────────────────────────────
    sup_eff = _short_term_effective_support(inp.support_level, inp.current_price)
    if inp.rsi < ST_RSI_OVERSOLD:
        anchor = min(sup_eff, inp.vwap)
        depth_pct = (
            (inp.current_price - anchor) / inp.current_price * 100.0
            if inp.current_price > 0
            else 0.0
        )
        # Deep support (e.g. 52w floor after clamp) is not a 1-month entry band — align with VWAP pullback
        if depth_pct > ST_MAX_NEAR_TERM_ZONE_DEPTH_PCT:
            el, eh = _r(inp.vwap * 0.985), _r(inp.vwap * 1.005)
            quality, q_color = "Acceptable", "#f5a623"
            zone_anchor = (
                "RSI oversold ({:.0f}) — near-term add zone at VWAP "
                "(deeper support ~${:.2f} is long-term / stress, not core 1m zone)"
            ).format(inp.rsi, sup_eff)
            warnings.append(
                "Support ~{:.0f}% below spot — 1m zone uses VWAP; use long-term tiers for larger adds.".format(
                    depth_pct
                )
            )
        else:
            el, eh = _r(anchor * 0.99), _r(anchor * 1.01)
            quality, q_color = "Ideal", "#00e5a0"
            zone_anchor = "RSI oversold ({:.0f}) — entry near support ${:.2f}".format(
                inp.rsi, sup_eff)

    elif inp.rsi < 50:
        el, eh = _r(inp.vwap * 0.985), _r(inp.vwap * 1.005)
        quality, q_color = "Acceptable", "#f5a623"
        zone_anchor = "VWAP pullback zone (RSI {:.0f})".format(inp.rsi)

    else:
        el, eh = _r(inp.current_price * 0.99), _r(inp.current_price * 1.005)
        quality, q_color = "Stretched", "#ff6b6b"
        zone_anchor = "Current price — RSI elevated ({:.0f}), not ideal".format(inp.rsi)
        warnings.append(
            "RSI {:.0f} is elevated — optional limit near VWAP (${:.2f}) for a cheaper fill".format(
                inp.rsi, inp.vwap))

    el, eh, fv_capped, fv_note = _cap_short_entry_zone_vs_fair_value(
        el, eh, fair_value=inp.fair_value, current_price=inp.current_price
    )
    if fv_capped and fv_note:
        zone_anchor = zone_anchor + " | " + fv_note
        warnings.append(
            "Short-term entry band capped vs fair value — spot/VWAP implied paying above model intrinsic."
        )
        if quality == "Ideal":
            quality, q_color = "Acceptable", "#f5a623"

    el, eh, zone_compressed = _compress_entry_zone_for_display(
        band_key="short",
        low=el,
        high=eh,
        current_price=inp.current_price,
    )
    if zone_compressed:
        zone_anchor = zone_anchor + " | Actionable-width cap applied"
        warnings.append("Short-term entry zone was too wide; narrowed for actionable execution.")

    if quality in ("Stretched", "Waiting") or "pullback" in zone_anchor.lower() or "wait for" in zone_anchor.lower():
        el, eh, clamped = _clamp_entry_high_to_spot(el, eh, inp.current_price)
        if clamped:
            zone_anchor = zone_anchor + " | Ceiling clamped to spot (no chase)"
            warnings.append("Entry ceiling capped at spot — pullback setup must not buy a rally.")

    # ── Stop & target ────────────────────────────────────────────────────
    stop_dist = max(
        inp.atr * ST_ATR_STOP_MULT,
        inp.current_price * (ST_MIN_STOP_DISTANCE_PCT_OF_SPOT / 100.0),
    )
    stop_loss     = _r(el - stop_dist)
    stop_loss_pct = _r((stop_loss - eh) / eh * 100, 1)
    _atr_target   = _r(eh + inp.atr * ST_ATR_TARGET_MULT)
    target        = _r(min(inp.resistance_level * 0.98, _atr_target))
    # When resistance cap sits at/below entry zone high (price near 52w high), resistance * 0.98
    # can produce a target below entry high — enforce a minimum of the ATR-based target.
    if target <= eh + 0.01:
        target = _atr_target

    st_cap_pct = _short_term_regime_cap_upside_pct(inp.regime_bull_pct)
    if st_cap_pct is not None:
        cap_px = _r(eh * (1.0 + st_cap_pct / 100.0))
        if target > cap_px + 1e-9:
            target = cap_px
            warnings.append(
                "Short-term upside capped at {:.1f}% above the entry band (HMM bull ~{:.0f}%) — "
                "non-bull tape dampens tactical targets vs raw ATR/resistance; treat larger moves as stretch / regime-shift scenarios.".format(
                    st_cap_pct, inp.regime_bull_pct
                )
            )

    target_pct    = _r((target - eh) / eh * 100, 1)
    rr            = _rr_from_displayed_levels(inp.current_price, stop_loss, target)

    # ── Warnings ─────────────────────────────────────────────────────────
    if rr < ST_MIN_RR:
        warnings.append(
            "R/R {:.2f}x is below {:.1f}x minimum — consider tighter stop or skip".format(rr, ST_MIN_RR))
    if inp.volume_ratio < 0.7:
        warnings.append(
            "Low volume ({:.1f}x average) — conviction in move is weak".format(inp.volume_ratio))

    # ── Verdict ──────────────────────────────────────────────────────────
    # Fixed: pattern_score threshold reduced from 55 to 35 to align with documented normal range (27-43 for non-bottom setups)
    # This reduces false negatives for valid technical setups
    all_clear = (inp.ml_prob >= ST_MIN_ML_PROB and inp.rsi < ST_RSI_OVERBOUGHT
                 and inp.regime_bull_pct >= 40 and inp.pattern_score >= 35 and rr >= ST_MIN_RR)
    if all_clear:
        verdict, conviction = "BUY", "Medium"
    elif inp.ml_prob >= ST_MIN_ML_PROB and rr >= 1.2:
        verdict, conviction = "WATCH", "Low"
    else:
        verdict, conviction = "WAIT", "Low"

    # ── Per-horizon 7-layer confidence boost ────────────────────────────
    if inp.horizon_confidence_pct is not None:
        hc = float(inp.horizon_confidence_pct)
        if verdict == "WAIT" and hc >= 55 and inp.ml_prob >= ST_MIN_ML_PROB and rr >= 1.2:
            verdict, conviction = "WATCH", "Low"
        elif verdict == "WATCH" and conviction == "Low" and hc >= 62:
            conviction = "Medium"
        elif verdict in ("WATCH", "BUY") and hc >= 72 and inp.ml_prob >= ST_MIN_ML_PROB and rr >= ST_MIN_RR:
            verdict, conviction = "BUY", "Medium"
        elif verdict == "BUY" and conviction == "Medium" and hc >= 78:
            conviction = "High"

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

    in_zone = el <= inp.current_price <= eh
    if in_zone:
        trigger = (
            "Price is already in ${el}–${eh} — waiting on RSI < {rsi_thresh:.0f} "
            "and ML prob > {ml_thresh:.0f}%, not a further pullback"
        ).format(el=el, eh=eh, rsi_thresh=ST_RSI_OVERSOLD, ml_thresh=ST_MIN_ML_PROB)
    else:
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
#   Price at/below MA50          → Bridge zone from current area up to MA50 (not only MA50×0.97–1.01,
#                                  which sat entirely above spot and implied "chase" vs short-term)
#   Price within 4% above MA50   → Acceptable  (MA50 × 0.99–1.04)
#   Price > 4% above MA50        → Stretched, flag and wait
# Cross-horizon: medium entry low never above short-term entry low (optional short_entry_* on inputs).
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
    # When set (e.g. from build_all_horizons_payload), MT entry low never sits above short-term buy zone
    short_entry_low: Optional[float] = None
    short_entry_high: Optional[float] = None
    # Caps swing target so minimum R/R math cannot inflate 3m target far above FV (NVDA-style outlier)
    fair_value: Optional[float] = None
    horizon_confidence_pct: Optional[float] = None  # 0-100, per-horizon 7-layer fused score


def _harmonize_medium_entry_with_short(
    inp: MediumTermInputs,
    el: float,
    eh: float,
    quality: str,
    q_color: str,
    zone_anchor: str,
) -> tuple[float, float, str, str, str]:
    """
    Enforce: medium-term entry is not a *higher* minimum price than short-term (no chase).
    When violated, widen toward [short .. MA50] per retail rule.
    """
    p = inp.current_price
    st_lo = inp.short_entry_low
    if st_lo is None or el <= st_lo + 1e-6:
        return el, eh, quality, q_color, zone_anchor

    el2 = _r(min(st_lo, p * 0.99, inp.ma50 * 0.97))
    st_hi = inp.short_entry_high if inp.short_entry_high is not None else eh
    eh2 = _r(max(st_hi, inp.ma50))
    if el2 >= eh2 - 1e-6:
        eh2 = _r(max(el2 * 1.02, inp.ma50 * 0.99, st_hi))
    qa, qc = quality, q_color
    if quality == "Ideal":
        qa, qc = "Acceptable", "#f5a623"
    anchor2 = (
        "Medium-term entry aligned with short (≤${:.2f}) through MA50 (${:.2f}) — "
        "longer horizon is not a higher entry price than short-term"
    ).format(st_lo, inp.ma50)
    return el2, eh2, qa, qc, anchor2


def _medium_term_signal_from_zone(
    inp: MediumTermInputs,
    el: float,
    eh: float,
    quality: str,
    q_color: str,
    zone_anchor: str,
    warnings: list,
) -> HorizonSignal:
    """Stop/target/R:R, verdict, and payload from a finalized (el, eh) medium-term band."""
    p = inp.current_price
    pct_above_ma50 = (p - inp.ma50) / inp.ma50 * 100

    # ── Stop: below MA50 invalidates — but if price is below MA50, structural MA50 stop can sit *above* spot
    structural_stop = _r(inp.ma50 * (1 - MT_STOP_BELOW_MA50_PCT / 100))
    if p < inp.ma50 and structural_stop > p * 1.02:
        entry_floor = min(el, p) if el > 0 else p
        stop_loss = _r(entry_floor * (1 - MT_STOP_BELOW_MA50_PCT / 100))
    else:
        stop_loss = structural_stop
    stop_loss_pct = _r((stop_loss - eh) / eh * 100, 1)

    # ── Target: ML-scaled with quality multiplier ────────────────────────
    quality_mult = 1.0
    if inp.fundamentals_score >= 70:       quality_mult += 0.03
    if inp.options_sentiment_score >= 60:  quality_mult += 0.02
    if inp.insider_activity_score >= 60:   quality_mult += 0.02

    target_pct = _r(inp.ml_prob / 100 * 25 * quality_mult, 1)
    target     = _r(eh * (1 + target_pct / 100))
    risk       = max(p - stop_loss, eh - stop_loss)
    rr         = _rr_from_displayed_levels(p, stop_loss, target)

    # Enforce minimum 2:1 R/R — but do not mechanical-bump above fair value (else 3m target looks like 40%+ upside)
    if rr < MT_MIN_RR and risk > 0:
        target_rr = _r(p + risk * MT_MIN_RR)
        if inp.fair_value and inp.fair_value > 0:
            fv_cap = _r(max(inp.fair_value * 1.12, eh * 1.05))
            if target_rr > fv_cap:
                target = _r(min(target_rr, fv_cap))
                warnings.append(
                    "Swing target capped vs fair value (${:.2f}) — R/R from displayed levels without implying a huge 3m upside"
                    .format(inp.fair_value)
                )
            else:
                target = target_rr
                warnings.append(
                    "Target adjusted upward to enforce minimum {:.1f}x R/R".format(MT_MIN_RR))
        else:
            target = target_rr
            warnings.append(
                "Target adjusted upward to enforce minimum {:.1f}x R/R".format(MT_MIN_RR))

    # Final guard: medium horizon target should not sit far above FV when FV is known
    if inp.fair_value and inp.fair_value > 0 and target > inp.fair_value * 1.15 + 1e-6:
        target = _r(min(target, inp.fair_value * 1.12))
        warnings.append("3m target aligned to fair value band (~+12% vs FV max for swing)")

    target_pct = _r((target - p) / p * 100, 1) if p > 0 else 0.0
    rr = _rr_from_displayed_levels(p, stop_loss, target)

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
    # Fixed: Added OR condition (regime_bull_pct >= MT_REGIME_BULL_MIN or ml_prob >= 45) to reduce false negatives
    # Previously required both to pass, which blocked valid setups when one signal was strong
    if (inp.ml_prob >= MT_MIN_ML_PROB and quality in ("Ideal", "Acceptable")
            and (inp.regime_bull_pct >= MT_REGIME_BULL_MIN or inp.ml_prob >= 45) and rr >= MT_MIN_RR):
        if inp.ml_prob >= 50:
            verdict, conviction = "BUY", "High"
        else:
            verdict, conviction = "WATCH", "Medium"
    elif inp.ml_prob >= 30 and quality != "Stretched":
        verdict, conviction = "WATCH", "Low"
    else:
        verdict, conviction = "WAIT", "Low"

    # ── Per-horizon 7-layer confidence boost ────────────────────────────
    if getattr(inp, "horizon_confidence_pct", None) is not None:
        hc = float(inp.horizon_confidence_pct)
        if verdict == "WAIT" and hc >= 55 and inp.ml_prob >= MT_MIN_ML_PROB:
            verdict, conviction = "WATCH", "Low"
        elif verdict == "WATCH" and conviction == "Low" and hc >= 62:
            conviction = "Medium"
        elif verdict == "WATCH" and hc >= 68 and rr >= MT_MIN_RR:
            verdict, conviction = "BUY", "Medium"
        elif verdict == "BUY" and hc >= 75:
            conviction = "High"

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

    if el <= p <= eh:
        trigger = (
            "Price is already in the MA50 zone (${el}–${eh}) — waiting on "
            "ML prob >= {ml:.0f}% and regime Bull >= 45%, not a further pullback"
            "{earn}"
        ).format(
            el=el, eh=eh, ml=MT_MIN_ML_PROB,
            earn=" — OR enter pre-earnings ({}d) with half position".format(
                inp.days_to_earnings) if earnings_flag else "")
    else:
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


def compute_medium_term_entry(inp: MediumTermInputs) -> HorizonSignal:
    p = inp.current_price
    warnings = []
    pct_above_ma50 = (p - inp.ma50) / inp.ma50 * 100

    # ── Entry zone anchored to MA50 ──────────────────────────────────────
    if pct_above_ma50 <= 0:
        # Bridge from current area toward MA50 — not a band that starts only at MA50×0.97 (above spot)
        cap_lo = min(p * 0.99, inp.ma50 * 0.97)
        if inp.short_entry_low is not None:
            cap_lo = min(cap_lo, inp.short_entry_low)
        el = _r(cap_lo)
        eh = _r(inp.ma50 * 1.01)
        if el >= eh - 1e-6:
            eh = _r(max(el * 1.02, inp.ma50 * 0.99))
        quality, q_color = "Ideal", "#00e5a0"
        zone_anchor = (
            "From current area toward MA50 (${:.2f}) — add toward trend; zone runs up to MA50+1%"
        ).format(inp.ma50)

    elif pct_above_ma50 <= MT_MA50_BAND_PCT:
        el, eh = _r(inp.ma50 * 0.99), _r(inp.ma50 * (1 + MT_MA50_BAND_PCT / 100))
        quality, q_color = "Acceptable", "#f5a623"
        zone_anchor = "Within {:.0f}% above MA50 (${:.2f})".format(MT_MA50_BAND_PCT, inp.ma50)

    else:
        el, eh = _r(inp.ma50 * 0.99), _r(inp.ma50 * 1.04)
        quality, q_color = "Stretched", "#ff6b6b"
        zone_anchor = "Price {:.1f}% above MA50 — optional limit near ${:.2f} for a cheaper fill".format(
            pct_above_ma50, inp.ma50)
        warnings.append(
            "Price is {:.1f}% above MA50 (${:.2f}). "
            "Ideal medium-term entry: ${:.2f}–${:.2f}".format(
                pct_above_ma50, inp.ma50, el, eh))

    el, eh, quality, q_color, zone_anchor = _harmonize_medium_entry_with_short(
        inp, el, eh, quality, q_color, zone_anchor)

    el, eh, zone_compressed = _compress_entry_zone_for_display(
        band_key="medium",
        low=el,
        high=eh,
        current_price=inp.current_price,
    )
    if zone_compressed:
        zone_anchor = zone_anchor + " | Actionable-width cap applied"
        warnings.append("Medium-term entry zone was too wide; narrowed for clearer timing.")

    if quality in ("Stretched", "Waiting") or "pullback" in zone_anchor.lower() or "wait for" in zone_anchor.lower():
        el, eh, clamped = _clamp_entry_high_to_spot(el, eh, inp.current_price)
        if clamped:
            zone_anchor = zone_anchor + " | Ceiling clamped to spot (no chase)"
            warnings.append("Swing entry ceiling capped at spot — pullback setup must not buy a rally.")

    return _medium_term_signal_from_zone(inp, el, eh, quality, q_color, zone_anchor, warnings)


# ══════════════════════════════════════════════════════════════════════════════
# LONG-TERM CALCULATOR  (6–18 months)
# ──────────────────────────────────────────────────────────────────────────────
# Three tiered entry zones — NONE anchored to current price.
#
#   T1  MA200 ± 5%          → dynamic % (starter)  ~2.5x R/R  — see tranche_heuristic
#   T2  Fair Value × MOS    → dynamic % (core)     ~3.5x R/R
#   T3  52w_low × 1.05–1.15 → dynamic % (tail)     ~5x+  R/R
#
# Stop:   ~5% below 52w low (structural invalidation) for single names; broad index ETFs use
#         max(MA200, 52w low) × 0.97 — same as price_targets / confidence watch levels (not tail-only).
# Target: today's FV as base; build_all_horizons then lifts to forward FV (EPS growth) + monotonic vs MT
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
    # Symbol for Tier 2 MOS profile (quality-based band); optional explicit override
    ticker: str = ""
    tier2_mos_pct: Optional[float] = None
    tier2_mos_by_class: Optional[Dict[str, Any]] = None
    tier2_mos_pct_by_ticker: Optional[Dict[str, Any]] = None
    # When set (e.g. from build_all_horizons_payload), primary entry must not start above short-term buy zone
    short_entry_low: Optional[float] = None
    short_entry_high: Optional[float] = None
    # Swing (medium) entry zone — T1 ceiling never above swing high; T1 floor never above swing low
    medium_entry_high: Optional[float] = None
    medium_entry_low: Optional[float] = None
    # Dynamic T1/T2/T3 % (shared with trade roadmap) — ATR + distance vs MA200 + fused model confidence
    atr: Optional[float] = None
    model_confidence_pct: Optional[float] = None
    horizon_confidence_pct: Optional[float] = None  # 0-100, per-horizon 7-layer fused score
    ma50: Optional[float] = None
    # When model FV is suppressed (banks, REITs, asset managers, pre-revenue biotech)
    fv_model_suppressed: bool = False
    fv_street_anchor_usd: Optional[float] = None
    fv_suppressed_reason: str = ""


def _harmonize_long_entry_zone_with_short(
    inp: LongTermInputs,
    tier1: EntryTier,
    entry_zone: EntryZone,
    warnings: list,
) -> EntryZone:
    """
    Owner/long entry is a T1 *ceiling*, not a tighter window than swing.

    A multi-year accumulator must accept at least as much discount as the
    swing trader: entry_zone.low never sits above nearer-horizon floors.
    Ceiling stays at T1.high (already capped to swing high).
    """
    floors = [v for v in (inp.short_entry_low, inp.medium_entry_low) if v is not None and v > 0]
    if not floors:
        return entry_zone
    nearer_floor = min(floors)
    if entry_zone.low <= nearer_floor + 1e-6:
        return entry_zone

    el = _r(min(entry_zone.low, nearer_floor))
    eh = entry_zone.high
    if el >= eh - 1e-6:
        eh = _r(max(el * 1.02, tier1.high))

    warnings.append(
        "Owner entry floor lowered to the swing/scout add zone (${:.2f}) — "
        "long-term capital must accept at least as much discount as nearer horizons."
        .format(nearer_floor)
    )
    return EntryZone(
        el,
        eh,
        anchor="T1 ceiling ${:.2f} (≤ MA200 zone) — floor includes nearer-horizon add levels through ${:.2f}".format(
            eh, el
        ),
        quality=entry_zone.quality,
        quality_color=entry_zone.quality_color,
    )


def compute_long_term_entry(inp: LongTermInputs) -> HorizonSignal:
    p = inp.current_price
    fv = inp.fair_value
    warnings: list[str] = []

    fv_anchor_label = "fair value"
    if inp.fv_model_suppressed:
        street = float(inp.fv_street_anchor_usd or 0)
        if street > 0:
            fv = street
            fv_anchor_label = "street consensus"
            warnings.append(
                "Model FV unavailable ({}). Tier 2 MOS uses street consensus ${:.2f}, not intrinsic model FV.".format(
                    (inp.fv_suppressed_reason or "suppressed").split("—")[0].strip(),
                    street,
                )
            )
        elif inp.ma200 and inp.ma200 > 0:
            fv = float(inp.ma200)
            fv_anchor_label = "MA200 technical"
            warnings.append(
                "Model FV unavailable and no street consensus — Tier 2 MOS uses MA200 technical anchor."
            )
        else:
            warnings.append("Model FV unavailable — tier MOS uses fallback anchor; treat tiers as indicative only.")

    mos_t2, mos_class = resolve_tier2_mos_pct(
        inp.ticker,
        inp.fundamentals_score,
        explicit_pct=inp.tier2_mos_pct,
        tier2_mos_by_class=inp.tier2_mos_by_class,
        ticker_overrides=inp.tier2_mos_pct_by_ticker,
    )
    mos_t2 = _r(mos_t2, 2)
    t2_label_suffix = "{:.0f}%".format(mos_t2)
    t2_profile_note = tier2_human_class_label(mos_class)

    # ── Current price MOS assessment ─────────────────────────────────────
    mos_pct          = _r((fv - p) / p * 100, 1)
    pct_above_ma200  = _r((p - inp.ma200) / inp.ma200 * 100, 1)
    min_price_to_buy = _r(fv * (1 - LT_REQUIRED_MOS_PCT / 100))

    if mos_pct >= LT_REQUIRED_MOS_PCT:
        assess_verdict = "BUY"
        assess_label   = "Sufficient MOS ({:.1f}%) vs {} — entry justified".format(mos_pct, fv_anchor_label)
        assess_color   = "#00e5a0"
    elif mos_pct >= LT_PARTIAL_MOS_PCT:
        assess_verdict = "PARTIAL"
        assess_label   = "Marginal discount ({:.1f}%) vs {} — partial position only".format(mos_pct, fv_anchor_label)
        assess_color   = "#f5a623"
    else:
        assess_verdict = "WAIT"
        assess_label   = "Only {:.1f}% discount vs {} — need {:.0f}% MOS for long-term entry".format(
            mos_pct, fv_anchor_label, LT_REQUIRED_MOS_PCT)
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

    t1_lo = _r(inp.ma200 * (1 - LT_MA200_BAND_PCT / 100))
    t1_hi = _r(inp.ma200 * (1 + LT_MA200_BAND_PCT / 100))
    mh = inp.medium_entry_high
    if mh is not None and mh > 0 and t1_hi > mh + 1e-6:
        if mh >= t1_lo - 1e-6:
            t1_hi = _r(min(t1_hi, mh))
            warnings.append(
                "Tier 1 MA200 ceiling capped to swing zone high (${:.2f}) — investor core entry never above swing top."
                .format(mh)
            )
        else:
            warnings.append(
                "Swing zone is entirely below MA200 Tier 1 — MA200 tiers still apply; swing is a nearer-term add band."
            )
    if t1_hi < t1_lo + 1e-6:
        t1_hi = _r(max(t1_lo * 1.02, inp.ma200 * 0.99))

    tier1 = make_tier(
        "T1", "Tier 1 — MA200 Zone",
        "Near 200-day moving average — medium conviction starter",
        t1_lo,
        t1_hi,
        "~2.5x", "Medium", "#f5a623")

    t2_center = fv * (1 - mos_t2 / 100)
    if inp.fv_model_suppressed:
        t2_title = "Tier 2 — {:.0f}% MOS (street-anchored)".format(mos_t2)
        t2_desc = (
            "Street consensus minus {:.0f}% MOS ({}) — core zone; model FV unavailable"
        ).format(mos_t2, t2_profile_note)
    else:
        t2_title = "Tier 2 — {} Margin of Safety".format(t2_label_suffix)
        t2_desc = (
            "Fair value minus {:.0f}% MOS ({}) — core accumulation zone"
        ).format(mos_t2, t2_profile_note)
    tier2 = make_tier(
        "T2", t2_title,
        t2_desc,
        _r(t2_center * (1 - LT_TIER2_BAND_PCT / 100)),
        _r(t2_center * (1 + LT_TIER2_BAND_PCT / 100)),
        "~3.5x", "High", "#00e5a0")

    # Same rule as Tier 1 above: the owner/investor add band never sits above the swing
    # zone top. Without this a FV-MOS band near spot (e.g. MSFT T2 ≤ $552 with spot $533,
    # swing zone $501–$526) told owners to buy higher than swing traders.
    if mh is not None and mh > 0 and tier2.high > mh + 1e-6:
        uncapped_hi = tier2.high
        new_hi = _r(mh)
        new_lo = _r(min(tier2.low, new_hi * (1 - 2 * LT_TIER2_BAND_PCT / 100)))
        tier2 = _refresh_tier_fv_metrics(replace(tier2, low=new_lo, high=new_hi), fv, p)
        warnings.append(
            "Tier 2 MOS ceiling capped to swing zone high (${:.2f}) — valuation alone would allow "
            "adds up to ${:.2f}, but owner adds never sit above the swing top.".format(mh, uncapped_hi)
        )

    tier3 = make_tier(
        "T3", "Tier 3 — Tail risk / 52w stress",
        "Stress scenario near 52w low — not a base-case entry; only if macro/liquidity breaks",
        _r(inp.week52_low * LT_TIER3_LOW_MULT),
        _r(inp.week52_low * LT_TIER3_HIGH_MULT),
        "~5x+", "Stress", "#64748b")

    tier1, tier2, tier3 = _enforce_strict_tier_ladder(tier1, tier2, tier3, fv, p, float(inp.week52_low or 0))

    # ── Entry zone for HorizonSignal — sync with active / target tier ───────
    all_tiers = [tier1, tier2, tier3]
    active_tier = resolve_active_tier(all_tiers, p)
    spot_position = classify_spot_tier_position(all_tiers, p)
    spot_position, mos_ceiling_flags = _enrich_mos_ceiling_context(
        spot_position,
        price=p,
        min_price_to_buy=min_price_to_buy,
        assess_verdict=assess_verdict,
        all_tiers=all_tiers,
    )
    if spot_position.get("below_all_within_mos") and assess_verdict == "BUY":
        assess_label = spot_position.get("label") or assess_label
        assess_color = "#00e5a0"
    target_tid = resolve_target_tier_id(all_tiers, p)
    display_tier = active_tier or next((t for t in all_tiers if t.id == target_tid), tier1)
    entry_zone = entry_zone_from_tier(display_tier, inside=active_tier is not None)
    entry_zone = _harmonize_long_entry_zone_with_short(inp, tier1, entry_zone, warnings)
    # Keep the displayed T1 tier band in lockstep with entry_zone — without this, a
    # ticker whose swing floor sits below MA200-5% shows two different "T1 floor"
    # numbers: entry_zone.low (harmonized) vs tiers[T1].low (raw MA200 anchor).
    if display_tier is tier1 and entry_zone.low < tier1.low - 1e-6:
        tier1.low = entry_zone.low
    if spot_position.get("state") == "between_tiers":
        detail = spot_position.get("detail")
        if detail:
            warnings.append(detail)
        assess_label = spot_position.get("label") or assess_label
        if assess_verdict == "BUY":
            assess_verdict = "PARTIAL"
            assess_label = (
                "MOS OK at spot, but price sits between tiers — partial/hold only; "
                "next add on {} retest".format(spot_position.get("floor_tier_id", "T1"))
            )
            assess_color = "#f5a623"
        bridge = build_bridge_band(
            float(spot_position.get("floor_band_high", 0)),
            float(spot_position.get("ceiling_band_low", 0)),
            inp.ma50 if inp.ma50 and inp.ma50 > 0 else None,
            band_label="T1.5 bridge — extension watch",
        )
        if bridge:
            spot_position = dict(spot_position)
            spot_position["bridge_band"] = bridge
            spot_position["in_bridge_band"] = bridge["low"] <= p <= bridge["high"]
    elif spot_position.get("state") == "at_or_below_ceiling":
        warnings.append(spot_position.get("detail") or "T1 ceiling reached — gaps through the window still count.")
    # Do not compress long zones: T1 is a ceiling. Narrowing the high recreates
    # "patient horizon has the shallowest band."

    # ── Structural invalidation (thesis-broken reference — not the displayed stop) ──
    tkey_lt = _norm_ticker_sym(inp.ticker)
    if tkey_lt in _STRUCTURAL_TAIL_ETFS:
        w52 = float(inp.week52_low) if inp.week52_low is not None else None
        fb = (w52 * 0.97) if w52 is not None else 0.0
        structural_stop = _r(
            structural_invalidation_below(
                float(inp.ma200) if inp.ma200 is not None else None,
                w52,
                fallback=fb,
            )
        )
        if tkey_lt in _COMMODITY_METAL_ETFS:
            inv_note = (
                "Commodity/metal ETF: structural floor ≈ max(MA200×0.97, 52w-low×0.97) — "
                "tracks structural risk, not the 52w tail alone."
            )
            inv_kind = "commodity_structural_floor"
        else:
            inv_note = (
                "Broad index ETF: structural floor ≈ max(MA200×0.97, 52w-low×0.97) — "
                "tracks structural risk, not the 52w tail alone."
            )
            inv_kind = "index_structural_floor"
    else:
        structural_stop = _r(inp.week52_low * 0.95)
        inv_note = (
            "Long-term floor ≈5% under the 52-week low — structural invalidation only, "
            "not a tight stop. Use nearer-term levels when you enter; treat this as a "
            "tail-stress / thesis-broken reference if price ever gets there."
        )
        inv_kind = "52w_stress_floor"

    tier_ref = active_tier or display_tier or tier1
    stop_loss, tactical_framing = _compute_long_tactical_stop(
        current_price=p,
        tier_ref=tier_ref,
        atr=inp.atr,
        structural_stop=structural_stop,
        entry_floor=entry_zone.low,
    )
    stop_loss_pct = _r((stop_loss - p) / p * 100, 1)
    target        = fv
    target_pct    = _r((fv - p) / p * 100, 1) if p > 0 else 0.0
    rr            = _rr_from_displayed_levels(p, stop_loss, target)

    if inp.regime_bull_pct < 40 and target_pct > 12:
        warnings.append(
            "Bear/transition-heavy HMM: +{:.1f}% upside to fair value from Tier 1 is a recovery scenario if conditions normalize — "
            "not a near-term base case while regime stays risk-off.".format(target_pct)
        )

    # ── Verdict ──────────────────────────────────────────────────────────
    if active_tier and assess_verdict in ("BUY", "PARTIAL"):
        if inp.regime_bull_pct >= 50 and inp.ml_prob >= 25:
            verdict, conviction = "BUY", ("High" if assess_verdict == "BUY" else "Medium")
        else:
            verdict, conviction = "WATCH", "Medium"
    elif assess_verdict == "BUY" and inp.ml_prob >= 40 and inp.regime_bull_pct >= 50:
        verdict, conviction = "BUY", "High"
    elif assess_verdict in ("BUY", "PARTIAL") and inp.ml_prob >= 25:
        verdict, conviction = "WATCH", "Medium"
    else:
        verdict, conviction = "WAIT", "Low"

    # ── Per-horizon 7-layer confidence boost ────────────────────────────
    if inp.horizon_confidence_pct is not None:
        hc = float(inp.horizon_confidence_pct)
        if verdict == "WAIT" and hc >= 58 and inp.ml_prob >= 25 and assess_verdict != "WAIT":
            verdict, conviction = "WATCH", "Medium"
        elif verdict == "WATCH" and hc >= 68:
            verdict, conviction = "BUY", "Medium"
        elif verdict == "BUY" and hc >= 75:
            conviction = "High"

    # When valuation alone says BUY/PARTIAL but this horizon's own overall verdict lands
    # lower (regime/ML/confidence didn't confirm), the House-panel label must say so
    # explicitly — otherwise "entry justified" reads as an unqualified green light sitting
    # right next to a WATCH/WAIT verdict, which looks like a flat contradiction rather than
    # "valuation is fine, the rest of the picture isn't yet" (same "one field, many surfaces"
    # class of gap action_title_by_mode already fixes for the verdict banner).
    if assess_verdict in ("BUY", "PARTIAL") and verdict != "BUY":
        assess_label += " (valuation only — overall verdict is {} until regime/ML/confidence confirm)".format(verdict)

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

    t1_ceiling = display_tier.high if display_tier.id == "T1" else tier1.high
    if active_tier:
        trigger = (
            "Price is in {label} (${low}–${high}) — scale per tier plan; "
            "full size when HMM Bull >= 60% and ML prob > 25%"
        ).format(
            label=display_tier.label.split("—")[0].strip() if "—" in display_tier.label else display_tier.id,
            low=display_tier.low,
            high=display_tier.high,
        )
    elif spot_position.get("below_all_within_mos") and assess_verdict in ("BUY", "PARTIAL"):
        # Takes priority over the generic "at_or_below_ceiling" copy below: a spot that's
        # off the bottom of the whole ladder but still within the full-size MOS ceiling
        # should say so explicitly, not just "T1 window gaps still count".
        trigger = (
            "Full MOS at spot (${:.2f} ≤ ${:.2f} full-size ceiling) — {} on valuation; "
            "scale tranches toward {} (≤ ${:.2f}) when timing/regime confirm"
        ).format(
            p,
            min_price_to_buy,
            "full size justified" if assess_verdict == "BUY" else "partial size OK",
            display_tier.id,
            display_tier.high,
        )
    elif spot_position.get("state") == "at_or_below_ceiling":
        trigger = (
            "Price ≤ ${ceiling:.2f} (T1 ceiling) — owner trigger is threshold-based; "
            "gaps through the T1 window still count. Scale at spot when HMM Bull >= 60% and ML prob > 25%"
        ).format(ceiling=t1_ceiling)
    else:
        if spot_position.get("state") == "between_tiers":
            floor_t = next((t for t in all_tiers if t.id == spot_position.get("floor_tier_id")), tier1)
            trigger = (
                "Hold at spot — no new long-term adds in the ${gap_lo:.2f}–${gap_hi:.2f} gap. "
                "Next add on pullback to {label} (≤ ${high:.2f}) when HMM Bull >= 60% and ML prob > 25%"
            ).format(
                gap_lo=spot_position.get("floor_band_high", floor_t.high),
                gap_hi=spot_position.get("ceiling_band_low", display_tier.low),
                label=floor_t.label.split("—")[0].strip() if "—" in floor_t.label else floor_t.id,
                high=floor_t.high,
            )
        else:
            trigger = (
                "Price ≤ ${ceiling:.2f} (T1 ceiling) "
                "AND HMM Bull >= 60% "
                "AND ML prob > 25%"
            ).format(ceiling=t1_ceiling)

    from signals.tranche_heuristic import compute_long_horizon_tier_percentages

    tranche_policy = compute_long_horizon_tier_percentages(
        current_price=float(p),
        ma200=float(inp.ma200) if inp.ma200 else None,
        atr=inp.atr,
        model_confidence_pct=inp.model_confidence_pct,
    )
    t1p = int(tranche_policy["t1_pct"])
    t2p = int(tranche_policy["t2_pct"])
    t3p = int(tranche_policy["t3_pct"])
    position_sizing = [
        {
            "tier": "T1 (MA200)",
            "allocation_pct": t1p,
            "note": "starter — MA200 zone (weight scales with extension vs MA200, vol, confidence)",
        },
        {
            "tier": "T2 ({:.0f}% MOS)".format(mos_t2),
            "allocation_pct": t2p,
            "note": "core — profile: {} (dynamic split)".format(t2_profile_note),
        },
        {
            "tier": "T3 (Tail risk)",
            "allocation_pct": t3p,
            "note": "stress sleeve — larger when front-load is reduced (extended / high vol)",
        },
    ]

    return HorizonSignal(
        label="Long-term", duration="6–18 months",
        verdict=verdict, signal=_ml_to_signal(inp.ml_prob), conviction=conviction,
        ml_prob=inp.ml_prob,
        entry_zone=entry_zone, target=target, target_pct=target_pct,
        stop_loss=stop_loss, stop_loss_pct=stop_loss_pct,
        risk_reward=rr, rationale=rationale, trigger_buy=trigger, warnings=warnings,
        fair_value=fv,
        stop_loss_kind="tactical_tier",
        stop_loss_framing=tactical_framing,
        entry_tiers={
            "active_tier_id": active_tier.id if active_tier else None,
            "target_tier_id": target_tid,
            "spot_position": spot_position,
            "current_assessment": {
                "verdict":              assess_verdict,
                "label":               assess_label,
                "color":               assess_color,
                "margin_of_safety_pct": mos_pct,
                "pct_above_ma200":     pct_above_ma200,
                "min_price_to_buy":    min_price_to_buy,
                **mos_ceiling_flags,
            },
            "tier2_profile": {
                "class": mos_class,
                "mos_pct": mos_t2,
                "label": t2_profile_note,
            },
            "structural_invalidation": {
                "price": structural_stop,
                "kind": inv_kind,
                "note": (
                    "≈5% below the 52-week low — thesis / tail-risk invalidation, "
                    "not a normal trailing stop. Manage risk at Tier 1 entries; "
                    "this level is a last-resort ‘broken story’ reference."
                )
                if inv_kind == "52w_stress_floor"
                else (
                    "Commodity/metal ETF: invalidation uses the tighter of MA200×0.97 vs 52w-low×0.97 — "
                    "full thesis exit if broken; not a day-to-day trailing stop."
                )
                if inv_kind == "commodity_structural_floor"
                else (
                    "Broad index ETF: invalidation uses the tighter of MA200×0.97 vs 52w-low×0.97 — "
                    "full thesis exit if broken; not a day-to-day trailing stop."
                ),
            },
            "tiers": [
                {
                    **asdict(tier1),
                    "levels": _tier_catch_levels(
                        tier1, fv, mos_pct, anchors=[("ma200", "MA200", inp.ma200 or 0.0)]
                    ),
                },
                {
                    **asdict(tier2),
                    "levels": _tier_catch_levels(tier2, fv, mos_pct),
                },
                {
                    **asdict(tier3),
                    "levels": _tier_catch_levels(tier3, fv, mos_pct),
                },
            ],
            "position_sizing": position_sizing,
            "tranche_policy": tranche_policy,
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
        **{k: v for k, v in kwargs.items() if k in ("forward_pe", "sector_forward_pe", "fcf_per_share", "analyst_target", "earnings_growth_pct", "guardrails")},
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
    ticker: str = "",
    tier2_mos_pct: Optional[float] = None,
    tier2_mos_by_class: Optional[Dict[str, Any]] = None,
    tier2_mos_pct_by_ticker: Optional[Dict[str, Any]] = None,
    model_confidence_pct: Optional[float] = None,
    # Per-horizon 7-layer fused confidence (0-100) — used to refine verdict/conviction per horizon
    st_confidence_pct: Optional[float] = None,
    mt_confidence_pct: Optional[float] = None,
    lt_confidence_pct: Optional[float] = None,
    fv_model_suppressed: bool = False,
    fv_street_anchor_usd: Optional[float] = None,
    fv_suppressed_reason: str = "",
    earnings_growth_pct: Optional[float] = None,
    analyst_target_high: Optional[float] = None,
    analyst_target_median: Optional[float] = None,
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
        fair_value=fair_value,
        horizon_confidence_pct=st_confidence_pct,
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
        short_entry_low=short.entry_zone.low,
        short_entry_high=short.entry_zone.high,
        fair_value=fair_value,
        horizon_confidence_pct=mt_confidence_pct,
    ))

    long_term = compute_long_term_entry(LongTermInputs(
        current_price=current_price,
        fair_value=fair_value,
        ma200=ma200,
        week52_low=week52_low,
        ml_prob=lt_ml_prob,
        regime_bull_pct=regime_bull_pct,
        fundamentals_score=fundamentals_score,
        ticker=ticker,
        tier2_mos_pct=tier2_mos_pct,
        tier2_mos_by_class=tier2_mos_by_class,
        tier2_mos_pct_by_ticker=tier2_mos_pct_by_ticker,
        short_entry_low=short.entry_zone.low,
        short_entry_high=short.entry_zone.high,
        medium_entry_high=medium.entry_zone.high,
        medium_entry_low=medium.entry_zone.low,
        atr=atr,
        model_confidence_pct=model_confidence_pct,
        horizon_confidence_pct=lt_confidence_pct,
        ma50=ma50,
        fv_model_suppressed=fv_model_suppressed,
        fv_street_anchor_usd=fv_street_anchor_usd,
        fv_suppressed_reason=fv_suppressed_reason,
    ))

    payload = {
        "short":  asdict(short),
        "medium": asdict(medium),
        "long":   asdict(long_term),
    }
    _harmonize_horizon_stop_framing(
        payload,
        current_price=current_price,
        ma50=ma50,
        ma200=ma200,
    )
    _enrich_horizon_entry_zone_extras(
        payload,
        current_price=current_price,
        vwap=vwap,
        support_level=support_level,
        ma50=ma50,
    )
    _flag_cross_horizon_invariants(payload)
    for key in ("short", "medium", "long"):
        refresh_horizon_rr_from_levels(payload.get(key) or {}, current_price)
    try:
        from signals.entry_band_touch import enrich_horizons_entry_touch

        if regime_bull_pct >= 60:
            _reg = "UP"
        elif regime_bull_pct <= 40:
            _reg = "DOWN"
        else:
            _reg = "NEUTRAL"
        enrich_horizons_entry_touch(
            payload,
            regime=_reg,
            current_price=current_price,
            atr=atr if atr and atr > 0 else current_price * 0.02,
        )
    except Exception:
        pass
    # Plan-quality gates last — need touch forecasts + painted levels in place.
    _apply_horizon_plan_invariants(
        payload,
        current_price=current_price,
        fair_value=fair_value,
        atr=atr if atr and atr > 0 else None,
        earnings_growth_pct=earnings_growth_pct,
        analyst_target_high=analyst_target_high,
        analyst_target_median=analyst_target_median,
    )
    for key in ("short", "medium", "long"):
        refresh_horizon_rr_from_levels(payload.get(key) or {}, current_price)
    return payload


def _harmonize_horizon_stop_framing(
    payload: dict[str, Any],
    *,
    current_price: float,
    ma50: float,
    ma200: float,
) -> None:
    """
    Attach explicit stop anchors so swing/build/thesis levels cannot be read as MA200
    when they are MA50/ATR-based. Clarify Tier 2 partial vs full-MOS ceiling.
    """
    short = payload.get("short") or {}
    medium = payload.get("medium") or {}
    long_h = payload.get("long") or {}
    if not short or not medium or not long_h:
        return

    t1_lo = _r(ma200 * (1 - LT_MA200_BAND_PCT / 100))
    t1_hi = _r(ma200 * (1 + LT_MA200_BAND_PCT / 100))
    ref = {
        "ma50": _r(ma50),
        "ma200": _r(ma200),
        "tier1_band": {"low": t1_lo, "high": t1_hi},
    }

    ez = short.get("entry_zone") or {}
    el, eh = ez.get("low"), ez.get("high")
    st_stop = short.get("stop_loss")
    if st_stop and el and eh:
        short["stop_loss_kind"] = "swing_atr"
        short["stop_loss_framing"] = (
            "Swing stop ${:.2f} — ATR below near-term entry (${:.2f}–${:.2f}), not MA200. "
            "Tier 1 MA200 zone is ${:.2f}–${:.2f} (MA200 ${:.2f})."
        ).format(float(st_stop), float(el), float(eh), t1_lo, t1_hi, ma200)

    mt_stop = medium.get("stop_loss")
    if mt_stop and ma50 > 0:
        medium["stop_loss_kind"] = "build_ma50"
        medium["stop_loss_framing"] = (
            "Build stop ${:.2f} — MA50×{:.2f} (MA50 ${:.2f}), pauses 1–3mo tranches. "
            "Not Tier 1 MA200 (${:.2f}–${:.2f})."
        ).format(
            float(mt_stop),
            1 - MT_STOP_BELOW_MA50_PCT / 100,
            ma50,
            t1_lo,
            t1_hi,
        )

    et = long_h.get("entry_tiers") or {}
    ca = dict(et.get("current_assessment") or {})
    min_buy = ca.get("min_price_to_buy")
    active_id = et.get("active_tier_id")
    ca["reference_levels"] = ref
    ca.setdefault(
        "full_size_ceiling_label",
        "Full-size ceiling (25% MOS to fair value)",
    )
    if min_buy and current_price > float(min_buy):
        ca["above_full_mos_ceiling"] = True
        ca["within_full_mos_ceiling"] = False
        ca.pop("full_size_eligible_at_spot", None)
        if active_id == "T2":
            ca["position_mode"] = "partial_only"
            msg = (
                "Inside Tier 2 band but above full-size ceiling ${:.2f} — "
                "partial position only; ceiling is for full allocation, not this tier band."
            ).format(float(min_buy))
            warnings = list(long_h.get("warnings") or [])
            if msg not in warnings:
                warnings.append(msg)
                long_h["warnings"] = warnings
    elif min_buy and current_price <= float(min_buy):
        ca["within_full_mos_ceiling"] = True
        ca["above_full_mos_ceiling"] = False
        if ca.get("verdict") == "BUY":
            ca["full_size_eligible_at_spot"] = True
            if ca.get("position_mode") not in ("partial_only", "hold_no_adds"):
                ca["position_mode"] = "full_size_ok"
        spot_pos = et.get("spot_position") or {}
        if spot_pos.get("below_all_within_mos"):
            detail = spot_pos.get("detail")
            if detail:
                warnings = list(long_h.get("warnings") or [])
                if detail not in warnings:
                    warnings.append(detail)
                    long_h["warnings"] = warnings
    elif active_id == "T2":
        ca["position_mode"] = "partial_only"
    et["current_assessment"] = ca
    et["reference_levels"] = ref
    long_h["entry_tiers"] = et
    payload["short"] = short
    payload["medium"] = medium
    payload["long"] = long_h


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
        ticker                  = "GOOGL",
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
