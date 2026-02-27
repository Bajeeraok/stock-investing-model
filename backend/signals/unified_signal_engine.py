"""
Unified Signal Engine — 3-layer confluence for Thrive Alpha.

Architecture:
  Layer 1: REGIME    — What environment are we in? (existing get_global_market_regime)
  Layer 2: PATTERN   — What is price structure saying? (new near_bottom_score)
  Layer 3: MOMENTUM  — Is the move starting / confirming? (RSI recovering + MACD turning)
           ↓
       CONFLUENCE     — Geometric signal agreement (0–1)
           ↓
       REGIME GATE    — Hard overrides (BEAR blocks STRONG BUY; BULL softens SELL)
           ↓
       ACTION + Kelly multiplier for position sizing

Design principle: layers GATE each other, not just average.
  - Regime is the map  → sets the maximum allowed conviction
  - Pattern is terrain  → identifies the entry setup
  - Momentum is green light → confirms the move has started

The engine does NOT replace composite_score / multi_horizon_scores.
It wraps them, adding pattern timing and hard regime gating.

Usage:
    engine = UnifiedSignalEngine(ticker, df, composite_score_value, market_regime, vix)
    result = engine.generate_signal()
    # result["action"], result["confluence"], result["confluence_kelly_mult"]
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from signals.pattern_signals import near_bottom_score, detect_regime


# ---------------------------------------------------------------------------
# Regime multiplier table (matches tier1_risk_engine.py for consistency)
# ---------------------------------------------------------------------------
_REGIME_MULT: dict[str, float] = {
    "STRONG_BULL": 1.0,
    "BULL":        1.0,
    "NEUTRAL":     0.60,
    "TRANSITION":  0.55,   # from detect_regime() TRANSITION state
    "BEAR":        0.30,
    "STRONG_BEAR": 0.10,
}

# Maximum action allowed per regime (hard gate)
_REGIME_MAX_ACTION: dict[str, str] = {
    "STRONG_BULL": "STRONG BUY",
    "BULL":        "STRONG BUY",
    "NEUTRAL":     "BUY",
    "TRANSITION":  "BUY",
    "BEAR":        "SPECULATIVE BUY",   # Counter-trend only, size down
    "STRONG_BEAR": "WATCH ONLY",
}

_ACTION_RANK: dict[str, int] = {
    "STRONG BUY":      4,
    "BUY":             3,
    "SPECULATIVE BUY": 2,
    "HOLD / WATCH":    1,
    "SELL / AVOID":    0,
    "WATCH ONLY":      0,
}


class UnifiedSignalEngine:
    """
    Three-layer signal confluence engine for Thrive Alpha.

    Parameters
    ----------
    ticker:          Asset symbol (used for sector-aware colour in output)
    df:              OHLCV DataFrame from fetch_ohlcv_dataframe() — needs close, ideally low/volume
    composite_score: 0-100 value from multi_horizon_scores()["composite_buy"]
    market_regime:   5-level global regime from get_global_market_regime()
    vix:             Current VIX level (None = ignored)
    rsi:             Latest RSI from composite_score output (None = recomputed)
    macd_hist:       Latest MACD histogram value (None = recomputed)
    """

    def __init__(
        self,
        ticker: str,
        df: pd.DataFrame,
        composite_score: float,
        market_regime: str = "NEUTRAL",
        vix: float | None = None,
        rsi: float | None = None,
        macd_hist: float | None = None,
    ) -> None:
        self.ticker          = ticker
        self.df              = df
        self.composite_score = float(composite_score)
        self.market_regime   = market_regime
        self.vix             = vix
        self._rsi_hint       = rsi
        self._macd_hint      = macd_hist

    # ── Public API ────────────────────────────────────────────────────────

    def generate_signal(self) -> dict:
        """
        Compute all three layers and return the confluence signal.

        Returns a dict with:
            regime, regime_multiplier
            pattern_score (0-100), pattern_signals
            momentum_score (0-1), momentum_signals
            confluence (0-1)
            raw_action (before gate), action (after regime gate)
            confluence_kelly_mult (0.5-1.5) — multiply into Kelly adjusted_fraction
            warning (str | None)
            narrative (list[str]) — human-readable conviction story
        """
        # Layer 1: Regime
        regime, regime_mult = self._get_regime()

        # Layer 2: Pattern — near-bottom detection
        p_score, p_signals, p_details = near_bottom_score(self.df, self.ticker)
        pattern_norm = p_score / 100.0

        # Layer 3: Momentum confirmation
        m_score, m_signals = self._get_momentum_confirmation()

        # Confluence = weighted combination (pattern is primary for timing)
        # Geometric mean of (pattern, composite) rewards agreement and punishes divergence
        tech_norm = self.composite_score / 100.0
        confluence = (
            pattern_norm * 0.40
            + tech_norm  * 0.35
            + m_score    * 0.25
        ) * regime_mult   # Regime dampens the entire confluence in bear markets

        confluence = round(float(np.clip(confluence, 0.0, 1.0)), 3)

        # Determine raw action from confluence
        raw_action = self._confluence_to_action(confluence)

        # Apply regime gate (hard cap on action)
        action, warning = apply_regime_gate(raw_action, regime, confluence)

        # Kelly multiplier: maps confluence 0-1 → 0.5-1.5×
        # Confluence < 0.33: reduce Kelly (low conviction)
        # Confluence 0.33-0.67: neutral (×1.0)
        # Confluence > 0.67: boost Kelly slightly (strong agreement)
        if confluence < 0.33:
            kelly_mult = 0.5 + confluence * 1.5      # 0.50 → 1.00
        elif confluence < 0.67:
            kelly_mult = 1.0
        else:
            kelly_mult = 1.0 + (confluence - 0.67) * 1.5  # 1.00 → 1.50
        kelly_mult = round(float(np.clip(kelly_mult, 0.25, 1.50)), 2)

        narrative = self._build_narrative(
            regime, confluence, action, p_signals, m_signals, p_score, warning
        )

        return {
            "ticker":                  self.ticker,
            "regime":                  regime,
            "regime_multiplier":       round(regime_mult, 2),
            "pattern_score":           round(p_score, 1),
            "pattern_signals":         p_signals,
            "pattern_details":         p_details,
            "momentum_score":          round(m_score, 3),
            "momentum_signals":        m_signals,
            "composite_score":         round(self.composite_score, 1),
            "confluence":              confluence,
            "raw_action":              raw_action,
            "action":                  action,
            "confluence_kelly_mult":   kelly_mult,
            "warning":                 warning,
            "narrative":               narrative,
        }

    # ── Layer implementations ──────────────────────────────────────────────

    def _get_regime(self) -> tuple[str, float]:
        """Map 5-level market_regime + df-derived MA regime to multiplier."""
        # Prefer the global market regime passed in (most authoritative)
        regime = self.market_regime or "NEUTRAL"
        mult   = _REGIME_MULT.get(regime, 0.60)

        # Also check local MA regime from the asset's own price series
        if self.df is not None and "close" in self.df.columns:
            local_regime = detect_regime(self.df)
            # If local says BEAR but global says BULL, be cautious → use lower mult
            if local_regime == "BEAR" and regime in ("BULL", "STRONG_BULL"):
                mult = min(mult, 0.55)

        return regime, mult

    def _get_momentum_confirmation(self) -> tuple[float, list[str]]:
        """
        Score 0-1: is momentum RECOVERING (not yet extended)?

        Best confirmation: RSI 30-55 AND rising, MACD histogram turning up.
        This specifically catches the early-recovery phase, not overbought continuation.
        """
        score   = 0.0
        signals: list[str] = []

        # RSI from hint or recompute
        rsi_val = self._rsi_hint
        if rsi_val is None and self.df is not None and "close" in self.df.columns:
            from signals.pattern_signals import _rsi as _compute_rsi
            rsi_s = _compute_rsi(self.df["close"], 14)
            rsi_val = float(rsi_s.iloc[-1]) if pd.notna(rsi_s.iloc[-1]) else None
            rsi_5ago = float(rsi_s.iloc[-6]) if len(rsi_s) >= 6 and pd.notna(rsi_s.iloc[-6]) else rsi_val
        else:
            rsi_5ago = None

        if rsi_val is not None:
            if 28 < rsi_val < 55:
                score += 0.5
                signals.append(f"RSI {rsi_val:.0f} recovering from oversold (not yet extended)")
            elif rsi_val <= 28:
                score += 0.35
                signals.append(f"RSI {rsi_val:.0f} extreme oversold (caution: can fall further)")
            # Bonus if rising
            if rsi_5ago is not None and rsi_val > rsi_5ago:
                score = min(score + 0.15, 0.65)
                signals.append("RSI trending up over last 5 bars")

        # MACD histogram from hint or recompute
        macd_h = self._macd_hint
        macd_h_3ago = None
        if macd_h is None and self.df is not None and "close" in self.df.columns and len(self.df) >= 35:
            from signals.pattern_signals import _macd_histogram
            hist = _macd_histogram(self.df["close"])
            if len(hist) >= 4:
                macd_h      = float(hist.iloc[-1]) if pd.notna(hist.iloc[-1]) else None
                macd_h_3ago = float(hist.iloc[-4]) if pd.notna(hist.iloc[-4]) else None

        if macd_h is not None:
            if macd_h_3ago is not None and macd_h > macd_h_3ago and macd_h < 0:
                score += 0.35
                signals.append("MACD histogram turning up from negative territory")
            elif macd_h_3ago is not None and macd_h > macd_h_3ago:
                score += 0.2
                signals.append("MACD histogram strengthening")

        return round(float(np.clip(score, 0, 1)), 3), signals

    @staticmethod
    def _confluence_to_action(confluence: float) -> str:
        if confluence >= 0.70:
            return "STRONG BUY"
        if confluence >= 0.50:
            return "BUY"
        if confluence >= 0.30:
            return "HOLD / WATCH"
        return "SELL / AVOID"

    @staticmethod
    def _build_narrative(
        regime: str,
        confluence: float,
        action: str,
        pattern_signals: list[str],
        momentum_signals: list[str],
        pattern_score: float,
        warning: str | None,
    ) -> list[str]:
        lines = []
        lines.append(f"Regime: {regime}  |  Confluence: {confluence*100:.0f}%  |  Signal: {action}")
        if pattern_signals:
            for s in pattern_signals:
                lines.append(f"✓ {s}")
        if momentum_signals:
            for s in momentum_signals:
                lines.append(f"✓ {s}")
        if not pattern_signals and not momentum_signals:
            lines.append("— No strong pattern or momentum confirmation detected")
        if warning:
            lines.append(f"⚠ {warning}")
        if pattern_score >= 70 and confluence >= 0.60:
            lines.append("★ High-probability reversal setup — confirm with fundamentals before sizing")
        return lines


# ---------------------------------------------------------------------------
# Regime gate (standalone, usable without the full engine)
# ---------------------------------------------------------------------------

def apply_regime_gate(
    action: str,
    regime: str,
    confluence: float,
) -> tuple[str, str | None]:
    """
    Apply hard regime overrides to the raw action signal.

    Rules:
      BEAR regime:        STRONG BUY → SPECULATIVE BUY (size -75%), warn
      STRONG_BEAR regime: anything bullish → WATCH ONLY
      BULL regime:        SELL/AVOID → TRIM/REDUCE (structure intact; partial exit only)

    Returns (gated_action, warning_message | None).
    """
    warning = None
    max_allowed = _REGIME_MAX_ACTION.get(regime, "BUY")

    if _ACTION_RANK.get(action, 0) > _ACTION_RANK.get(max_allowed, 0):
        original = action
        action   = max_allowed
        if regime in ("BEAR", "STRONG_BEAR"):
            warning = (
                f"Counter-trend setup in {regime} regime — "
                f"'{original}' downgraded to '{action}'. Size down aggressively (25% of normal Kelly)."
            )
        else:
            warning = f"Regime cap: '{original}' → '{action}' ({regime} limits max conviction)."

    # Bull softens SELL signals
    if regime in ("BULL", "STRONG_BULL") and action == "SELL / AVOID":
        action  = "TRIM / REDUCE"
        warning = "Bull regime intact — trim partial position rather than full exit."

    return action, warning


# ---------------------------------------------------------------------------
# Convenience: run full unified signal for a ticker from scratch
# ---------------------------------------------------------------------------

def run_unified_signal(
    ticker: str,
    period: str = "2y",
    composite_score: float | None = None,
    market_regime: str = "NEUTRAL",
    vix: float | None = None,
) -> dict:
    """
    Fetch data and run UnifiedSignalEngine in one call.
    Useful for scripting / API routes. If composite_score is None,
    it is computed from the close series via multi_horizon_scores().
    """
    from signals.fetcher import fetch_ohlcv_dataframe, fetch_ohlcv_safe
    from signals.indicators import multi_horizon_scores

    df = fetch_ohlcv_dataframe(ticker, period)
    if df is None:
        return {"error": f"Could not fetch OHLCV for {ticker}"}

    # Compute composite_score if not provided
    rsi_hint, macd_hint = None, None
    if composite_score is None:
        close = fetch_ohlcv_safe(ticker, period)
        if close is not None:
            sig = multi_horizon_scores(close, market_regime=market_regime, vix=vix)
            composite_score = float(sig.get("composite_buy") or 50)
            rsi_hint        = sig.get("rsi")
            macd_hint       = sig.get("macd_hist")
        else:
            composite_score = 50.0

    engine = UnifiedSignalEngine(
        ticker          = ticker,
        df              = df,
        composite_score = composite_score,
        market_regime   = market_regime,
        vix             = vix,
        rsi             = rsi_hint,
        macd_hist       = macd_hint,
    )
    return engine.generate_signal()
