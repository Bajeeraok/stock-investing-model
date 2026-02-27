"""
ConfidenceEngine — 7-layer signal confluence for Thrive Alpha.

North star: retail investors need calibrated confidence, not just "buy".
They need: why, what could go wrong, how confident the model is, what to watch.

Seven signal layers (each 0-1, missing layers are skipped with weight renormalized):
  1. regime_hmm         (0.15) — HMM bull-state probability
  2. pattern_technical  (0.15) — Near-bottom pattern score + composite technical score
  3. lgbm_probability   (0.20) — LightGBM P(10%+ gain in 20 days)
  4. options_sentiment  (0.15) — Put/call ratio, IV rank (contrarian)
  5. insider_signal     (0.15) — Net insider buying from SEC Form 4
  6. fundamental_score  (0.10) — Valuation + quality (from existing FMP data)
  7. nlp_sentiment      (0.10) — Stub (FinBERT pending; falls back gracefully)

Hard disqualifiers (override final score):
  - HMM bear probability > 0.80  → ×0.40 (deep bear regime)
  - Net insider selling > 80%    → ×0.60 (institutional conviction against)

Returns:
  confidence (0-1), component scores dict, labels dict, disqualifiers list,
  risk_factors list, watch_levels dict
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

WEIGHTS: dict[str, float] = {
    "regime_hmm":        0.15,
    "pattern_technical": 0.15,
    "lgbm_probability":  0.20,
    "options_sentiment": 0.15,
    "insider_signal":    0.15,
    "fundamental_score": 0.10,
    "nlp_sentiment":     0.10,
}


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class ConfidenceEngine:
    """
    Computes a calibrated confidence score (0-1) from all available signal layers.

    Usage:
        engine = ConfidenceEngine()
        result = engine.compute(
            ticker="NVDA",
            df=ohlcv_df,
            composite_score=75.0,
            market_regime="BULL",
            config=app_config,
            vix=18.5,
        )
        # result["confidence"], result["breakdown"], result["action"]
    """

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or WEIGHTS

    def compute(
        self,
        ticker: str,
        df: pd.DataFrame | None,
        composite_score: float,        # 0-100 from multi_horizon_scores()
        market_regime: str = "NEUTRAL",
        config: dict | None = None,
        vix: float | None = None,
        close: pd.Series | None = None,
        volume: pd.Series | None = None,
        val_score: float | None = None,   # from composite_score output
        qlt_score: float | None = None,   # from composite_score output
    ) -> dict:
        """
        Compute full confidence score. Each layer degrades gracefully to None
        when data is unavailable; weights are renormalized over available layers.
        """
        scores:   dict[str, float | None] = {}
        labels:   dict[str, str]          = {}
        details:  dict[str, Any]          = {}

        close_s = close if close is not None else (df["close"] if df is not None and "close" in df.columns else None)
        vol_s   = volume if volume is not None else (df["volume"] if df is not None and "volume" in df.columns else None)

        # ── Layer 1: HMM regime ────────────────────────────────────────────
        if close_s is not None and len(close_s) >= 252:
            from signals.hmm_regime import get_hmm_regime
            hmm = get_hmm_regime(ticker, close_s, vol_s)
            if hmm and not hmm.get("error"):
                scores["regime_hmm"] = hmm["bull_probability"]
                labels["regime_hmm"] = (
                    f"Bull {hmm['bull_probability']*100:.0f}% / "
                    f"Trans {hmm['transition_probability']*100:.0f}% / "
                    f"Bear {hmm['bear_probability']*100:.0f}%"
                )
                details["hmm"] = hmm
            else:
                # Fall back to MA-based regime proxy
                scores["regime_hmm"] = _regime_to_prob(market_regime)
                labels["regime_hmm"] = f"{market_regime} regime (MA-based fallback)"
        else:
            scores["regime_hmm"] = _regime_to_prob(market_regime)
            labels["regime_hmm"] = f"{market_regime} (no HMM — insufficient history)"

        # ── Layer 2: Pattern + technical ─────────────────────────────────
        if df is not None and not df.empty:
            from signals.pattern_signals import near_bottom_score
            p_score, p_signals, _ = near_bottom_score(df, ticker)
            # Blend pattern (40%) with composite technical (60%)
            tech_norm = composite_score / 100.0
            pattern_norm = p_score / 100.0
            blended = 0.40 * pattern_norm + 0.60 * tech_norm
            scores["pattern_technical"] = round(blended, 3)
            labels["pattern_technical"] = (
                f"Pattern {p_score:.0f}/100; technical {composite_score:.0f}/100"
                + (f" — {p_signals[0]}" if p_signals else "")
            )
        else:
            scores["pattern_technical"] = round(composite_score / 100.0, 3)
            labels["pattern_technical"] = f"Technical score {composite_score:.0f}/100 (no OHLCV for pattern)"

        # ── Layer 3: LightGBM probability ────────────────────────────────
        # Catches ImportError (lightgbm not installed) and OSError (libgomp.so.1
        # missing on slim Docker images — fixed by adding libgomp1 to Dockerfile,
        # but we degrade gracefully in the meantime so the engine still runs).
        if df is not None:
            try:
                from signals.ml_models import predict_probability
                lgbm_prob = predict_probability(ticker, df)
                if lgbm_prob is not None:
                    scores["lgbm_probability"] = lgbm_prob
                    labels["lgbm_probability"] = f"{lgbm_prob*100:.0f}% prob of 10%+ gain in 20d"
                else:
                    logger.debug("LGBM model not trained for %s — skipping layer", ticker)
            except (ImportError, OSError) as e:
                logger.warning("LightGBM unavailable (%s) — skipping layer for %s", type(e).__name__, ticker)
            except Exception as e:
                logger.warning("LightGBM predict failed for %s: %s — skipping layer", ticker, e)

        # ── Layer 4: Options sentiment ────────────────────────────────────
        _ETFS = {"SPY", "QQQ", "GLD", "SLV", "IWM", "DIA", "VOO", "VTI",
                 "XLE", "XLF", "XLI", "XLB", "XLU", "XLP"}
        if ticker.upper() not in _ETFS:
            from signals.options_signals import fetch_options_signals
            opts = fetch_options_signals(ticker)
            if "options_score" in opts and not opts.get("error"):
                scores["options_sentiment"] = opts["options_score"]
                labels["options_sentiment"] = opts.get("options_label", "options data")
                details["options"] = opts
        else:
            # ETFs: use VIX as fear proxy if available
            if vix is not None:
                vix_score = max(0.3, min(0.8, 1.0 - (vix - 15) / 40))
                scores["options_sentiment"] = round(vix_score, 3)
                labels["options_sentiment"] = f"VIX {vix:.1f} proxy (ETF — no single-stock options)"

        # ── Layer 5: Insider signal ───────────────────────────────────────
        insider_result = _score_insider(ticker)
        if insider_result is not None:
            scores["insider_signal"] = insider_result["score"]
            labels["insider_signal"] = insider_result["label"]
            details["insider"] = insider_result

        # ── Layer 6: Fundamental score ────────────────────────────────────
        if val_score is not None and qlt_score is not None:
            fund = round((0.6 * val_score + 0.4 * qlt_score) / 100.0, 3)
            scores["fundamental_score"] = fund
            labels["fundamental_score"] = f"Valuation {val_score:.0f}/100, Quality {qlt_score:.0f}/100"
        elif val_score is not None:
            scores["fundamental_score"] = round(val_score / 100.0, 3)
            labels["fundamental_score"] = f"Valuation {val_score:.0f}/100 (quality n/a)"
        else:
            # Normalized composite as fallback
            scores["fundamental_score"] = round(composite_score / 100.0 * 0.7, 3)
            labels["fundamental_score"] = "Composite score proxy (FMP data n/a)"

        # ── Layer 7: NLP sentiment (stub) ─────────────────────────────────
        # FinBERT integration pending. Transformers library is too large to add
        # without user opt-in. This layer is intentionally excluded until ready.
        # scores["nlp_sentiment"] = _finbert_score(ticker)
        labels["nlp_sentiment"] = "NLP sentiment (FinBERT — pending integration)"

        # ── Weighted confidence (renormalize over available layers) ────────
        available = {k: v for k, v in scores.items() if v is not None}
        total_w   = sum(self.weights[k] for k in available)
        if total_w == 0:
            confidence = 0.5
        else:
            confidence = sum(available[k] * self.weights[k] for k in available) / total_w

        # ── Hard disqualifiers ─────────────────────────────────────────────
        disqualifiers: list[str] = []

        hmm_data = details.get("hmm", {})
        if hmm_data.get("bear_probability", 0) > 0.80:
            confidence *= 0.40
            disqualifiers.append(
                f"HMM bear probability {hmm_data['bear_probability']*100:.0f}% — "
                "deep bear regime detected, confidence suppressed 60%"
            )

        insider_data = details.get("insider", {})
        if insider_data.get("sell_ratio", 0) > 0.80:
            confidence *= 0.60
            disqualifiers.append(
                "Heavy net insider selling (>80% of activity) — "
                "institutional conviction against; confidence suppressed 40%"
            )

        confidence = round(float(np.clip(confidence, 0.0, 1.0)), 3)

        # ── Action label ───────────────────────────────────────────────────
        action = _confidence_to_action(confidence)

        # ── Risk factors and watch levels ──────────────────────────────────
        risk_factors = _build_risk_factors(
            scores, market_regime, vix, disqualifiers, composite_score
        )
        watch_levels = _build_watch_levels(df, composite_score)

        return {
            "ticker":          ticker,
            "confidence":      confidence,
            "action":          action,
            "breakdown":       {
                k: {
                    "score": round(available.get(k, 0.0), 3) if k in available else None,
                    "weight": self.weights[k],
                    "label": labels.get(k, ""),
                    "available": k in available,
                }
                for k in self.weights
            },
            "disqualifiers":   disqualifiers,
            "risk_factors":    risk_factors,
            "watch_levels":    watch_levels,
            "market_regime":   market_regime,
            "n_layers_active": len(available),
        }


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def run_confidence(
    ticker: str,
    period: str = "2y",
    market_regime: str = "NEUTRAL",
    config: dict | None = None,
    vix: float | None = None,
) -> dict:
    """
    Fetch all required data and run ConfidenceEngine in one call.
    Suitable for API routes and scripting.
    """
    from signals.fetcher import fetch_ohlcv_dataframe, fetch_ohlcv_safe
    from signals.indicators import multi_horizon_scores

    df    = fetch_ohlcv_dataframe(ticker, period)
    close = fetch_ohlcv_safe(ticker, period)

    composite_score = 50.0
    val_score = qlt_score = None
    if close is not None:
        sig = multi_horizon_scores(close, market_regime=market_regime, vix=vix)
        composite_score = float(sig.get("composite_buy") or 50)
        val_score = sig.get("val_score")
        qlt_score = sig.get("qlt_score")

    engine = ConfidenceEngine()
    return engine.compute(
        ticker=ticker,
        df=df,
        composite_score=composite_score,
        market_regime=market_regime,
        config=config,
        vix=vix,
        close=close,
        val_score=val_score,
        qlt_score=qlt_score,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _regime_to_prob(regime: str) -> float:
    """Map MA-based regime string to bull probability proxy."""
    return {
        "STRONG_BULL": 0.90, "BULL": 0.75, "NEUTRAL": 0.50,
        "TRANSITION":  0.45, "BEAR": 0.25, "STRONG_BEAR": 0.10,
    }.get(regime, 0.50)


def _score_insider(ticker: str) -> dict | None:
    """
    Score insider activity from edgar_insider.py output.
    Returns score 0-1 (1 = strong net buying), or None if unavailable.
    """
    try:
        from signals.edgar_insider import run_insider_flow
        result = run_insider_flow([ticker], days_lookback=90)
        activities = result.get("ticker_activities", [])
        ticker_act = next((a for a in activities if a["ticker"] == ticker), None)
        if ticker_act is None:
            return None

        buys  = int(ticker_act.get("buys_shares", 0) or 0)
        sells = int(ticker_act.get("sells_shares", 0) or 0)
        total = buys + sells
        if total == 0:
            return {"score": 0.5, "label": "No insider activity (90d)", "sell_ratio": 0.0}

        buy_ratio  = buys / total
        sell_ratio = sells / total

        # Score: strong buying → 0.9, neutral → 0.5, strong selling → 0.1
        score = 0.1 + 0.8 * buy_ratio

        label = (
            f"Net buying {buy_ratio*100:.0f}% of activity ({buys:,} shares bought)" if buy_ratio > 0.6 else
            f"Net selling {sell_ratio*100:.0f}% of activity ({sells:,} shares sold)" if sell_ratio > 0.6 else
            f"Mixed insider activity ({buys:,} bought, {sells:,} sold)"
        )

        return {"score": round(score, 3), "label": label, "sell_ratio": sell_ratio}
    except Exception as exc:
        logger.debug("Insider signal failed for %s: %s", ticker, exc)
        return None


def _confidence_to_action(confidence: float) -> str:
    if confidence >= 0.80: return "STRONG BUY"
    if confidence >= 0.65: return "BUY"
    if confidence >= 0.45: return "HOLD / WATCH"
    if confidence >= 0.30: return "REDUCE"
    return "AVOID"


def _build_risk_factors(
    scores: dict,
    market_regime: str,
    vix: float | None,
    disqualifiers: list[str],
    composite_score: float,
) -> list[str]:
    risks = list(disqualifiers)
    if market_regime in ("BEAR", "STRONG_BEAR"):
        risks.append(f"Macro regime is {market_regime} — counter-trend trades carry elevated risk")
    if vix is not None and vix > 28:
        risks.append(f"VIX {vix:.1f} — extreme volatility, size down and widen stops")
    if composite_score < 40:
        risks.append("Technical score weak — no momentum confirmation yet")
    hmm_val = scores.get("regime_hmm")
    if hmm_val is not None and hmm_val < 0.40:
        risks.append("HMM assigns <40% probability to bull state — regime is uncertain")
    lgbm_val = scores.get("lgbm_probability")
    if lgbm_val is not None and lgbm_val < 0.35:
        risks.append(f"ML model gives only {lgbm_val*100:.0f}% probability of 10%+ gain — weak ML signal")
    return risks


def _build_watch_levels(df: pd.DataFrame | None, composite_score: float) -> dict:
    """Key price levels to watch for thesis invalidation."""
    if df is None or "close" not in df.columns or df.empty:
        return {}
    close = df["close"].dropna()
    price = float(close.iloc[-1])
    ma50  = float(close.rolling(50, min_periods=20).mean().iloc[-1])
    ma200 = float(close.rolling(200, min_periods=60).mean().iloc[-1])
    low_52w = float(close.rolling(252, min_periods=60).min().iloc[-1])
    return {
        "current_price":     round(price, 2),
        "invalidation_below": round(low_52w * 0.97, 2),   # 3% below 52w low = thesis broken
        "key_support_ma50":   round(ma50, 2),
        "key_support_ma200":  round(ma200, 2),
        "note": (
            "Break below 52-week low (×0.97) invalidates the setup — exit if breached. "
            "MA50 and MA200 are key support levels to watch."
        ),
    }
