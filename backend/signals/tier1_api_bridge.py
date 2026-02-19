"""
tier1_api_bridge.py
Generates all Tier 1 risk feature payloads for Thrive Alpha's
/api/run (or equivalent) endpoint.

Call generate_tier1_payload() and merge result into your existing
DashboardData dict before returning the JSON response.

Requires: tier1_risk_engine.py in same package.
"""

import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import time

from .tier1_risk_engine import (
    PositionSizingEngine, RiskTolerance,
    DrawdownSimulator, ExitEngine,
    EarningsPredictor, ConcentrationMonitor,
)


# ─────────────────────────────────────────────────────────────
#  CONFIG — tune these to match your setup
# ─────────────────────────────────────────────────────────────

DEFAULT_PORTFOLIO_VALUE  = 100_000   # Override with real value
DEFAULT_RISK_TOLERANCE   = RiskTolerance.MODERATE
SLEEP_BETWEEN_CALLS      = 0.35      # yfinance rate limit buffer


# ─────────────────────────────────────────────────────────────
#  DATA FETCHERS
# ─────────────────────────────────────────────────────────────

def fetch_ticker_data(ticker: str) -> dict:
    """Fetch price, ATR, returns, IV proxy, support/resistance for one ticker."""
    try:
        time.sleep(SLEEP_BETWEEN_CALLS)
        t    = yf.Ticker(ticker)
        hist = t.history(period="6mo", prepost=False)
        if hist.empty or len(hist) < 20:
            return {}

        close  = hist["Close"]
        high   = hist["High"]
        low    = hist["Low"]
        volume = hist["Volume"]

        # ATR(14)
        tr     = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr_14 = float(tr.rolling(14).mean().iloc[-1])

        # 30-day daily returns
        returns_30d = close.pct_change().dropna().tail(30).tolist()

        # Support levels (recent swing lows)
        support_levels = _find_support_levels(close, low)

        # Resistance levels (recent swing highs)
        resistance_levels = _find_resistance_levels(close, high)

        # Historical max drawdown over 1 year
        year_close  = close.tail(252)
        roll_max    = year_close.cummax()
        drawdowns   = (year_close - roll_max) / roll_max * 100
        max_dd      = float(drawdowns.min())

        # IV proxy: annualized 30-day realized vol as implied-move estimate
        rv_30d      = float(returns_30d[-20:] and np.std(returns_30d[-20:]) * np.sqrt(252) * 100) if len(returns_30d) >= 20 else 30.0

        info = t.info or {}

        return {
            "ticker":             ticker,
            "price":              float(close.iloc[-1]),
            "atr_14":             round(atr_14, 2),
            "returns_30d":        [round(r, 6) for r in returns_30d],
            "support_levels":     support_levels,
            "resistance_levels":  resistance_levels,
            "hist_max_drawdown":  round(max_dd, 1),
            "rv_30d_pct":         round(rv_30d, 1),
            "sector":             info.get("sector", "Unknown"),
            "next_earnings_date": info.get("earningsDate", [None])[0] if isinstance(info.get("earningsDate"), list) else None,
            "beta":               info.get("beta", 1.0),
            "cost_basis":         float(close.iloc[-1]),  # Use current price if no cost basis
        }
    except Exception as e:
        print(f"  ⚠️  fetch_ticker_data({ticker}): {e}")
        return {}


def _find_support_levels(close: pd.Series, low: pd.Series) -> list[float]:
    """Find 3 recent support levels from swing lows."""
    lows = []
    arr  = low.values
    for i in range(2, len(arr) - 2):
        if arr[i] < arr[i-1] and arr[i] < arr[i-2] and arr[i] < arr[i+1] and arr[i] < arr[i+2]:
            lows.append(float(arr[i]))
    # Deduplicate nearby levels (within 1%)
    lows = sorted(set(round(l, 2) for l in lows), reverse=True)
    current = float(close.iloc[-1])
    below_current = [l for l in lows if l < current * 0.99]
    return sorted(below_current, reverse=True)[:4]


def _find_resistance_levels(close: pd.Series, high: pd.Series) -> list[float]:
    """Find 3 recent resistance levels from swing highs."""
    highs = []
    arr   = high.values
    for i in range(2, len(arr) - 2):
        if arr[i] > arr[i-1] and arr[i] > arr[i-2] and arr[i] > arr[i+1] and arr[i] > arr[i+2]:
            highs.append(float(arr[i]))
    highs   = sorted(set(round(h, 2) for h in highs))
    current = float(close.iloc[-1])
    above   = [h for h in highs if h > current * 1.01]
    return sorted(above)[:4]


def fetch_vix() -> float:
    """Fetch current VIX level."""
    try:
        time.sleep(SLEEP_BETWEEN_CALLS)
        vix = yf.Ticker("^VIX").history(period="2d")
        return float(vix["Close"].iloc[-1]) if not vix.empty else 20.0
    except Exception:
        return 20.0


# ─────────────────────────────────────────────────────────────
#  MAIN GENERATOR
# ─────────────────────────────────────────────────────────────

