"""Shared (pooled) LightGBM odds blended with each stock's own history odds.

One model trained across ~570 S&P 500 stocks replaces the small per-ticker models for
the "+N% within H trading days" question. The displayed probability is
    w * pooled_model + (1 - w) * this stock's historical hit rate for the same question,
with w chosen per horizon by walk-forward validation (scripts/train_pooled_odds.py).
Crypto, gold/commodity and bond/defensive tickers keep the per-ticker path.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from signals.ml_models import (
    _BOND_DEFENSIVE,
    _GOLD_COMMODITY,
    HORIZONS,
    MODELS_DIR,
    build_features,
    get_target_gain,
)

logger = logging.getLogger(__name__)

# Outside data/ so it ships in the Docker image (.dockerignore excludes data/).
ARTIFACT_PATH = Path(__file__).resolve().parent.parent / "artifacts" / "pooled_odds.json"
HIST_MIN_SAMPLES = 100
HIST_START = pd.Timestamp("2000-01-01")
PROB_FLOOR, PROB_CAP = 0.02, 0.98


def pooled_eligible(ticker: str) -> bool:
    t = (ticker or "").upper()
    return bool(t) and not t.endswith("-USD") and t not in _GOLD_COMMODITY and t not in _BOND_DEFENSIVE


def atr_pct(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(14, min_periods=10).mean() / df["close"]


def market_features(spy_close: pd.Series) -> pd.DataFrame:
    c = spy_close.astype(float)
    return pd.DataFrame({
        "spy_ret20": c.pct_change(20),
        "spy_ret60": c.pct_change(60),
        "spy_above_ma200": (c > c.rolling(200).mean()).astype(int),
        "spy_vol20": c.pct_change().rolling(20).std() * np.sqrt(252),
        "spy_dd_1y": 1 - c / c.rolling(252, min_periods=60).max(),
    })


def ticker_features(df: pd.DataFrame, spy_feat: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """Per-bar features using data up to each bar only (stock + market + relative strength)."""
    if not {"close", "high", "low"}.issubset(df.columns):
        return None
    f = build_features(df, ticker, "short")
    if f is None or f.empty:
        return None
    f = f.drop(columns=["target", "regime_label"], errors="ignore")
    f["atr_pct"] = atr_pct(df).reindex(f.index)
    f = f.join(spy_feat, how="left")
    f["rs20"] = f["price_ret_20d"] - f["spy_ret20"]
    f["rs60"] = f["price_ret_60d"] - f["spy_ret60"]
    return f


def forward_label(close: pd.Series, days: int, gain: float) -> pd.Series:
    y = (close.shift(-days) / close - 1 >= gain).astype(float)
    y.iloc[-days:] = np.nan
    return y


def history_rate_series(close: pd.Series, days: int, gain: float) -> pd.Series:
    """Hit rate of the same question over outcomes already known at each bar."""
    return forward_label(close, days, gain).shift(days).expanding(min_periods=HIST_MIN_SAMPLES).mean()


def history_rate(close: pd.Series, days: int, gain: float) -> float | None:
    c = close.dropna().to_numpy(float)
    n = len(c) - days
    if n < HIST_MIN_SAMPLES:
        return None
    return float((c[days:] / c[:n] - 1 >= gain).mean())


@lru_cache(maxsize=1)
def _load_artifact(path: str, mtime: float) -> dict[str, Any] | None:
    try:
        import lightgbm as lgb
    except (ImportError, OSError):
        return None
    try:
        raw = json.loads(Path(path).read_text())
        boosters = {k: lgb.Booster(model_str=s) for k, s in raw["models"].items()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("pooled odds artifact unreadable (%s): %s", path, exc)
        return None
    return {**raw, "models": boosters}


def load_artifact(path: Path | None = None) -> dict[str, Any] | None:
    p = Path(path or ARTIFACT_PATH)
    if not p.exists():
        return None
    return _load_artifact(str(p), p.stat().st_mtime)


def _long_close(ticker: str, close: pd.Series) -> pd.Series:
    """History odds are trained on closes since HIST_START; a 2y/5y frame would skew them."""
    try:
        from signals.fetcher import fetch_ohlcv_safe
        full = fetch_ohlcv_safe(ticker, "max")
    except Exception:  # noqa: BLE001
        full = None
    if full is None or len(full) <= len(close):
        return close
    full = full[full.index <= close.index[-1]]
    return full[full.index >= HIST_START]


def _spy_df() -> pd.DataFrame | None:
    from signals.fetcher import fetch_ohlcv_dataframe
    return fetch_ohlcv_dataframe("SPY", "2y")


def predict_pooled(
    ticker: str,
    df: pd.DataFrame,
    horizon_key: str,
    spy_df: pd.DataFrame | None = None,
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Blended odds for the latest bar, or None (caller falls back to the per-ticker model)."""
    if not pooled_eligible(ticker) or df is None or df.empty:
        return None
    art = artifact or load_artifact()
    if not art or horizon_key not in art.get("models", {}):
        return None
    spy = spy_df if spy_df is not None else _spy_df()
    if spy is None or "close" not in spy.columns or len(spy) < 260:
        return None
    feats = ticker_features(df, market_features(spy["close"]), ticker)
    if feats is None or feats.empty:
        return None
    days = HORIZONS[horizon_key]["days"]
    gain = get_target_gain(ticker, horizon_key)
    row = feats.iloc[[-1]].copy()
    row["gain"] = gain
    cols = art["features"]
    if any(c not in row.columns for c in cols) or row[cols].isna().any(axis=None):
        return None
    p_model = float(art["models"][horizon_key].predict(row[cols].to_numpy(float))[0])
    p_hist = history_rate(_long_close(ticker, df["close"]), days, gain)
    w = float(art["weights"][horizon_key])
    prob = w * p_model + (1 - w) * (p_hist if p_hist is not None else float(art["base_rate"][horizon_key]))
    return {
        "prob": round(min(max(prob, PROB_FLOOR), PROB_CAP), 3),
        "prob_model": round(p_model, 3),
        "prob_hist": None if p_hist is None else round(p_hist, 3),
        "model_weight": w,
        "method": "pooled_blend",
        "model_version": art.get("version"),
    }
