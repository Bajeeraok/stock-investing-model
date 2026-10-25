"""
LightGBM-based price prediction for Thrive Alpha.

Predicts probability of forward return exceeding a threshold over three horizons,
covering all retail investor types:

  Short-term  (20d / ~1 month)  — swing traders, momentum players
  Medium-term (60d / ~3 months) — position traders, quarterly rebalancers
  Long-term  (120d / ~6 months) — buy-and-hold, accumulation strategies

Why not a single threshold?
  Different assets and horizons have very different base rates.
  10% in 20 days is a 3-5% event for SPY → model always outputs low probability.
  Calibrating thresholds per asset type + horizon keeps each model's positive
  class rate at ~15-25%, giving meaningful discrimination (20-70% output range).

Horizon × asset-type gain thresholds (target ~18% base rate each):
                     20d    60d    120d
  broad_etf / default:  5%    10%    15%
  gold / commodity:     3%     6%    10%
  bonds / defensive:    3%     6%    10%
  high-beta growth:     8%    15%    25%

Walk-forward training discipline:
  - Features are computed only from data available at each bar (no lookahead)
  - Separate model file per ticker × horizon (lgbm_{ticker}_{horizon}.pkl)
  - Train/test split: 80% chronological (not random) to prevent data leakage

Graceful degradation: returns None if lightgbm is not installed.

Features (all backward-looking):
  dist_from_52w_low/high — annual range context
  dist_from_ma50/200     — trend context
  rsi_14 + rsi_slope_5d  — momentum + recovery signal
  macd_hist + slope_3d   — momentum direction
  bollinger_pct_b        — mean-reversion context
  volume_ratio_20d       — unusual volume
  price_ret_5d/20d/60d   — multi-horizon momentum
  vol_20d                — realised volatility
  regime_is_{bull/bear/transition/high_vol} — regime-aware inputs
  bear_depth             — how deep in drawdown
  drawdown_from_1y_high  — drawdown context
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

MIN_TRAIN_BARS    = 400     # Minimum bars before we attempt training
TRAIN_SPLIT_RATIO = 0.80    # Chronological split (not random)

DEFAULT_RETRAIN_DAYS = 7    # Retrain weekly if no config available
DEFAULT_LGBM_PERIOD  = "5y"

# ── Three prediction horizons ──────────────────────────────────────────────────
# Each trains a separate model → lgbm_{ticker}_{horizon_key}.pkl
# Covers short-term traders (20d), position traders (60d), accumulators (120d)
HORIZONS: dict[str, dict] = {
    "short":  {"days": 20,  "label": "1 month",  "description": "Short-term"},
    "medium": {"days": 60,  "label": "3 months", "description": "Medium-term"},
    "long":   {"days": 120, "label": "6 months", "description": "Long-term"},
}

# ── Per-horizon, per-asset-type return thresholds ─────────────────────────────
# Calibrated so each group has ~15-25% positive class rate.
_GAIN_THRESHOLDS: dict[str, dict[str, float]] = {
    "short": {
        "gold_commodity": 0.03,  # 3%  — low daily vol; 3% is meaningful in 20d
        "bond_defensive": 0.03,
        "broad_etf":      0.05,  # 5%  — SPY, QQQ, IWM
        "growth_high":    0.08,  # 8%  — NVDA, TSLA, AMD
        "default":        0.05,
    },
    "medium": {
        "gold_commodity": 0.06,  # 6%  — meaningful 3-month move for gold
        "bond_defensive": 0.06,
        "broad_etf":      0.10,  # 10% — 3-month SPY target
        "growth_high":    0.15,  # 15% — 3-month growth target
        "default":        0.10,
    },
    "long": {
        "gold_commodity": 0.10,  # 10% — 6-month gold target
        "bond_defensive": 0.10,
        "broad_etf":      0.15,  # 15% — 6-month SPY target
        "growth_high":    0.25,  # 25% — 6-month growth target
        "default":        0.15,
    },
}

_GOLD_COMMODITY = {"GLD", "SLV", "GDX", "GDXJ", "IAU", "SIL", "PSLV", "USO", "UCO", "DBO"}
_BOND_DEFENSIVE = {"TLT", "IEF", "SHY", "BND", "AGG", "XLU", "VPU", "SCHD"}
_GROWTH_HIGH    = {"NVDA", "TSLA", "AMD", "SMCI", "MSTR", "COIN", "PLTR", "RIVN", "LCID",
                   "BTC-USD", "ETH-USD", "CRSP", "ASAN", "SNOW"}


def get_target_gain(ticker: str, horizon_key: str = "short") -> float:
    """Return the forward-return threshold for ticker × horizon."""
    t = ticker.upper()
    thresholds = _GAIN_THRESHOLDS.get(horizon_key, _GAIN_THRESHOLDS["short"])
    if t in _GOLD_COMMODITY:
        return thresholds["gold_commodity"]
    if t in _BOND_DEFENSIVE:
        return thresholds["bond_defensive"]
    if t in _GROWTH_HIGH:
        return thresholds["growth_high"]
    return thresholds["default"]


def _interpret_prob(prob: float | None) -> str:
    """Human-readable probability interpretation for UI display."""
    if prob is None:   return "Unavailable"
    if prob >= 0.65:   return "Strong"
    if prob >= 0.50:   return "Bullish"
    if prob >= 0.35:   return "Neutral"
    if prob >= 0.20:   return "Cautious"
    return "Weak"


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


def model_needs_retrain(ticker: str, config: dict | None = None, horizon_key: str = "short") -> bool:
    """
    Return True if model is missing or older than retrain_interval_days.
    Each horizon has its own pkl file; all three are checked during predict_all_horizons.
    """
    import time
    path = _model_path(ticker, horizon_key)
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
    horizon_key: str = "short",
    inference_only: bool = False,
) -> float | None:
    """
    Return P(threshold gain in horizon days) for the LATEST bar in df.

    df must have at least a 'close' column; 'volume' is used if present.
    Returns None if lightgbm is not installed or insufficient data.

    horizon_key: "short" (20d), "medium" (60d), or "long" (120d).
    inference_only: if True, returns None when no cached model exists instead
      of triggering training. Use this during dashboard/table load to avoid
      blocking the response on a potentially long training job.
    """
    try:
        import lightgbm as lgb  # noqa: F401
    except (ImportError, OSError) as e:
        logger.debug("lightgbm unavailable (%s: %s) — ML probability skipped", type(e).__name__, e)
        return None

    if df is None or "close" not in df.columns or len(df) < MIN_TRAIN_BARS:
        return None

    # Inference-only mode: never block the caller on training
    if inference_only and not _model_path(ticker, horizon_key).exists():
        return None

    needs_retrain = force_retrain or model_needs_retrain(ticker, config, horizon_key)
    model = _load_or_train(ticker, df, needs_retrain, horizon_key)
    if model is None:
        return None

    features_df = build_features(df, ticker, horizon_key)
    if features_df is None or features_df.empty:
        return None

    last_row = features_df.drop(columns=["target", "regime_label"], errors="ignore").iloc[[-1]]
    last_row = last_row.select_dtypes(include=[np.number]).dropna(axis=1)
    if last_row.empty:
        return None

    try:
        prob = float(model.predict_proba(last_row)[0, 1])
        # Cap ML output so it never hits exactly 0% or 100% (stability + UI sanity).
        prob = min(max(prob, 0.02), 0.98)
        return round(prob, 3)
    except Exception as exc:
        logger.warning("LGBM inference failed for %s [%s]: %s", ticker, horizon_key, exc)
        return None


def predict_all_horizons(
    ticker: str,
    df: pd.DataFrame,
    force_retrain: bool = False,
    config: dict | None = None,
    inference_only: bool = False,
) -> dict[str, dict]:
    """
    Return ML probability predictions for all three horizons.

    Returns a dict keyed by horizon ("short", "medium", "long"), each containing:
      prob            — probability 0-1 (None if model unavailable)
      threshold_pct   — return % the model is predicting (e.g. 5 for "5% gain")
      horizon_days    — number of trading days (20 / 60 / 120)
      label           — human label ("1 month" / "3 months" / "6 months")
      description     — "Short-term" / "Medium-term" / "Long-term"
      interpretation  — "Strong" / "Bullish" / "Neutral" / "Cautious" / "Weak"

    Use this for the UI breakdown panel. Use predict_probability() for a single
    horizon when you only need one value (e.g. the lgbm_probability layer score).
    """
    result: dict[str, dict] = {}
    for h_key, meta in HORIZONS.items():
        prob      = predict_probability(ticker, df, force_retrain, config, h_key, inference_only)
        threshold = get_target_gain(ticker, h_key)
        result[h_key] = {
            "prob":           prob,
            "threshold_pct":  round(threshold * 100),
            "horizon_days":   meta["days"],
            "label":          meta["label"],
            "description":    meta["description"],
            "interpretation": _interpret_prob(prob),
        }
    return result


VAL_SHARE_OF_TRAIN = 0.20


def purged_split_bounds(n: int, purge: int) -> tuple[int, int, int, int]:
    """(train_end, val_start, val_end, test_start) for train|purge|val|purge|test."""
    trainval_end = int(n * TRAIN_SPLIT_RATIO)
    te_start = min(n, trainval_end + purge)
    va_end = trainval_end
    tr_end = max(0, int(trainval_end * (1 - VAL_SHARE_OF_TRAIN)))
    va_start = min(va_end, tr_end + purge)
    return tr_end, va_start, va_end, te_start


def train_and_save(ticker: str, df: pd.DataFrame, horizon_key: str = "short") -> dict:
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

    features_df = build_features(df, ticker, horizon_key)
    if features_df is None or len(features_df) < MIN_TRAIN_BARS:
        return {"error": f"Insufficient labelled data ({len(features_df) if features_df is not None else 0} bars)"}

    labelled      = features_df.dropna(subset=["target"])
    regime_col    = "regime_label"      # added by build_features
    feature_cols  = [c for c in labelled.columns if c not in ("target", regime_col)]
    X      = labelled[feature_cols].select_dtypes(include=[np.number])
    y      = labelled["target"]
    regime = labelled[regime_col] if regime_col in labelled.columns else None

    # Chronological train | purge | validation | purge | test. The purge gap equals the
    # label horizon so no training label window overlaps validation/test bars. Early
    # stopping uses validation only; reported metrics use the untouched test slice.
    purge = int(HORIZONS.get(horizon_key, HORIZONS["short"])["days"])
    tr_end, va_start, va_end, te_start = purged_split_bounds(len(X), purge)
    X_train, y_train = X.iloc[:tr_end], y.iloc[:tr_end]
    X_val,   y_val   = X.iloc[va_start:va_end], y.iloc[va_start:va_end]
    X_test,  y_test  = X.iloc[te_start:], y.iloc[te_start:]
    reg_train = regime.iloc[:tr_end]   if regime is not None else None
    reg_test  = regime.iloc[te_start:] if regime is not None else None
    if len(y_val) < 20 or len(y_test) < 20:
        return {"error": f"Insufficient data after purged split (val={len(y_val)}, test={len(y_test)})"}

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
        eval_set=[(X_val, y_val)] if y_val.nunique() >= 2 else None,
        callbacks=(
            [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)]
            if y_val.nunique() >= 2 else [lgb.log_evaluation(-1)]
        ),
    )

    path = _model_path(ticker, horizon_key)
    with open(path, "wb") as f:
        pickle.dump(model, f)

    # ── Global metrics ────────────────────────────────────────────────────
    metrics: dict = {
        "n_train":          len(y_train),
        "n_val":            len(y_val),
        "n_test":           len(y_test),
        "purge_bars":       purge,
        "regime_coverage":  coverage,
        "regime_warnings":  warnings_list,
    }
    try:
        import warnings as _warnings
        probs = model.predict_proba(X_test)[:, 1]

        # ROC AUC requires both classes present in y_true — guard explicitly.
        # This happens when the 20% test split or a small regime subset lands
        # entirely on one label (all positive or all negative), which is more
        # likely for longer horizons (60d/120d) where returns trend in one direction.
        if y_test.nunique() >= 2:
            with _warnings.catch_warnings():
                _warnings.simplefilter("ignore")   # suppress UndefinedMetricWarning
                metrics["auc"] = round(float(roc_auc_score(y_test, probs)), 3)
        else:
            metrics["auc"] = None
            metrics["auc_note"] = f"test set has only one class (base_rate={y_test.mean():.2f}) — AUC undefined"

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
                subset_y = y_test[mask]
                if subset_y.nunique() < 2:
                    # Only one class in this regime slice — AUC not meaningful
                    auc_by_regime[lbl] = f"one-class (base={subset_y.mean():.2f})"
                    continue
                try:
                    with _warnings.catch_warnings():
                        _warnings.simplefilter("ignore")
                        sub_auc = roc_auc_score(subset_y, probs[mask.values])
                    auc_by_regime[lbl] = round(float(sub_auc), 3)
                    if sub_auc < 0.52:
                        warnings_list.append(
                            f"AUC {sub_auc:.3f} in {lbl} regime — model has no edge here; "
                            f"do not rely on ML signal during {lbl} conditions"
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

def build_features(
    df: pd.DataFrame,
    ticker: str = "",
    horizon_key: str = "short",
) -> pd.DataFrame | None:
    """
    Build feature matrix from OHLCV DataFrame.
    Each row uses only data up to and including that bar (no future leakage).

    The same feature set is used for all horizons; only the target label changes.
    Target: P(forward_return >= threshold) over horizon_days.

    Regime label column (used for sample weighting, NOT as an input feature):
      BULL       — price > MA50 > MA200
      BEAR       — price < MA50 < MA200
      HIGH_VOL   — realised vol > 70th percentile (crash / volatility spike)
      TRANSITION — everything else
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

    # ── Target — horizon- and asset-type-aware ────────────────────────────
    horizon_days = HORIZONS.get(horizon_key, HORIZONS["short"])["days"]
    target_gain  = get_target_gain(ticker, horizon_key)
    fwd_ret      = close.shift(-horizon_days) / close - 1
    out["target"] = (fwd_ret >= target_gain).astype(float)
    out.loc[out.index[-horizon_days:], "target"] = np.nan

    return out.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _model_path(ticker: str, horizon_key: str = "short") -> Path:
    return MODELS_DIR / f"lgbm_{ticker.upper()}_{horizon_key}.pkl"


