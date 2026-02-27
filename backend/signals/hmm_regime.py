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

    return {
        "bull_probability":       round(bull_prob, 3),
        "transition_probability": round(transition_prob, 3),
        "bear_probability":       round(bear_prob, 3),
        "dominant_state":         dominant,
        "state_means_daily_ret":  [round(float(means[i]), 5) for i in order],
        "n_bars_fit":             len(features),
        "error":                  None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_features(close: pd.Series, volume: pd.Series | None) -> np.ndarray | None:
    """Build [daily_return, |daily_return|, log_vol_change] feature matrix."""
    ret = close.pct_change().dropna()
    if len(ret) < MIN_BARS_TO_FIT:
        return None

    feats = [ret.values, np.abs(ret.values)]

    if volume is not None:
        vol_aligned = volume.reindex(ret.index).fillna(method="ffill").fillna(1)
        log_vol = np.log(vol_aligned.values.clip(1))
        log_vol_change = np.diff(log_vol, prepend=log_vol[0])
        feats.append(log_vol_change)

    arr = np.column_stack(feats)
    # Remove rows with NaN / inf (can appear at boundaries)
    mask = np.all(np.isfinite(arr), axis=1)
    return arr[mask]


def _model_path(ticker: str) -> Path:
    return MODELS_DIR / f"hmm_{ticker.upper()}.pkl"


def _load_or_fit(ticker: str, features: np.ndarray, force_refit: bool) -> object | None:
    from hmmlearn.hmm import GaussianHMM

    path = _model_path(ticker)
    if path.exists() and not force_refit:
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            logger.debug("HMM cache corrupt for %s — refitting", ticker)

    try:
        model = GaussianHMM(
            n_components=3,
            covariance_type="full",
            n_iter=200,
            random_state=42,
            tol=1e-4,
        )
        # Fit on all bars except last RECENT_BARS to avoid future peeking
        train = features[:-RECENT_BARS] if len(features) > RECENT_BARS + 100 else features
        model.fit(train)
        with open(path, "wb") as f:
            pickle.dump(model, f)
        return model
    except Exception as exc:
        logger.warning("HMM fit failed for %s: %s", ticker, exc)
        return None


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
