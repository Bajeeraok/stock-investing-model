"""
Score interpretation style: TRENDING vs MEAN_REVERTING.

Momentum-style composites (trend + RSI + MACD) can invert vs forward returns on choppy
tape: high scores cluster after rallies (poor forward edge), low scores after selloffs
(better forward edge). We do **not** change the raw 0–100 score; we only flip how
thresholds map to BUY/HOLD/SELL and horizon suggestions when the detector says MR.

Detection: lag-1 autocorrelation of daily returns over a recent window — negative
autocorr ≈ short-term mean reversion (up days follow down days).
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def detect_interpretation_style(
    close: pd.Series,
    volume: pd.Series | None = None,
    config: dict | None = None,
    ticker: str | None = None,
    *,
    for_backtest_buckets: bool = False,
) -> tuple[str, dict[str, Any]]:
    """
    Returns ("TRENDING" | "MEAN_REVERTING", metadata dict).

    When disabled in config or insufficient history, returns TRENDING.

    for_backtest_buckets: when True, ignores interpretation.enabled and runs ACF / force lists
    if score.interpretation.apply_to_backtest_buckets is True — so historical bucket tests can
    align with MR logic without changing live signal gating.
    """
    del volume  # reserved for future (e.g. volume climax features)

    ic = ((config or {}).get("score") or {}).get("interpretation") or {}
    apply_bt = bool(ic.get("apply_to_backtest_buckets", True))
    if not for_backtest_buckets and not ic.get("enabled", False):
        return "TRENDING", {"reason": "disabled"}
    if for_backtest_buckets and not apply_bt:
        return "TRENDING", {"reason": "backtest_buckets_disabled"}

    tnorm = (ticker or "").upper().replace(".", "-").split("-")[0]
    force_tr = [str(x).upper().replace(".", "-").split("-")[0] for x in (ic.get("force_trending") or [])]
    if tnorm and tnorm in force_tr:
        return "TRENDING", {"reason": "force_trending", "ticker": tnorm}

    force_mr = [str(x).upper().replace(".", "-").split("-")[0] for x in (ic.get("force_mean_reverting") or [])]
    if tnorm and tnorm in force_mr:
        return "MEAN_REVERTING", {"reason": "force_mean_reverting", "ticker": tnorm}

    min_bars = int(ic.get("min_bars", 130))
    acf_window = int(ic.get("acf_window", 126))
    # Live signals: strict MR cutoff. Backtest buckets: relaxed by default so more bars
    # get (100−score) bucket mapping — the strict live threshold left most history as
    # TRENDING, so refresh looked unchanged.
    mr_thr = float(ic.get("acf_mean_reversion_max", -0.028))
    if for_backtest_buckets:
        mr_thr = float(ic.get("acf_mean_reversion_max_backtest", 0.0))
    tr_min = float(ic.get("acf_trend_min", 0.04))

    if close is None or len(close.dropna()) < min_bars:
        return "TRENDING", {"reason": "insufficient_history", "min_bars": min_bars}

    r = close.pct_change().dropna()
    if len(r) < acf_window:
        return "TRENDING", {"reason": "insufficient_returns", "have": len(r)}

    tail = r.iloc[-acf_window:]
    try:
        acf1 = float(tail.autocorr(lag=1))
    except Exception:
        return "TRENDING", {"reason": "acf_failed"}

    if pd.isna(acf1):
        return "TRENDING", {"reason": "acf_nan"}

    meta: dict[str, Any] = {
        "acf_lag1": round(acf1, 4),
        "acf_window": acf_window,
        "mr_threshold": mr_thr,
        "trend_threshold": tr_min,
        "for_backtest_buckets": for_backtest_buckets,
    }

    if acf1 <= mr_thr:
        meta["reason"] = "negative_autocorr"
        return "MEAN_REVERTING", meta
    if acf1 >= tr_min:
        meta["reason"] = "positive_autocorr"
        return "TRENDING", meta

    # Neutral autocorr band: live = TRENDING. For backtest buckets, treat chop as MR
    # so bucket assignment matches dip/rally semantics (optional).
    if for_backtest_buckets and ic.get("backtest_neutral_chop_as_mr", True):
        meta["reason"] = "neutral_chop_as_mr"
        return "MEAN_REVERTING", meta

    meta["reason"] = "neutral_autocorr"
    return "TRENDING", meta


def backtest_bucket_style_at_bar(
    close: pd.Series,
    idx: int,
    ticker: str,
    config: dict | None = None,
) -> str:
    """
    Interpretation style used for bucket assignment at bar idx (causal subset only up to idx).

    Matches ``composite_bar_score_for_backtest`` / ``detect_interpretation_style(..., for_backtest_buckets=True)``.
    Returns ``"MEAN_REVERTING"`` or ``"TRENDING"``.
    """
    subset = close.iloc[: idx + 1]
    style, _ = detect_interpretation_style(
        subset,
        None,
        config,
        ticker=ticker,
        for_backtest_buckets=True,
    )
    return style


def _norm_ticker_sym(ticker: str | None) -> str:
    if not ticker:
        return ""
    return str(ticker).strip().upper().replace(".", "-").split("-")[0]


def effective_buy_min(ticker: str, score_cfg: dict | None = None) -> float:
    """
    BUY threshold for ML-aware signals and portfolio suggestions.
    `score_cfg` is the `score` section from config (e.g. config.get("score") or {}).

    Optional `buy_min_by_ticker` map overrides global `buy_min` per symbol (backtest calibration).
    """
    sc = score_cfg or {}
    base = float(sc.get("buy_min", 70))
    ovr = sc.get("buy_min_by_ticker") or {}
    t = _norm_ticker_sym(ticker)
    if t and t in ovr and ovr[t] is not None:
        try:
            v = float(ovr[t])
            if 0 < v <= 100:
                return v
        except (TypeError, ValueError):
            pass
    return base
