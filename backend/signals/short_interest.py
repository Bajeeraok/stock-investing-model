"""
short_interest.py — Short interest scoring from FINRA data via yfinance.

Yahoo Finance aggregates FINRA bi-weekly short interest reports and surfaces
the following fields through yfinance Ticker.info (no extra API key required):
  - shortPercentOfFloat  : short shares / float (e.g. 0.0523 = 5.23%)
  - shortRatio           : days to cover at avg daily volume
  - sharesShort          : absolute short position (shares)
  - sharesShortPriorMonth: prior period for trend direction

Why short interest matters in this model:
  1. Squeeze detection  — SI > 15% + positive momentum → potential short squeeze
     When our ML score turns bullish on a heavily shorted name, the cover pressure
     amplifies the move. The "Momentum Squeeze" scenario probability should be gated
     on actual SI, not a fixed adjustment.

  2. Smart-money bear signal — SI > 20% with NO bullish technical setup → risk factor.
     If sophisticated short sellers are heavily positioned against a stock AND our
     technicals are weak, that convergence warrants additional caution.

  3. Days-to-cover (DTC) — DTC > 5 means the position can't be unwound quickly.
     High DTC + rising price = forced covering amplifies upside. Low DTC = shorts
     can exit easily and the squeeze fizzles.

Interpretation thresholds (sourced from FINRA / academic literature):
  SI %    | DTC  | Classification     | Signal
  < 2%    | —    | Near-zero short    | No squeeze risk; remove from squeeze scenarios
  2–5%    | —    | Normal / low       | Typical market level; neutral
  5–10%   | <5   | Moderate           | Watch for momentum shifts
  10–15%  | 5–10 | Elevated           | Squeeze risk building; momentum confirmation needed
  15–25%  | >7   | High               | Active squeeze potential on catalyst
  > 25%   | >10  | Extreme / crowded  | Highest squeeze potential OR deep structural bear

Output format:
  short_pct       : float (0–1 scale, raw from FINRA)
  days_to_cover   : float
  short_ratio_label: str
  squeeze_risk    : str ("none" | "low" | "moderate" | "elevated" | "high" | "extreme")
  squeeze_score   : float 0–1 (1 = maximum squeeze potential when bullish catalyst present)
  bear_signal     : bool (True when extreme SI with no bullish confirmation)
  label           : str (human-readable summary)
  source          : str
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# Short interest % of float → squeeze risk tier
_SI_TIERS = [
    (0.02, "none",     0.00),
    (0.05, "low",      0.15),
    (0.10, "moderate", 0.35),
    (0.15, "elevated", 0.60),
    (0.25, "high",     0.80),
    (1.00, "extreme",  0.95),
]

_DTC_TIERS = [
    (3,  "quick exit possible"),
    (5,  "moderate cover time"),
    (10, "slow to unwind"),
    (99, "very slow — squeeze amplified"),
]


def _si_tier(si_pct: float) -> tuple[str, float]:
    """Return (risk_label, squeeze_score_base) for a given SI %."""
    for threshold, label, score in _SI_TIERS:
        if si_pct <= threshold:
            return label, score
    return "extreme", 0.95


def _dtc_label(dtc: float) -> str:
    for threshold, label in _DTC_TIERS:
        if dtc <= threshold:
            return label
    return "very slow — squeeze amplified"


def fetch_short_interest(ticker: str) -> dict | None:
    """
    Fetch short interest data for ticker via yfinance (sourced from FINRA).

    Returns None if data is unavailable or yfinance does not carry the ticker.

    Key return fields:
        short_pct       — short shares / float (0-1 scale)
        days_to_cover   — DTC at avg daily volume
        squeeze_risk    — "none" | "low" | "moderate" | "elevated" | "high" | "extreme"
        squeeze_score   — 0-1 (higher = more explosive if bullish catalyst hits)
        trend           — "increasing" | "decreasing" | "stable" | "unknown"
        label           — human-readable summary for UI
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker.upper()).info
        if not isinstance(info, dict) or not info:
            return None

        si_pct  = info.get("shortPercentOfFloat")    # e.g. 0.0523
        dtc     = info.get("shortRatio")             # days to cover
        shares_short      = info.get("sharesShort")
        shares_short_prior = info.get("sharesShortPriorMonth")
        float_shares      = info.get("floatShares")

        # Need at least SI% to be meaningful
        if si_pct is None:
            return None

        try:
            si_pct = float(si_pct)
        except (TypeError, ValueError):
            return None

        # Days to cover
        try:
            dtc = float(dtc) if dtc is not None else None
        except (TypeError, ValueError):
            dtc = None

        # Trend: compare current vs prior month
        trend = "unknown"
        if shares_short is not None and shares_short_prior is not None:
            try:
                s = float(shares_short)
                p = float(shares_short_prior)
                if p > 0:
                    chg = (s - p) / p
                    if chg > 0.05:
                        trend = "increasing"
                    elif chg < -0.05:
                        trend = "decreasing"
                    else:
                        trend = "stable"
            except (TypeError, ValueError):
                pass

        risk_label, squeeze_score_base = _si_tier(si_pct)

        # DTC amplifier: high DTC means shorts can't exit quickly → amplifies squeeze
        dtc_amp = 0.0
        if dtc is not None:
            if dtc >= 10:   dtc_amp = 0.10
            elif dtc >= 7:  dtc_amp = 0.07
            elif dtc >= 5:  dtc_amp = 0.04

        # Trend amplifier: rising short interest + high SI = building conviction
        trend_amp = 0.05 if trend == "increasing" and si_pct > 0.10 else 0.0

        squeeze_score = min(0.99, squeeze_score_base + dtc_amp + trend_amp)

        # Bear signal: very high SI with no squeeze setup → structural problem
        bear_signal = si_pct > 0.20 and trend == "increasing"

        # ── Human-readable label ────────────────────────────────────────────
        si_str   = f"{si_pct*100:.1f}%"
        dtc_str  = f"{dtc:.1f}d DTC" if dtc is not None else "DTC unknown"
        risk_str = risk_label.upper()

        if si_pct < 0.03:
            narrative = f"Short interest {si_str} — near-zero squeeze risk"
        elif si_pct < 0.10:
            narrative = f"Short interest {si_str} — moderate; squeeze needs strong catalyst"
        elif si_pct < 0.20:
            narrative = (
                f"Elevated short interest {si_str} ({dtc_str}) — "
                "active squeeze potential on positive catalyst"
            )
        else:
            narrative = (
                f"Extreme short interest {si_str} ({dtc_str}) — "
                f"{'rising short conviction, caution' if trend == 'increasing' else 'maximum squeeze coil if bulls gain control'}"
            )

        if trend != "unknown":
            narrative += f" · trend {trend}"

        return {
            "short_pct":         round(si_pct, 4),
            "short_pct_display": si_str,
            "days_to_cover":     round(dtc, 1) if dtc is not None else None,
            "dtc_label":         _dtc_label(dtc) if dtc is not None else None,
            "trend":             trend,
            "squeeze_risk":      risk_label,
            "squeeze_score":     round(squeeze_score, 3),
            "bear_signal":       bear_signal,
            "label":             narrative,
            "source":            "FINRA via yfinance",
        }

    except Exception as exc:
        logger.debug("Short interest fetch failed for %s: %s", ticker, exc)
        return None


