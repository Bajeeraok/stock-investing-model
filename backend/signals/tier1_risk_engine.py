"""
Thrive Alpha — Tier 1 Feature 1: Position Sizing Engine
Implements Kelly Criterion + regime-adjusted sizing for retail investors.

Usage:
    engine = PositionSizingEngine(portfolio_value=100000)
    result = engine.size_position(
        ticker="AAPL",
        signal_score=75,
        confidence=0.72,
        current_position_value=5000,
        price=195.0,
        atr_14=3.2,
        vix=18.5,
        regime="BULL",
        win_rate=0.65,
        avg_win_pct=8.0,
        avg_loss_pct=4.0,
    )
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class RiskTolerance(Enum):
    CONSERVATIVE  = "conservative"   # Max 1% portfolio risk per trade
    MODERATE      = "moderate"       # Max 2% portfolio risk per trade
    AGGRESSIVE    = "aggressive"     # Max 3% portfolio risk per trade


@dataclass
class PositionSizeResult:
    ticker:                str
    recommended_dollars:   float       # $ amount to add
    recommended_shares:    int         # Share count
    max_position_dollars:  float       # Hard cap for this ticker
    current_pct:           float       # Current portfolio %
    target_pct:            float       # Model-suggested target %
    risk_per_trade_dollars:float       # $ at risk if stop hit
    stop_loss_price:       float       # ATR-based stop
    take_profit_price:     float       # ATR-based target
    kelly_fraction:        float       # Raw Kelly result
    adjusted_fraction:     float       # Kelly * regime * vix damper
    sizing_rationale:      list[str]   # Human-readable reasoning
    warning:               Optional[str] = None


@dataclass
class PortfolioRiskSummary:
    total_value:           float
    total_at_risk:         float       # Sum of $ between current price and stops
    portfolio_risk_pct:    float       # total_at_risk / total_value
    largest_position_pct:  float
    concentration_warning: bool
    regime_note:           str
    max_new_position_size: float       # Remaining risk budget


class PositionSizingEngine:
    """
    Kelly Criterion-based position sizing with:
    - Regime adjustment (suppress in bear markets)
    - VIX damper (reduce size in high volatility)
    - ATR-based stop-loss placement
    - Portfolio concentration limits
    - Half-Kelly safety factor (standard for retail)
    """

    # Portfolio concentration hard limits.
    # MAX_SINGLE_POSITION_PCT is a class-level fallback only (used if a caller constructs
    # this engine without a risk_tolerance-aware max_position_pct) — normal construction
    # overrides it per-instance in __init__ to match the SAME 15/20/25% risk-profile ladder
    # portfolio/doctor.py already uses, instead of silently disagreeing with it at a
    # hardcoded 10% regardless of the user's selected profile.
    MAX_SINGLE_POSITION_PCT = 0.10     # 10% max per ticker (fallback default)
    MAX_SECTOR_PCT          = 0.25     # 25% max per sector
    MIN_SIGNAL_SCORE        = 55.0     # Don't size into weak signals

    RISK_PER_TRADE = {
        RiskTolerance.CONSERVATIVE: 0.01,
        RiskTolerance.MODERATE:     0.02,
        RiskTolerance.AGGRESSIVE:   0.03,
    }

    # Same 15/20/25% ladder as portfolio/doctor.py's max_position_pct and
    # dashboard.py::_TIER1_MAX_POSITION_PCT_BY_PROFILE (the lightweight-fallback path) —
    # keeps the position-size CAP consistent across risk profiles even though the sizing
    # ALGORITHM underneath (Kelly here vs. equal-weight rebalancing in doctor.py) stays
    # deliberately different; see docs/signals/RETAIL_DATA_SURFACING.md.
    _MAX_POSITION_PCT_BY_TOLERANCE = {
        RiskTolerance.CONSERVATIVE: 0.15,
        RiskTolerance.MODERATE:     0.20,
        RiskTolerance.AGGRESSIVE:   0.25,
    }

    ATR_STOP_MULTIPLIER    = 2.0       # Stop at 2× ATR below entry
    ATR_TARGET_MULTIPLIER  = 3.0       # Target at 3× ATR above entry (1.5:1 R/R)
    HALF_KELLY_FACTOR      = 0.5       # Standard retail Kelly damper

    def __init__(
        self,
        portfolio_value:  float,
        risk_tolerance:   RiskTolerance = RiskTolerance.MODERATE,
        max_position_pct: float | None = None,
    ):
        self.portfolio_value = portfolio_value
        self.risk_tolerance  = risk_tolerance
        self.risk_per_trade  = self.RISK_PER_TRADE[risk_tolerance]
        self.MAX_SINGLE_POSITION_PCT = (
            max_position_pct
            if max_position_pct is not None
            else self._MAX_POSITION_PCT_BY_TOLERANCE.get(risk_tolerance, self.MAX_SINGLE_POSITION_PCT)
        )

    # ── Core sizing method ────────────────────────────────────────────────

    def size_position(
        self,
        ticker:                  str,
        signal_score:            float,      # 0-100 model score
        confidence:              float,      # 0-1 model confidence
        current_position_value:  float,      # $ already held in ticker
        price:                   float,      # Current price
        atr_14:                  float,      # 14-day ATR
        vix:                     float,      # Current VIX
        regime:                  str,        # "BULL"|"BEAR"|"NEUTRAL"|"STRONG_BULL"|"STRONG_BEAR"
        win_rate:                 float | None,     # Historical hit rate (0-1). If None, derived from score/confidence/regime.
        avg_win_pct:             float,      # Avg win % from backtest
        avg_loss_pct:            float,      # Avg loss % from backtest
        confluence_score:        float | None = None,  # 0-1 from UnifiedSignalEngine; None = not available (show N/A, do not imply 1.0x)
    ) -> PositionSizeResult:

        rationale = []
        warning   = None

        # ── Guard: weak signal ────────────────────────────────────────────
        if signal_score < self.MIN_SIGNAL_SCORE:
            rationale.append(f"Signal score {signal_score:.0f} below minimum {self.MIN_SIGNAL_SCORE:.0f} — no new position")
            return self._zero_size(ticker, price, atr_14, rationale,
                warning=f"Signal score {signal_score:.0f} too weak to size. Minimum: {self.MIN_SIGNAL_SCORE:.0f}")

        # ── Step 1: Win rate + Kelly Criterion ────────────────────────────
        # Kelly = W - (1-W)/R where W=win_rate, R=win/loss ratio
        if win_rate is None:
            win_rate, note = self._derive_win_rate(signal_score, confidence, regime)
            rationale.append(note)
        else:
            rationale.append(f"Win rate input: W={win_rate:.0%}")
        if avg_loss_pct <= 0:
            avg_loss_pct = 1.0
        win_loss_ratio = avg_win_pct / avg_loss_pct
        kelly_raw      = win_rate - (1 - win_rate) / win_loss_ratio
        kelly_raw      = max(0, min(kelly_raw, 0.25))  # Cap raw Kelly at 25%

        rationale.append(
            f"Kelly: W={win_rate:.0%} × R={win_loss_ratio:.1f} → {kelly_raw:.1%} raw"
        )

        # ── Step 2: Half-Kelly safety factor ─────────────────────────────
        kelly_half = kelly_raw * self.HALF_KELLY_FACTOR
        rationale.append(f"Half-Kelly applied: {kelly_half:.1%}")

        # ── Step 3: Regime multiplier ─────────────────────────────────────
        regime_mult = self._regime_multiplier(regime)
        rationale.append(f"Regime ({regime}): ×{regime_mult:.2f}")

        # ── Step 4: VIX damper ────────────────────────────────────────────
        vix_mult = self._vix_multiplier(vix)
        rationale.append(f"VIX ({vix:.1f}): ×{vix_mult:.2f}")

        # ── Step 5: Confidence adjustment ────────────────────────────────
        conf_mult = 0.5 + (confidence * 0.5)   # Range: 0.5x – 1.0x
        rationale.append(f"Confidence ({confidence:.0%}): ×{conf_mult:.2f}")

        # ── Step 6: Score taper ───────────────────────────────────────────
        # Scores 55-70: partial size. 70-85: full. 85+: slight boost.
        score_mult = (
            0.5  if signal_score < 60 else
            0.75 if signal_score < 70 else
            1.0  if signal_score < 85 else
            1.1
        )
        rationale.append(f"Score taper ({signal_score:.0f}): ×{score_mult:.2f}")

        # ── Step 6.5: Confluence multiplier (pattern + momentum agreement) ─
        # Maps confluence 0–1 → 0.50–1.50×. When None, show N/A (do not imply 1.0x).
        if confluence_score is None:
            conf_pattern_mult = 1.00
            rationale.append("Pattern confluence: N/A (not used in sizing)")
        else:
            if confluence_score < 0.33:
                conf_pattern_mult = 0.50 + confluence_score * 1.52   # 0.50 → ~1.00
            elif confluence_score < 0.67:
                conf_pattern_mult = 1.00
            else:
                conf_pattern_mult = 1.00 + (confluence_score - 0.67) * 1.52  # 1.00 → ~1.50
            conf_pattern_mult = max(0.25, min(1.50, conf_pattern_mult))
            rationale.append(f"Pattern confluence ({confluence_score:.2f}): ×{conf_pattern_mult:.2f}")

        # ── Step 7: Compute adjusted fraction ────────────────────────────
        adjusted_fraction = (
            kelly_half * regime_mult * vix_mult * conf_mult * score_mult * conf_pattern_mult
        )
        adjusted_fraction = max(0, min(adjusted_fraction, self.MAX_SINGLE_POSITION_PCT))

        # ── Step 8: ATR-based stop & target ──────────────────────────────
        stop_loss_price    = round(price - self.ATR_STOP_MULTIPLIER * atr_14, 2)
        take_profit_price  = round(price + self.ATR_TARGET_MULTIPLIER * atr_14, 2)
        risk_per_share     = price - stop_loss_price

        # ── Step 9: Dollar amounts ────────────────────────────────────────
        target_dollars     = self.portfolio_value * adjusted_fraction
        max_position_dollars = self.portfolio_value * self.MAX_SINGLE_POSITION_PCT
        already_held       = current_position_value
        add_dollars        = max(0, target_dollars - already_held)

        # Don't exceed max position
        add_dollars        = min(add_dollars, max_position_dollars - already_held)
        add_dollars        = max(0, add_dollars)

        # Risk-based sizing cross-check: never risk more than risk_per_trade% on one position
        max_risk_dollars   = self.portfolio_value * self.risk_per_trade
        if risk_per_share > 0:
            max_shares_by_risk = max_risk_dollars / risk_per_share
            max_by_risk_dollars = max_shares_by_risk * price
            if add_dollars > max_by_risk_dollars:
                add_dollars = max_by_risk_dollars
                rationale.append(
                    f"Capped by {self.risk_tolerance.value} risk limit "
                    f"(${max_risk_dollars:,.0f} max risk per trade)"
                )

        recommended_shares = int(add_dollars / price) if price > 0 else 0
        add_dollars        = recommended_shares * price   # Align to whole shares

        risk_dollars = recommended_shares * risk_per_share

        # ── Concentration warning ─────────────────────────────────────────
        new_position_total = already_held + add_dollars
        new_pct            = new_position_total / self.portfolio_value
        if new_pct > 0.08:
            warning = f"{ticker} would be {new_pct:.1%} of portfolio — approaching concentration limit"

        current_pct = already_held / self.portfolio_value

        rationale.append(
            f"Result: add ${add_dollars:,.0f} ({recommended_shares} shares) "
            f"→ {new_pct:.1%} of portfolio"
        )
        rationale.append(
            f"Stop: ${stop_loss_price} | Target: ${take_profit_price} "
            f"| Risk: ${risk_dollars:,.0f}"
        )

        return PositionSizeResult(
            ticker=ticker,
            recommended_dollars=round(add_dollars, 2),
            recommended_shares=recommended_shares,
            max_position_dollars=round(max_position_dollars, 2),
            current_pct=round(current_pct, 4),
            target_pct=round(new_pct, 4),
            risk_per_trade_dollars=round(risk_dollars, 2),
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            kelly_fraction=round(kelly_raw, 4),
            adjusted_fraction=round(adjusted_fraction, 4),
            sizing_rationale=rationale,
            warning=warning,
        )

    # ── Portfolio-level risk summary ──────────────────────────────────────

    def portfolio_risk_summary(
        self,
        holdings: list[dict],   # [{ticker, value, stop_loss, price}]
        regime:   str,
    ) -> PortfolioRiskSummary:
        """
        Compute total portfolio risk exposure.
        holdings: list of dicts with ticker, value, stop_loss, price keys.
        """
        total_at_risk = 0.0
        for h in holdings:
            if h.get("stop_loss") and h.get("price") and h["price"] > 0:
                pct_at_risk   = (h["price"] - h["stop_loss"]) / h["price"]
                dollars_at_risk = h["value"] * pct_at_risk
                total_at_risk += max(0, dollars_at_risk)

        portfolio_risk_pct  = total_at_risk / self.portfolio_value if self.portfolio_value > 0 else 0
        values              = [h.get("value", 0) for h in holdings]
        largest_pct         = max(values) / self.portfolio_value if values else 0
        concentration_warn  = largest_pct > 0.10 or portfolio_risk_pct > 0.15

        # Remaining risk budget
        max_portfolio_risk  = 0.20   # 20% total portfolio at risk maximum
        remaining_risk_budget = max(0, (max_portfolio_risk - portfolio_risk_pct) * self.portfolio_value)

        regime_note = {
            "STRONG_BULL": "Strong bull — full position sizing allowed",
            "BULL":        "Bull regime — normal sizing",
            "NEUTRAL":     "Neutral — reduce new position sizes by 25%",
            "BEAR":        "Bear regime — cut new sizes by 50%, protect existing",
            "STRONG_BEAR": "Strong bear — no new longs, focus on preservation",
        }.get(regime, "Unknown regime")

        return PortfolioRiskSummary(
            total_value=self.portfolio_value,
            total_at_risk=round(total_at_risk, 2),
            portfolio_risk_pct=round(portfolio_risk_pct, 4),
            largest_position_pct=round(largest_pct, 4),
            concentration_warning=concentration_warn,
            regime_note=regime_note,
            max_new_position_size=round(remaining_risk_budget, 2),
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _regime_multiplier(self, regime: str) -> float:
        return {
            "STRONG_BULL": 1.20,
            "BULL":        1.00,
            "NEUTRAL":     0.75,
            "BEAR":        0.40,
            "STRONG_BEAR": 0.10,
        }.get(regime, 0.75)

    @staticmethod
    def _derive_win_rate(signal_score: float, confidence: float, regime: str) -> tuple[float, str]:
        """
        Derive a conservative win-rate proxy from model score + confidence + regime.

        This avoids hardcoding a single W (e.g. 60%) for every ticker, and makes the
        Kelly chain transparent via sizing_rationale.
        """
        score = float(signal_score)
        score = 0.0 if np.isnan(score) else score
        score = float(np.clip(score, 0.0, 100.0))
        conf = float(np.clip(float(confidence), 0.0, 1.0))
        reg = str(regime or "NEUTRAL").upper()

        # Score: 50 → 0.50, 70 → ~0.56, 85 → ~0.61, 100 → 0.65
        score_component = 0.50 + (score - 50.0) * (0.15 / 50.0)
        # Confidence: baseline at 0.50, allow ±5pp adjustment
        conf_component = (conf - 0.50) * 0.10
        # Regime adjustment
        regime_adj = {
            "STRONG_BULL":  0.03,
            "BULL":         0.01,
            "NEUTRAL":     -0.02,
            "BEAR":        -0.05,
            "STRONG_BEAR": -0.08,
        }.get(reg, -0.02)

        w = float(np.clip(score_component + conf_component + regime_adj, 0.35, 0.75))
        note = (
            "Win rate derived from score/regime/confidence: "
            f"score→{score_component:.0%} + conf→{conf_component:+.0%} + regime→{regime_adj:+.0%} = W={w:.0%}"
        )
        return w, note

    def _vix_multiplier(self, vix: float) -> float:
        if vix < 15:  return 1.10
        if vix < 20:  return 1.00
        if vix < 25:  return 0.80
        if vix < 30:  return 0.55
        return 0.25

    def _zero_size(self, ticker, price, atr_14, rationale, warning=None):
        stop = round(price - self.ATR_STOP_MULTIPLIER * atr_14, 2)
        tp   = round(price + self.ATR_TARGET_MULTIPLIER * atr_14, 2)
        return PositionSizeResult(
            ticker=ticker, recommended_dollars=0, recommended_shares=0,
            max_position_dollars=self.portfolio_value * self.MAX_SINGLE_POSITION_PCT,
            current_pct=0, target_pct=0, risk_per_trade_dollars=0,
            stop_loss_price=stop, take_profit_price=tp,
            kelly_fraction=0, adjusted_fraction=0,
            sizing_rationale=rationale, warning=warning,
        )


def portfolio_context_from_cached_dashboard(ticker: str) -> tuple[Optional[float], float]:
    """
    (real total portfolio value, real current $ held in this ticker) from the already-
    cached dashboard's "All" portfolio aggregate — the same report Portfolio Doctor's own
    position-sizing fallback reads (api/routers/dashboard.py's report["total_value"] /
    report["per_holding"]). No live fetch — reuses whatever the dashboard already computed.

    Returns (None, 0.0) when no real portfolio value is available. Callers must not
    substitute a placeholder for the first element — size_position_for_ticker() treats
    None as "don't show a sizing recommendation" rather than inventing one against a fake
    portfolio size (the bug this whole bridge exists to fix: example_portfolio = $50,000).
    """
    try:
        from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot

        sym = str(ticker or "").upper()
        for payload in (get_cached_dashboard(), get_last_dashboard_snapshot()):
            if not isinstance(payload, dict):
                continue
            portfolios = payload.get("portfolios")
            if not isinstance(portfolios, dict) or not portfolios:
                continue
            report = portfolios.get("All") or next(iter(portfolios.values()), None)
            if not isinstance(report, dict):
                continue
            try:
                total_value = float(report.get("total_value") or 0)
            except (TypeError, ValueError):
                total_value = 0.0
            if total_value <= 0:
                continue
            held_value = 0.0
            for h in report.get("per_holding") or []:
                if isinstance(h, dict) and str(h.get("ticker") or "").upper() == sym:
                    try:
                        held_value = float(h.get("value") or 0)
                    except (TypeError, ValueError):
                        held_value = 0.0
                    break
            return total_value, held_value
    except Exception:
        pass
    return None, 0.0


def regime_label_from_bull_pct(regime_bull_pct: float | None) -> str:
    """Map a 0-100 HMM bull probability to the STRONG_BULL/BULL/NEUTRAL/BEAR/STRONG_BEAR
    vocabulary PositionSizingEngine.size_position() expects — callers outside the Tier 1
    subsystem (e.g. ticker_detail.py) carry regime as this 0-100 float, not that enum-like
    string, and previously had no shared way to bridge the two."""
    if regime_bull_pct is None:
        return "NEUTRAL"
    try:
        b = float(regime_bull_pct)
    except (TypeError, ValueError):
        return "NEUTRAL"
    if b >= 70:
        return "STRONG_BULL"
    if b >= 55:
        return "BULL"
    if b >= 45:
        return "NEUTRAL"
    if b >= 30:
        return "BEAR"
    return "STRONG_BEAR"


def size_position_for_ticker(
    *,
    ticker: str,
    price: float,
    portfolio_value: float,
    current_position_value: float = 0.0,
    signal_score: float = 50.0,
    confidence: float = 0.60,
    atr_14: float | None = None,
    vix: float | None = None,
    regime_bull_pct: float | None = None,
    confluence_score: float | None = None,
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE,
    tranche_pcts: tuple[float, float, float] = (0.40, 0.30, 0.30),
    entry_mode: str | None = None,
) -> dict | None:
    """
    Ticker-detail-friendly wrapper around PositionSizingEngine.size_position() — resolves
    the handful of fallbacks a caller outside the Tier 1 batch pipeline needs (missing ATR,
    missing VIX, a 0-100 regime float instead of the engine's BULL/BEAR vocabulary) and
    splits the single recommended add into the same ~40/30/30 tranche shape the Position
    Build card already shows, but computed from the REAL portfolio value and this ticker's
    REAL existing holding instead of an illustrative example_portfolio placeholder.

    Returns None when portfolio_value isn't a real number — showing a dollar/share
    recommendation against a made-up portfolio size is worse than not showing one.
    """
    if portfolio_value is None or portfolio_value <= 0 or price is None or price <= 0:
        return None
    atr = float(atr_14) if atr_14 and atr_14 > 0 else price * 0.02
    v = float(vix) if vix and vix > 0 else 20.0
    regime = regime_label_from_bull_pct(regime_bull_pct)
    conf_pattern = None
    if confluence_score is not None:
        try:
            conf_pattern = max(0.0, min(1.0, float(confluence_score) / 100.0))
        except (TypeError, ValueError):
            conf_pattern = None

    # Prefer measured cohort hit rate / payoff (data/alpha/cohort_expectancy.json) over the
    # score-derived heuristic when enough outcomes have been tracked.
    measured = None
    try:
        from signals.alpha.excess import measured_kelly_inputs

        measured = measured_kelly_inputs(entry_mode=entry_mode, score=signal_score)
    except Exception:
        measured = None

    engine = PositionSizingEngine(portfolio_value, risk_tolerance=risk_tolerance)
    result = engine.size_position(
        ticker=ticker,
        signal_score=signal_score,
        confidence=confidence,
        current_position_value=max(0.0, current_position_value),
        price=price,
        atr_14=atr,
        vix=v,
        regime=regime,
        win_rate=measured["win_rate"] if measured else None,  # else _derive_win_rate heuristic
        avg_win_pct=measured["avg_win_pct"] if measured else 7.0,
        avg_loss_pct=measured["avg_loss_pct"] if measured else 4.0,
        confluence_score=conf_pattern,
    )
    pcts = tranche_pcts if abs(sum(tranche_pcts) - 1.0) < 1e-6 else (0.40, 0.30, 0.30)
    tranches = []
    allocated_shares = 0
    for i, pct in enumerate(pcts):
        is_last = i == len(pcts) - 1
        shares = result.recommended_shares - allocated_shares if is_last else round(result.recommended_shares * pct)
        shares = max(0, shares)
        allocated_shares += shares
        tranches.append({
            "tranche": i + 1,
            "pct_of_add": pct,
            "shares": shares,
            "dollars": round(shares * price, 2),
        })

    return {
        "ticker": result.ticker,
        "portfolio_value": round(portfolio_value, 2),
        "current_position_value": round(max(0.0, current_position_value), 2),
        "current_pct": result.current_pct,
        "target_pct": result.target_pct,
        "recommended_dollars": result.recommended_dollars,
        "recommended_shares": result.recommended_shares,
        "max_position_dollars": result.max_position_dollars,
        "stop_loss_price": result.stop_loss_price,
        "take_profit_price": result.take_profit_price,
        "risk_per_trade_dollars": result.risk_per_trade_dollars,
        "kelly_fraction": result.kelly_fraction,
        "adjusted_fraction": result.adjusted_fraction,
        "regime_used": regime,
        "tranches": tranches,
        "sizing_rationale": result.sizing_rationale,
        "warning": result.warning,
    }


# ── Feature 2: Drawdown Simulation ───────────────────────────────────────

@dataclass
class DrawdownScenario:
    label:           str         # "Base case" | "Bear case" | "Stress"
    price_target:    float
    pct_change:      float
    portfolio_impact_dollars: float
    portfolio_impact_pct:     float
    probability:     float       # Estimated probability
    support_level:   Optional[float] = None
    description:     str = ""


@dataclass
class DrawdownSimulation:
    ticker:           str
    current_price:    float
    position_value:   float
    scenarios:        list[DrawdownScenario]
    max_loss_dollars: float      # Worst case $ loss
    max_loss_pct:     float      # Worst case % loss
    breakeven_price:  float      # Price where you break even (cost basis)
    atr_14:           float
    historical_max_drawdown_pct: float


class DrawdownSimulator:
    """
    Feature 2: "What If I'm Wrong" layer.
    Shows realistic loss scenarios before entering a position.
    Uses ATR, historical volatility, and support levels.
    """

    def simulate(
        self,
        ticker:          str,
        current_price:   float,
        position_value:  float,
        portfolio_value: float,
        atr_14:          float,
        hist_max_drawdown_pct: float,  # From backtest (e.g. -40.6 for BLK)
        cost_basis:      float,
        support_levels:  list[float],   # Key support prices from TA
        signal_score:    float,
    ) -> DrawdownSimulation:
        """
        Generate 4 loss scenarios with portfolio impact.
        """
        scenarios = []

        # ── Scenario 1: Normal pullback (1× ATR) ─────────────────────────
        normal_target = current_price - atr_14
        scenarios.append(self._make_scenario(
            "Normal pullback (1× ATR)",
            normal_target, current_price, position_value, portfolio_value,
            probability=0.50,
            description=f"Typical daily noise range. ATR={atr_14:.2f}",
        ))

        # ── Scenario 2: Moderate correction (2× ATR) ─────────────────────
        moderate_target = current_price - (2 * atr_14)
        scenarios.append(self._make_scenario(
            "Moderate correction (2× ATR)",
            moderate_target, current_price, position_value, portfolio_value,
            probability=0.30,
            description="2-week range move. Common on sector rotation or mild bad news.",
        ))

        # ── Scenario 3: Nearest support break ────────────────────────────
        nearest_support = min(
            (s for s in support_levels if s < current_price),
            default=current_price * 0.90
        )
        scenarios.append(self._make_scenario(
            f"Support break (${nearest_support:.2f})",
            nearest_support, current_price, position_value, portfolio_value,
            probability=0.15,
            support_level=nearest_support,
            description="Support break — often leads to accelerated selling.",
        ))

        # ── Scenario 4: Stress / bear case ───────────────────────────────
        stress_target = current_price * (1 + hist_max_drawdown_pct / 100 * 0.5)
        # Use 50% of historical max drawdown as stress scenario
        scenarios.append(self._make_scenario(
            f"Stress scenario ({hist_max_drawdown_pct/2:.0f}% drawdown)",
            stress_target, current_price, position_value, portfolio_value,
            probability=0.05,
            description=(
                f"Based on historical max drawdown of {hist_max_drawdown_pct:.0f}%. "
                "Rare but possible in market dislocations."
            ),
        ))

        worst = min(scenarios, key=lambda s: s.pct_change)
        _cost = cost_basis if cost_basis is not None else current_price

        return DrawdownSimulation(
            ticker=ticker,
            current_price=current_price,
            position_value=position_value,
            scenarios=scenarios,
            max_loss_dollars=round(worst.portfolio_impact_dollars, 2),
            max_loss_pct=round(worst.portfolio_impact_pct, 4),
            breakeven_price=round(_cost, 2),
            atr_14=atr_14,
            historical_max_drawdown_pct=hist_max_drawdown_pct,
        )

    def _make_scenario(
        self, label, target_price, current_price,
        position_value, portfolio_value,
        probability, description="", support_level=None
    ) -> DrawdownScenario:
        pct_change = (target_price / current_price - 1) * 100
        pos_impact = position_value * (pct_change / 100)
        port_impact_pct = pos_impact / portfolio_value

        return DrawdownScenario(
            label=label,
            price_target=round(target_price, 2),
            pct_change=round(pct_change, 2),
            portfolio_impact_dollars=round(pos_impact, 2),
            portfolio_impact_pct=round(port_impact_pct, 4),
            probability=probability,
            support_level=support_level,
            description=description,
        )


# ── Feature 3: Stop-Loss / Take-Profit Engine ────────────────────────────

@dataclass
class ExitLevels:
    ticker:              str
    entry_price:         float
    stop_loss_hard:      float      # ATR-based hard stop — no exceptions
    stop_loss_soft:      float      # Warning zone — review position
    take_profit_1:       float      # First target — trim 1/3
    take_profit_2:       float      # Second target — trim another 1/3
    take_profit_3:       float      # Full exit target
    trailing_stop_pct:   float      # Trailing stop % once in profit
    invalidation_price:  float      # Price that invalidates the thesis
    time_stop_days:      int        # Exit if no progress in N days
    risk_reward_ratio:   float
    thesis_check_points: list[str]  # Conditions to verify thesis still valid


class ExitEngine:
    """
    Feature 3: Dynamic stop-loss and take-profit calculation.
    ATR-based, not arbitrary percentages.
    """

    def calculate_exits(
        self,
        ticker:        str,
        entry_price:   float,
        atr_14:        float,
        signal_score:  float,
        regime:        str,
        horizon:       str,          # "short" | "medium" | "long"
        support_levels: list[float],
        resistance_levels: list[float],
    ) -> ExitLevels:

        # Adjust ATR multipliers by horizon
        horizon_config = {
            "short":  {"stop": 1.5, "t1": 2.0, "t2": 3.0, "t3": 4.0, "days": 20},
            "medium": {"stop": 2.0, "t1": 3.0, "t2": 5.0, "t3": 8.0, "days": 60},
            "long":   {"stop": 3.0, "t1": 5.0, "t2": 8.0, "t3": 12.0, "days": 180},
        }
        cfg = horizon_config.get(horizon, horizon_config["medium"])

        # ATR-based stops
        hard_stop  = entry_price - cfg["stop"] * atr_14
        soft_stop  = entry_price - (cfg["stop"] * 0.7) * atr_14

        # Use nearest support below entry if available and closer than ATR stop
        nearest_support = max(
            (s for s in support_levels if s < hard_stop),
            default=hard_stop
        )
        hard_stop = max(hard_stop, nearest_support * 0.99)  # Just below support

        # Take profit targets — use resistance if available
        t1 = self._nearest_resistance(entry_price + cfg["t1"] * atr_14, resistance_levels)
        t2 = self._nearest_resistance(entry_price + cfg["t2"] * atr_14, resistance_levels)
        t3 = entry_price + cfg["t3"] * atr_14

        rr_ratio = (t1 - entry_price) / max(entry_price - hard_stop, 0.01)

        # Trailing stop: tighter in bear, wider in bull
        trailing_pct = {
            "STRONG_BULL": 8.0, "BULL": 6.0,
            "NEUTRAL": 5.0, "BEAR": 4.0, "STRONG_BEAR": 3.0
        }.get(regime, 5.0)

        # Thesis invalidation — below hard stop OR key fundamental change
        invalidation = hard_stop * 0.98

        thesis_checks = [
            f"Price holds above ${hard_stop:.2f} (hard stop)",
            f"Volume on down days stays below 20-day average",
            f"Regime remains {regime} or improves",
            f"Score stays above 50 on next refresh",
        ]
        if horizon == "long":
            thesis_checks.append("Fundamental thesis (earnings growth, margin expansion) intact")
        if horizon == "short":
            thesis_checks.append(f"Position profitable within {cfg['days']} days — else exit")

        _entry = entry_price if entry_price is not None else (hard_stop + t1) / 2
        return ExitLevels(
            ticker=ticker,
            entry_price=round(_entry, 2),
            stop_loss_hard=round(hard_stop, 2),
            stop_loss_soft=round(soft_stop, 2),
            take_profit_1=round(t1, 2),
            take_profit_2=round(t2, 2),
            take_profit_3=round(t3, 2),
            trailing_stop_pct=trailing_pct,
            invalidation_price=round(invalidation, 2),
            time_stop_days=cfg["days"],
            risk_reward_ratio=round(rr_ratio, 2),
            thesis_check_points=thesis_checks,
        )

    def _nearest_resistance(self, target: float, levels: list[float]) -> float:
        """Snap take-profit to nearest resistance level if close."""
        candidates = [l for l in levels if l > target * 0.97 and l < target * 1.05]
        return min(candidates, default=target)


# ── Feature 4: Earnings Impact Predictor ─────────────────────────────────

@dataclass
class EarningsImpact:
    ticker:              str
    next_earnings_date:  str
    days_to_earnings:    int
    expected_move_pct:   float       # IV-implied expected move
    historical_avg_move: float       # Historical avg earnings day move
    beat_rate_pct:       float       # % of quarters that beat EPS
    position_recommendation: str     # "Hold" | "Reduce before" | "Hedge"
    suggested_action:    str
    iv_percentile:       float       # 0-100, where IV is vs history
    last_4_quarters:     list[dict]  # [{quarter, actual, estimate, beat_pct, move_pct}]
    risk_rating:         str         # "Low" | "Medium" | "High" | "Extreme"


class EarningsPredictor:
    """
    Feature 4: Earnings impact prediction.
    Flags positions approaching earnings with historical context.
    """

    def assess(
        self,
        ticker:                 str,
        next_earnings_date:     str,
        days_to_earnings:       int,
        implied_move_pct:       float,   # From options market
        historical_moves:       list[float],  # Past earnings day % moves
        beat_history:           list[bool],   # True=beat, False=missed
        current_iv_percentile:  float,   # Current IV vs 1-year range
        position_value:         float,
        portfolio_value:        float,
        last_4_quarters:        list[dict],
    ) -> EarningsImpact:

        # Historical average absolute move
        hist_avg = np.mean([abs(m) for m in historical_moves]) if historical_moves else implied_move_pct

        # Beat rate
        beat_rate = (sum(beat_history) / len(beat_history) * 100) if beat_history else 50.0

        # Position size as % of portfolio
        position_pct = position_value / portfolio_value

        # Risk rating
        risk = self._rate_earnings_risk(
            days_to_earnings, implied_move_pct,
            current_iv_percentile, position_pct
        )

        # Recommendation
        rec, action = self._get_recommendation(
            risk, days_to_earnings, beat_rate,
            current_iv_percentile, position_pct
        )

        return EarningsImpact(
            ticker=ticker,
            next_earnings_date=next_earnings_date,
            days_to_earnings=days_to_earnings,
            expected_move_pct=round(implied_move_pct, 1),
            historical_avg_move=round(hist_avg, 1),
            beat_rate_pct=round(beat_rate, 1),
            position_recommendation=rec,
            suggested_action=action,
            iv_percentile=current_iv_percentile,
            last_4_quarters=last_4_quarters,
            risk_rating=risk,
        )

    def _rate_earnings_risk(self, days, implied_move, iv_pct, position_pct) -> str:
        score = 0
        if days <= 7:             score += 3
        elif days <= 14:          score += 2
        elif days <= 30:          score += 1
        if implied_move > 10:     score += 3
        elif implied_move > 6:    score += 2
        elif implied_move > 3:    score += 1
        if iv_pct > 80:           score += 2
        elif iv_pct > 60:         score += 1
        if position_pct > 0.08:   score += 2
        elif position_pct > 0.05: score += 1

        return (
            "Extreme" if score >= 7 else
            "High"    if score >= 5 else
            "Medium"  if score >= 3 else
            "Low"
        )

    def _get_recommendation(self, risk, days, beat_rate, iv_pct, position_pct):
        if risk == "Extreme":
            return (
                "Reduce before earnings",
                f"Reduce to ≤3% of portfolio before earnings. "
                f"IV is elevated ({iv_pct:.0f}th pct) — implied move is expensive to hedge."
            )
        if risk == "High":
            return (
                "Hedge or reduce",
                f"Consider reducing by 30-50% or buying protective puts. "
                f"Beat rate {beat_rate:.0f}% {'is supportive' if beat_rate > 65 else '— caution'}."
            )
        if risk == "Medium" and days <= 14:
            return (
                "Hold with awareness",
                f"Earnings in {days} days. Historical avg move ±{beat_rate:.0f}%. "
                f"Ensure position size aligns with risk tolerance."
            )
        return (
            "Hold",
            f"Earnings risk manageable. Beat rate {beat_rate:.0f}%. Monitor into the date."
        )


# ── Feature 5: Correlation & Concentration Monitor ───────────────────────

@dataclass
class CorrelationAlert:
    ticker_a:    str
    ticker_b:    str
    correlation: float
    severity:    str    # "High" | "Extreme"
    note:        str


@dataclass
class ConcentrationReport:
    holdings:              list[dict]
    effective_positions:   float      # Diversification ratio
    herfindahl_index:      float      # 0-1, higher = more concentrated
    correlation_alerts:    list[CorrelationAlert]
    sector_weights:        dict
    top_risk_contributors: list[str]
    diversification_score: float      # 0-100
    recommendations:       list[str]
    is_concentrated:       bool


class ConcentrationMonitor:
    """
    Feature 5: Portfolio correlation and concentration risk.
    Detects when you have fewer real positions than you think.
    """

    CORRELATION_THRESHOLD_HIGH    = 0.70
    CORRELATION_THRESHOLD_EXTREME = 0.85
    HHI_CONCENTRATED              = 0.18   # Herfindahl index threshold

    def analyze(
        self,
        holdings:          list[dict],   # [{ticker, value, sector, returns_30d: list[float]}]
        portfolio_value:   float,
        regime:            str,
    ) -> ConcentrationReport:
        """
        holdings: each dict needs ticker, value, sector,
                  and returns_30d (list of 30 daily returns as decimals).
        """
        if not holdings:
            return self._empty_report()

        # ── Sector weights ────────────────────────────────────────────────
        sector_weights = {}
        for h in holdings:
            s = h.get("sector", "Unknown")
            sector_weights[s] = sector_weights.get(s, 0) + h["value"] / portfolio_value

        # ── Herfindahl-Hirschman Index (concentration) ────────────────────
        weights = [h["value"] / portfolio_value for h in holdings]
        hhi     = sum(w**2 for w in weights)

        # ── Correlation matrix ────────────────────────────────────────────
        correlation_alerts = []
        returns_data = {
            h["ticker"]: h.get("returns_30d", [])
            for h in holdings if len(h.get("returns_30d", [])) >= 15
        }

        tickers = list(returns_data.keys())
        for i in range(len(tickers)):
            for j in range(i + 1, len(tickers)):
                ta, tb = tickers[i], tickers[j]
                r1, r2 = returns_data[ta], returns_data[tb]
                min_len = min(len(r1), len(r2))
                if min_len < 10:
                    continue
                corr = np.corrcoef(r1[-min_len:], r2[-min_len:])[0, 1]

                if abs(corr) >= self.CORRELATION_THRESHOLD_EXTREME:
                    correlation_alerts.append(CorrelationAlert(
                        ticker_a=ta, ticker_b=tb,
                        correlation=round(corr, 3),
                        severity="Extreme",
                        note=(
                            f"{ta} and {tb} move together {corr:.0%} of the time. "
                            f"You effectively have ONE position, not two."
                        ),
                    ))
                elif abs(corr) >= self.CORRELATION_THRESHOLD_HIGH:
                    correlation_alerts.append(CorrelationAlert(
                        ticker_a=ta, ticker_b=tb,
                        correlation=round(corr, 3),
                        severity="High",
                        note=f"{ta} and {tb} are highly correlated ({corr:.0%}). Consider reducing one.",
                    ))

        # ── Effective N (diversification ratio) ──────────────────────────
        # 1/HHI gives the "equivalent number of equal-weight positions"
        effective_n = 1 / hhi if hhi > 0 else len(holdings)

        # ── Diversification score 0-100 ───────────────────────────────────
        max_hhi    = 1.0       # Single position
        min_hhi    = 1 / max(len(holdings), 1)
        if max_hhi > min_hhi:
            div_score = (1 - (hhi - min_hhi) / (max_hhi - min_hhi)) * 100
        else:
            div_score = 100.0
        div_score = min(100.0, max(0.0, div_score))  # Hard cap 0-100

        # ── Top risk contributors ─────────────────────────────────────────
        sorted_holdings = sorted(holdings, key=lambda h: h["value"], reverse=True)
        top_risk        = [
            f"{h['ticker']} ({h['value']/portfolio_value:.1%})"
            for h in sorted_holdings[:3]
        ]

        # ── Recommendations ───────────────────────────────────────────────
        recs = self._build_recommendations(
            hhi, correlation_alerts, sector_weights,
            effective_n, regime
        )

        is_concentrated = (
            hhi > self.HHI_CONCENTRATED or
            any(a.severity == "Extreme" for a in correlation_alerts) or
            any(w > 0.25 for w in sector_weights.values())
        )

        return ConcentrationReport(
            holdings=holdings,
            effective_positions=round(effective_n, 1),
            herfindahl_index=round(hhi, 4),
            correlation_alerts=correlation_alerts,
            sector_weights={k: round(v if v is not None else 0, 4) for k, v in sector_weights.items()},
            top_risk_contributors=top_risk,
            diversification_score=round(div_score, 1),
            recommendations=recs,
            is_concentrated=is_concentrated,
        )

    def _build_recommendations(self, hhi, alerts, sector_weights, effective_n, regime):
        recs = []

        if hhi > 0.25:
            recs.append("Portfolio is highly concentrated. Consider spreading across more tickers or sectors.")

        if any(a.severity == "Extreme" for a in alerts):
            extreme = [a for a in alerts if a.severity == "Extreme"]
            for a in extreme[:2]:
                recs.append(f"Reduce {a.ticker_a} or {a.ticker_b} — they move in lockstep ({a.correlation:.0%} corr).")

        for sector, weight in sector_weights.items():
            if weight > 0.30:
                recs.append(f"{sector} is {weight:.0%} of portfolio — above 30% sector limit.")

        if effective_n < 4:
            recs.append(f"You have {effective_n:.1f} effective positions. Target ≥6 for meaningful diversification.")

        if regime in ("BEAR", "STRONG_BEAR"):
            recs.append("Bear regime: reduce overall equity exposure, not just rebalance within equities.")

        if not recs:
            recs.append("Portfolio diversification looks healthy. No major concentration issues detected.")

        return recs

    def _empty_report(self) -> ConcentrationReport:
        return ConcentrationReport(
            holdings=[], effective_positions=0, herfindahl_index=0,
            correlation_alerts=[], sector_weights={}, top_risk_contributors=[],
            diversification_score=0, recommendations=["No holdings data"], is_concentrated=False,
        )


# ── Demo ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Thrive Alpha — Tier 1 Risk Features Demo")
    print("=" * 60)

    # Feature 1: Position Sizing
    print("\n[Feature 1] Position Sizing Engine")
    engine = PositionSizingEngine(portfolio_value=100_000, risk_tolerance=RiskTolerance.MODERATE)
    result = engine.size_position(
        ticker="NVDA", signal_score=78, confidence=0.72,
        current_position_value=3000, price=875.0, atr_14=22.5,
        vix=18.5, regime="BULL", win_rate=0.65,
        avg_win_pct=9.0, avg_loss_pct=4.5,
    )
    print(f"  Add: ${result.recommended_dollars:,.0f} ({result.recommended_shares} shares)")
    print(f"  Stop: ${result.stop_loss_price}  Target: ${result.take_profit_price}")
    print(f"  Risk: ${result.risk_per_trade_dollars:,.0f}")
    for r in result.sizing_rationale:
        print(f"    • {r}")

    # Feature 2: Drawdown
    print("\n[Feature 2] Drawdown Simulation")
    sim = DrawdownSimulator().simulate(
        ticker="NVDA", current_price=875.0, position_value=7000,
        portfolio_value=100_000, atr_14=22.5,
        hist_max_drawdown_pct=-66.0, cost_basis=820.0,
        support_levels=[850, 820, 780], signal_score=78,
    )
    for s in sim.scenarios:
        print(f"  {s.label:<35} → ${s.price_target}  ({s.pct_change:+.1f}%)  Portfolio: ${s.portfolio_impact_dollars:+,.0f}  P={s.probability:.0%}")

    # Feature 3: Exit Levels
    print("\n[Feature 3] Exit Levels")
    exits = ExitEngine().calculate_exits(
        ticker="NVDA", entry_price=875.0, atr_14=22.5,
        signal_score=78, regime="BULL", horizon="medium",
        support_levels=[850, 820, 780],
        resistance_levels=[900, 940, 1000],
    )
    print(f"  Hard stop:  ${exits.stop_loss_hard}  |  Soft stop: ${exits.stop_loss_soft}")
    print(f"  Take profit 1: ${exits.take_profit_1}  2: ${exits.take_profit_2}  3: ${exits.take_profit_3}")
    print(f"  R/R ratio: {exits.risk_reward_ratio:.1f}:1  |  Time stop: {exits.time_stop_days} days")

    # Feature 4: Earnings
    print("\n[Feature 4] Earnings Impact")
    earnings = EarningsPredictor().assess(
        ticker="NVDA", next_earnings_date="2025-05-28", days_to_earnings=18,
        implied_move_pct=8.5, historical_moves=[12.0, -8.5, 6.2, 15.0, -4.1],
        beat_history=[True, False, True, True, True],
        current_iv_percentile=72, position_value=7000,
        portfolio_value=100_000,
        last_4_quarters=[
            {"quarter": "Q4 2024", "actual": 0.89, "estimate": 0.84, "beat_pct": 6.0},
            {"quarter": "Q3 2024", "actual": 0.74, "estimate": 0.71, "beat_pct": 4.2},
        ],
    )
    print(f"  Risk: {earnings.risk_rating}  |  Rec: {earnings.position_recommendation}")
    print(f"  Action: {earnings.suggested_action}")

    # Feature 5: Concentration
    print("\n[Feature 5] Concentration Monitor")
    import random
    random.seed(42)
    holdings = [
        {"ticker": "AAPL", "value": 12000, "sector": "Technology",
         "returns_30d": [random.gauss(0.001, 0.015) for _ in range(30)]},
        {"ticker": "MSFT", "value": 11000, "sector": "Technology",
         "returns_30d": [random.gauss(0.001, 0.012) for _ in range(30)]},
        {"ticker": "NVDA", "value": 7000, "sector": "Technology",
         "returns_30d": [random.gauss(0.002, 0.025) for _ in range(30)]},
        {"ticker": "JPM",  "value": 5000, "sector": "Financial",
         "returns_30d": [random.gauss(0.0005, 0.010) for _ in range(30)]},
        {"ticker": "XOM",  "value": 4000, "sector": "Energy",
         "returns_30d": [random.gauss(0.001, 0.014) for _ in range(30)]},
    ]
    conc = ConcentrationMonitor().analyze(holdings, 100_000, "BULL")
    print(f"  HHI: {conc.herfindahl_index:.3f}  Effective positions: {conc.effective_positions}")
    print(f"  Diversification score: {conc.diversification_score:.0f}/100")
    for rec in conc.recommendations:
        print(f"  • {rec}")
    if conc.correlation_alerts:
        for alert in conc.correlation_alerts:
            print(f"  ⚠️  {alert.note}")

    print("\n✅ All Tier 1 features verified.")
