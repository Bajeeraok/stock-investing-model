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
) -> tuple[str, dict[str, Any]]:
    """
    Returns ("TRENDING" | "MEAN_REVERTING", metadata dict).

    When disabled in config or insufficient history, returns TRENDING.
    """
    del volume  # reserved for future (e.g. volume climax features)

    ic = ((config or {}).get("score") or {}).get("interpretation") or {}
    if not ic.get("enabled", False):
        return "TRENDING", {"reason": "disabled"}

    tnorm = (ticker or "").upper().replace(".", "-").split("-")[0]
    force_tr = [str(x).upper().replace(".", "-").split("-")[0] for x in (ic.get("force_trending") or [])]
    if tnorm and tnorm in force_tr:
        return "TRENDING", {"reason": "force_trending", "ticker": tnorm}

    force_mr = [str(x).upper().replace(".", "-").split("-")[0] for x in (ic.get("force_mean_reverting") or [])]
    if tnorm and tnorm in force_mr:
        return "MEAN_REVERTING", {"reason": "force_mean_reverting", "ticker": tnorm}

    min_bars = int(ic.get("min_bars", 130))
    acf_window = int(ic.get("acf_window", 126))
    mr_thr = float(ic.get("acf_mean_reversion_max", -0.028))
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
    }

    if acf1 <= mr_thr:
        meta["reason"] = "negative_autocorr"
        return "MEAN_REVERTING", meta
    if acf1 >= tr_min:
        meta["reason"] = "positive_autocorr"
        return "TRENDING", meta

    meta["reason"] = "neutral_autocorr"
    return "TRENDING", meta