_LGBM_MEMORY_CACHE: dict[str, object] = {}


def _lgbm_cache_max() -> int:
    import os

    raw = (os.environ.get("LGBM_MODEL_CACHE_MAX") or "").strip()
    if raw:
        try:
            return max(0, min(128, int(raw)))
        except ValueError:
            pass
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_NAME"):
        return 24
    return 32


def lgbm_model_cache_stats() -> dict[str, int]:
    return {"size": len(_LGBM_MEMORY_CACHE), "max_entries": _lgbm_cache_max()}


def trim_lgbm_model_cache(*, keep: int | None = None) -> dict[str, int]:
    cap = _lgbm_cache_max() if keep is None else max(0, keep)
    before = len(_LGBM_MEMORY_CACHE)
    if cap == 0:
        _LGBM_MEMORY_CACHE.clear()
    elif len(_LGBM_MEMORY_CACHE) > cap:
        while len(_LGBM_MEMORY_CACHE) > cap:
            _LGBM_MEMORY_CACHE.pop(next(iter(_LGBM_MEMORY_CACHE)))
    return {"before": before, "after": len(_LGBM_MEMORY_CACHE), "max_entries": cap}


def _lgbm_cache_key(ticker: str, horizon_key: str) -> str:
    return f"{ticker.upper()}:{horizon_key}"