def short_interest_risk_factors(si: dict | None) -> list[str]:
    """
    Generate risk factor strings from short interest data for the
    confidence engine risk_factors list.
    """
    if si is None:
        return []
    risks: list[str] = []
    si_pct = si.get("short_pct", 0)
    risk   = si.get("squeeze_risk", "none")
    trend  = si.get("trend", "unknown")
    dtc    = si.get("days_to_cover")

    if risk in ("elevated", "high", "extreme"):
        dtc_str = f", {dtc:.1f}d DTC" if dtc else ""
        risks.append(
            f"Short interest {si_pct*100:.1f}% of float ({risk}{dtc_str}) — "
            "squeeze potential exists if ML signal turns bullish"
        )
    if si.get("bear_signal"):
        risks.append(
            f"Rising institutional short conviction ({si_pct*100:.1f}% and increasing) — "
            "structural bet against the stock; treat as headwind until reversed"
        )
    if trend == "increasing" and si_pct > 0.08:
        risks.append(
            "Short interest trend increasing — smart-money positioning against; "
            "wait for trend reversal before building full position"
        )
    return risks


def squeeze_probability_adj(si: dict | None, ml_bullish: bool = False) -> float:
    """
    Return a probability adjustment (+/-) for the squeeze scenario based
    on actual short interest data.

    ml_bullish: True when LightGBM ML probability > 0.50 (positive catalyst alignment).
    Without ML confirmation, high SI is a headwind, not a tailwind.

    Returns:
        positive float → boost squeeze scenario probability (squeeze coiled, ML aligned)
        negative float → suppress squeeze scenario probability (low SI, no coil)
        0.0            → neutral (no data or mid-range)
    """
    if si is None:
        return 0.0   # no data → use default fixed adjustment

    si_pct = si.get("short_pct", 0)
    squeeze_score = si.get("squeeze_score", 0)

    if si_pct < 0.03:
        # Essentially no short interest — squeeze scenario is misleading
        return -0.18   # suppress significantly

    if si_pct < 0.05:
        return -0.08   # low SI → modest suppression

    # Mid range: return data-driven adjustment
    if ml_bullish:
        # ML confirms positive direction + high SI = real squeeze setup
        return round(squeeze_score * 0.30, 3)   # max +0.30 when extreme SI + ML bullish
    else:
        # High SI without ML confirmation → bears may be right
        if si_pct > 0.15:
            return -0.05   # slight caution
        return 0.0
