"""
HMM-based probabilistic regime detection.

Why this beats MA crossovers:
  - MA crossovers are lagging — they confirm the regime AFTER the move
  - HMM learns the statistical fingerprint of each regime from price behaviour
  - Returns soft probabilities: "78% bull, 18% transition, 4% bear"
    rather than a hard label that flips with a single bar

Three hidden states fit naturally to:
  State 0 (bear):       negative mean return, high volatility
  State 1 (transition): near-zero return, moderate volatility
  State 2 (bull):       positive mean return, low-to-moderate volatility

Features: [daily_return, |daily_return| (vol proxy), log_volume_change]

Model persistence: backend/data/models/hmm_{ticker}.pkl
Graceful degradation: returns None if hmmlearn is not installed.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MIN_BARS_TO_FIT = 252   # Need at least 1 year to fit meaningfully
RECENT_BARS     = 60    # Bars used to estimate current regime probability

# Regime sanity thresholds (percent gaps)
# Avoid noise: a tiny -0.4% dip below MA50 should not flip the regime.
MA50_CONFLICT_THRESHOLD_PCT = 1.5   # % below MA50 to trigger conflict
MA200_CONFLICT_THRESHOLD_PCT = 3.0  # % below MA200 to trigger stronger conflict


def validate_regime(
    *,
    ticker: str,
    hmm_dominant: str,  # "BULL" | "TRANSITION" | "BEAR" (optionally "STRONG_BULL")
    last_close: float,
    ma20: float,
    ma50: float,
    ma200: float,
    prev_close: float | None = None,
    prev_ma50: float | None = None,
    days_since_earnings: int | None = None,
    post_earnings_return_pct: float | None = None,
    use_gap_threshold: bool = True,
) -> dict:
    """
    Cross-validate HMM regime against MA structure.

    Returns a dict with:
      - resolved_regime: validated regime to use downstream
      - conflict: whether we overrode / downgraded
      - conflict_severity: LOW | MEDIUM | HIGH
      - gaps and a momentum hint (moving_toward_ma50)

    Designed so we can embed this directly into the HMM payload returned by `get_hmm_regime()`.
    """
    gap_ma50 = (last_close - ma50) / ma50 * 100.0 if ma50 else 0.0
    gap_ma200 = (last_close - ma200) / ma200 * 100.0 if ma200 else 0.0

    prev_gap_ma50 = None
    if prev_close is not None and prev_ma50 not in (None, 0):
        prev_gap_ma50 = (prev_close - float(prev_ma50)) / float(prev_ma50) * 100.0

    gap_trend_ma50 = None
    moving_toward_ma50 = None
    if prev_gap_ma50 is not None:
        gap_trend_ma50 = gap_ma50 - prev_gap_ma50
        # If we were below MA50, "toward" means the gap is getting less negative.
        # If we were above MA50, "toward" means the gap is shrinking.
        moving_toward_ma50 = (abs(gap_ma50) < abs(prev_gap_ma50))

    below_ma50 = gap_ma50 < 0
    below_ma200 = gap_ma200 < 0
    below_ma50_strong = gap_ma50 <= -MA50_CONFLICT_THRESHOLD_PCT if use_gap_threshold else below_ma50
    below_ma200_strong = gap_ma200 <= -MA200_CONFLICT_THRESHOLD_PCT if use_gap_threshold else below_ma200

    above_stack = (last_close > ma50) and (ma50 > ma200)
    strong_bull_stack = (last_close > ma20) and (ma20 > ma50) and (ma50 > ma200)

    ma_regime = (
        "BULL" if above_stack else
        "BEAR" if below_ma200_strong else
        "TRANSITION"
    )

    resolved = hmm_dominant
    conflict = False
    severity = "none"
    reason = None
    note = "HMM and MA agree"

    # ── Post-earnings override ─────────────────────────────────────────────
    # If we're within a short window after earnings and the stock sold off hard
    # AND is meaningfully below MA50, force TRANSITION (HMM can lag post-event).
    post_earnings_override = (
        days_since_earnings is not None
        and days_since_earnings <= 5
        and post_earnings_return_pct is not None
        and post_earnings_return_pct <= -5.0
        and gap_ma50 <= -3.0
        and hmm_dominant in ("BULL", "STRONG_BULL")
    )
    if post_earnings_override:
        resolved = "TRANSITION"
        conflict = True
        severity = "HIGH"
        reason = "POST_EARNINGS_OVERRIDE"
        note = (
            f"Post-earnings override: {abs(gap_ma50):.1f}% below MA50, HMM lagging"
        )

    # If the post-earnings override triggers, keep TRANSITION regardless of MA200.
    if post_earnings_override:
        pass
    elif hmm_dominant == "BULL":
        if ma_regime == "BEAR":
            resolved = "BEAR"
            conflict = True
            severity = "HIGH"
            reason = "HMM_BULL_BUT_BELOW_MA200"
            note = f"HMM overridden: price {gap_ma50:+.2f}% vs MA50"
        elif below_ma50_strong:
            resolved = "TRANSITION"
            conflict = True
            severity = "MEDIUM"
            reason = "HMM_BULL_BUT_BELOW_MA50"
            note = f"HMM overridden: price {gap_ma50:+.2f}% vs MA50"
            # Momentum nuance: if the gap is improving quickly, keep the override but lower severity.
            if gap_trend_ma50 is not None and gap_trend_ma50 >= 0.50:
                severity = "LOW"
        elif below_ma50 and below_ma200:
            # Borderline: below both but within thresholds → do NOT override by default.
            # We only override if the MA200 gap is meaningfully negative.
            if below_ma200_strong:
                resolved = "TRANSITION"
                conflict = True
                severity = "MEDIUM"
                reason = "HMM_BULL_BORDERLINE_BELOW_MAS"
                note = f"HMM overridden: price {gap_ma50:+.2f}% vs MA50"

    elif hmm_dominant == "BEAR":
        if above_stack:
            resolved = "TRANSITION"
            conflict = True
            severity = "MEDIUM"
            reason = "HMM_BEAR_BUT_ABOVE_STACK"
            note = f"HMM overclaiming Bear: price {gap_ma50:+.2f}% vs MA50"

    elif hmm_dominant == "STRONG_BULL":
        # Not currently emitted by our 3-state HMM, but kept for compatibility if added later.
        if not strong_bull_stack:
            resolved = ma_regime if ma_regime in ("BULL", "TRANSITION") else "TRANSITION"
            conflict = True
            severity = "LOW"
            reason = "HMM_STRONG_BULL_NO_MA_STACK"
            note = "STRONG_BULL downgraded: MA stack not aligned"

    return {
        "resolved_regime": resolved,
        "ma_regime": ma_regime,
        "conflict": conflict,
        "conflict_severity": severity,
        "reason": reason,
        "note": note,
        "gap_ma50_pct": round(gap_ma50, 2),
        "gap_ma200_pct": round(gap_ma200, 2),
        "gap_trend_ma50_pct": round(gap_trend_ma50, 2) if gap_trend_ma50 is not None else None,
        "moving_toward_ma50": moving_toward_ma50,
        "days_since_earnings": days_since_earnings,
        "post_earnings_return_pct": round(float(post_earnings_return_pct), 2) if post_earnings_return_pct is not None else None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_hmm_regime(
    ticker: str,
    close: pd.Series,
    volume: pd.Series | None = None,
    force_refit: bool = False,
    most_recent_earnings_date: str | None = None,
    days_since_earnings: int | None = None,
    post_earnings_return_pct: float | None = None,
    post_earnings_volume_ratio: float | None = None,
) -> dict | None:
    """
    Fit (or load) a 3-state HMM and return current regime probabilities.

    Returns:
        {
          "bull_probability":       float,   # 0-1
          "transition_probability": float,
          "bear_probability":       float,
          "dominant_state":         str,     # "BULL" | "TRANSITION" | "BEAR"
          "state_means":            list[float],   # mean daily return per state
          "n_bars_fit":             int,
          "error":                  str | None,
        }
    or None if hmmlearn is not installed.
    """
    try:
        from hmmlearn.hmm import GaussianHMM  # noqa: F401
    except ImportError:
        logger.debug("hmmlearn not installed — HMM regime unavailable")
        return None

    if close is None or len(close) < MIN_BARS_TO_FIT:
        return _error_result(f"Need {MIN_BARS_TO_FIT}+ bars; got {len(close) if close is not None else 0}")

    features = _build_features(close, volume)
    if features is None or len(features) < MIN_BARS_TO_FIT:
        return _error_result("Could not build HMM features")

    model = _load_or_fit(ticker, features, force_refit)
    if model is None:
        return _error_result("HMM fit failed")

    # Predict probabilities on the most recent window
    recent = features[-RECENT_BARS:]
    try:
        state_probs = model.predict_proba(recent)   # shape (n_bars, 3)
        current_probs = state_probs[-1]             # latest bar
    except Exception as exc:
        return _error_result(f"HMM predict failed: {exc}")

    # Identify which state index = bull / bear / transition by mean return
    means = model.means_[:, 0]   # first feature = daily return
    order = np.argsort(means)    # lowest mean first
    # order[0] = bear, order[1] = transition, order[2] = bull

    bear_idx       = int(order[0])
    transition_idx = int(order[1])
    bull_idx       = int(order[2])

    bear_prob       = float(current_probs[bear_idx])
    transition_prob = float(current_probs[transition_idx])
    bull_prob       = float(current_probs[bull_idx])

    dominant = (
        "BULL"       if bull_prob > 0.55 else
        "BEAR"       if bear_prob > 0.55 else
        "TRANSITION"
    )

    # Cross-check against observable MA structure (sanity guard).
    # Uses % gap thresholds to avoid flip-flopping on marginal dips (e.g., -0.4% below MA50).
    dominant_validated = dominant
    conflict = None
    try:
        if close is not None and len(close) >= 200:
            close_s = close.dropna()
            if len(close_s) >= 200:
                last_close = float(close_s.iloc[-1])
                ma20 = float(close_s.rolling(20, min_periods=20).mean().iloc[-1])
                ma50 = float(close_s.rolling(50, min_periods=50).mean().iloc[-1])
                ma200 = float(close_s.rolling(200, min_periods=200).mean().iloc[-1])
                prev_close = float(close_s.iloc[-2]) if len(close_s) >= 2 else None
                prev_ma50 = (
                    float(close_s.rolling(50, min_periods=50).mean().iloc[-2])
                    if len(close_s) >= 51
                    else None
                )
                v = validate_regime(
                    ticker=ticker,
                    hmm_dominant=dominant,
                    last_close=last_close,
                    ma20=ma20,
                    ma50=ma50,
                    ma200=ma200,
                    prev_close=prev_close,
                    prev_ma50=prev_ma50,
                    days_since_earnings=days_since_earnings,
                    post_earnings_return_pct=post_earnings_return_pct,
                    use_gap_threshold=True,
                )

                dominant_validated = v["resolved_regime"]
                if v["conflict"]:
                    conflict = {
                        "reason": v["reason"],
                        "severity": v["conflict_severity"],
                        "note": v["note"],
                        "gap_ma50_pct": v["gap_ma50_pct"],
                        "gap_ma200_pct": v["gap_ma200_pct"],
                        "gap_trend_ma50_pct": v["gap_trend_ma50_pct"],
                        "moving_toward_ma50": v["moving_toward_ma50"],
                        "days_since_earnings": v["days_since_earnings"],
                        "post_earnings_return_pct": v["post_earnings_return_pct"],
                        "last_close": round(last_close, 2),
                        "ma50": round(ma50, 2),
                        "ma200": round(ma200, 2),
                    }
                    logger.info(
                        "[hmm] %s regime conflict: dominant=%s → validated=%s (close=%.2f ma50=%.2f ma200=%.2f) [gap_ma50=%+.2f%% severity=%s]",
                        ticker,
                        dominant,
                        dominant_validated,
                        last_close,
                        ma50,
                        ma200,
                        float(v["gap_ma50_pct"]),
                        v["conflict_severity"],
                    )
    except Exception:
        pass

    return {
        "bull_probability":       round(bull_prob, 3),
        "transition_probability": round(transition_prob, 3),
        "bear_probability":       round(bear_prob, 3),
        "dominant_state":         dominant,
        "dominant_state_validated": dominant_validated,
        "ma_conflict":           conflict,
        "earnings_context": {
            "most_recent_earnings_date": most_recent_earnings_date,
            "days_since_earnings": days_since_earnings,
            "post_earnings_return_pct": round(float(post_earnings_return_pct), 2) if post_earnings_return_pct is not None else None,
            "post_earnings_volume_ratio": round(float(post_earnings_volume_ratio), 2) if post_earnings_volume_ratio is not None else None,
        },
        "state_means_daily_ret":  [round(float(means[i]), 5) for i in order],
        "n_bars_fit":             len(features),
        "error":                  None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_features(close: pd.Series, volume: pd.Series | None) -> np.ndarray | None:
    """
    Build standardised [daily_return, |daily_return|, log_vol_change] feature matrix.

    Features are z-score standardised AND clipped to ±4σ before fitting.
    Clipping removes flash-crash outliers (e.g. -20% in a single day) that
    cause extreme Gaussian likelihoods, destabilise the EM covariance update,
    and produce the "Model is not converging" log warning.
    """
    ret = close.pct_change().dropna()
    if len(ret) < MIN_BARS_TO_FIT:
        return None

    feats = [ret.values, np.abs(ret.values)]

    if volume is not None:
        vol_aligned = volume.reindex(ret.index).ffill().fillna(1)
        log_vol = np.log(vol_aligned.values.clip(1))
        log_vol_change = np.diff(log_vol, prepend=log_vol[0])
        feats.append(log_vol_change)

    arr = np.column_stack(feats)
    # Remove rows with NaN / inf (can appear at boundaries)
    mask = np.all(np.isfinite(arr), axis=1)
    arr = arr[mask]

    # Standardise each feature to zero-mean unit-variance so the EM algorithm
    # treats each dimension equally — without this the return column (~0.001 scale)
    # and vol-change column (~0.1 scale) have very different magnitudes.
    std = arr.std(axis=0)
    std[std == 0] = 1.0   # avoid division by zero for constant features
    arr = (arr - arr.mean(axis=0)) / std

    # Clip to ±4σ (post-standardisation so ±4 means ±4 std-devs).
    # Flash crashes / circuit-breaker days sit 8-15σ away from the mean and
    # pull the Gaussian means toward the tail, causing EM to step backwards.
    arr = np.clip(arr, -4.0, 4.0)

    return arr


def _model_path(ticker: str) -> Path:
    return MODELS_DIR / f"hmm_{ticker.upper()}.pkl"


def _load_or_fit(ticker: str, features: np.ndarray, force_refit: bool) -> object | None:
    import warnings
    import logging as _std_logging
    from hmmlearn.hmm import GaussianHMM

    path = _model_path(ticker)
    if path.exists() and not force_refit:
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            logger.debug("HMM cache corrupt for %s — refitting", ticker)

    # Fit on all bars except last RECENT_BARS to avoid future peeking
    train = features[:-RECENT_BARS] if len(features) > RECENT_BARS + 100 else features

    # ── Silence hmmlearn's logger during fitting ───────────────────────────
    # hmmlearn emits "Model is not converging" via logging.warning() (not via
    # warnings.warn), so warnings.simplefilter("ignore") does NOT suppress it.
    # We temporarily raise the hmmlearn logger to CRITICAL so no WARNING-level
    # messages reach the application log. The model output is still usable.
    _hmm_log = _std_logging.getLogger("hmmlearn")
    _hmm_prev_level = _hmm_log.level
    _hmm_log.setLevel(_std_logging.CRITICAL)

    best_model, best_score = None, -np.inf
    # Five random restarts — keep the model with the highest log-likelihood.
    # HMM EM is sensitive to initialisation; more restarts reduce the chance of
    # landing in a poor local optimum that produces unstable covariances.
    for seed in (42, 7, 123, 17, 99):
        try:
            candidate = GaussianHMM(
                n_components=3,
                covariance_type="diag",   # fewer params than "full" → more stable
                n_iter=500,
                random_state=seed,
                tol=1e-3,                 # slightly relaxed — avoids false "not converging"
                min_covar=1e-2,           # floor on diagonal covariance entries;
                                          # prevents near-zero variance that causes
                                          # the EM log-likelihood to step backwards
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")   # belt-and-suspenders for ConvergenceWarning
                candidate.fit(train)
            score = candidate.score(train)
            if score > best_score:
                best_score, best_model = score, candidate
        except Exception as exc:
            logger.debug("HMM fit attempt seed=%s failed for %s: %s", seed, ticker, exc)
        finally:
            pass  # logger level restored after the loop

    # Restore hmmlearn logger level
    _hmm_log.setLevel(_hmm_prev_level)

    if best_model is None:
        logger.warning("All HMM fit attempts failed for %s", ticker)
        return None

    try:
        with open(path, "wb") as f:
            pickle.dump(best_model, f)
    except Exception:
        pass   # model still usable in memory even if persist fails

    return best_model


def _error_result(msg: str) -> dict:
    return {
        "bull_probability":       0.5,
        "transition_probability": 0.3,
        "bear_probability":       0.2,
        "dominant_state":         "TRANSITION",
        "state_means_daily_ret":  [],
        "n_bars_fit":             0,
        "error":                  msg,
    }
