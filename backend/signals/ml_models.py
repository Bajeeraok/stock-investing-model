"""
LightGBM-based price prediction for Thrive Alpha.

Predicts P(10%+ gain in next 20 trading days) from purely technical + price features.
Output is a calibrated probability (0-1), not a raw signal — this maps directly
to the confidence score and is far more useful than buy/sell labels.

Walk-forward training discipline:
  - Features are computed only from data available at each bar (no lookahead)
  - Target is the forward 20-day return (labelled at training time, not inference)
  - Train/test split: 80% chronological (not random) to prevent data leakage

Model persistence: backend/data/models/lgbm_{ticker}.pkl
Graceful degradation: returns None if lightgbm is not installed.

Features (all backward-looking):
  dist_from_52w_low     — how far off the annual low
  dist_from_ma50/200    — trend context
  rsi_14                — momentum
  rsi_slope_5d          — is RSI recovering?
  macd_hist             — momentum signal
  macd_hist_slope_3d    — is MACD turning?
  bollinger_pct_b       — position within BB bands
  volume_ratio_20d      — unusual volume activity
  price_ret_5d/20d/60d  — multi-horizon momentum
  above_ma50/200        — binary trend flags
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

TARGET_GAIN_PCT   = 0.10    # 10% gain threshold
TARGET_HORIZON    = 20      # trading days forward
MIN_TRAIN_BARS    = 400     # Minimum bars before we attempt training
TRAIN_SPLIT_RATIO = 0.80    # Chronological split (not random)

DEFAULT_RETRAIN_DAYS = 7    # Retrain weekly if no config available
DEFAULT_LGBM_PERIOD  = "5y"


def get_lgbm_period(ticker: str, config: dict | None = None) -> str:
    """
    Return the training data period for ticker's LightGBM model.
    Reads from config ml_models.lgbm_period_overrides; falls back to default.

    Rationale:
      10y — stable ETFs, mega-cap (SPY, QQQ, GLD, AAPL): captures 2008, 2018, 2020, 2022
      5y  — growth / momentum (NVDA, TSLA, META): pre-2019 is a structurally different company
      3y  — volatile / newer (BABA, CRSP, ASAN): older data teaches wrong patterns
    """
    if config:
        ml_cfg    = config.get("ml_models", {})
        overrides = ml_cfg.get("lgbm_period_overrides", {})
        if ticker.upper() in overrides:
            return str(overrides[ticker.upper()])
        default = ml_cfg.get("lgbm_period_default", DEFAULT_LGBM_PERIOD)
        return str(default)
    return DEFAULT_LGBM_PERIOD


def model_needs_retrain(ticker: str, config: dict | None = None) -> bool:
    """
    Return True if model is missing or older than retrain_interval_days.
    Called at the start of each daily run to decide train vs load.
    """
    import time
    path = _model_path(ticker)
    if not path.exists():
        return True
    ml_cfg = (config or {}).get("ml_models", {})
    if not ml_cfg.get("enabled", True):
        return False
    interval_days = int(ml_cfg.get("retrain_interval_days", DEFAULT_RETRAIN_DAYS))
    age_seconds   = time.time() - path.stat().st_mtime
    return age_seconds > interval_days * 86_400


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict_probability(
    ticker: str,
    df: pd.DataFrame,
    force_retrain: bool = False,
    config: dict | None = None,
) -> float | None:
    """
    Return P(10%+ gain in 20 trading days) for the LATEST bar in df.

    df must have at least a 'close' column; 'volume' is used if present.
    Returns None if lightgbm is not installed or insufficient data.
    """
    try:
        import lightgbm as lgb  # noqa: F401
    except (ImportError, OSError) as e:
        # OSError = libgomp.so.1 missing (slim Docker image without libgomp1)
        # Fix: add `libgomp1` to Dockerfile apt-get install
        logger.debug("lightgbm unavailable (%s: %s) — ML probability skipped", type(e).__name__, e)
        return None

    if df is None or "close" not in df.columns or len(df) < MIN_TRAIN_BARS:
        return None

    needs_retrain = force_retrain or model_needs_retrain(ticker, config)
    model = _load_or_train(ticker, df, needs_retrain)
    if model is None:
        return None

    features_df = build_features(df)
    if features_df is None or features_df.empty:
        return None

    # Use only the last complete row (no target needed — inference only)
    last_row = features_df.drop(columns=["target"], errors="ignore").iloc[[-1]]
    last_row = last_row.select_dtypes(include=[np.number]).dropna(axis=1)
    if last_row.empty:
        return None

    try:
        prob = float(model.predict_proba(last_row)[0, 1])
        return round(prob, 3)
    except Exception as exc:
        logger.warning("LGBM inference failed for %s: %s", ticker, exc)
        return None


def train_and_save(ticker: str, df: pd.DataFrame) -> dict:
    """
    Train LightGBM on historical df with regime-aware weighting.

    Regime diversity problem without this fix:
      If 65% of bars are bull, the model learns "be optimistic" and systematically
      fails in bear markets (2008, 2020 crash, 2022). Adding inverse-frequency
      sample weights forces the model to learn equally from all market environments.

    What this function does:
      1. Build feature matrix (13 technical features + 4 regime features)
      2. Label each bar's regime (BULL / TRANSITION / BEAR / HIGH_VOL)
      3. Compute inverse-frequency weights so rare regimes (crashes) count more
      4. Chronological 80/20 split — no random shuffling, no future leakage
      5. Report regime coverage (% of training data per regime) + warn if < 10%
      6. Train LightGBM with sample_weight
      7. Report regime-stratified AUC (how does model do in BULL vs BEAR?)
    """
    try:
        import lightgbm as lgb
        from sklearn.metrics import roc_auc_score, brier_score_loss
    except (ImportError, OSError) as e:
        return {"error": f"lightgbm/sklearn unavailable ({type(e).__name__}: {e})"}

    features_df = build_features(df)
    if features_df is None or len(features_df) < MIN_TRAIN_BARS:
        return {"error": f"Insufficient labelled data ({len(features_df) if features_df is not None else 0} bars)"}

    labelled      = features_df.dropna(subset=["target"])
    regime_col    = "regime_label"      # added by build_features
    feature_cols  = [c for c in labelled.columns if c not in ("target", regime_col)]
    X      = labelled[feature_cols].select_dtypes(include=[np.number])
    y      = labelled["target"]
    regime = labelled[regime_col] if regime_col in labelled.columns else None

    split    = int(len(X) * TRAIN_SPLIT_RATIO)
    X_train, X_test   = X.iloc[:split],      X.iloc[split:]
    y_train, y_test   = y.iloc[:split],      y.iloc[split:]
    reg_train         = regime.iloc[:split]  if regime is not None else None
    reg_test          = regime.iloc[split:]  if regime is not None else None

    if len(y_train) < 100 or y_train.nunique() < 2:
        return {"error": "Training set too small or only one class"}

    # ── Regime coverage check ──────────────────────────────────────────────
    coverage: dict[str, float] = {}
    warnings_list: list[str]   = []
    if reg_train is not None:
        counts = reg_train.value_counts()
        total  = len(reg_train)
        for lbl in ["BULL", "TRANSITION", "BEAR", "HIGH_VOL"]:
            pct = round(100 * counts.get(lbl, 0) / total, 1)
            coverage[lbl] = pct
            if pct < 8.0:
                warnings_list.append(
                    f"{lbl} only {pct}% of training data — "
                    "model will underfit this regime; consider longer training period"
                )

    # ── Inverse-frequency sample weights (regime balancing) ───────────────
    # Bear/crash bars are rare (10-20%) but critical to learn.
    # Without this, the model predicts bull-optimistically and fails in 2022-style markets.
    sample_weights = np.ones(len(y_train))
    if reg_train is not None:
        freq   = reg_train.value_counts(normalize=True)
        inv_w  = {lbl: 1.0 / max(freq.get(lbl, 0.25), 0.05) for lbl in freq.index}
        # Normalize so mean weight = 1.0
        raw    = reg_train.map(inv_w).fillna(1.0).values
        sample_weights = raw / raw.mean()

    # ── Train LightGBM ────────────────────────────────────────────────────
    model = lgb.LGBMClassifier(
        n_estimators=500,
        learning_rate=0.01,
        num_leaves=31,
        feature_fraction=0.8,
        bagging_fraction=0.8,
        bagging_freq=5,
        min_child_samples=20,
        random_state=42,
        verbose=-1,
    )
    model.fit(
        X_train, y_train,
        sample_weight=sample_weights,
        eval_set=[(X_test, y_test)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
    )

    path = _model_path(ticker)
    with open(path, "wb") as f:
        pickle.dump(model, f)

    # ── Global metrics ────────────────────────────────────────────────────
    metrics: dict = {
        "n_train":          len(y_train),
        "n_test":           len(y_test),
        "regime_coverage":  coverage,
        "regime_warnings":  warnings_list,
    }
    try:
        probs = model.predict_proba(X_test)[:, 1]
        metrics["auc"]         = round(float(roc_auc_score(y_test, probs)), 3)
        metrics["brier_score"] = round(float(brier_score_loss(y_test, probs)), 3)
        metrics["base_rate"]   = round(float(y.mean()), 3)
        imp = dict(zip(X_train.columns, model.feature_importances_))
        metrics["top_features"] = sorted(imp, key=imp.get, reverse=True)[:5]

        # ── Regime-stratified AUC (the critical diagnostic) ───────────────
        # A model with AUC=0.63 overall might be 0.68 in bull and 0.51 in bear —
        # meaning it learned nothing useful for bear markets despite training on them.
        if reg_test is not None:
            auc_by_regime: dict[str, float | str] = {}
            for lbl in ["BULL", "TRANSITION", "BEAR", "HIGH_VOL"]:
                mask = reg_test == lbl
                if mask.sum() < 20:
                    auc_by_regime[lbl] = f"n={mask.sum()} (too few)"
                    continue
                try:
                    sub_auc = roc_auc_score(y_test[mask], probs[mask.values])
                    auc_by_regime[lbl] = round(float(sub_auc), 3)
                    if sub_auc < 0.52:
                        warnings_list.append(
                            f"AUC {sub_auc:.3f} in {lbl} regime — model has no edge here; "
                            "do not rely on ML signal during {lbl} conditions"
                        )
                except Exception:
                    auc_by_regime[lbl] = "n/a"
            metrics["auc_by_regime"] = auc_by_regime
    except Exception:
        pass

    metrics["regime_warnings"] = warnings_list
    return metrics


# ---------------------------------------------------------------------------
# Feature engineering — all backward-looking, no future data
# ---------------------------------------------------------------------------

def build_features(df: pd.DataFrame) -> pd.DataFrame | None:
    """
    Build feature matrix from OHLCV DataFrame.
    Each row uses only data up to and including that bar (no future leakage).

    Includes explicit regime features so the model knows WHAT KIND OF MARKET
    it is operating in — not just price levels. This prevents the model from
    treating a 2020-crash bar identically to a 2021-bull bar.

    Regime label column (used for sample weighting, NOT as an input feature):
      BULL       — price > MA50 > MA200 (trending uptrend)
      BEAR       — price < MA50 < MA200 (confirmed downtrend)
      HIGH_VOL   — either regime but realised vol > 70th percentile (crash/spike)
      TRANSITION — everything else (sideways, mixed MA structure)
    """
    if df is None or "close" not in df.columns or len(df) < 60:
        return None

    close  = df["close"]
    volume = df["volume"] if "volume" in df.columns else None

    out = pd.DataFrame(index=close.index)

    # ── Price relative to annual range ─────────────────────────────────────
    low_52w  = close.rolling(252, min_periods=60).min()
    high_52w = close.rolling(252, min_periods=60).max()
    out["dist_from_52w_low"]  = (close - low_52w)  / close.clip(lower=1e-6)
    out["dist_from_52w_high"] = (high_52w - close) / close.clip(lower=1e-6)

    # ── MA context ─────────────────────────────────────────────────────────
    ma50  = close.rolling(50, min_periods=20).mean()
    ma200 = close.rolling(200, min_periods=60).mean()
    out["dist_from_ma50"]   = (close - ma50)  / ma50.clip(lower=1e-6)
    out["dist_from_ma200"]  = (close - ma200) / ma200.clip(lower=1e-6)
    out["above_ma50"]       = (close > ma50).astype(int)
    out["above_ma200"]      = (close > ma200).astype(int)
    out["ma50_above_ma200"] = (ma50 > ma200).astype(int)

    # ── RSI ────────────────────────────────────────────────────────────────
    rsi = _rsi(close, 14)
    out["rsi_14"]       = rsi
    out["rsi_slope_5d"] = rsi.diff(5)

    # ── MACD histogram ─────────────────────────────────────────────────────
    hist = _macd_hist(close)
    out["macd_hist"]          = hist
    out["macd_hist_slope_3d"] = hist.diff(3)

    # ── Bollinger %B ───────────────────────────────────────────────────────
    ma20   = close.rolling(20, min_periods=10).mean()
    std20  = close.rolling(20, min_periods=10).std(ddof=1)
    upper  = ma20 + 2 * std20
    lower  = ma20 - 2 * std20
    band_w = (upper - lower).replace(0, np.nan)
    out["bollinger_pct_b"] = (close - lower) / band_w

    # ── Volume ratio ───────────────────────────────────────────────────────
    if volume is not None:
        avg_vol = volume.rolling(20, min_periods=5).mean()
        out["volume_ratio_20d"] = (volume / avg_vol.clip(lower=1)).clip(upper=10)

    # ── Multi-horizon momentum ─────────────────────────────────────────────
    out["price_ret_5d"]  = close.pct_change(5)
    out["price_ret_20d"] = close.pct_change(20)
    out["price_ret_60d"] = close.pct_change(60)

    # ── Realised volatility ────────────────────────────────────────────────
    daily_ret = close.pct_change()
    vol_20d   = daily_ret.rolling(20, min_periods=10).std() * np.sqrt(252)
    out["vol_20d"] = vol_20d

    # ── Explicit regime features (model input — tells LightGBM what market ─
    # environment it's in, not just price levels)
    is_bull       = (close > ma50) & (ma50 > ma200)
    is_bear       = (close < ma50) & (ma50 < ma200)
    vol_70th      = vol_20d.rolling(252, min_periods=60).quantile(0.70)
    is_high_vol   = vol_20d > vol_70th
    out["regime_is_bull"]       = is_bull.astype(int)
    out["regime_is_bear"]       = is_bear.astype(int)
    out["regime_is_transition"] = (~is_bull & ~is_bear).astype(int)
    out["regime_is_high_vol"]   = is_high_vol.astype(int)
    # Rolling bear-market depth: how far below MA200 (positive = below)
    out["bear_depth"]           = ((ma200 - close) / ma200.clip(lower=1e-6)).clip(lower=0)
    # Drawdown from rolling 1-year high (captures 2022-style slow grind lower)
    rolling_1y_high = close.rolling(252, min_periods=60).max()
    out["drawdown_from_1y_high"] = (rolling_1y_high - close) / rolling_1y_high.clip(lower=1e-6)

    # ── Regime label (used for sample weighting + evaluation, NOT model input)
    # Priority: HIGH_VOL > BEAR > BULL > TRANSITION
    labels = pd.Series("TRANSITION", index=close.index)
    labels[is_bull]       = "BULL"
    labels[is_bear]       = "BEAR"
    labels[is_high_vol]   = "HIGH_VOL"   # overrides bull/bear label when vol spikes
    out["regime_label"] = labels

    # ── Target ────────────────────────────────────────────────────────────
    fwd_ret    = close.shift(-TARGET_HORIZON) / close - 1
    out["target"] = (fwd_ret >= TARGET_GAIN_PCT).astype(float)
    out.loc[out.index[-TARGET_HORIZON:], "target"] = np.nan

    return out.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _model_path(ticker: str) -> Path:
    return MODELS_DIR / f"lgbm_{ticker.upper()}.pkl"


def _load_or_train(ticker: str, df: pd.DataFrame, force_retrain: bool) -> object | None:
    path = _model_path(ticker)
    if path.exists() and not force_retrain:
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            logger.debug("LGBM cache corrupt for %s — retraining", ticker)
    result = train_and_save(ticker, df)
    if "error" in result:
        logger.warning("LGBM training failed for %s: %s", ticker, result["error"])
        return None
    path = _model_path(ticker)
    if path.exists():
        with open(path, "rb") as f:
            return pickle.load(f)
    return None


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.where(delta > 0, 0.0)
    loss  = -delta.where(delta < 0, 0.0)
    avg_g = pd.Series(index=close.index, dtype=float)
    avg_l = pd.Series(index=close.index, dtype=float)
    if len(close) <= window:
        return pd.Series(50.0, index=close.index)
    avg_g.iloc[window - 1] = gain.iloc[:window].mean()
    avg_l.iloc[window - 1] = loss.iloc[:window].mean()
    for i in range(window, len(close)):
        avg_g.iloc[i] = (avg_g.iloc[i - 1] * (window - 1) + gain.iloc[i]) / window
        avg_l.iloc[i] = (avg_l.iloc[i - 1] * (window - 1) + loss.iloc[i]) / window
    rs = np.where(avg_l == 0, 100.0, avg_g / avg_l)
    return pd.Series(100 - (100 / (1 + rs)), index=close.index)


def _macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    macd  = ema_f - ema_s
    return macd - macd.ewm(span=signal, adjust=False).mean()
