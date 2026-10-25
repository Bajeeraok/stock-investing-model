"""
Model / data drift monitoring: feature PSI vs the training reference, calibration drift of
tracked probabilities, and realized excess-return decay. Produces a status per check
(ok / warn / alert) that the daily job writes to data/alpha/drift_report.json.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

PSI_WARN, PSI_ALERT = 0.10, 0.25


def psi(reference: pd.Series, current: pd.Series, bins: int = 10) -> float:
    r = pd.to_numeric(reference, errors="coerce").dropna()
    c = pd.to_numeric(current, errors="coerce").dropna()
    if len(r) < 20 or len(c) < 20:
        return float("nan")
    edges = np.unique(np.quantile(r, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    rp = np.histogram(r, edges)[0] / len(r)
    cp = np.histogram(c, edges)[0] / len(c)
    rp, cp = np.clip(rp, 1e-4, None), np.clip(cp, 1e-4, None)
    return float(np.sum((cp - rp) * np.log(cp / rp)))


def _status(v: float, warn: float, alert: float) -> str:
    if not np.isfinite(v):
        return "unknown"
    return "alert" if v >= alert else "warn" if v >= warn else "ok"


def feature_drift(reference: pd.DataFrame, current: pd.DataFrame, features: list[str] | None = None) -> dict[str, Any]:
    feats = features or [c for c in reference.columns if c in current.columns and reference[c].dtype.kind in "fi"]
    out = {}
    for f in feats:
        v = psi(reference[f], current[f])
        out[f] = {"psi": round(v, 4) if np.isfinite(v) else None, "status": _status(v, PSI_WARN, PSI_ALERT)}
    return out


def calibration_drift(prob: pd.Series, outcome: pd.Series, bins: int = 5) -> dict[str, Any]:
    """Expected calibration error of tracked probabilities vs realized 0/1 outcomes."""
    d = pd.DataFrame({"p": prob, "y": outcome}).dropna()
    if len(d) < 30:
        return {"n": len(d), "ece": None, "status": "unknown"}
    d["b"] = pd.cut(d["p"], np.linspace(0, 1, bins + 1), include_lowest=True)
    g = d.groupby("b", observed=True).agg(p=("p", "mean"), y=("y", "mean"), n=("y", "size"))
    ece = float((g["n"] * (g["p"] - g["y"]).abs()).sum() / g["n"].sum())
    return {"n": len(d), "ece": round(ece, 4), "status": _status(ece, 0.05, 0.10)}


def edge_decay(excess_pct: pd.Series, expected_pct: float, window: int = 60) -> dict[str, Any]:
    """Rolling mean realized excess vs the expected (walk-forward) excess."""
    x = pd.to_numeric(excess_pct, errors="coerce").dropna().tail(window)
    if len(x) < 20:
        return {"n": len(x), "status": "unknown"}
    m = float(x.mean())
    se = float(x.std(ddof=1) / np.sqrt(len(x))) or 1e-9
    z = (m - expected_pct) / se
    return {"n": len(x), "realized_mean_pct": round(m, 3), "expected_pct": expected_pct, "z": round(z, 2),
            "status": "alert" if z < -2.5 else "warn" if z < -1.5 else "ok"}


def overall_status(*sections: dict[str, Any]) -> str:
    seen = []
    for s in sections:
        if "status" in s:
            seen.append(s["status"])
        else:
            seen.extend(v.get("status") for v in s.values() if isinstance(v, dict))
    return "alert" if "alert" in seen else "warn" if "warn" in seen else "ok"