def generate_tier1_payload(
    holdings: list[dict],
    signals:  list[dict],
    portfolio_value: float = DEFAULT_PORTFOLIO_VALUE,
    regime:   str = "BULL",
    risk_tolerance: RiskTolerance = DEFAULT_RISK_TOLERANCE,
    horizon:  str = "medium",
) -> dict:
    """
    Master function — generates all 5 Tier 1 feature payloads.

    Args:
        holdings: list of portfolio holdings dicts, each with:
                  {ticker, value, cost_basis?}
        signals:  list of signal dicts from your existing engine, each with:
                  {ticker, score, confidence, win_rate, avg_win_pct, avg_loss_pct}
        portfolio_value: total portfolio USD value
        regime:   current market regime string
        risk_tolerance: RiskTolerance enum
        horizon:  "short" | "medium" | "long"

    Returns:
        Dict with keys: position_sizing, drawdown_sim, exit_levels,
                        earnings_impacts, concentration
    """
    print(f"\n{'─'*55}")
    print(f"  Tier 1 Risk Engine — {len(holdings)} holdings, {len(signals)} signals")
    print(f"{'─'*55}")

    vix     = fetch_vix()
    print(f"  VIX: {vix:.1f}  Regime: {regime}  Portfolio: ${portfolio_value:,.0f}")

    # Fetch market data for all unique tickers
    tickers = list({h["ticker"] for h in holdings} |
                   {s["ticker"] for s in signals})

    print(f"  Fetching data for {len(tickers)} tickers...")
    market_data = {}
    for ticker in tickers:
        print(f"    {ticker}...", end="\r")
        data = fetch_ticker_data(ticker)
        if data:
            market_data[ticker] = data

    sizing_engine  = PositionSizingEngine(portfolio_value, risk_tolerance)
    dd_simulator   = DrawdownSimulator()
    exit_engine    = ExitEngine()
    earnings_pred  = EarningsPredictor()
    conc_monitor   = ConcentrationMonitor()

    # ── Feature 1: Position Sizing ────────────────────────────────────────
    print("\n  [1] Position sizing...")
    position_sizing_out = []
    for sig in signals:
        ticker = sig["ticker"]
        if ticker not in market_data:
            continue
        md = market_data[ticker]
        holding_value = next((h["value"] for h in holdings if h["ticker"] == ticker), 0.0)

        result = sizing_engine.size_position(
            ticker=ticker,
            signal_score=sig.get("score", 50),
            confidence=sig.get("confidence", 0.60),
            current_position_value=holding_value,
            price=md["price"],
            atr_14=md["atr_14"],
            vix=vix,
            regime=regime,
            win_rate=sig.get("win_rate", 0.60),
            avg_win_pct=sig.get("avg_win_pct", 7.0),
            avg_loss_pct=sig.get("avg_loss_pct", 4.0),
        )
        position_sizing_out.append({
            "ticker":                 result.ticker,
            "recommended_dollars":    result.recommended_dollars,
            "recommended_shares":     result.recommended_shares,
            "max_position_dollars":   result.max_position_dollars,
            "current_pct":            result.current_pct,
            "target_pct":             result.target_pct,
            "risk_per_trade_dollars": result.risk_per_trade_dollars,
            "stop_loss_price":        result.stop_loss_price,
            "take_profit_price":      result.take_profit_price,
            "kelly_fraction":         result.kelly_fraction,
            "adjusted_fraction":      result.adjusted_fraction,
            "sizing_rationale":       result.sizing_rationale,
            "warning":                result.warning,
        })

    # ── Feature 2: Drawdown Simulation ────────────────────────────────────
    print("  [2] Drawdown simulation...")
    drawdown_out = []
    for h in holdings:
        ticker = h["ticker"]
        if ticker not in market_data:
            continue
        md = market_data[ticker]

        sim = dd_simulator.simulate(
            ticker=ticker,
            current_price=md["price"],
            position_value=h["value"],
            portfolio_value=portfolio_value,
            atr_14=md["atr_14"],
            hist_max_drawdown_pct=md["hist_max_drawdown"],
            cost_basis=h.get("cost_basis", md["price"]),
            support_levels=md["support_levels"],
            signal_score=next((s["score"] for s in signals if s["ticker"] == ticker), 50),
        )
        drawdown_out.append({
            "ticker":          sim.ticker,
            "current_price":   sim.current_price,
            "position_value":  sim.position_value,
            "scenarios": [
                {
                    "label":                    s.label,
                    "price_target":             s.price_target,
                    "pct_change":               s.pct_change,
                    "portfolio_impact_dollars": s.portfolio_impact_dollars,
                    "portfolio_impact_pct":     s.portfolio_impact_pct,
                    "probability":              s.probability,
                    "support_level":            s.support_level,
                    "description":              s.description,
                }
                for s in sim.scenarios
            ],
            "max_loss_dollars":            sim.max_loss_dollars,
            "max_loss_pct":                sim.max_loss_pct,
            "breakeven_price":             sim.breakeven_price,
            "atr_14":                      sim.atr_14,
            "historical_max_drawdown_pct": sim.historical_max_drawdown_pct,
        })

    # ── Feature 3: Exit Levels ────────────────────────────────────────────
    print("  [3] Exit levels...")
    exit_out = []
    for h in holdings:
        ticker = h["ticker"]
        if ticker not in market_data:
            continue
        md = market_data[ticker]

        exits = exit_engine.calculate_exits(
            ticker=ticker,
            entry_price=h.get("cost_basis", md["price"]),
            atr_14=md["atr_14"],
            signal_score=next((s["score"] for s in signals if s["ticker"] == ticker), 50),
            regime=regime,
            horizon=horizon,
            support_levels=md["support_levels"],
            resistance_levels=md["resistance_levels"],
        )
        exit_out.append({
            "ticker":              exits.ticker,
            "entry_price":         exits.entry_price,
            "stop_loss_hard":      exits.stop_loss_hard,
            "stop_loss_soft":      exits.stop_loss_soft,
            "take_profit_1":       exits.take_profit_1,
            "take_profit_2":       exits.take_profit_2,
            "take_profit_3":       exits.take_profit_3,
            "trailing_stop_pct":   exits.trailing_stop_pct,
            "invalidation_price":  exits.invalidation_price,
            "time_stop_days":      exits.time_stop_days,
            "risk_reward_ratio":   exits.risk_reward_ratio,
            "thesis_check_points": exits.thesis_check_points,
        })

    # ── Feature 4: Earnings Impact ────────────────────────────────────────
    print("  [4] Earnings assessment...")
    earnings_out = []
    for h in holdings:
        ticker = h["ticker"]
        if ticker not in market_data:
            continue
        md = market_data[ticker]

        if not md.get("next_earnings_date"):
            continue

        try:
            earnings_dt  = pd.Timestamp(md["next_earnings_date"]).tz_localize(None)
            days_to_earn = max(0, (earnings_dt - pd.Timestamp.now()).days)
        except Exception:
            continue

        implied_move = md["rv_30d_pct"] * 0.4   # Rough IV proxy from realized vol

        assessment = earnings_pred.assess(
            ticker=ticker,
            next_earnings_date=str(earnings_dt.date()),
            days_to_earnings=days_to_earn,
            implied_move_pct=implied_move,
            historical_moves=[],        # Add from your FMP data if available
            beat_history=[],
            current_iv_percentile=50.0, # Override with real IV percentile if available
            position_value=h["value"],
            portfolio_value=portfolio_value,
            last_4_quarters=[],
        )
        earnings_out.append({
            "ticker":                  assessment.ticker,
            "next_earnings_date":      assessment.next_earnings_date,
            "days_to_earnings":        assessment.days_to_earnings,
            "expected_move_pct":       assessment.expected_move_pct,
            "historical_avg_move":     assessment.historical_avg_move,
            "beat_rate_pct":           assessment.beat_rate_pct,
            "position_recommendation": assessment.position_recommendation,
            "suggested_action":        assessment.suggested_action,
            "iv_percentile":           assessment.iv_percentile,
            "last_4_quarters":         assessment.last_4_quarters,
            "risk_rating":             assessment.risk_rating,
        })

    # ── Feature 5: Concentration ──────────────────────────────────────────
    print("  [5] Concentration analysis...")
    holdings_with_returns = []
    for h in holdings:
        ticker = h["ticker"]
        md     = market_data.get(ticker, {})
        holdings_with_returns.append({
            "ticker":     ticker,
            "value":      h["value"],
            "sector":     md.get("sector", "Unknown"),
            "returns_30d": md.get("returns_30d", []),
        })

    conc = conc_monitor.analyze(holdings_with_returns, portfolio_value, regime)
    concentration_out = {
        "holdings":              [{"ticker": h["ticker"], "value": h["value"], "sector": h.get("sector")} for h in holdings_with_returns],
        "effective_positions":   conc.effective_positions,
        "herfindahl_index":      conc.herfindahl_index,
        "correlation_alerts": [
            {
                "ticker_a":    a.ticker_a,
                "ticker_b":    a.ticker_b,
                "correlation": a.correlation,
                "severity":    a.severity,
                "note":        a.note,
            }
            for a in conc.correlation_alerts
        ],
        "sector_weights":        conc.sector_weights,
        "top_risk_contributors": conc.top_risk_contributors,
        "diversification_score": conc.diversification_score,
        "recommendations":       conc.recommendations,
        "is_concentrated":       conc.is_concentrated,
    }

    print(f"\n  ✅ Tier 1 complete")
    print(f"     Sizing: {len(position_sizing_out)} | Drawdown: {len(drawdown_out)} | "
          f"Exits: {len(exit_out)} | Earnings: {len(earnings_out)}")
    print(f"     Conc score: {conc.diversification_score:.0f}/100  "
          f"Alerts: {len(conc.correlation_alerts)}")

    return {
        "position_sizing":  position_sizing_out,
        "drawdown_sim":     drawdown_out,
        "exit_levels":      exit_out,
        "earnings_impacts": earnings_out,
        "concentration":    concentration_out,
    }
