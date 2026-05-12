"""
Marginal Contribution to Risk (MCTR) — per-position risk contribution.

Shows what % of total portfolio volatility each position contributes,
which is often very different from its % of portfolio value.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_mctr(
    per_holding: list[dict],
    total_value: float,
    *,
    lookback_days: int = 252,
    fetch_close=None,
) -> dict[str, Any]:
    """
    Compute marginal contribution to risk for each position.

    Returns {positions: [{ticker, value_pct, risk_pct, risk_ratio}], portfolio_vol, note}
    """
    if fetch_close is None:
        from signals.fetcher import fetch_ohlcv_safe
        def fetch_close(t: str, period: str) -> pd.Series | None:
            return fetch_ohlcv_safe(t, period)

    holdings = [(h["ticker"], h.get("value", 0), h.get("pct", 0))
                for h in per_holding if h.get("ticker") and h.get("value") and h.get("pct")]

    if len(holdings) < 2 or total_value <= 0:
        return {"positions": [], "portfolio_vol": None, "note": "Need at least 2 positions"}

    tickers = [t for t, _, _ in holdings]
    weights = np.array([v / total_value for _, v, _ in holdings])

    period = "2y" if lookback_days <= 504 else "5y"
    rets_dict: dict[str, pd.Series] = {}
    for t in tickers:
        try:
            hist = fetch_close(t, period)
            if hist is not None and len(hist) > 60:
                rets_dict[t] = hist.pct_change().dropna()
        except Exception:
            pass

    if len(rets_dict) < 2:
        return {"positions": [], "portfolio_vol": None, "note": "Insufficient price history"}

    available = [t for t in tickers if t in rets_dict]
    df = pd.DataFrame({t: rets_dict[t] for t in available}).dropna()
    if len(df) < 30:
        return {"positions": [], "portfolio_vol": None, "note": "Insufficient overlapping history"}

    # Rebuild weights for available tickers only
    idx_map = {t: i for i, t in enumerate(tickers)}
    w = np.array([weights[idx_map[t]] for t in available])
    w = w / w.sum()  # renormalize

    cov = df.cov().values * 252  # annualize
    port_var = float(w @ cov @ w)
    port_vol = float(np.sqrt(port_var)) if port_var > 0 else 0.001

    # MCTR = (Cov @ w) / port_vol * w_i
    cov_w = cov @ w
    mctr_raw = (cov_w * w) / port_vol

    # Normalize to percentages
    total_mctr = mctr_raw.sum()
    if total_mctr <= 0:
        total_mctr = 1.0

    positions = []
    for i, t in enumerate(available):
        risk_pct = float(mctr_raw[i] / total_mctr * 100)
        value_pct = float(w[i] * 100)
        positions.append({
            "ticker": t,
            "value_pct": round(value_pct, 1),
            "risk_pct": round(risk_pct, 1),
            "risk_ratio": round(risk_pct / value_pct, 2) if value_pct > 0 else 0,
        })

    positions.sort(key=lambda x: -x["risk_pct"])

    # Top concentrators
    top3_risk = sum(p["risk_pct"] for p in positions[:3])
    top3_value = sum(p["value_pct"] for p in positions[:3])

    note = None
    if positions and positions[0]["risk_pct"] > positions[0]["value_pct"] * 1.5:
        top = positions[0]
        note = (
            f"{top['ticker']} is {top['value_pct']:.0f}% of value but {top['risk_pct']:.0f}% of risk "
            f"\u2014 concentration is higher than it appears"
        )

    # Portfolio beta vs SPY
    portfolio_beta = None
    try:
        if "SPY" in rets_dict:
            spy_ret = rets_dict["SPY"].reindex(df.index)
        else:
            _spy_close = fetch_close("SPY", period)
            if _spy_close is not None and len(_spy_close) > 60:
                spy_ret = _spy_close.pct_change().dropna().reindex(df.index)
            else:
                spy_ret = None

        if spy_ret is not None:
            port_ret = pd.Series((df.values * w).sum(axis=1), index=df.index)
            aligned = pd.DataFrame({"port": port_ret, "spy": spy_ret}).dropna()
            if len(aligned) > 30:
                cov_ps = np.cov(aligned["port"], aligned["spy"])
                var_spy = cov_ps[1, 1]
                if var_spy > 0:
                    portfolio_beta = round(float(cov_ps[0, 1] / var_spy), 2)
    except Exception:
        pass

    return {
        "positions": positions,
        "portfolio_vol_annual_pct": round(port_vol * 100, 1),
        "portfolio_beta": portfolio_beta,
        "top3_risk_pct": round(top3_risk, 1),
        "top3_value_pct": round(top3_value, 1),
        "note": note,
    }
