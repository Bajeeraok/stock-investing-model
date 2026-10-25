"""
Core/satellite allocation: SPY is the core; a trend-regime filter cuts equity exposure in
risk-off tape; a satellite sleeve for stock picks exists only while a selection signal is
validated (otherwise it folds back into SPY).

Regime rule (causal, evaluated on the close, applied next session):
  risk_on  when SPY > SMA(ma_days) * (1 + band)   — re-entry needs a clear break up
  risk_off when SPY < SMA(ma_days) * (1 - band)   — exit needs a clear break down
  otherwise keep the previous state (hysteresis avoids whipsaws around the average).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

DEFAULTS: dict[str, Any] = {
    "ma_days": 200,
    "band_pct": 1.0,
    "risk_on_equity_pct": 100,
    "risk_off_equity_pct": 30,
    "satellite_pct": 20,
    "cost_bps": 5,
}


def _cfg(cfg: dict | None) -> dict[str, Any]:
    out = dict(DEFAULTS)
    out.update({k: v for k, v in (cfg or {}).items() if v is not None})
    return out


def regime_series(close: pd.Series, ma_days: int = 200, band_pct: float = 1.0) -> pd.Series:
    """1.0 = risk-on, 0.0 = risk-off, NaN before the average has enough history."""
    close = close.dropna()
    sma = close.rolling(ma_days).mean()
    up, dn = sma * (1 + band_pct / 100), sma * (1 - band_pct / 100)
    state = np.full(len(close), np.nan)
    cur = np.nan
    c, u, d = close.to_numpy(), up.to_numpy(), dn.to_numpy()
    for i in range(len(close)):
        if np.isnan(u[i]):
            continue
        if np.isnan(cur):
            cur = 1.0 if c[i] >= sma.iloc[i] else 0.0
        elif c[i] > u[i]:
            cur = 1.0
        elif c[i] < d[i]:
            cur = 0.0
        state[i] = cur
    return pd.Series(state, index=close.index)


def allocation(spy_close: pd.Series, *, satellite_validated: bool = False, cfg: dict | None = None) -> dict[str, Any]:
    """Today's recommended split (percent of portfolio) plus the evidence behind it."""
    c = _cfg(cfg)
    reg = regime_series(spy_close, int(c["ma_days"]), float(c["band_pct"]))
    if reg.dropna().empty:
        return {"status": "insufficient_history"}
    risk_on = bool(reg.dropna().iloc[-1] >= 0.5)
    equity = float(c["risk_on_equity_pct"] if risk_on else c["risk_off_equity_pct"])
    sat = float(c["satellite_pct"]) if (satellite_validated and risk_on) else 0.0
    sma = float(spy_close.rolling(int(c["ma_days"])).mean().iloc[-1])
    last = float(spy_close.iloc[-1])
    if not satellite_validated:
        sat_note = "No stock-selection signal has passed out-of-sample validation — satellite folded into SPY."
    elif not risk_on:
        sat_note = "Risk-off — satellite closed; reduced exposure held in SPY only."
    else:
        sat_note = "Validated selection signal — satellite sleeve open for top-ranked picks."
    return {
        "as_of": str(pd.Timestamp(spy_close.index[-1]).date()),
        "regime": "risk_on" if risk_on else "risk_off",
        "spy_close": round(last, 2),
        "spy_sma": round(sma, 2),
        "spy_vs_sma_pct": round(100 * (last / sma - 1), 2),
        "core_spy_pct": round(equity - sat, 1),
        "satellite_pct": round(sat, 1),
        "cash_pct": round(100 - equity, 1),
        "satellite_validated": bool(satellite_validated),
        "satellite_note": sat_note,
        "rule": (
            f"SPY vs {int(c['ma_days'])}d SMA with ±{c['band_pct']}% band: risk-on {c['risk_on_equity_pct']}% "
            f"equity, risk-off {c['risk_off_equity_pct']}% equity (rest in T-bills)."
        ),
    }


def backtest(
    spy_close: pd.Series,
    cash_yield_pct: pd.Series | float = 0.0,
    *,
    cfg: dict | None = None,
) -> dict[str, Any]:
    """Daily backtest of the regime rule vs buy-and-hold SPY (signal on close, trade next day)."""
    c = _cfg(cfg)
    close = spy_close.dropna()
    ret = close.pct_change().fillna(0.0)
    reg = regime_series(close, int(c["ma_days"]), float(c["band_pct"]))
    on, off = float(c["risk_on_equity_pct"]) / 100, float(c["risk_off_equity_pct"]) / 100
    w = (reg * on + (1 - reg) * off).shift(1)
    start = w.first_valid_index()
    ret, w = ret.loc[start:], w.loc[start:]
    if isinstance(cash_yield_pct, pd.Series):
        cy = cash_yield_pct.reindex(ret.index).ffill().fillna(0.0) / 100 / 252
    else:
        cy = pd.Series(float(cash_yield_pct) / 100 / 252, index=ret.index)
    turn = w.diff().abs().fillna(0.0)
    strat = w * ret + (1 - w) * cy - turn * float(c["cost_bps"]) / 1e4
    return {
        "start": str(ret.index[0].date()),
        "end": str(ret.index[-1].date()),
        "buy_hold": _metrics(ret),
        "regime": _metrics(strat),
        "avg_equity_pct": round(100 * float(w.mean()), 1),
        "switches_per_year": round(float((turn > 0).sum()) / (len(ret) / 252), 2),
        "equity_curve": strat,
        "bh_curve": ret,
    }


def _metrics(r: pd.Series) -> dict[str, float]:
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    vol = float(r.std() * np.sqrt(252))
    dd = float((eq / eq.cummax() - 1).min())
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 else 0.0
    return {
        "cagr_pct": round(100 * cagr, 2),
        "vol_pct": round(100 * vol, 2),
        "sharpe": round(float(r.mean() / r.std() * np.sqrt(252)), 2) if r.std() > 0 else 0.0,
        "max_dd_pct": round(100 * dd, 2),
        "calmar": round(cagr / abs(dd), 2) if dd < 0 else 0.0,
    }


def satellite_validated(alpha_dir) -> bool:
    """Satellite opens only when some stock-selection signal passed out-of-sample checks."""
    import json
    from pathlib import Path

    d = Path(alpha_dir)
    try:
        from signals.alpha.pooled_model import load_artifact

        art = load_artifact(d / "pooled_model.pkl") or {}
        if any(isinstance(h, dict) and h.get("promoted") for h in (art.get("horizons") or {}).values()):
            return True
    except Exception:
        pass
    try:
        return bool(json.loads((d / "fundamental_validation.json").read_text()).get("validated"))
    except (OSError, ValueError, AttributeError):
        return False
