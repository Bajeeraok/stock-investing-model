"""
ConfidenceEngine — 7-layer signal confluence for Thrive Alpha.

North star: retail investors need calibrated confidence, not just "buy".
They need: why, what could go wrong, how confident the model is, what to watch.

Seven signal layers (each 0-1, missing layers are skipped with weight renormalized):
  1. regime_hmm         — HMM bull-state probability
  2. pattern_technical  — Near-bottom pattern score + composite technical score
  3. lgbm_probability   — LightGBM P(threshold gain), **short horizon only** (not avg of S/M/L)
  4. options_sentiment  — Put/call ratio, IV rank (**contrarian**: high P/C nudges score up as “fear”)
  5. insider_signal     — Net insider buying from SEC Form 4
  6. fundamental_score  — Valuation + quality (from existing FMP data)
  7. nlp_sentiment      — FMP headlines + keyword lexicon, optional FMP per-article scores; else Alpha Vantage; else Yahoo Finance headlines + lexicon (no API key)

Weights are now ASSET-TYPE-AWARE via the pre-flight classifier:
  - ETF_VOLATILITY (UVXY) → INCOMPATIBLE, returns early
  - ETF_COMMODITY (GLD)   → regime 35%, no insider/fundamentals/news
  - ETF_EQUITY (ARKK/QQQ) → no insider/fundamentals/news
  - EQUITY_ADR (BABA)     → insider disabled, ML+options elevated
  - EQUITY_SPECULATIVE    → options elevated, fundamentals reduced
  - EQUITY_DEFENSIVE (KO) → fundamentals+insider elevated
  - EQUITY_US             → standard 7-layer profile

Hard disqualifiers (override final score):
  - HMM bear probability > 0.80  → configurable mult (see config confidence.regime_blend); eased toward 1.0 to limit stacked leverage
  - Net insider selling > 80%    → ×0.60 (institutional conviction against)

Returns:
  confidence (0-1), component scores dict, labels dict, disqualifiers list,
  risk_factors list, watch_levels dict, pre_flight dict (coherence + playbook)
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Fallback weights (overridden per-asset by the pre-flight classifier)
WEIGHTS: dict[str, float] = {
    "regime_hmm":        0.11,
    "pattern_technical": 0.15,
    "lgbm_probability":  0.18,
    "options_sentiment": 0.14,
    "insider_signal":    0.14,
    "fundamental_score": 0.14,
    "nlp_sentiment":     0.14,
}

# Maps pre_flight weight profile keys → engine layer keys
_PF_TO_ENGINE: dict[str, str] = {
    "regime":       "regime_hmm",
    "pattern":      "pattern_technical",
    "ml":           "lgbm_probability",
    "options":      "options_sentiment",
    "insider":      "insider_signal",
    "fundamentals": "fundamental_score",
    "news":         "nlp_sentiment",
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
        Asset-type-aware weights are loaded from the pre-flight classifier.
        """
        # ── Pre-flight asset classification ───────────────────────────────
        try:
            from signals.pre_flight import classify_asset as _classify_asset
            classification = _classify_asset(ticker)
        except Exception as _ce:
            logger.debug("Pre-flight classify failed for %s: %s", ticker, _ce)
            classification = None

        # INCOMPATIBLE instruments (UVXY, VXX, VIXY) get blocked immediately
        if classification is not None and not classification.is_scoreable:
            return _incompatible_result(ticker, classification)

        # Build effective weights from asset-type weight profile
        if classification is not None:
            wp = classification.weight_profile
            effective_weights = {
                _PF_TO_ENGINE[pf_key]: getattr(wp, pf_key)
                for pf_key in ("regime", "pattern", "ml", "options", "insider", "fundamentals", "news")
            }
        else:
            effective_weights = dict(self.weights)

        scores:   dict[str, float | None] = {}
        labels:   dict[str, str]          = {}
        details:  dict[str, Any]          = {}

        close_s = close if close is not None else (df["close"] if df is not None and "close" in df.columns else None)
        vol_s   = volume if volume is not None else (df["volume"] if df is not None and "volume" in df.columns else None)

        # ── Layer 1: HMM regime ────────────────────────────────────────────
        if close_s is not None and len(close_s) >= 252:
            from signals.hmm_regime import get_hmm_regime
            # Earnings-aware regime validation (Scenario 5 alignment):
            # within 5 days post-earnings, a sharp selloff can make HMM lag.
            # We compute context cheaply from existing close series + cached earnings date lookup.
            days_since_earnings = None
            post_earnings_return_pct = None
            post_earnings_volume_ratio = None
            most_recent_earnings_date = None
            try:
                from signals.providers import get_most_recent_earnings
                e = get_most_recent_earnings(ticker, config)
                if e and e.get("days_since") is not None and e.get("date"):
                    most_recent_earnings_date = str(e["date"])
                    days_since_earnings = int(e["days_since"])
                    # Approximate post-earnings return since last earnings date.
                    # Uses last close on/before the earnings date as baseline.
                    try:
                        e_dt = pd.Timestamp(str(e["date"]))
                        c = close_s.dropna()
                        idx = c.index
                        if isinstance(idx, pd.DatetimeIndex) and getattr(idx, "tz", None) is not None:
                            c = c.copy()
                            c.index = c.index.tz_localize(None)
                        v = None
                        if vol_s is not None:
                            v = vol_s.dropna()
                            if isinstance(v.index, pd.DatetimeIndex) and getattr(v.index, "tz", None) is not None:
                                v = v.copy()
                                v.index = v.index.tz_localize(None)
                        baseline = c.loc[c.index <= e_dt]
                        if not baseline.empty:
                            base_close = float(baseline.iloc[-1])
                            last_close = float(c.iloc[-1])
                            if base_close > 0:
                                post_earnings_return_pct = (last_close / base_close - 1.0) * 100.0
                        # Volume ratio: first trading day after earnings vs prior 20d avg
                        if v is not None and not v.empty:
                            pre = v.loc[v.index <= e_dt].tail(20)
                            post = v.loc[v.index > e_dt]
                            if not pre.empty and not post.empty:
                                pre_avg = float(pre.mean())
                                post_day = float(post.iloc[0])
                                if pre_avg > 0:
                                    post_earnings_volume_ratio = post_day / pre_avg
                    except Exception:
                        pass
            except Exception:
                pass

            earnings_context = {
                "most_recent_earnings_date": most_recent_earnings_date,
                "days_since_earnings": days_since_earnings,
                "post_earnings_return_pct": round(float(post_earnings_return_pct), 2) if post_earnings_return_pct is not None else None,
                "post_earnings_volume_ratio": round(float(post_earnings_volume_ratio), 2) if post_earnings_volume_ratio is not None else None,
            }

            hmm = get_hmm_regime(
                ticker,
                close_s,
                vol_s,
                most_recent_earnings_date=most_recent_earnings_date,
                days_since_earnings=days_since_earnings,
                post_earnings_return_pct=post_earnings_return_pct,
                post_earnings_volume_ratio=post_earnings_volume_ratio,
            )
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
                bull_p = _regime_to_prob(market_regime)
                scores["regime_hmm"] = bull_p
                labels["regime_hmm"] = f"{market_regime} regime (MA-based fallback)"
                # Keep a minimal HMM payload so the pre-flight playbook can still be earnings-aware.
                details["hmm"] = {
                    "bull_probability": bull_p,
                    "transition_probability": round(max(0.0, 1.0 - bull_p) * 0.6, 3),
                    "bear_probability": round(max(0.0, 1.0 - bull_p) * 0.4, 3),
                    "dominant_state": market_regime if market_regime in ("BULL", "BEAR", "TRANSITION", "STRONG_BULL") else "TRANSITION",
                    "dominant_state_validated": market_regime if market_regime in ("BULL", "BEAR", "TRANSITION", "STRONG_BULL") else "TRANSITION",
                    "ma_conflict": None,
                    "earnings_context": earnings_context,
                    "error": (hmm or {}).get("error") if isinstance(hmm, dict) else "HMM unavailable",
                }
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
        ml_horizons: dict | None = None
        if df is not None:
            try:
                from signals.ml_models import predict_all_horizons
                from signals.probability_calibration import apply_calibration_to_ml_horizons

                ml_horizons = predict_all_horizons(ticker, df, config=config)
                ml_horizons = apply_calibration_to_ml_horizons(ml_horizons, config)
                # Use short-term probability as the layer score
                short = ml_horizons.get("short", {})
                lgbm_prob = short.get("prob")
                if lgbm_prob is not None:
                    ml_adj = float(lgbm_prob)
                    ml_cfg = (config or {}).get("confidence", {}).get("ml_short_horizon", {}) or {}
                    if ml_cfg.get("shrink_neutral_band", True):
                        lo = float(ml_cfg.get("neutral_low", 0.38))
                        hi = float(ml_cfg.get("neutral_high", 0.58))
                        pull = float(ml_cfg.get("neutral_pull_to_50_factor", 0.55))
                        if lo <= ml_adj <= hi:
                            ml_adj = 0.5 + (ml_adj - 0.5) * pull
                            ml_adj = round(float(np.clip(ml_adj, 0.0, 1.0)), 3)
                    scores["lgbm_probability"] = ml_adj
                    thr = short.get("threshold_pct", 5)
                    cal_note = " (calibrated)" if short.get("prob_raw") is not None else ""
                    nb_note = ""
                    if ml_adj != float(lgbm_prob):
                        nb_note = " · neutral-band shrink (mid-range 20d prob pulled toward 50%)"
                    labels["lgbm_probability"] = (
                        f"{ml_adj*100:.0f}% layer score from {lgbm_prob*100:.0f}% raw P({thr}%+ in 20d){cal_note} "
                        f"({short.get('interpretation', '')}) — short-horizon momentum, not full thesis confidence"
                        f"{nb_note}"
                    )
                else:
                    logger.debug("LGBM model not trained for %s — skipping layer", ticker)
            except (ImportError, OSError) as e:
                logger.warning("LightGBM unavailable (%s) — skipping layer for %s", type(e).__name__, ticker)
            except Exception as e:
                logger.warning("LightGBM predict failed for %s: %s — skipping layer", ticker, e)

        # ── Layer 4: Options sentiment ────────────────────────────────────
        # Equity index/ sector ETFs: use VIX proxy (no single-stock options). GLD/SLV have active
        # options — fetch from Tradier so commodity ETF positioning is visible.
        _ETFS_VIX_PROXY = {"SPY", "QQQ", "IWM", "DIA", "VOO", "VTI",
                          "XLE", "XLF", "XLI", "XLB", "XLU", "XLP"}
        if ticker.upper() not in _ETFS_VIX_PROXY:
            from signals.options_signals import fetch_options_signals

            hmm_bear_p: float | None = None
            _hd = details.get("hmm")
            if isinstance(_hd, dict) and _hd.get("bear_probability") is not None:
                try:
                    hmm_bear_p = float(_hd["bear_probability"])
                except (TypeError, ValueError):
                    hmm_bear_p = None
            opt_mode = str((config or {}).get("confidence", {}).get("options_pc_mode") or "auto").lower()
            opts = fetch_options_signals(
                ticker,
                hmm_bear_probability=hmm_bear_p,
                options_pc_mode=opt_mode,
            )
            details["options"] = opts
            if not opts.get("error") and opts.get("options_score") is not None:
                scores["options_sentiment"] = opts["options_score"]
                labels["options_sentiment"] = opts.get("options_label", "options data")
            elif opts.get("error"):
                # Omit layer so weight redistributes — do not inject neutral 0.5 as signal
                labels["options_sentiment"] = (
                    (opts.get("options_label") or "Options data unavailable")
                    + " — layer skipped (weight redistributed)"
                )
        else:
            # ETFs: use VIX as fear proxy if available — honest "estimated" until single-stock options exist
            if vix is not None:
                vix_score = max(0.3, min(0.8, 1.0 - (vix - 15) / 40))
                scores["options_sentiment"] = round(vix_score, 3)
                labels["options_sentiment"] = f"VIX {vix:.1f} proxy (ETF — no single-stock options) (estimated)"

        # ── Layer 5: Insider signal ───────────────────────────────────────
        insider_result = _score_insider(ticker)
        if insider_result is not None:
            scores["insider_signal"] = insider_result["score"]
            labels["insider_signal"] = insider_result["label"]
            details["insider"] = insider_result

        # ── Layer 6: Fundamental score ────────────────────────────────────
        # Priority: (1) FMP key_metrics val+qlt + EPS consensus adjustment
        #           (2) yfinance info fallback
        #           (3) composite score proxy
        analyst_est: dict | None = None
        if config:
            analyst_est = _fetch_analyst_estimates(config, ticker)
            if analyst_est:
                details["analyst_est"] = analyst_est

        if val_score is not None and qlt_score is not None:
            fund = round((0.6 * val_score + 0.4 * qlt_score) / 100.0, 3)
            # Analyst certainty nudge: tight consensus boosts confidence slightly;
            # wide disagreement (high dispersion) penalises it.
            if analyst_est and analyst_est.get("certainty") is not None:
                cert = analyst_est["certainty"]           # 0-1
                nudge = (cert - 0.50) * 0.06             # ±0.03 max
                fund = round(float(np.clip(fund + nudge, 0.0, 1.0)), 3)
            n = analyst_est.get("analyst_count") if analyst_est else None
            disp = analyst_est.get("eps_dispersion") if analyst_est else None
            lbl = f"Valuation {val_score:.0f}/100, Quality {qlt_score:.0f}/100"
            if n:
                lbl += f" · {n} analyst consensus"
            if disp is not None:
                lbl += f" (EPS dispersion {disp*100:.0f}% — {'tight' if disp < 0.15 else 'wide'})"
            scores["fundamental_score"] = fund
            labels["fundamental_score"] = lbl

        elif val_score is not None:
            fund = round(val_score / 100.0, 3)
            if analyst_est and analyst_est.get("certainty") is not None:
                cert = analyst_est["certainty"]
                nudge = (cert - 0.50) * 0.04
                fund = round(float(np.clip(fund + nudge, 0.0, 1.0)), 3)
            scores["fundamental_score"] = fund
            labels["fundamental_score"] = f"Valuation {val_score:.0f}/100 (quality n/a)"

        else:
            # Prefer FMP analyst EPS → forward P/E over yfinance info when available
            fmp_fund = _score_fmp_analyst_fundamentals(analyst_est, close_s)
            if fmp_fund is not None:
                scores["fundamental_score"] = fmp_fund["score"]
                labels["fundamental_score"] = fmp_fund["label"]
            else:
                yf_fund = _score_yfinance_fundamentals(ticker)
                if yf_fund is not None:
                    scores["fundamental_score"] = yf_fund["score"]
                    labels["fundamental_score"] = yf_fund["label"]
                else:
                    scores["fundamental_score"] = round(composite_score / 100.0 * 0.7, 3)
                    labels["fundamental_score"] = "Composite score proxy (no fundamentals data)"

        # ── Short interest (FINRA via yfinance) ───────────────────────────
        # Not a scored layer — feeds risk_factors and disqualifiers.
        # Also stored in details for the pre-flight + price_targets engine.
        si_data = _fetch_short_interest_data(ticker)
        if si_data is not None:
            details["short_interest"] = si_data

        # ── Layer 7: NLP sentiment — FMP stock news (preferred), else Alpha Vantage ─
        # FMP: data.fmp_api_key (Starter). Alpha Vantage: data.alpha_vantage_api_key (free tier).
        # Gracefully skipped when no key or rate limit hit.
        nlp_result = _score_nlp_sentiment(ticker, config)
        if nlp_result is not None:
            scores["nlp_sentiment"] = nlp_result["score"]
            labels["nlp_sentiment"] = nlp_result["label"]
            details["nlp"] = nlp_result
        else:
            labels["nlp_sentiment"] = (
                "News sentiment N/A (no usable headlines from FMP, Alpha Vantage, or Yahoo Finance for this symbol). "
                "Layer weight redistributed to other layers."
            )

        # Structured logging: positive-weight layers with no score (weight redistributed)
        try:
            for layer in effective_weights:
                w = float(effective_weights.get(layer) or 0)
                if w <= 0:
                    continue
                if scores.get(layer) is None:
                    logger.info(
                        "confidence_layer_omitted ticker=%s layer=%s weight=%.4f label=%s",
                        ticker,
                        layer,
                        w,
                        (labels.get(layer) or "")[:220],
                    )
        except Exception:
            pass

        # ── Weighted confidence (renormalize over available layers) ────────
        # Respect asset-type zero-weights (e.g. insider=0 for ETFs/ADRs)
        available = {
            k: v for k, v in scores.items()
            if v is not None and effective_weights.get(k, 0) > 0
        }
        total_w = sum(effective_weights[k] for k in available)
        if total_w == 0:
            confidence = 0.5
        else:
            confidence = sum(available[k] * effective_weights[k] for k in available) / total_w

        confidence_blend_only = round(float(confidence), 4)
        # Structured audit: layer blend vs multiplicative gates (HMM bear, insider)
        penalty_audit: dict[str, Any] = {
            "confidence_blend_only": confidence_blend_only,
            "hmm_bear_penalty": {
                "triggered": False,
                "bear_probability": None,
                "multiplier": 1.0,
                "variant": None,
                "suppressed_pct_if_applied": None,
            },
            "insider_sell_penalty": {"triggered": False, "multiplier": 1.0},
        }

        # ── Hard disqualifiers ─────────────────────────────────────────────
        disqualifiers: list[str] = []

        hmm_data = details.get("hmm", {})
        try:
            _bp = hmm_data.get("bear_probability")
            penalty_audit["hmm_bear_penalty"]["bear_probability"] = float(_bp) if _bp is not None else None
        except (TypeError, ValueError):
            pass

        if hmm_data.get("bear_probability", 0) > 0.80:
            rb = (config or {}).get("confidence", {}).get("regime_blend", {}) or {}
            soften = bool(rb.get("soften_bear_when_above_ma200", True))
            mult_hard = float(rb.get("bear_penalty_mult", 0.46))
            mult_soft = float(rb.get("bear_penalty_mult_above_ma200", 0.76))
            ease = float(np.clip(float(rb.get("bear_penalty_ease_toward_one", 0.18)), 0.0, 1.0))

            def _ease_toward_one(mult: float) -> float:
                m = float(mult)
                return float(m + (1.0 - m) * ease)

            above_ma = False
            if close_s is not None and len(close_s.dropna()) >= 200:
                c_arr = close_s.dropna()
                last_c = float(c_arr.iloc[-1])
                ma200 = float(c_arr.rolling(200).mean().iloc[-1])
                above_ma = last_c > ma200 and not pd.isna(ma200)
            penalty_audit["hmm_bear_penalty"]["triggered"] = True
            penalty_audit["hmm_bear_penalty"]["ease_toward_one"] = ease
            if soften and above_ma:
                m_raw, m_use = mult_soft, _ease_toward_one(mult_soft)
                confidence *= m_use
                penalty_audit["hmm_bear_penalty"]["multiplier_raw"] = m_raw
                penalty_audit["hmm_bear_penalty"]["multiplier"] = m_use
                penalty_audit["hmm_bear_penalty"]["variant"] = "soft_above_ma200"
                penalty_audit["hmm_bear_penalty"]["suppressed_pct_if_applied"] = round((1 - m_use) * 100, 1)
                disqualifiers.append(
                    f"HMM bear probability {hmm_data['bear_probability']*100:.0f}% — "
                    f"confidence suppressed ~{round((1 - m_use) * 100):.0f}% "
                    "(price still above MA200; trend/regime conflict — soft penalty, eased vs raw mult)"
                )
            else:
                m_raw, m_use = mult_hard, _ease_toward_one(mult_hard)
                confidence *= m_use
                penalty_audit["hmm_bear_penalty"]["multiplier_raw"] = m_raw
                penalty_audit["hmm_bear_penalty"]["multiplier"] = m_use
                penalty_audit["hmm_bear_penalty"]["variant"] = "hard"
                penalty_audit["hmm_bear_penalty"]["suppressed_pct_if_applied"] = round((1 - m_use) * 100, 1)
                disqualifiers.append(
                    f"HMM bear probability {hmm_data['bear_probability']*100:.0f}% — "
                    f"deep bear regime — confidence suppressed ~{round((1 - m_use) * 100):.0f}% "
                    "(eased vs raw mult; see confidence.regime_blend in config)"
                )

        insider_data = details.get("insider", {})
        if insider_data.get("sell_ratio", 0) > 0.80:
            confidence *= 0.60
            penalty_audit["insider_sell_penalty"] = {"triggered": True, "multiplier": 0.60}
            disqualifiers.append(
                "Heavy net insider selling (>80% of activity) — "
                "institutional conviction against; confidence suppressed 40%"
            )

        confidence = round(float(np.clip(confidence, 0.0, 1.0)), 3)
        penalty_audit["confidence_final"] = confidence
        try:
            hm = float(penalty_audit["hmm_bear_penalty"].get("multiplier") or 1.0)
            im = float(penalty_audit["insider_sell_penalty"].get("multiplier") or 1.0)
            penalty_audit["combined_multiplier"] = round(hm * im, 4)
        except (TypeError, ValueError):
            penalty_audit["combined_multiplier"] = None

        # ── Action label ───────────────────────────────────────────────────
        action = _confidence_to_action(confidence)

        # ── Risk factors and watch levels ──────────────────────────────────
        si_data = details.get("short_interest")
        risk_factors = _build_risk_factors(
            scores, market_regime, vix, disqualifiers, composite_score,
            short_interest=si_data,
        )
        watch_levels = _build_watch_levels(df, composite_score)

        # ── Pre-flight deep analysis (coherence, playbook, divergence) ─────
        pre_flight_data = _run_pre_flight(
            ticker=ticker,
            classification=classification,
            scores=scores,
            hmm_data=details.get("hmm", {}),
            close_s=close if close is not None else (
                df["close"] if df is not None and "close" in df.columns else None
            ),
        )

        return {
            "ticker":          ticker,
            "confidence":      confidence,
            "action":          action,
            # HMM debug payload (includes MA conflict override info)
            "hmm":             details.get("hmm"),
            "breakdown":       {
                k: {
                    "score":     round(scores.get(k, 0.0), 3) if scores.get(k) is not None else None,
                    "weight":    effective_weights.get(k, self.weights.get(k, 0)),
                    "label":     labels.get(k, "") or ("" if k in available else "N/A — weight redistributed to other layers."),
                    "available": k in available,
                }
                for k in effective_weights
            },
            "ml_horizons":      ml_horizons,
            "disqualifiers":    disqualifiers,
            "risk_factors":     risk_factors,
            "watch_levels":     watch_levels,
            "market_regime":    market_regime,
            "n_layers_active":  len(available),
            # Short interest (FINRA via yfinance) — for UI display + scenario engine
            "short_interest":   details.get("short_interest"),
            # Analyst EPS consensus (FMP) — certainty, dispersion, count
            "analyst_estimates": details.get("analyst_est"),
            # Headlines + score for UI (roadmap / ticker detail transparency)
            "nlp":               details.get("nlp"),
            # Blend vs multiplicative penalties (HMM bear gate, insider) — for audits & UI
            "penalty_audit":     penalty_audit,
            # Pre-flight enrichment
            "pre_flight":       pre_flight_data,
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

    # GAP B fix: fetch live VIX when not supplied by caller (standalone /api/confidence route).
    # This enables: ETF options VIX proxy, VIX risk factor, and VIX multiplier on composite score.
    if vix is None:
        try:
            import yfinance as _yf
            _vd = _yf.download("^VIX", period="5d", progress=False, threads=False, auto_adjust=True)
            if _vd is not None and not _vd.empty:
                _vc = _vd.get("Close") if hasattr(_vd, "get") else _vd["Close"]
                if _vc is not None:
                    _vals = _vc.dropna()
                    if len(_vals) > 0:
                        vix = round(float(_vals.iloc[-1]), 2)
        except Exception:
            pass

    composite_score = 50.0
    val_score = qlt_score = None
    if close is not None:
        # GAP A fix: pass ticker + config so _valuation_score/_quality_score can call FMP.
        # Without ticker+config, val_score/qlt_score are always None → Layer 6 falls back.
        sig = multi_horizon_scores(
            close,
            market_regime=market_regime,
            vix=vix,
            ticker=ticker,
            config=config,
        )
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
        result = run_insider_flow([ticker], days_lookback=180)
        activities = result.get("ticker_activities", [])
        ticker_act = next((a for a in activities if a["ticker"] == ticker), None)
        if ticker_act is None:
            return None

        buys  = int(ticker_act.get("buys_shares", 0) or 0)
        sells = int(ticker_act.get("sells_shares", 0) or 0)
        total = buys + sells
        if total == 0:
            return {"score": 0.5, "label": "No insider activity (180d)", "sell_ratio": 0.0}

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


def _fetch_analyst_estimates(config: dict, ticker: str) -> dict | None:
    """
    Call FMP fetch_analyst_estimates and return normalised dict, or None on any failure.
    Cached implicitly by FMP function (no caching here — called once per request).
    """
    try:
        from signals.fmp_client import fetch_analyst_estimates, get_api_key
        if not get_api_key(config):
            return None
        est, err = fetch_analyst_estimates(config, ticker)
        if err or est is None:
            logger.debug("FMP analyst estimates for %s: %s", ticker, err)
            return None
        return est if isinstance(est, dict) else None
    except Exception as exc:
        logger.debug("_fetch_analyst_estimates %s: %s", ticker, exc)
        return None


def _score_fmp_analyst_fundamentals(
    analyst_est: dict | None, close_s: "pd.Series | None"
) -> dict | None:
    """
    Derive a fundamental score from FMP analyst EPS consensus when FMP
    key_metrics (val_score) is unavailable.

    Uses:
      - Forward P/E = current price / eps_avg
      - Analyst certainty score (tight consensus = quality signal)
    """
    if analyst_est is None:
        return None
    eps_avg = analyst_est.get("eps_avg") or analyst_est.get("eps_fwd")
    if eps_avg is None or eps_avg <= 0:
        return None

    # Current price from close series
    price = None
    if close_s is not None and len(close_s) > 0:
        try:
            price = float(close_s.iloc[-1])
        except Exception:
            pass
    if not price or price <= 0:
        return None

    fwd_pe = price / eps_avg
    # P/E scoring same rubric as _score_yfinance_fundamentals
    if fwd_pe <= 0:    pe_s = 0.30
    elif fwd_pe < 12:  pe_s = 0.85
    elif fwd_pe <= 20: pe_s = 0.75
    elif fwd_pe <= 30: pe_s = 0.55
    elif fwd_pe <= 45: pe_s = 0.35
    else:              pe_s = 0.20

    # Certainty nudge: tight consensus boosts the score
    certainty = analyst_est.get("certainty")
    cert_nudge = 0.0
    if certainty is not None:
        cert_nudge = (certainty - 0.5) * 0.08    # ±0.04 max

    score = round(float(np.clip(pe_s + cert_nudge, 0.0, 1.0)), 3)

    n = analyst_est.get("analyst_count")
    disp = analyst_est.get("eps_dispersion")
    label_parts = [f"FMP analyst P/E {fwd_pe:.1f} (EPS avg ${eps_avg:.2f})"]
    if n:
        label_parts.append(f"{n} analysts")
    if disp is not None:
        label_parts.append(f"dispersion {disp*100:.0f}% — {'tight' if disp < 0.15 else 'wide'}")
    return {"score": score, "label": " · ".join(label_parts)}


def _fetch_short_interest_data(ticker: str) -> dict | None:
    """
    Thin wrapper around short_interest.fetch_short_interest() with error guard.
    Returns None for ETFs / instruments where yfinance doesn't carry SI data.
    """
    try:
        from signals.short_interest import fetch_short_interest
        return fetch_short_interest(ticker)
    except Exception as exc:
        logger.debug("Short interest fetch failed for %s: %s", ticker, exc)
        return None


# High-PE growth names: if yfinance returns suspiciously low P/E (e.g. 17 for NVDA),
# recompute from price/trailingEps to avoid split/stale errors driving fundamentals score.
_HIGH_PE_GROWTH_FUND = frozenset(
    {"NVDA", "AVGO", "META", "AMD", "TSLA", "CRM", "NOW", "SNOW", "PLTR", "NET", "DDOG", "MDB", "CRWD", "PANW"}
)


def _score_yfinance_fundamentals(ticker: str) -> dict | None:
    """
    Pull basic fundamentals from yfinance Ticker.info (free, no key required).
    Returns score 0-1 + label, or None if data unavailable.

    Scoring rubric (each component 0-1, averaged):
      pe_score   — forward P/E vs sector-neutral baseline (15-30 = fair, < 15 = cheap, > 40 = expensive)
      margin_score — profit margin (>15% = healthy, <5% = weak, negative = stressed)
      growth_score — revenue/earnings growth (>20% = strong, <0% = declining)
      debt_score  — debt/equity (<0.5 = low, >2.0 = high for non-financials)
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        if not isinstance(info, dict) or not info:
            return None

        components: list[float] = []
        parts: list[str] = []

        # P/E: prefer TTM for display; sanity-check for high-PE growth (e.g. NVDA 35–40x, not 17.3)
        fpe = info.get("trailingPE") or info.get("forwardPE")
        pe_label = "TTM P/E"
        if fpe is not None:
            try:
                fpe = float(fpe)
                ticker_upper = ticker.upper().split(".")[0]
                if (
                    fpe > 0
                    and fpe < 22
                    and ticker_upper in _HIGH_PE_GROWTH_FUND
                ):
                    price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
                    trailing_eps = info.get("trailingEps")
                    if price is not None and trailing_eps is not None and float(trailing_eps) > 0:
                        ttm_recomputed = float(price) / float(trailing_eps)
                        if 25 <= ttm_recomputed <= 100:
                            fpe = ttm_recomputed
                            pe_label = "TTM P/E"
                if fpe <= 0:
                    pe_s = 0.3    # negative earnings = stressed
                elif fpe < 12:
                    pe_s = 0.85   # cheap
                elif fpe <= 20:
                    pe_s = 0.75   # fair
                elif fpe <= 30:
                    pe_s = 0.55   # premium
                elif fpe <= 45:
                    pe_s = 0.35   # expensive
                else:
                    pe_s = 0.20   # very expensive
                components.append(pe_s)
                parts.append(f"{pe_label} {fpe:.1f}")
            except (TypeError, ValueError):
                pass

        # Profit margin
        margin = info.get("profitMargins")
        if margin is not None:
            try:
                m = float(margin)
                if m >= 0.20:    margin_s = 0.90
                elif m >= 0.10:  margin_s = 0.70
                elif m >= 0.03:  margin_s = 0.50
                elif m >= 0.0:   margin_s = 0.35
                else:            margin_s = 0.15   # loss-making
                components.append(margin_s)
                parts.append(f"Margin {m*100:.1f}%")
            except (TypeError, ValueError):
                pass

        # Revenue growth (YoY)
        growth = info.get("revenueGrowth") or info.get("earningsGrowth")
        if growth is not None:
            try:
                g = float(growth)
                if g >= 0.30:    growth_s = 0.90
                elif g >= 0.15:  growth_s = 0.75
                elif g >= 0.05:  growth_s = 0.60
                elif g >= 0.0:   growth_s = 0.45
                else:            growth_s = 0.20   # revenue declining
                components.append(growth_s)
                parts.append(f"Growth {g*100:.0f}%")
            except (TypeError, ValueError):
                pass

        # Debt/equity
        de = info.get("debtToEquity")
        if de is not None:
            try:
                d = float(de) / 100.0   # yfinance returns % form
                if d <= 0.3:    debt_s = 0.90
                elif d <= 0.8:  debt_s = 0.70
                elif d <= 1.5:  debt_s = 0.50
                elif d <= 3.0:  debt_s = 0.30
                else:           debt_s = 0.15
                components.append(debt_s)
                parts.append(f"D/E {d:.1f}x")
            except (TypeError, ValueError):
                pass

        if not components:
            return None

        score  = round(float(np.mean(components)), 3)
        label  = "yfinance fundamentals: " + ", ".join(parts)
        return {"score": score, "label": label}
    except Exception as exc:
        logger.debug("yfinance fundamentals for %s: %s", ticker, exc)
        return None


def _sanitize_fmp_request_error(err: str | None, max_len: int = 120) -> str | None:
    """Short, single-line hint for UI when FMP news fails (no secrets in fmp_client errors)."""
    if not err:
        return None
    s = " ".join(str(err).split())
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s


def _nlp_pack_sentiment_summary(
    summary: dict,
    source: str,
    note: str = "",
    *,
    fmp_request_error: str | None = None,
) -> dict | None:
    """Map raw [-1,1] to layer score [0,1]. Returns None if no raw score."""
    raw_score = summary.get("sentiment_score_avg")
    if raw_score is None:
        return None
    raw_f = float(raw_score)
    score = round(float(np.clip((raw_f + 1.0) / 2.0, 0.0, 1.0)), 3)
    headline_count = int(summary.get("headline_count", 0))
    sentiment_label = summary.get("sentiment_label", "Neutral")
    method = summary.get("sentiment_method", "")
    method_note = ""
    if method == "keyword":
        method_note = " · keyword lexicon"
    elif method == "fmp_field":
        method_note = " · FMP article scores"
    elif method == "yfinance":
        method_note = " · Yahoo Finance headlines"
    label = f"News {sentiment_label} ({headline_count} headlines · {source}{method_note}{note})"
    out: dict = {
        "score": score,
        "label": label,
        "raw_score": raw_f,
        "headline_count": headline_count,
        "sentiment_label": sentiment_label,
        "headlines": summary.get("headlines", [])[:10],
        "source": source,
        "method": method or None,
    }
    if fmp_request_error:
        out["fmp_request_error"] = fmp_request_error
    return out


def _yfinance_news_summary(ticker: str) -> dict | None:
    """
    Free path: Yahoo Finance ticker.news (no API key). Same keyword lexicon as FMP when scores missing.
    Returns a summary dict compatible with _nlp_pack_sentiment_summary, or None.
    """
    if not ticker:
        return None
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        sym = (ticker or "").upper().split("-")[0].strip()
        if not sym:
            return None
        t = yf.Ticker(sym)
        news = getattr(t, "news", None) or []
        if not isinstance(news, list) or not news:
            return None
        raw_items: list[dict] = []
        for n in news[:15]:
            if not isinstance(n, dict):
                continue
            title = (n.get("title") or "")[:500]
            if not title.strip():
                continue
            summ = (n.get("summary") or n.get("description") or "")[:2000]
            raw_items.append({"title": title, "text": summ})
        if not raw_items:
            return None
        from signals.news_keyword_sentiment import aggregate_keyword_sentiment

        kw_avg, n_h, kw_hit = aggregate_keyword_sentiment(raw_items, ticker=sym)
        headlines = [
            {"title": (it.get("title") or "")[:120], "score": None, "label": "Neutral"}
            for it in raw_items[:10]
        ]
        if kw_hit and kw_avg is not None:
            label = "Bullish" if kw_avg > 0.15 else "Bearish" if kw_avg < -0.15 else "Neutral"
            return {
                "ticker": sym,
                "sentiment_score_avg": round(float(kw_avg), 4),
                "sentiment_label": label,
                "sentiment_method": "keyword",
                "headline_count": n_h,
                "headlines": headlines,
            }
        # Headlines present but no lexicon hit — neutral 0.0 so layer still shows copy + headlines
        return {
            "ticker": sym,
            "sentiment_score_avg": 0.0,
            "sentiment_label": "Neutral",
            "sentiment_method": "yfinance",
            "headline_count": len(raw_items),
            "headlines": headlines,
        }
    except Exception as exc:
        logger.debug("yfinance news NLP for %s: %s", ticker, exc)
        return None


def _score_nlp_sentiment(ticker: str, config: dict | None) -> dict | None:
    """
    News sentiment: FMP (headlines + optional API fields + keyword lexicon), then Alpha Vantage,
    then Yahoo Finance headlines + lexicon (no API key).
    Raw scores are -1..+1 from vendors/lexicon; mapped to 0..1 for the layer.
    """
    if not config:
        return None
    use_yf = (config.get("data") or {}).get("use_yfinance_news_fallback", True)
    try:
        from signals.alpha_vantage_client import fetch_news_sentiment, get_api_key as get_av_key
        from signals.fmp_client import fetch_stock_news, get_api_key as get_fmp_key

        # 1) FMP when configured
        if get_fmp_key(config):
            summary, err = fetch_stock_news(config, ticker, limit=10)
            if not err and summary is not None:
                packed = _nlp_pack_sentiment_summary(summary, "FMP")
                if packed is not None:
                    return packed
            # No usable FMP sentiment, or request error — try AV before giving up
            fmp_note = " (FMP request failed)" if err else " (FMP had no sentiment score)"
            fmp_err_safe = _sanitize_fmp_request_error(err) if err else None
            if get_av_key(config):
                s2, e2 = fetch_news_sentiment(config, ticker, limit=10)
                if not e2 and s2 is not None and s2.get("sentiment_score_avg") is not None:
                    p2 = _nlp_pack_sentiment_summary(
                        s2, "Alpha Vantage", note=fmp_note, fmp_request_error=fmp_err_safe
                    )
                    if p2 is not None:
                        return p2
            if use_yf:
                yf_sum = _yfinance_news_summary(ticker)
                if yf_sum is not None:
                    p3 = _nlp_pack_sentiment_summary(
                        yf_sum, "Yahoo Finance", note=fmp_note, fmp_request_error=fmp_err_safe
                    )
                    if p3 is not None:
                        return p3
            logger.debug("News sentiment N/A for %s after FMP (+ optional AV + yfinance)", ticker)
            return None

        # 2) Alpha Vantage only (no FMP key)
        if get_av_key(config):
            summary, err = fetch_news_sentiment(config, ticker, limit=10)
            if not err and summary is not None and summary.get("sentiment_score_avg") is not None:
                return _nlp_pack_sentiment_summary(summary, "Alpha Vantage")
            if use_yf:
                yf_sum = _yfinance_news_summary(ticker)
                if yf_sum is not None:
                    p3 = _nlp_pack_sentiment_summary(yf_sum, "Yahoo Finance", note=" (Alpha Vantage unavailable)")
                    if p3 is not None:
                        return p3
            return None

        # 3) No paid keys — Yahoo Finance only
        if use_yf:
            yf_sum = _yfinance_news_summary(ticker)
            if yf_sum is not None:
                return _nlp_pack_sentiment_summary(yf_sum, "Yahoo Finance")
        return None
    except Exception as exc:
        logger.debug("NLP sentiment failed for %s: %s", ticker, exc)
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
    short_interest: dict | None = None,
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
        risks.append(f"ML model gives only {lgbm_val*100:.0f}% short-term probability — weak near-term signal")
    # Short interest risk factors (FINRA via yfinance)
    if short_interest is not None:
        try:
            from signals.short_interest import short_interest_risk_factors
            si_risks = short_interest_risk_factors(short_interest)
            risks.extend(si_risks)
        except Exception:
            pass
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
        "invalidation_below": round(low_52w * 0.97, 2),
        "key_support_ma50":   round(ma50, 2),
        "key_support_ma200":  round(ma200, 2),
        "note": (
            "Break below 52-week low (×0.97) invalidates the setup — exit if breached. "
            "MA50 and MA200 are key support levels to watch."
        ),
    }


def _incompatible_result(ticker: str, classification: Any) -> dict:
    """Return a blocked result for instruments like UVXY that cannot be scored."""
    flags = [f.to_dict() for f in classification.flags] if classification else []
    return {
        "ticker":          ticker,
        "confidence":      None,
        "action":          "INCOMPATIBLE",
        "breakdown":       {},
        "nlp":             None,
        "ml_horizons":     None,
        "disqualifiers":   ["Standard equity model not applicable for this instrument type."],
        "risk_factors":    ["Volatility ETFs behave inversely to equity market — do not use standard signals."],
        "watch_levels":    {},
        "market_regime":   "N/A",
        "n_layers_active": 0,
        "penalty_audit": None,
        "pre_flight": {
            "is_scoreable":      False,
            "asset_type":        classification.asset_type.value if classification else "UNKNOWN",
            "asset_name":        classification.name if classification else ticker,
            "weight_label":      classification.weight_profile.label if classification else "",
            "flags":             flags,
            "coherence":         None,
            "transition_bonus":  None,
            "rsi_direction":     None,
            "divergence":        None,
            "regime_transition": None,
            "playbook":          [],
            "current_mode":      "INCOMPATIBLE",
            "current_action":    "Standard equity model not applicable for this instrument type.",
            "position_size":     "0%",
        },
    }


def _run_pre_flight(
    ticker: str,
    classification: Any,
    scores: dict,
    hmm_data: dict,
    close_s: pd.Series | None,
) -> dict:
    """
    Run the full pre-flight signal fusion engine and return a serialisable dict.
    Gracefully returns minimal data if the engine fails.
    """
    base: dict = {
        "is_scoreable":      True,
        "asset_type":        None,
        "asset_name":        ticker,
        "weight_label":      "",
        "flags":             [],
        "coherence":         None,
        "transition_bonus":  None,
        "rsi_direction":     None,
        "divergence":        None,
        "regime_transition": None,
        "playbook":          [],
        "current_mode":      None,
        "current_action":    None,
        "position_size":     None,
    }

    if classification is not None:
        base["asset_type"]   = classification.asset_type.value
        base["asset_name"]   = classification.name
        base["weight_label"] = classification.weight_profile.label
        base["flags"]        = [f.to_dict() for f in classification.flags]

    try:
        from signals.pre_flight import run_full_engine, SignalInput

        # Convert 0-1 engine scores to 0-100 for SignalInput
        def _to_100(v: float | None) -> float | None:
            return round(v * 100, 1) if v is not None else None

        # RSI current / previous from price series (last value and 5 bars ago)
        rsi_current  = None
        rsi_previous = None
        if close_s is not None and len(close_s) >= 20:
            try:
                import ta
                rsi_series = ta.momentum.RSIIndicator(close_s).rsi()
                rsi_current  = float(rsi_series.iloc[-1]) if not np.isnan(rsi_series.iloc[-1]) else None
                rsi_previous = float(rsi_series.iloc[-6]) if len(rsi_series) > 6 and not np.isnan(rsi_series.iloc[-6]) else rsi_current
            except Exception:
                pass

        sig_input = SignalInput(
            ticker=ticker,
            hmm_bull_prob=_to_100(hmm_data.get("bull_probability")) or 0.0,
            hmm_transition_prob=_to_100(hmm_data.get("transition_probability")) or 0.0,
            hmm_bear_prob=_to_100(hmm_data.get("bear_probability")) or 0.0,
            pattern_score=_to_100(scores.get("pattern_technical")),
            ml_probability=_to_100(scores.get("lgbm_probability")),
            options_sentiment=_to_100(scores.get("options_sentiment")),
            insider_activity=_to_100(scores.get("insider_signal")),
            fundamentals=_to_100(scores.get("fundamental_score")),
            rsi_current=rsi_current,
            rsi_previous=rsi_previous,
            earnings_date=(hmm_data.get("earnings_context") or {}).get("most_recent_earnings_date"),
            days_since_earnings=(hmm_data.get("earnings_context") or {}).get("days_since_earnings"),
            post_earnings_return_pct=(hmm_data.get("earnings_context") or {}).get("post_earnings_return_pct"),
            post_earnings_volume_ratio=(hmm_data.get("earnings_context") or {}).get("post_earnings_volume_ratio"),
        )

        result = run_full_engine(sig_input)
        rd = result.to_dict()

        base.update({
            "coherence":         rd.get("coherence"),
            "transition_bonus":  rd.get("transition_bonus"),
            "rsi_direction":     rd.get("rsi_signal"),
            "divergence":        rd.get("divergence"),
            "regime_transition": rd.get("regime_transition"),
            "playbook":          rd.get("playbook", []),
            "current_mode":      rd.get("current_mode"),
            "current_action":    rd.get("current_action"),
            "position_size":     rd.get("summary", {}).get("position_size"),
        })
        # Surface tension when bull is high but shift probability is also high
        rt = base.get("regime_transition")
        bull_p = hmm_data.get("bull_probability") or 0
        if rt and bull_p >= 0.8:
            shift_p = rt.get("shift_probability") if isinstance(rt, dict) else getattr(rt, "shift_probability", None)
            if shift_p is not None and float(shift_p) >= 40:
                days = (rt.get("days_estimate") if isinstance(rt, dict) else getattr(rt, "days_estimate", None)) or "5–10 days"
                base["regime_tension_note"] = (
                    f"Regime is bull ({bull_p*100:.0f}%) but {shift_p}% chance of shift in {days}. "
                    "Not necessarily wrong — regimes can flip quickly; consider position size."
                )
    except Exception as exc:
        logger.debug("Pre-flight engine failed for %s: %s", ticker, exc)

    return base
