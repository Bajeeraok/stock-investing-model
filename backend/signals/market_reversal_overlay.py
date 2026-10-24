"""
Market stress + short-horizon bounce / reversal *setup* overlay (index-level).

Not a guarantee of next-day direction — combines:
  - Rule-based scores from SPY + VIX (drawdown, vol spike, RSI, MA distance)
  - Optional LightGBM P(bounce) trained on historical stress episodes (see train_market_reversal_ml.py)

Applied market-wide to composite_buy (config-gated) and exposed on every signal row + dashboard.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Must match training script order exactly
FEATURE_COLUMNS: list[str] = [
    "spy_ret_1",
    "spy_ret_5",
    "spy_ret_20",
    "spy_dd_20h",
    "spy_dist_ma200",
    "spy_rsi_14",
    "vix_level",
    "vix_ret_5",
    "vix_z_20",
    "rv10_spy",
]


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_g = gain.rolling(window, min_periods=window).mean()
    avg_l = loss.rolling(window, min_periods=window).mean()
    rs = avg_g / avg_l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _date_indexed(series: pd.Series) -> pd.Series:
    """Same values, index normalized to tz-naive midnight dates (last value wins per day)."""
    idx = pd.to_datetime(series.index, errors="coerce", utc=True).tz_convert(None).normalize()
    out = pd.Series(series.values, index=idx)
    out = out[~out.index.isna()]
    return out[~out.index.duplicated(keep="last")].sort_index()


def feature_row_from_series(
    spy: pd.Series,
    vix: pd.Series,
) -> dict[str, float] | None:
    """
    Point-in-time features at the last bar of aligned SPY/VIX closes.
    """
    if spy is None or vix is None or len(spy) < 220 or len(vix) < 30:
        return None
    # Align on calendar dates. SPY (FMP, naive dates) and ^VIX (yfinance, tz-aware
    # timestamps) never share an exact index value, so the raw intersection was empty and
    # every ticker reported insufficient_spy_vix_history despite years of data on both.
    spy = _date_indexed(spy)
    vix = _date_indexed(vix)
    common = spy.index.intersection(vix.index)
    if len(common) < 220:
        return None
    s = spy.reindex(common).ffill().bfill()
    vx = vix.reindex(common).ffill().bfill()

    ret_1 = float(s.pct_change().iloc[-1])
    ret_5 = float(s.pct_change(5).iloc[-1])
    ret_20 = float(s.pct_change(20).iloc[-1])
    roll_max_20 = s.rolling(20, min_periods=10).max().iloc[-1]
    dd_20h = float((s.iloc[-1] / roll_max_20) - 1.0) if roll_max_20 and roll_max_20 > 0 else 0.0
    ma200 = float(s.rolling(200, min_periods=60).mean().iloc[-1])
    dist_ma200 = float((s.iloc[-1] / ma200) - 1.0) if ma200 > 0 else 0.0
    rsi = float(_rsi(s, 14).iloc[-1])
    if np.isnan(rsi):
        rsi = 50.0

    v = float(vx.iloc[-1])
    v5 = float(vx.pct_change(5).iloc[-1])
    v20 = vx.iloc[-20:]
    v_mu = float(v20.mean())
    v_sd = float(v20.std()) or 1e-6
    v_z = float((v - v_mu) / v_sd)

    r10 = s.pct_change().iloc[-10:]
    rv10 = float(r10.std() * np.sqrt(252) * 100.0) if len(r10) >= 5 else 15.0

    return {
        "spy_ret_1": ret_1,
        "spy_ret_5": ret_5,
        "spy_ret_20": ret_20,
        "spy_dd_20h": dd_20h,
        "spy_dist_ma200": dist_ma200,
        "spy_rsi_14": rsi,
        "vix_level": v,
        "vix_ret_5": v5,
        "vix_z_20": v_z,
        "rv10_spy": rv10,
    }


def _rule_stress(f: dict[str, float]) -> float:
    """0–100 higher = more macro / technical stress."""
    score = 0.0
    if f["vix_level"] > 30:
        score += 35
    elif f["vix_level"] > 22:
        score += 22
    elif f["vix_level"] > 18:
        score += 10

    if f["spy_ret_5"] < -0.04:
        score += 30
    elif f["spy_ret_5"] < -0.02:
        score += 18
    elif f["spy_ret_5"] < 0:
        score += 8

    if f["spy_dd_20h"] < -0.06:
        score += 22
    elif f["spy_dd_20h"] < -0.03:
        score += 12

    if f["spy_rsi_14"] < 30:
        score += 10
    if f["spy_dist_ma200"] < -0.08:
        score += 10

    return float(max(0.0, min(100.0, score)))


def _rule_bounce_setup(f: dict[str, float], stress: float) -> float:
    """
    0–100: elevated chance of sharp mean-reversion *when* stress is already high.
    Not "market will go up tomorrow" — washout + vol stabilizing hints.
    """
    b = 0.0
    if stress < 35:
        return 0.0
    if f["spy_rsi_14"] < 35:
        b += 25
    if f["spy_dd_20h"] < -0.04:
        b += 20
    if f["spy_ret_5"] < -0.02:
        b += 15
    if f["vix_z_20"] > 1.0:
        b += 15
    if f["vix_ret_5"] < 0.02 and f["vix_level"] > 20:
        b += 12  # vol not still exploding
    if f["spy_ret_1"] > 0:
        b += 10  # already bouncing
    return float(max(0.0, min(100.0, b)))


def _model_path(config: dict) -> Path:
    mro = config.get("market_reversal_overlay") or {}
    root = mro.get("model_path")
    if root:
        return Path(root)
    try:
        from config_loader import get_data_root

        return Path(get_data_root()) / "models" / "market_reversal_lgbm.pkl"
    except Exception:
        return Path(__file__).resolve().parent.parent / "data" / "models" / "market_reversal_lgbm.pkl"


def predict_ml_bounce_prob(feat: dict[str, float], config: dict) -> tuple[float | None, str | None]:
    """Returns (probability 0–1, error)."""
    mro = config.get("market_reversal_overlay") or {}
    if not mro.get("ml_enabled", True):
        return None, None
    path = _model_path(config)
    if not path.exists():
        return None, "no_model_file"
    try:
        import lightgbm as lgb  # noqa: F401
    except Exception as e:
        logger.debug("lightgbm missing: %s", e)
        return None, "lightgbm_unavailable"
    try:
        with open(path, "rb") as f:
            bundle = pickle.load(f)
        model = bundle.get("model")
        cols = bundle.get("feature_columns", FEATURE_COLUMNS)
        if model is None:
            return None, "bad_bundle"
        x = np.array([[float(feat.get(c, 0.0)) for c in cols]], dtype=np.float64)
        proba = model.predict_proba(x)[0, 1]
        return float(proba), None
    except Exception as e:
        logger.debug("ML bounce predict failed: %s", e)
        return None, str(e)


def build_market_reversal_overlay(
    config: dict,
    *,
    vix: float | None,
    real_yield: float | None,
    market_regime_data: dict | None,
    close_spy: pd.Series | None,
    vix_series: pd.Series | None,
) -> dict[str, Any]:
    """
    Full overlay dict for API + run_daily. Does not throw.
    """
    mro_cfg = config.get("market_reversal_overlay") or {}
    if not mro_cfg.get("enabled", True):
        return {"enabled": False}

    feat = None
    if close_spy is not None and vix_series is not None:
        feat = feature_row_from_series(close_spy, vix_series)
    if feat is None:
        common_n = None
        try:
            if close_spy is not None and vix_series is not None:
                common_n = len(_date_indexed(close_spy).index.intersection(_date_indexed(vix_series).index))
        except Exception:
            common_n = None
        return {
            "enabled": True,
            "error": "insufficient_spy_vix_history",
            "history": {
                "spy_bars": None if close_spy is None else len(close_spy),
                "vix_bars": None if vix_series is None else len(vix_series),
                "common_dates": common_n,
                "need": {"spy": 220, "vix": 30, "common": 220},
            },
            "stress_score": None,
            "bounce_setup_score": None,
            "composite_buy_delta": 0,
            "label": "unknown",
            "headline": "Market overlay: need SPY + VIX history",
            "bullets": [],
            "ml_bounce_prob": None,
            "ml_error": None,
            "features": None,
        }

    stress = _rule_stress(feat)
    bounce = _rule_bounce_setup(feat, stress)
    ml_p, ml_err = predict_ml_bounce_prob(feat, config)

    # Blend ML into bounce score display (cap influence)
    bounce_display = bounce
    if ml_p is not None:
        w = float(mro_cfg.get("ml_blend_weight", 0.35))
        bounce_display = float((1 - w) * bounce + w * (ml_p * 100.0))

    rotation = (market_regime_data or {}).get("rotation_risk") or "Medium"
    breadth = (market_regime_data or {}).get("market_breadth") or "Neutral"
    ry = real_yield if real_yield is not None else 0.0
    if rotation == "High" and breadth == "Weak":
        stress = min(100.0, stress + 8.0)
    if ry > 2.5:
        stress = min(100.0, stress + 5.0)

    stress_penalty = float(mro_cfg.get("stress_penalty", 10))
    bounce_bonus = float(mro_cfg.get("bounce_bonus", 6))
    max_delta = float(mro_cfg.get("max_score_delta", 10))

    delta = 0.0
    if stress >= 55:
        delta -= stress_penalty * ((stress - 50) / 50.0)
    if bounce_display >= 45 and stress >= 40:
        delta += bounce_bonus * ((bounce_display / 100.0) * ((stress - 35) / 65.0))

    delta = float(np.clip(delta, -max_delta, max_delta))

    if stress >= 65:
        label = "stressed"
    elif bounce_display >= 50 and stress >= 45:
        label = "bounce_risk"
    elif stress >= 45:
        label = "cautious"
    else:
        label = "normal"

    bullets: list[str] = [
        f"SPY 5d: {feat['spy_ret_5']*100:.1f}%, VIX: {feat['vix_level']:.1f} (z={feat['vix_z_20']:.2f})",
        f"Stress {stress:.0f}/100 · Bounce-setup {bounce_display:.0f}/100",
    ]
    if ml_p is not None:
        bullets.append(f"ML P(sharp bounce | stress features): {ml_p*100:.0f}% (calibrated on history; not a guarantee)")
    if rotation == "High":
        bullets.append("Rotation risk High — tech entries already stepped down when applicable")

    headline = {
        "stressed": "Market stress elevated — size down new risk; bounces can be violent either way",
        "bounce_risk": "Washout / vol stress with bounce-setup conditions — elevated reversal probability next sessions",
        "cautious": "Backdrop cautious — favor confirmation over chasing",
        "normal": "Broad market backdrop within normal range (overlay)",
    }.get(label, "Market backdrop")

    return {
        "enabled": True,
        "stress_score": round(stress, 1),
        "bounce_setup_score": round(bounce_display, 1),
        "bounce_rule_score": round(bounce, 1),
        "composite_buy_delta": round(delta, 2),
        "label": label,
        "headline": headline,
        "bullets": bullets,
        "ml_bounce_prob": None if ml_p is None else round(ml_p, 4),
        "ml_error": ml_err,
        "features": {k: round(float(v), 6) if isinstance(v, (float, int)) else v for k, v in feat.items()},
        "vix": vix,
        "real_yield": real_yield,
    }


def apply_overlay_to_composite(
    composite_buy: float,
    confluence_score: float | None,
    overlay: dict[str, Any],
    *,
    apply_adjustment: bool,
) -> tuple[float, float]:
    """Returns (new_composite, new_confluence)."""
    if not apply_adjustment or not overlay.get("enabled"):
        return composite_buy, confluence_score if confluence_score is not None else composite_buy
    d = float(overlay.get("composite_buy_delta") or 0.0)
    cb = float(np.clip(composite_buy + d, 0, 100))
    base_c = float(confluence_score if confluence_score is not None else composite_buy)
    cf = float(np.clip(base_c + d, 0, 100))
    return cb, cf
