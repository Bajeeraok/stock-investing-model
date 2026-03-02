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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_hmm_regime(
    ticker: str,
    close: pd.Series,
    volume: pd.Series | None = None,
    force_refit: bool = False,
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
    # If HMM says BULL but price is below both MA50 and MA200, treat as TRANSITION.
    # If HMM says BEAR but price is above both MA50 and MA200, treat as TRANSITION.
    dominant_validated = dominant
    conflict = None
    try:
        if close is not None and len(close) >= 200:
            close_s = close.dropna()
            if len(close_s) >= 200:
                last_close = float(close_s.iloc[-1])
                ma50 = float(close_s.rolling(50, min_periods=50).mean().iloc[-1])
                ma200 = float(close_s.rolling(200, min_periods=200).mean().iloc[-1])
                below_both = (last_close < ma50) and (last_close < ma200)
                above_both = (last_close > ma50) and (last_close > ma200)
                if dominant == "BULL" and below_both:
                    dominant_validated = "TRANSITION"
                    conflict = {
                        "reason": "HMM_BULL_BUT_BELOW_MAS",
                        "last_close": round(last_close, 2),
                        "ma50": round(ma50, 2),
                        "ma200": round(ma200, 2),
                    }
                elif dominant == "BEAR" and above_both:
                    dominant_validated = "TRANSITION"
                    conflict = {
                        "reason": "HMM_BEAR_BUT_ABOVE_MAS",
                        "last_close": round(last_close, 2),
                        "ma50": round(ma50, 2),
                        "ma200": round(ma200, 2),
                    }
                if conflict:
                    logger.info(
                        "[hmm] %s regime conflict: dominant=%s → validated=%s (close=%.2f ma50=%.2f ma200=%.2f)",
                        ticker,
                        dominant,
                        dominant_validated,
                        conflict["last_close"],
                        conflict["ma50"],
                        conflict["ma200"],
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
