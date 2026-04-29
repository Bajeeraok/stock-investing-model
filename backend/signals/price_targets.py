"""
price_targets.py — Consolidated buy/sell zones, expected returns, and scenario analysis.

Architecture rationale:
  Technical levels (MA50, MA200, 52w-low) anchor the ENTRY ZONE — they tell us
  WHERE price has structural support.  ML horizon probabilities tell us WHETHER
  and HOW SOON to act at those levels.  Combining both gives retail investors a
  complete "when, what price, what return, what could go wrong" answer.

Entry zone logic (consolidated with technical score):
  - LOW  = max(MA50 × 0.98, 52w-low × 1.05)   — don't buy near 52w-low unless
             RSI is reversing; MA50 is the natural dip-buy level
  - HIGH = current_price (buy at or below current)
  - For strong bull regime or STRONG BUY signal → HIGH = current_price × 1.02
             (willing to chase slightly into strength)

Stop loss:
  - Short-term: MA50 × 0.97 (break below MA50 = thesis challenged)
  - Medium-term: MA200 × 0.97 (break below MA200 = structural breakdown)
  - Long-term: max(MA200, 52w-low) × 0.97 when both exist (structural vs tail); else legacy 52w-based

Scenarios (asset-type-aware):
  Each scenario has:  name, trigger, probability, short/med/long targets,
  return_pct, rationale.  Three universal + up to two asset-specific ones.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from signals.structural_invalidation import structural_invalidation_below

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Expected return formula
# ---------------------------------------------------------------------------

def _expected_return(prob: float | None, upside_pct: float, downside_pct: float = -4.0) -> float | None:
    """
    EV = P(win) × upside + P(loss) × downside.
    If ML prob is None returns None (no model trained yet).
    """
    if prob is None:
        return None
    return round(prob * upside_pct + (1 - prob) * downside_pct, 2)


def _risk_reward(entry: float, target: float, stop: float) -> float | None:
    """Ratio of potential gain to potential loss. None if stop == entry."""
    if abs(entry - stop) < 0.01:
        return None
    gain = abs(target - entry)
    loss = abs(entry - stop)
    return round(gain / loss, 2)


# ---------------------------------------------------------------------------
# Technical level extraction
# ---------------------------------------------------------------------------

def _extract_levels(df: pd.DataFrame, close: pd.Series) -> dict:
    """Pull key price levels from the OHLCV dataframe."""
    if df is None or df.empty or close is None or len(close) < 20:
        return {}
    c = close.dropna()
    n = len(c)
    price  = float(c.iloc[-1])
    ma50   = float(c.rolling(50, min_periods=20).mean().iloc[-1])  if n >= 20  else price
    ma200  = float(c.rolling(200, min_periods=60).mean().iloc[-1]) if n >= 60  else price
    low52  = float(c.rolling(252, min_periods=60).min().iloc[-1])  if n >= 60  else price * 0.75
    high52 = float(c.rolling(252, min_periods=60).max().iloc[-1])  if n >= 60  else price * 1.25
    # Simple 20-day historical volatility (annualised)
    rets = c.pct_change().dropna()
    vol  = float(rets.tail(20).std() * np.sqrt(252)) if len(rets) >= 10 else 0.25
    return {
        "current_price": round(price, 2),
        "ma50":          round(ma50,  2),
        "ma200":         round(ma200, 2),
        "low_52w":       round(low52, 2),
        "high_52w":      round(high52, 2),
        "vol_annual":    round(vol, 3),
    }


# ---------------------------------------------------------------------------
# Horizon price targets
# ---------------------------------------------------------------------------

def _horizon_targets(
    lv: dict,
    horizon: dict,          # one entry from ml_horizons (short/medium/long)
    regime: str,
    horizon_key: str,       # "short" | "medium" | "long"
    ticker: str | None = None,
) -> dict:
    """
    Compute entry zone, base/bull/bear targets, stop, risk/reward, and
    expected return for one ML horizon.
    """
    price  = lv.get("current_price", 0)
    ma50   = lv.get("ma50", price)
    ma200  = lv.get("ma200", price)
    low52  = lv.get("low_52w", price * 0.75)
    if price == 0:
        return {}

    # ── ML inputs ──────────────────────────────────────────────────────────
    prob       = horizon.get("prob")                       # 0-1 or None
    thr        = float(horizon.get("threshold_pct", 5))   # e.g. 5 means 5%
    label      = horizon.get("label", "")                  # "1 month"
    interp     = horizon.get("interpretation", "Neutral")
    days       = int(horizon.get("horizon_days", 20))

    prob_pct   = round(prob * 100, 1) if prob is not None else None

    # ── Entry zone (consolidated with technical support) ───────────────────
    # Low anchor: don't chase; let price come to MA50 or better
    entry_low  = max(ma50 * 0.98, low52 * 1.05)
    # High anchor: current price for most, slight chase allowed in strong bull
    is_bull    = regime in ("BULL", "STRONG_BULL")
    entry_high = price * 1.02 if is_bull else price
    entry_low  = min(entry_low, entry_high * 0.97)  # ensure spread makes sense

    # ── Stop loss (horizon-dependent) ──────────────────────────────────────
    if horizon_key == "short":
        stop = ma50 * 0.97        # below MA50 = near-term thesis broken
    elif horizon_key == "medium":
        stop = ma200 * 0.97       # below MA200 = structural breakdown
    else:
        stop = structural_invalidation_below(ma200, low52, fallback=low52 * 0.97)

    # ── Price targets ──────────────────────────────────────────────────────
    # Base  = current × (1 + threshold) — the ML model's own bar
    # Bull  = base + extra upside scaled by horizon length
    # Bear  = entry × (1 - downside) — same stop logic from entry perspective
    base_ret   = thr / 100
    extra_bull = (days / 252) * 0.10   # longer horizon → more upside in bull case
    extra_bear = 0.06 + (days / 252) * 0.04

    target_base  = round(price * (1 + base_ret), 2)
    target_bull  = round(price * (1 + base_ret + extra_bull), 2)
    target_bear  = round(price * (1 - extra_bear), 2)

    # ── Expected return (probability-weighted) ─────────────────────────────
    downside_assumption = -extra_bear * 100   # rough expected loss if wrong
    exp_return = _expected_return(prob, thr, downside_assumption)

    # ── Risk / reward at entry midpoint ────────────────────────────────────
    entry_mid  = round((entry_low + entry_high) / 2, 2)
    rr_ratio   = _risk_reward(entry_mid, target_base, stop)

    # ── Rationale ─────────────────────────────────────────────────────────
    support_label = (
        f"MA50 ${ma50:.2f}" if horizon_key == "short" else
        f"MA200 ${ma200:.2f}" if horizon_key == "medium" else
        f"structural max(MA200 ${ma200:.2f}, 52w-low ${low52:.2f})"
    )
    if prob is None:
        action_hint = "ML model not yet trained — rely on technical levels only"
    elif prob >= 0.55:
        action_hint = f"Strong ML confirmation ({prob_pct}%) — entry at dips toward {support_label}"
    elif prob >= 0.35:
        action_hint = f"Moderate ML signal ({prob_pct}%) — scale in at {support_label}, hold reserve"
    else:
        action_hint = f"Weak ML signal ({prob_pct}%) — wait for {support_label} to act as proven support"

    return {
        "horizon_key":    horizon_key,
        "label":          label,
        "days":           days,
        "ml_prob_pct":    prob_pct,
        "threshold_pct":  thr,
        "interpretation": interp,
        "entry_zone": {
            "low":       round(entry_low, 2),
            "high":      round(entry_high, 2),
            "anchor":    support_label,
            "note":      f"Buy zone anchored to {support_label}",
        },
        "targets": {
            "base": target_base,    # ML threshold achieved
            "bull": target_bull,    # optimistic — regime improves
            "bear": target_bear,    # pessimistic — thesis partially fails
        },
        "returns": {
            "base":     thr,
            "bull":     round((target_bull / price - 1) * 100, 1),
            "bear":     round((target_bear / price - 1) * 100, 1),
            "expected": exp_return,
        },
        "stop_loss":    round(stop, 2),
        "risk_reward":  rr_ratio,
        "action_hint":  action_hint,
    }


# ---------------------------------------------------------------------------
# Scenario engine (asset-type-aware)
# ---------------------------------------------------------------------------

_UNIVERSAL_SCENARIOS = {
    "bull": {
        "name":      "Bull Case",
        "trigger":   "Regime upgrade + ML confirmation",
        "rationale": "HMM transitions to full bull state, ML probability crosses 60%+. "
                     "Institutional flow accelerates. Full position justified.",
        "multipliers": {"base": 1.10, "target_mult": 1.15, "prob_boost": 0.20},
    },
    "base": {
        "name":      "Base Case",
        "trigger":   "Current signals hold",
        "rationale": "ML probability stays in current range, regime unchanged. "
                     "Gradual price appreciation toward technical target.",
        "multipliers": {"base": 1.00, "target_mult": 1.05, "prob_boost": 0.00},
    },
    "bear": {
        "name":      "Bear Case",
        "trigger":   "Regime deterioration + ML miss",
        "rationale": "HMM shifts toward bear state, ML probability drops below 20%. "
                     "Stop-loss triggered at key support break.",
        "multipliers": {"base": 0.92, "target_mult": 0.88, "prob_boost": -0.25},
    },
}

_ASSET_SCENARIOS: dict[str, list[dict]] = {
    "EQUITY_US": [
        {
            "name":    "Earnings Beat",
            "trigger": "EPS surprise >5% + guidance raised",
            "rationale": "Consistent earnings beats with raised guidance compress the put premium "
                         "and attract systematic buyers. Post-earnings drift typically +3-8%.",
            "return_adj":  +0.06,
            "prob_adj":    +0.15,
        },
        {
            "name":    "Fed Rate Cut",
            "trigger": "25-50bps cut + dovish forward guidance",
            "rationale": "Rate cuts reduce the discount rate applied to future earnings, "
                         "expanding P/E multiples. Growth stocks see the largest re-rating.",
            "return_adj":  +0.05,
            "prob_adj":    +0.10,
        },
        {
            "name":    "Earnings Miss / Guidance Cut",
            "trigger": "EPS miss >3% or forward guidance below consensus",
            "rationale": "Guidance cuts trigger analyst estimate revisions downward. "
                         "Institutional sell programs activate below prior support.",
            "return_adj":  -0.08,
            "prob_adj":    -0.20,
        },
    ],
    "EQUITY_SPECULATIVE": [
        {
            "name":    "Momentum Squeeze",
            "trigger": "Short interest >20% + positive catalyst",
            "rationale": "High short interest creates a coiled spring. A positive catalyst "
                         "(earnings beat, partnership, product launch) forces short covering.",
            "return_adj":  +0.12,
            "prob_adj":    +0.20,
        },
        {
            "name":    "Institutional Exit",
            "trigger": "Major fund filing 13G/D showing reduced stake",
            "rationale": "Large fund exits in high-beta names create sustained selling pressure. "
                         "Retail sentiment alone cannot absorb the supply.",
            "return_adj":  -0.12,
            "prob_adj":    -0.25,
        },
        {
            "name":    "Fed Pivot (Risk-On)",
            "trigger": "Fed signals pause/cut cycle",
            "rationale": "Speculative assets disproportionately benefit from lower rates — "
                         "cost of capital drops and growth premium expands sharply.",
            "return_adj":  +0.10,
            "prob_adj":    +0.15,
        },
    ],
    "EQUITY_DEFENSIVE": [
        {
            "name":    "Dividend Increase",
            "trigger": "Board raises dividend >5%",
            "rationale": "Dividend growth signals management confidence in cash flow durability. "
                         "Income-oriented funds add on yield-floor support.",
            "return_adj":  +0.04,
            "prob_adj":    +0.12,
        },
        {
            "name":    "Recession Signal",
            "trigger": "Inverted yield curve + PMI < 50 for 3 months",
            "rationale": "Defensive names act as safe havens in recessions. "
                         "Relative strength vs S&P500 improves even in absolute drawdowns.",
            "return_adj":  +0.03,
            "prob_adj":    +0.10,
        },
        {
            "name":    "Rate Spike",
            "trigger": "10Y Treasury yield rises >50bps",
            "rationale": "Yield-seeking investors rotate from low-growth defensives to bonds. "
                         "P/E compression hits high-yielding stocks disproportionately.",
            "return_adj":  -0.06,
            "prob_adj":    -0.15,
        },
    ],
    "EQUITY_ADR": [
        {
            "name":    "Geopolitical De-escalation",
            "trigger": "Trade deal progress / regulatory thaw",
            "rationale": "ADR discount to NAV narrows when geopolitical risk premium reduces. "
                         "Foreign institutional investors re-enter the market.",
            "return_adj":  +0.10,
            "prob_adj":    +0.18,
        },
        {
            "name":    "Regulatory Crackdown",
            "trigger": "New government policy targeting the sector",
            "rationale": "Regulatory risk is the primary idiosyncratic risk for foreign ADRs. "
                         "Sector-wide crackdowns can compress multiples 30-50% in weeks.",
            "return_adj":  -0.18,
            "prob_adj":    -0.30,
        },
        {
            "name":    "Currency Depreciation",
            "trigger": "Local currency weakens >5% vs USD",
            "rationale": "Revenue earned locally translates to fewer USD for ADR holders. "
                         "Repatriation risk adds a layer of uncertainty.",
            "return_adj":  -0.06,
            "prob_adj":    -0.10,
        },
    ],
    "ETF_EQUITY": [
        {
            "name":    "Broad Market Rally",
            "trigger": "S&P500 breaks to new highs, VIX < 15",
            "rationale": "Equity ETFs track the broad market. Low volatility + upward momentum "
                         "accelerates passive inflows and drives above-average returns.",
            "return_adj":  +0.06,
            "prob_adj":    +0.12,
        },
        {
            "name":    "Market Correction (10%+ drawdown)",
            "trigger": "S&P500 falls 10%+ from highs",
            "rationale": "ETFs have no earnings buffer. Broad market corrections flow directly "
                         "through. Trailing stop recommended at MA200.",
            "return_adj":  -0.10,
            "prob_adj":    -0.20,
        },
        {
            "name":    "Fed Quantitative Tightening Reversal",
            "trigger": "Fed announces QT slowdown or balance sheet expansion",
            "rationale": "Liquidity expansion historically boosts equity multiples. "
                         "ETFs benefit proportionally to their market-cap weight.",
            "return_adj":  +0.07,
            "prob_adj":    +0.12,
        },
    ],
    "ETF_COMMODITY": [
        {
            "name":    "Fed Rate Cuts (Dovish Pivot)",
            "trigger": "Fed cuts 50+ bps or signals extended pause",
            "rationale": "Rate cuts weaken the USD and lower real yields — both primary "
                         "tailwinds for gold and commodity ETFs. Historical avg +8-12% within 3 months.",
            "return_adj":  +0.08,
            "prob_adj":    +0.18,
        },
        {
            "name":    "Inflation Re-acceleration",
            "trigger": "CPI prints >4% for 2+ consecutive months",
            "rationale": "Commodities are the classic inflation hedge. Institutional "
                         "allocators increase commodity exposure as real yields turn negative.",
            "return_adj":  +0.10,
            "prob_adj":    +0.20,
        },
        {
            "name":    "USD Strength Spike",
            "trigger": "DXY rises >3% in a month (risk-off flight to USD)",
            "rationale": "Commodities are priced in USD — stronger dollar makes them more expensive "
                         "for foreign buyers, reducing demand and compressing prices.",
            "return_adj":  -0.07,
            "prob_adj":    -0.15,
        },
        {
            "name":    "Geopolitical Crisis (Safe-Haven Demand)",
            "trigger": "Major geopolitical escalation / financial system stress",
            "rationale": "Gold specifically benefits from safe-haven flows. Crisis periods "
                         "see gold spike 5-15% in weeks as institutional hedging demand surges.",
            "return_adj":  +0.08,
            "prob_adj":    +0.15,
        },
    ],
}


def _fetch_macro_context(config: dict | None) -> dict:
    """
    Fetch live macro data to gate scenario probabilities.
    All free — uses yfinance tickers + FRED API (key from config).

    Returns:
        vix         — current VIX level (fear index)
        yield_10y   — current 10Y Treasury yield (^TNX)
        yield_2y    — current 2Y Treasury yield (^IRX)
        yield_curve — 10Y - 2Y spread (positive = normal, negative = inverted)
        fed_rate    — latest Fed Funds rate from FRED (needs key)
        cpi_yoy     — latest CPI year-over-year % from FRED (needs key)
        dxy         — DXY USD index current level
    """
    ctx: dict = {}

    # ── yfinance free tickers (no key required) ──────────────────────────────
    _YF_MACRO = {
        "vix":       "^VIX",
        "yield_10y": "^TNX",
        "yield_2y":  "^IRX",
        "dxy":       "DX-Y.NYB",
    }
    try:
        import yfinance as yf
        for key, sym in _YF_MACRO.items():
            try:
                d = yf.download(sym, period="5d", progress=False, threads=False, auto_adjust=True)
                if d is not None and not d.empty:
                    close_col = d.get("Close") if hasattr(d, "get") else None
                    if close_col is None and hasattr(d, "columns") and "Close" in d.columns:
                        close_col = d["Close"]
                    if close_col is not None:
                        val = close_col.dropna()
                        if len(val) > 0:
                            ctx[key] = round(float(val.iloc[-1]), 3)
            except Exception:
                pass
    except Exception:
        pass

    # Yield curve spread
    if "yield_10y" in ctx and "yield_2y" in ctx:
        ctx["yield_curve"] = round(ctx["yield_10y"] - ctx["yield_2y"], 3)

    # ── FRED (key required, free) ────────────────────────────────────────────
    if config:
        try:
            from signals.fred_client import fetch_series_range, get_latest_value, get_api_key
            fred_key_present = bool(get_api_key(config))
            if fred_key_present:
                # Fed Funds Rate (monthly)
                ff = get_latest_value(config, "FEDFUNDS")
                if ff is not None:
                    ctx["fed_rate"] = round(ff, 3)
                # CPI (monthly, compute YoY manually from last 13 observations)
                try:
                    from datetime import date, timedelta
                    start = (date.today() - timedelta(days=400)).isoformat()
                    obs, _ = fetch_series_range(config, "CPIAUCSL", start_date=start)
                    if obs and len(obs) >= 13:
                        clean = [o for o in obs if o.get("value") not in (".", None, "")]
                        if len(clean) >= 13:
                            cur  = float(clean[-1]["value"])
                            yr_ago = float(clean[-13]["value"])
                            if yr_ago > 0:
                                ctx["cpi_yoy"] = round((cur - yr_ago) / yr_ago * 100, 2)
                except Exception:
                    pass
        except Exception:
            pass

    return ctx


def _fetch_earnings_info(ticker: str) -> dict:
    """
    Fetch next earnings date from yfinance (free, no key).
    Returns dict with next_earnings_date, days_until_earnings, earnings_note.
    """
    result: dict = {}
    try:
        import yfinance as yf
        from datetime import date, datetime as dt
        t = yf.Ticker(ticker)

        # Try calendar first (most reliable)
        cal = getattr(t, "calendar", None)
        next_date = None
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed is not None:
                if hasattr(ed, "__iter__") and not isinstance(ed, str):
                    ed = list(ed)
                    if ed:
                        next_date = ed[0]
                else:
                    next_date = ed
        elif cal is not None and hasattr(cal, "columns"):
            for col in ("Earnings Date", "earningsDate"):
                if col in cal.columns:
                    vals = cal[col].dropna()
                    if len(vals) > 0:
                        next_date = vals.iloc[0]
                        break

        # Fallback: earnings_dates attribute
        if next_date is None:
            try:
                ed_df = t.earnings_dates
                if ed_df is not None and not ed_df.empty:
                    today = date.today()
                    future = ed_df[pd.to_datetime(ed_df.index).date > today]
                    if not future.empty:
                        next_date = future.index[-1]  # earliest future date
            except Exception:
                pass

        if next_date is not None:
            try:
                if hasattr(next_date, "date"):
                    nd = next_date.date()
                else:
                    nd = pd.to_datetime(next_date).date()
                today = date.today()
                delta = (nd - today).days
                if 0 <= delta <= 180:
                    result["next_earnings_date"] = nd.isoformat()
                    result["days_until_earnings"] = delta
                    if delta <= 7:
                        result["earnings_note"] = f"⚠️ Earnings in {delta} day{'s' if delta != 1 else ''} — elevated event risk"
                    elif delta <= 21:
                        result["earnings_note"] = f"Earnings in ~{delta} days — pre-earnings positioning window"
                    else:
                        result["earnings_note"] = f"Next earnings ~{nd.strftime('%b %d, %Y')} ({delta} days)"
            except Exception:
                pass
    except Exception as exc:
        logger.debug("Earnings date fetch failed for %s: %s", ticker, exc)
    return result


def _next_trading_day(close_idx: pd.Index, ts: pd.Timestamp) -> pd.Timestamp | None:
    """First close index day strictly after ts."""
    if close_idx is None or len(close_idx) == 0:
        return None
    try:
        pos = close_idx.searchsorted(ts, side="right")
        if pos >= len(close_idx):
            return None
        return close_idx[pos]
    except Exception:
        return None


def _compute_earnings_target_block(
    ticker: str,
    *,
    price: float,
    close: pd.Series,
    short_prob: float | None,
    earnings_info: dict | None,
) -> dict:
    """
    Build a dedicated earnings-event target block:
    - expected one-day earnings move from historical earnings reactions
    - implied upside/downside targets around current price
    - simple directional bias from short-horizon ML probability
    - calibration hit-rate from prior events (walk-forward, no lookahead)
    """
    out = {
        "available": False,
        "next_earnings_date": (earnings_info or {}).get("next_earnings_date"),
        "days_until_earnings": (earnings_info or {}).get("days_until_earnings"),
    }
    if price <= 0 or close is None or len(close) < 40:
        return out

    event_rows: list[dict] = []
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        ed_df = getattr(t, "earnings_dates", None)
        if ed_df is not None and not ed_df.empty:
            close_s = close.dropna()
            if len(close_s) >= 40:
                close_idx = close_s.index
                # Keep only recent history for stability/performance
                event_dates_raw = pd.to_datetime(ed_df.index, errors="coerce").dropna()
                normed: list[pd.Timestamp] = []
                for d in event_dates_raw:
                    try:
                        ts = pd.Timestamp(d)
                        if ts.tzinfo is not None:
                            ts = ts.tz_localize(None)
                        normed.append(ts.normalize())
                    except Exception:
                        continue
                event_dates = sorted(list(set(normed)))[-16:]
                for ed in event_dates:
                    next_day = _next_trading_day(close_idx, ed)
                    if next_day is None:
                        continue
                    try:
                        pos = close_idx.get_loc(next_day)
                        if isinstance(pos, slice):
                            pos = pos.start
                        if pos is None or pos < 1 or pos + 1 >= len(close_idx):
                            continue
                        pre_close = float(close_s.iloc[pos - 1])
                        post_close = float(close_s.iloc[pos + 1])
                        if pre_close <= 0:
                            continue
                        signed_move = (post_close / pre_close - 1.0) * 100.0
                        abs_move = abs(signed_move)
                        if np.isfinite(abs_move):
                            event_rows.append({
                                "event_date": pd.to_datetime(ed).date().isoformat(),
                                "pre_close": round(pre_close, 2),
                                "post_close": round(post_close, 2),
                                "realized_move_pct": round(float(signed_move), 2),
                                "abs_move_pct": round(float(abs_move), 2),
                            })
                    except Exception:
                        continue
    except Exception as exc:
        logger.debug("Earnings target history fetch failed for %s: %s", ticker, exc)

    event_rows = sorted(event_rows, key=lambda x: x.get("event_date", ""))
    abs_moves = [float(r["abs_move_pct"]) for r in event_rows if r.get("abs_move_pct") is not None]

    eval_rows: list[dict] = []
    if len(event_rows) > 1:
        for i in range(1, len(event_rows)):
            hist = [float(x["abs_move_pct"]) for x in event_rows[max(0, i - 6):i] if x.get("abs_move_pct") is not None]
            if not hist:
                continue
            exp_i = float(np.mean(hist))
            realized_i = float(event_rows[i]["abs_move_pct"])
            eval_rows.append({
                "event_date": event_rows[i]["event_date"],
                "expected_move_pct": round(exp_i, 2),
                "realized_abs_move_pct": round(realized_i, 2),
                "hit": realized_i <= exp_i,
            })

    if len(abs_moves) == 0:
        fallback_move = max(3.0, min(12.0, float(close.pct_change().dropna().tail(20).std() * 100 * np.sqrt(2))))
        expected_move = round(fallback_move, 1)
        sample = 0
        hit_rate = None
        mae = None
        method_note = "Fallback from recent realized volatility (no earnings history available)"
    else:
        sample = len(abs_moves)
        hits = sum(1 for r in eval_rows if r.get("hit"))
        eval_n = len(eval_rows)
        hit_rate = round(hits / eval_n, 2) if eval_n > 0 else None
        mae = (
            round(
                float(np.mean([abs(float(r["realized_abs_move_pct"]) - float(r["expected_move_pct"])) for r in eval_rows])),
                2,
            )
            if eval_rows
            else None
        )
        expected_move = round(float(np.mean(abs_moves[-6:])), 1)
        method_note = f"Expected move from last {min(6, sample)} earnings reactions (1-day post-earnings)"

    upside = round(price * (1 + expected_move / 100), 2)
    downside = round(price * (1 - expected_move / 100), 2)

    if short_prob is None:
        bias = "Neutral"
        bias_prob = None
        directional = round(price, 2)
    else:
        bias_prob = round(short_prob * 100, 1)
        if short_prob >= 0.55:
            bias = "Bullish"
            directional = round(price * (1 + (expected_move * 0.55) / 100), 2)
        elif short_prob <= 0.45:
            bias = "Bearish"
            directional = round(price * (1 - (expected_move * 0.55) / 100), 2)
        else:
            bias = "Neutral"
            directional = round(price, 2)

    confidence = None
    if hit_rate is not None:
        sample_factor = min(1.0, sample / 8.0)
        confidence = int(round((hit_rate * 100) * sample_factor))

    out.update({
        "available": True,
        "expected_move_pct": expected_move,
        "upside_target": upside,
        "downside_target": downside,
        "directional_target": directional,
        "bias": bias,
        "bias_prob_pct": bias_prob,
        "historical_events": sample,
        "historical_avg_abs_move_pct": round(float(np.mean(abs_moves)), 1) if abs_moves else None,
        "historical_median_abs_move_pct": round(float(np.median(abs_moves)), 1) if abs_moves else None,
        "calibration_hit_rate": hit_rate,
        "calibration_mae_pct": mae,
        "confidence_pct": confidence,
        "backtest_events": len(eval_rows),
        "backtest_summary": (
            {
                "evaluated_events": len(eval_rows),
                "containment_hit_rate": hit_rate,
                "mean_abs_error_pct": mae,
            }
            if eval_rows
            else None
        ),
        "recent_events": event_rows[-5:] if event_rows else [],
        "method_note": method_note,
    })
    return out


def _tilt_universal_scenarios_for_hmm(
    scenarios: list[dict],
    hmm_probs: dict | None,
) -> None:
    """Soften bull/base/bear probabilities when HMM is bearish / transitional (see scenario_regime_aware)."""
    if not hmm_probs:
        return
    try:
        from signals.scenario_regime_aware import compute_regime_factor

        factor, desc = compute_regime_factor(
            hmm_probs.get("bull"),
            hmm_probs.get("bear"),
            hmm_probs.get("transition"),
        )
    except Exception:
        return
    if abs(factor - 1.0) < 1e-6:
        return
    for scen in scenarios:
        st = scen.get("scenario_type")
        if st not in ("bull", "base", "bear"):
            continue
        try:
            p = float(scen.get("probability", 0.05))
        except (TypeError, ValueError):
            p = 0.05
        if st == "bull":
            p *= factor
        elif st == "bear":
            p *= 2.0 - factor
        else:
            p *= 1.0 + (factor - 1.0) * 0.3
        scen["probability"] = round(min(0.95, max(0.05, p)), 2)
        scen["regime_hmm_factor"] = round(factor, 3)
        scen["regime_hmm_note"] = desc


def _build_scenarios(
    price: float,
    ml_prob_short: float | None,
    thr_short: float,
    asset_type: str,
    regime: str,
    vol_annual: float,
    macro: dict | None = None,
    earnings_info: dict | None = None,
    analyst_targets: dict | None = None,
    short_interest: dict | None = None,
    regime_hmm_probs: dict | None = None,
) -> list[dict]:
    """
    Build 5-6 scenarios: 3 universal (bull/base/bear) + up to 3 asset-specific.
    Each scenario gives a price target, return %, and probability estimate.

    macro: live context from _fetch_macro_context() — gates scenario probabilities
    earnings_info: from _fetch_earnings_info() — annotates earnings scenarios with timing
    regime_hmm_probs: optional dict with bull/bear/transition (0–1) — tilts universal scenario probs
    """
    ctx = macro or {}
    at  = analyst_targets or {}
    scenarios: list[dict] = []

    # Base ML probability
    base_prob = ml_prob_short or 0.40

    # ── Analyst target anchors (FMP consensus, when available) ─────────────
    # Use Wall Street median as the "base" target and high as the "bull" target.
    # If analyst targets are unavailable, fall back to synthetic ML multiples.
    analyst_median = at.get("median") or at.get("mean")
    analyst_high   = at.get("high")
    analyst_low    = at.get("low")
    analyst_count  = at.get("analyst_count")

    # Compute analyst-implied returns (for display/comparison)
    analyst_median_ret = round((analyst_median / price - 1) * 100, 1) if analyst_median and price > 0 else None
    analyst_high_ret   = round((analyst_high   / price - 1) * 100, 1) if analyst_high   and price > 0 else None
    analyst_low_ret    = round((analyst_low    / price - 1) * 100, 1) if analyst_low    and price > 0 else None

    # ── Macro-aware probability adjustments ─────────────────────────────────
    # VIX: high VIX suppresses bull probs, elevates bear probs
    vix = ctx.get("vix")
    vix_bull_adj  = 0.0
    vix_bear_adj  = 0.0
    if vix is not None:
        if vix > 30:
            vix_bull_adj = -0.10; vix_bear_adj = +0.15
        elif vix > 22:
            vix_bull_adj = -0.05; vix_bear_adj = +0.07
        elif vix < 14:
            vix_bull_adj = +0.05; vix_bear_adj = -0.05

    # Yield curve: inverted = recession risk, normal = expansion
    yc = ctx.get("yield_curve")
    yc_bear_adj = 0.0
    if yc is not None and yc < -0.25:
        yc_bear_adj = +0.08   # inverted curve: recession risk elevated

    # Fed rate: high rates suppress rate-sensitive bull scenarios
    fed = ctx.get("fed_rate")
    rate_cut_ready = fed is not None and fed >= 4.0   # room to cut
    rate_cut_prob_adj = +0.10 if rate_cut_ready else -0.05

    # CPI: high inflation = commodity bull, equity bear (rate hike risk)
    cpi = ctx.get("cpi_yoy")
    inflation_hot = cpi is not None and cpi > 3.5
    inflation_cool = cpi is not None and cpi < 2.5

    # ── Universal scenarios (bull / base / bear) ────────────────────────────
    for sk, sv in _UNIVERSAL_SCENARIOS.items():
        base_adj = sv["multipliers"]["prob_boost"]
        if sk == "bull":
            adj = base_adj + vix_bull_adj
        elif sk == "bear":
            adj = base_adj + vix_bear_adj + yc_bear_adj
        else:
            adj = base_adj

        adj_prob = min(0.95, max(0.05, base_prob + adj))

        # Analyst target anchoring:
        #   bull  → use analyst high target (Wall Street optimistic case)
        #   base  → use analyst median target (Wall Street consensus)
        #   bear  → always synthetic (analysts rarely model tail risk)
        if sk == "bull" and analyst_high is not None and analyst_high > price:
            target     = analyst_high
            adj_return = round((analyst_high / price - 1) * 100, 1)
            anchor_note = f"Analyst high target ${analyst_high:.2f}"
            if analyst_count:
                anchor_note += f" ({analyst_count} analysts)"
        elif sk == "base" and analyst_median is not None and analyst_median > 0:
            target     = analyst_median
            adj_return = round((analyst_median / price - 1) * 100, 1)
            anchor_note = f"Analyst median target ${analyst_median:.2f}"
            if analyst_count:
                anchor_note += f" ({analyst_count} analysts)"
        else:
            adj_return = thr_short * sv["multipliers"]["base"]
            if sk == "bear":
                adj_return = -(6.0 + vol_annual * 10)
            target     = round(price * (1 + adj_return / 100), 2)
            anchor_note = None

        # Build macro context note for transparency
        macro_note = _macro_note(sk, ctx, vix, yc, fed, cpi)
        if anchor_note:
            macro_note = anchor_note + (" · " + macro_note if macro_note else "")

        scenarios.append({
            "scenario_type":    sk,
            "name":             sv["name"],
            "trigger":          sv["trigger"],
            "rationale":        sv["rationale"],
            "probability":      round(adj_prob, 2),
            "price_target":     target,
            "return_pct":       round(adj_return, 1),
            "timeframe":        "1-3 months",
            "is_base":          sk == "base",
            "macro_note":       macro_note,
            "analyst_anchored": anchor_note is not None,
        })

    # ── Asset-specific scenarios ────────────────────────────────────────────
    si = short_interest or {}
    ml_bullish = (ml_prob_short or 0) >= 0.50

    specific = _ASSET_SCENARIOS.get(asset_type, _ASSET_SCENARIOS.get("EQUITY_US", []))
    for s in specific[:3]:
        extra_adj = 0.0
        sname = s["name"]
        si_note: str | None = None

        # ── Short interest gating for squeeze/institutional scenarios ──────
        if "Squeeze" in sname or "squeeze" in sname:
            try:
                from signals.short_interest import squeeze_probability_adj
                si_adj = squeeze_probability_adj(si if si else None, ml_bullish=ml_bullish)
                extra_adj += si_adj
                si_pct = si.get("short_pct")
                if si_pct is not None:
                    risk = si.get("squeeze_risk", "")
                    dtc  = si.get("days_to_cover")
                    dtc_str = f", {dtc:.1f}d DTC" if dtc else ""
                    si_note = (
                        f"Live SI: {si_pct*100:.1f}% of float ({risk}{dtc_str}) · "
                        f"{'probability boosted' if si_adj > 0 else 'probability suppressed — low short base'}"
                    )
                else:
                    si_note = "Short interest data unavailable — using default probability"
            except Exception:
                pass

        if "Institutional Exit" in sname and si.get("bear_signal"):
            extra_adj += 0.08   # rising SI trend confirms institutional positioning
            si_note = f"SI {si.get('short_pct', 0)*100:.1f}% and increasing — confirms institutional bearish conviction"

        # ── Rate-cut scenarios: gate on actual fed rate level ──────────────
        if "Rate Cut" in sname or "Dovish" in sname or "Pivot" in sname:
            extra_adj += rate_cut_prob_adj
            if rate_cut_ready:
                s = dict(s)
                s["trigger"] = s["trigger"] + f" (Fed currently at {fed:.2f}% — room to cut)"

        # ── Inflation scenarios ────────────────────────────────────────────
        if "Inflation" in sname and inflation_hot:
            extra_adj += 0.08
        if "USD Strength" in sname and ctx.get("dxy"):
            dxy = ctx["dxy"]
            if dxy > 105:
                extra_adj += 0.06
                s = dict(s)
                s["trigger"] = s["trigger"] + f" (DXY at {dxy:.1f} — dollar already strong)"

        # ── Earnings scenarios: annotate with actual date ──────────────────
        if "Earnings" in sname and earnings_info:
            days = earnings_info.get("days_until_earnings")
            note = earnings_info.get("earnings_note", "")
            if days is not None:
                s = dict(s)
                if days <= 21:
                    extra_adj += 0.05
                    s["trigger"] = s["trigger"] + f" — {note}"
                else:
                    s["trigger"] = s["trigger"] + f" ({note})"
            s["timeframe"] = (
                f"~{days}d (at earnings)" if days is not None and days <= 45 else "1-2 months"
            )

        adj_prob   = min(0.95, max(0.05, base_prob + s["prob_adj"] + extra_adj))
        adj_return = thr_short + s["return_adj"] * 100
        target     = round(price * (1 + adj_return / 100), 2)
        scenarios.append({
            "scenario_type": "specific",
            "name":          s["name"],
            "trigger":       s["trigger"],
            "rationale":     s["rationale"],
            "probability":   round(adj_prob, 2),
            "price_target":  target,
            "return_pct":    round(adj_return, 1),
            "timeframe":     s.get("timeframe", "1-2 months"),
            "is_base":       False,
            "si_note":       si_note,
        })

    _tilt_universal_scenarios_for_hmm(scenarios, regime_hmm_probs)

    # Sort by return (descending — bull to bear)
    scenarios.sort(key=lambda x: x["return_pct"], reverse=True)
    return scenarios


def _macro_note(
    scenario_key: str, ctx: dict,
    vix: float | None, yc: float | None,
    fed: float | None, cpi: float | None
) -> str:
    """Generate a short live-data annotation for the universal scenarios."""
    parts: list[str] = []
    if vix is not None:
        mood = "calm" if vix < 16 else "elevated" if vix < 25 else "fearful"
        parts.append(f"VIX {vix:.1f} ({mood})")
    if yc is not None:
        curve = "inverted ⚠️" if yc < 0 else "normal"
        parts.append(f"Yield curve {yc:+.2f}% ({curve})")
    if fed is not None:
        parts.append(f"Fed Funds {fed:.2f}%")
    if cpi is not None:
        parts.append(f"CPI {cpi:.1f}% YoY")
    if not parts:
        return ""
    return "Live macro: " + " · ".join(parts)


# ---------------------------------------------------------------------------
# Master function
# ---------------------------------------------------------------------------

def run_price_targets(
    ticker: str,
    period: str = "2y",
    market_regime: str = "NEUTRAL",
    config: dict | None = None,
) -> dict:
    """
    Compute consolidated buy/sell zones, expected returns, and scenario analysis.

    Calls:
      - fetch_ohlcv_dataframe / fetch_ohlcv_safe  (price data)
      - multi_horizon_scores                       (confidence + technical)
      - predict_all_horizons                       (ML multi-horizon probs)
      - classify_asset                             (asset type for scenarios)
    """
    from signals.fetcher import fetch_ohlcv_dataframe, fetch_ohlcv_safe
    from signals.indicators import multi_horizon_scores

    df    = fetch_ohlcv_dataframe(ticker, period)
    close = fetch_ohlcv_safe(ticker, period)

    if close is None or len(close) < 20:
        return {"ticker": ticker, "error": "Insufficient price history", "horizons": {}, "scenarios": []}

    lv = _extract_levels(df, close)
    price = lv.get("current_price", 0)
    if price == 0:
        return {"ticker": ticker, "error": "No current price", "horizons": {}, "scenarios": []}

    # ── Technical composite ────────────────────────────────────────────────
    sig = multi_horizon_scores(close, market_regime=market_regime)
    composite   = float(sig.get("composite_buy") or 50)
    confluence  = float(sig.get("confluence_score") or composite)

    # ── ML horizon probabilities ───────────────────────────────────────────
    ml_horizons: dict = {}
    try:
        from signals.ml_models import predict_all_horizons
        if df is not None and not df.empty:
            ml_horizons = predict_all_horizons(ticker, df, inference_only=True) or {}
    except Exception as e:
        logger.debug("ML horizons failed for %s: %s", ticker, e)

    # ── Asset classification ───────────────────────────────────────────────
    asset_type = "EQUITY_US"
    try:
        from signals.pre_flight import classify_asset
        cls = classify_asset(ticker)
        asset_type = cls.asset_type.value
    except Exception:
        pass

    # ── Per-horizon targets ────────────────────────────────────────────────
    horizons_out: dict = {}
    horizon_keys = ["short", "medium", "long"]
    for hk in horizon_keys:
        hdata = ml_horizons.get(hk, {})
        if not hdata:
            # Build a synthetic horizon entry even without ML
            thr = {"short": 5.0, "medium": 8.0, "long": 12.0}[hk]
            days_map = {"short": 20, "medium": 60, "long": 120}
            label_map = {"short": "~1 month", "medium": "~3 months", "long": "~6 months"}
            hdata = {
                "prob": None, "threshold_pct": thr,
                "horizon_days": days_map[hk], "label": label_map[hk],
                "description": hk.capitalize() + "-term",
                "interpretation": "Unavailable",
            }
        horizons_out[hk] = _horizon_targets(lv, hdata, market_regime, hk, ticker=ticker.upper())

    # ── Short interest (FINRA via yfinance) — gates squeeze scenario ─────
    si_data: dict | None = None
    try:
        from signals.short_interest import fetch_short_interest
        si_data = fetch_short_interest(ticker)
        logger.debug("Short interest for %s: %s", ticker, si_data)
    except Exception as _sie:
        logger.debug("Short interest failed for %s: %s", ticker, _sie)

    # ── FMP analyst price target consensus (GAP C fix) ───────────────────
    # fetch_price_target_consensus returns {high, low, median} Wall Street targets.
    # We use this to anchor the bull-case scenario target rather than a synthetic multiple.
    analyst_targets: dict = {}
    if config:
        try:
            from signals.fmp_client import fetch_price_target_consensus, get_api_key
            if get_api_key(config):
                pt, _pt_err = fetch_price_target_consensus(config, ticker)
                if pt and isinstance(pt, dict):
                    for k in ("targetHigh", "targetLow", "targetMedian", "targetMean",
                              "priceTargetHigh", "priceTargetLow", "priceTargetMedian"):
                        v = pt.get(k)
                        if v is not None:
                            try:
                                simple_k = k.replace("priceTarget", "").replace("target", "").lower()
                                analyst_targets[simple_k] = round(float(v), 2)
                            except (TypeError, ValueError):
                                pass
                    # Also try analyst count
                    for ck in ("numberOfAnalysts", "numAnalysts", "analysts"):
                        c = pt.get(ck)
                        if c is not None:
                            try:
                                analyst_targets["analyst_count"] = int(c)
                            except (TypeError, ValueError):
                                pass
        except Exception as _ate:
            logger.debug("FMP price target fetch for %s: %s", ticker, _ate)

    # Compute analyst-implied returns (for display) safely in this scope
    analyst_median = analyst_targets.get("median") or analyst_targets.get("mean")
    analyst_high   = analyst_targets.get("high")
    analyst_low    = analyst_targets.get("low")
    analyst_median_ret = round((float(analyst_median) / price - 1) * 100, 1) if analyst_median and price > 0 else None
    analyst_high_ret   = round((float(analyst_high)   / price - 1) * 100, 1) if analyst_high   and price > 0 else None
    analyst_low_ret    = round((float(analyst_low)    / price - 1) * 100, 1) if analyst_low    and price > 0 else None

    # ── Live macro context (VIX, 10Y, Fed rate, CPI, DXY) ────────────────
    macro = _fetch_macro_context(config)
    logger.debug("Macro context for %s: %s", ticker, macro)

    # ── Earnings timing ───────────────────────────────────────────────────
    earnings_info = _fetch_earnings_info(ticker)

    # ── HMM regime (for scenario probability tilt — same object as dashboard HMM) ──
    regime_hmm_probs: dict | None = None
    try:
        from signals.hmm_regime import get_hmm_regime

        vol_series = df["volume"] if df is not None and "volume" in df.columns else None
        vix_live = macro.get("vix") if isinstance(macro, dict) else None
        hr = get_hmm_regime(ticker, close, volume=vol_series, vix=vix_live)
        if hr and not hr.get("error"):
            regime_hmm_probs = {
                "bull": hr.get("bull_probability"),
                "bear": hr.get("bear_probability"),
                "transition": hr.get("transition_probability"),
            }
    except Exception as _hmm_sc:
        logger.debug("HMM regime for scenario tilt failed %s: %s", ticker, _hmm_sc)

    # ── Scenario engine ────────────────────────────────────────────────────
    short_prob = ml_horizons.get("short", {}).get("prob")
    short_thr  = float(ml_horizons.get("short", {}).get("threshold_pct", 5.0))
    vol        = lv.get("vol_annual", 0.25)
    scenarios  = _build_scenarios(
        price, short_prob, short_thr, asset_type, market_regime, vol,
        macro=macro, earnings_info=earnings_info,
        analyst_targets=analyst_targets,
        short_interest=si_data,
        regime_hmm_probs=regime_hmm_probs,
    )
    earnings_target = _compute_earnings_target_block(
        ticker,
        price=price,
        close=close,
        short_prob=short_prob,
        earnings_info=earnings_info,
    )

    return {
        "ticker":          ticker,
        "analysis_date":   datetime.utcnow().strftime("%Y-%m-%d"),
        "current_price":   price,
        "market_regime":   market_regime,
        "asset_type":      asset_type,
        "confluence_score": round(confluence, 1),
        "macro_context": {
            "vix":         macro.get("vix"),
            "yield_10y":   macro.get("yield_10y"),
            "yield_2y":    macro.get("yield_2y"),
            "yield_curve": macro.get("yield_curve"),
            "fed_rate":    macro.get("fed_rate"),
            "cpi_yoy":     macro.get("cpi_yoy"),
            "dxy":         macro.get("dxy"),
            "note": "Live macro data used to gate scenario probabilities",
        },
        "earnings_info": earnings_info,
        "technical_levels": {
            "ma50":    lv.get("ma50"),
            "ma200":   lv.get("ma200"),
            "low_52w": lv.get("low_52w"),
            "high_52w": lv.get("high_52w"),
            "note": (
                "MA50 = short-term dip-buy anchor · "
                "MA200 = medium-term structural support · "
                "52w-low = last line of defence before thesis invalidation"
            ),
        },
        "short_interest": si_data,
        "analyst_targets": {
            "median":         analyst_targets.get("median"),
            "high":           analyst_targets.get("high"),
            "low":            analyst_targets.get("low"),
            "analyst_count":  analyst_targets.get("analyst_count"),
            "median_return":  analyst_median_ret,
            "high_return":    analyst_high_ret,
            "low_return":     analyst_low_ret,
            "available":      bool(analyst_targets),
            "note": (
                f"Wall Street consensus from {analyst_targets.get('analyst_count', '?')} analysts via FMP"
                if analyst_targets else
                "Analyst targets unavailable — using ML-derived synthetic targets"
            ),
        },
        "earnings_target": earnings_target,
        "horizons":  horizons_out,
        "scenarios": scenarios,
    }