def _store_lgbm_in_cache(cache_key: str, model: object) -> None:
    _LGBM_MEMORY_CACHE[cache_key] = model
    cap = _lgbm_cache_max()
    while len(_LGBM_MEMORY_CACHE) > cap:
        _LGBM_MEMORY_CACHE.pop(next(iter(_LGBM_MEMORY_CACHE)))


def _load_or_train(
    ticker: str,
    df: pd.DataFrame,
    force_retrain: bool,
    horizon_key: str = "short",
) -> object | None:
    path = _model_path(ticker, horizon_key)
    cache_key = _lgbm_cache_key(ticker, horizon_key)
    if not force_retrain and cache_key in _LGBM_MEMORY_CACHE:
        return _LGBM_MEMORY_CACHE[cache_key]
    if path.exists() and not force_retrain:
        try:
            with open(path, "rb") as f:
                model = pickle.load(f)
            _store_lgbm_in_cache(cache_key, model)
            return model
        except Exception:
            logger.debug("LGBM cache corrupt for %s [%s] — retraining", ticker, horizon_key)
    result = train_and_save(ticker, df, horizon_key)
    if "error" in result:
        logger.warning("LGBM training failed for %s [%s]: %s", ticker, horizon_key, result["error"])
        return None
    path = _model_path(ticker, horizon_key)
    if path.exists():
        with open(path, "rb") as f:
            model = pickle.load(f)
        _store_lgbm_in_cache(cache_key, model)
        return model
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
