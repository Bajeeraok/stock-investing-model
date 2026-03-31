"""
Regime-aware signal weights, Hurst-based asset classification, bucket calibration,
and inversion detection (high-score buckets underperforming low-score buckets).

Use either Hurst weights **or** empirical threshold calibration from the same
backtest window — not both fit on identical data — to reduce double-fitting.

Logging: callers configure logging; no basicConfig on import.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Enums & Config
# ──────────────────────────────────────────────


class AssetRegime(Enum):
    MEAN_REVERTING = "mean_reverting"
    RANDOM_WALK = "random_walk"
    TRENDING = "trending"


@dataclass
class SignalWeights:
    """7-layer signal weights — must sum to 1.0"""

    hmm_regime: float = 0.20
    momentum: float = 0.20
    technicals: float = 0.15
    fundamentals: float = 0.15
    options_sentiment: float = 0.10
    insider_activity: float = 0.10
    news_sentiment: float = 0.10

    def as_dict(self) -> dict[str, float]:
        return {
            "hmm_regime": self.hmm_regime,
            "momentum": self.momentum,
            "technicals": self.technicals,
            "fundamentals": self.fundamentals,
            "options_sentiment": self.options_sentiment,
            "insider_activity": self.insider_activity,
            "news_sentiment": self.news_sentiment,
        }

    def validate(self) -> None:
        total = sum(self.as_dict().values())
        if abs(total - 1.0) >= 1e-6:
            raise ValueError(f"SignalWeights must sum to 1.0, got {total:.6f}")


WEIGHTS_TRENDING = SignalWeights(
    hmm_regime=0.25,
    momentum=0.25,
    technicals=0.15,
    fundamentals=0.10,
    options_sentiment=0.10,
    insider_activity=0.10,
    news_sentiment=0.05,
)
WEIGHTS_MEAN_REVERTING = SignalWeights(
    hmm_regime=0.20,
    momentum=0.05,
    technicals=0.25,
    fundamentals=0.20,
    options_sentiment=0.10,
    insider_activity=0.15,
    news_sentiment=0.05,
)
WEIGHTS_RANDOM_WALK = SignalWeights(
    hmm_regime=0.20,
    momentum=0.15,
    technicals=0.20,
    fundamentals=0.20,
    options_sentiment=0.10,
    insider_activity=0.10,
    news_sentiment=0.05,
)

for _w in (WEIGHTS_TRENDING, WEIGHTS_MEAN_REVERTING, WEIGHTS_RANDOM_WALK):
    _w.validate()


# ──────────────────────────────────────────────
# Hurst exponent
# ──────────────────────────────────────────────


def compute_hurst_exponent(
    price_series: pd.Series,
    min_lags: int = 10,
    max_lags: int = 100,
) -> float:
    """
    Rescaled range (R/S) analysis; slope of log(R/S) vs log(lag) ≈ Hurst.

    max_lags is capped from series length so short histories still return stable estimates.
    """
    prices = np.log(price_series.dropna().values)
    n = len(prices)
    if n < min_lags * 3:
        return 0.5

    max_lags_eff = min(max_lags, max(min_lags + 1, n // 4))
    lags = range(min_lags, max_lags_eff)
    rs_values: list[tuple[int, float]] = []

    for lag in lags:
        n_windows = len(prices) // lag
        if n_windows < 2:
            continue

        rs_list: list[float] = []
        for i in range(n_windows):
            window = prices[i * lag : (i + 1) * lag]
            mean = np.mean(window)
            deviations = np.cumsum(window - mean)
            r_rng = np.max(deviations) - np.min(deviations)
            s = np.std(window, ddof=1)
            if s > 0:
                rs_list.append(r_rng / s)

        if rs_list:
            rs_values.append((lag, float(np.mean(rs_list))))

    if len(rs_values) < 5:
        return 0.5

    lags_arr = np.log([x[0] for x in rs_values])
    rs_arr = np.log([x[1] for x in rs_values])
    hurst = float(np.polyfit(lags_arr, rs_arr, 1)[0])
    return float(np.clip(hurst, 0.01, 0.99))


def classify_regime(hurst: float) -> AssetRegime:
    if hurst < 0.45:
        return AssetRegime.MEAN_REVERTING
    if hurst > 0.55:
        return AssetRegime.TRENDING
    return AssetRegime.RANDOM_WALK


def get_regime_weights(regime: AssetRegime) -> SignalWeights:
    mapping = {
        AssetRegime.TRENDING: WEIGHTS_TRENDING,
        AssetRegime.MEAN_REVERTING: WEIGHTS_MEAN_REVERTING,
        AssetRegime.RANDOM_WALK: WEIGHTS_RANDOM_WALK,
    }
    return mapping[regime]


# ──────────────────────────────────────────────
# Regime-aware score
# ──────────────────────────────────────────────


@dataclass
class RawSignals:
    """Raw layer scores, each normalized 0–100."""

    hmm_regime: float
    momentum: float
    technicals: float
    fundamentals: float
    options_sentiment: float
    insider_activity: float
    news_sentiment: float


def compute_regime_aware_score(
    signals: RawSignals,
    weights: SignalWeights,
    regime: AssetRegime,
) -> dict[str, Any]:
    weights.validate()
    w = weights.as_dict()
    s = signals.__dict__
    weighted_score = sum(w[k] * s[k] for k in w)
    weighted_score = round(min(max(weighted_score, 0), 100), 2)

    momentum_adjustment = 0.0
    if regime == AssetRegime.MEAN_REVERTING and signals.momentum > 70:
        momentum_adjustment = -((signals.momentum - 70) / 30) * 10
        weighted_score = max(0.0, weighted_score + momentum_adjustment)

    return {
        "final_score": round(weighted_score, 2),
        "regime": regime.value,
        "momentum_adjustment": round(momentum_adjustment, 2),
        "component_scores": {k: round(w[k] * s[k], 2) for k in w},
    }


# ──────────────────────────────────────────────
# Threshold calibration
# ──────────────────────────────────────────────


@dataclass
class BucketThresholds:
    strong_buy_floor: float = 70.0
    buy_floor: float = 50.0
    neutral_floor: float = 30.0


def calibrate_thresholds_from_backtest(
    backtest_df: pd.DataFrame,
    horizon: str = "3m",
) -> BucketThresholds:
    """
    Empirical score thresholds from sorted score vs rolling mean forward return.

    Uses the **minimum** score among rows whose smoothed return crosses each hurdle
    (sorted ascending by score), not idxmax on a boolean mask.
    """
    return_col = f"return_{horizon}"
    if return_col not in backtest_df.columns:
        raise ValueError(f"Missing column: {return_col}")
    if "score" not in backtest_df.columns:
        raise ValueError("Missing column: score")

    df = backtest_df.sort_values("score").copy()
    df["rolling_return"] = df[return_col].rolling(20, min_periods=10).mean()

    positive = df[df["rolling_return"] > 0].dropna(subset=["rolling_return"])
    neutral_floor = float(positive["score"].min()) if len(positive) > 0 else 30.0

    buy_ok = df[df["rolling_return"] > 2.0].dropna(subset=["rolling_return"])
    buy_floor = float(buy_ok["score"].min()) if len(buy_ok) > 0 else 50.0

    strong_ok = df[df["rolling_return"] > 5.0].dropna(subset=["rolling_return"])
    strong_buy_floor = float(strong_ok["score"].min()) if len(strong_ok) > 0 else 70.0

    # enforce weak ordering: neutral <= buy <= strong
    buy_floor = max(buy_floor, neutral_floor)
    strong_buy_floor = max(strong_buy_floor, buy_floor)

    return BucketThresholds(
        strong_buy_floor=round(strong_buy_floor, 1),
        buy_floor=round(buy_floor, 1),
        neutral_floor=round(neutral_floor, 1),
    )


def assign_bucket(score: float, thresholds: BucketThresholds) -> str:
    if score >= thresholds.strong_buy_floor:
        return "strong"
    if score >= thresholds.buy_floor:
        return "buy"
    if score >= thresholds.neutral_floor:
        return "neutral"
    return "weak"


# ──────────────────────────────────────────────
# Inversion guard
# ──────────────────────────────────────────────


@dataclass
class BucketStats:
    bucket: str
    mean_return: float
    hit_rate: float
    n: int


def detect_inversion(
    bucket_stats: list[BucketStats],
    horizon: str = "3m",
    min_n: int = 20,
) -> dict[str, Any]:
    """
    Flags when higher-score buckets underperform lower-score buckets.

    Combines (1) adjacent-pair monotonicity after sorting by bucket strength and
    (2) direct strong vs weak comparison when both are sufficiently sampled.
    """
    qualified = [b for b in bucket_stats if b.n >= min_n]

    if len(qualified) < 2:
        return {
            "inverted": False,
            "severity": "unknown",
            "reason": f"Insufficient sample sizes (need N≥{min_n})",
            "recommendation": "Collect more data before serving signals",
            "horizon": horizon,
        }

    order = {"strong": 3, "buy": 2, "neutral": 1, "weak": 0}
    qualified.sort(key=lambda b: order.get(b.bucket, -1), reverse=True)

    returns = [b.mean_return for b in qualified]
    inversions = sum(
        1 for i in range(len(returns) - 1) if returns[i] < returns[i + 1]
    )
    inversion_ratio = inversions / (len(returns) - 1) if len(returns) > 1 else 0.0

    strong_b = next((b for b in qualified if b.bucket == "strong"), None)
    weak_b = next((b for b in qualified if b.bucket == "weak"), None)
    primary_inversion = bool(
        strong_b and weak_b and strong_b.mean_return < weak_b.mean_return
    )

    if inversion_ratio >= 0.67 or (primary_inversion and inversion_ratio >= 0.5):
        severity = "SEVERE"
        recommendation = (
            "BLOCK strong-buy signals. Apply Hurst-based regime weights. "
            "Recalibrate score thresholds using calibrate_thresholds_from_backtest() "
            "on a held-out period (avoid fitting weights and thresholds on the same slice)."
        )
    elif inversion_ratio >= 0.33 or primary_inversion:
        severity = "MODERATE"
        recommendation = (
            "Reduce strong-buy conviction. Apply regime-aware weights. "
            "Add disclaimer to high-score outputs."
        )
    else:
        severity = "NONE"
        recommendation = "No action needed."

    inverted = inversion_ratio >= 0.33 or primary_inversion

    return {
        "inverted": inverted,
        "inversion_ratio": round(inversion_ratio, 2),
        "primary_strong_vs_weak_inversion": primary_inversion,
        "severity": severity,
        "horizon": horizon,
        "bucket_returns": {b.bucket: b.mean_return for b in qualified},
        "recommendation": recommendation,
    }


def run_inversion_diagnostic(
    ticker: str,
    price_history: pd.Series,
    backtest_stats: list[BucketStats],
    current_signals: Optional[RawSignals] = None,
    horizon: str = "3m",
) -> dict[str, Any]:
    """
    Hurst → regime → weights; optional regime-aware score; inversion check on bucket stats.
    """
    hurst = compute_hurst_exponent(price_history)
    regime = classify_regime(hurst)
    weights = get_regime_weights(regime)

    inversion = detect_inversion(backtest_stats, horizon=horizon)

    new_score_result = None
    if current_signals is not None:
        new_score_result = compute_regime_aware_score(current_signals, weights, regime)

    report: dict[str, Any] = {
        "ticker": ticker,
        "hurst_exponent": round(hurst, 4),
        "asset_regime": regime.value,
        "regime_weights": weights.as_dict(),
        "inversion_check": inversion,
        "new_score": new_score_result,
    }

    log.debug(
        "signal_inversion diagnostic %s: Hurst=%.4f regime=%s inversion=%s",
        ticker,
        hurst,
        regime.value,
        inversion.get("severity"),
    )
    return report
