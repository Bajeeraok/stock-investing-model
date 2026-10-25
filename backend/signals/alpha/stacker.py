"""
Learn confidence-layer weights from tracked outcomes instead of hand-setting them.

Input rows carry the 7 layer scores (0..1) — under ``layer_scores`` or a
``breakdown``/``confidence_breakdown`` mapping of ``{layer: {"score": x}}`` — plus a
forward excess return vs SPY. A non-negative linear model is fit on the older 70% of
rows (by date) and checked on the newer 30%: the learned weights are only accepted if
their rank IC beats the current hand-set weights out of sample.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_WEIGHTS_PATH = BACKEND_ROOT / "data" / "alpha" / "learned_layer_weights.json"

LAYERS = (
    "regime_hmm",
    "pattern_technical",
    "lgbm_probability",
    "options_sentiment",
    "insider_signal",
    "fundamental_score",
    "nlp_sentiment",
)

_CACHE: dict[str, tuple[float, dict | None]] = {}


def extract_layer_scores(row: dict[str, Any]) -> dict[str, float]:
    src = row.get("layer_scores")
    if not isinstance(src, dict):
        src = row.get("confidence_breakdown") or row.get("breakdown") or {}
    out = {}
    for k in LAYERS:
        v = src.get(k)
        if isinstance(v, dict):
            v = v.get("score")
        try:
            if v is not None and np.isfinite(float(v)):
                out[k] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def _rank_ic(pred: np.ndarray, y: np.ndarray) -> float:
    if len(pred) < 10:
        return float("nan")
    pr = np.argsort(np.argsort(pred))
    yr = np.argsort(np.argsort(y))
    c = np.corrcoef(pr, yr)[0, 1]
    return float(c) if np.isfinite(c) else float("nan")


def _matrix(rows: list[dict[str, Any]], target: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    X, y, dates = [], [], []
    for r in rows:
        s = extract_layer_scores(r)
        t = r.get(target)
        if t is None or len(s) < 3:
            continue
        X.append([s.get(k, 0.5) for k in LAYERS])
        y.append(float(t))
        dates.append(str(r.get("as_of_date") or r.get("date") or ""))
    order = np.argsort(dates, kind="stable")
    return np.asarray(X)[order], np.asarray(y)[order], [dates[i] for i in order]


def fit_layer_weights(
    rows: Iterable[dict[str, Any]],
    default_weights: dict[str, float],
    *,
    target: str = "excess_return_pct",
    min_n: int = 200,
    train_frac: float = 0.7,
) -> dict[str, Any]:
    from sklearn.linear_model import LinearRegression

    X, y, _ = _matrix(list(rows), target)
    n = len(y)
    if n < min_n:
        return {"accepted": False, "n": n, "reason": f"need >= {min_n} rows with layer scores and {target}"}
    cut = int(n * train_frac)
    mu, sd = X[:cut].mean(0), X[:cut].std(0) + 1e-9
    lr = LinearRegression(positive=True).fit((X[:cut] - mu) / sd, y[:cut])
    coef = np.clip(lr.coef_ / sd, 0, None)
    if coef.sum() <= 0:
        return {"accepted": False, "n": n, "reason": "no layer has positive out-of-sample relation"}
    w = coef / coef.sum()
    dw = np.array([default_weights.get(k, 0.0) for k in LAYERS])
    dw = dw / dw.sum() if dw.sum() > 0 else dw
    ic_learned = _rank_ic(X[cut:] @ w, y[cut:])
    ic_default = _rank_ic(X[cut:] @ dw, y[cut:])
    accepted = bool(np.isfinite(ic_learned) and (not np.isfinite(ic_default) or ic_learned > ic_default))
    return {
        "accepted": accepted,
        "n": n,
        "n_test": n - cut,
        "weights": {k: round(float(v), 4) for k, v in zip(LAYERS, w)},
        "ic_learned": round(ic_learned, 4) if np.isfinite(ic_learned) else None,
        "ic_default": round(ic_default, 4) if np.isfinite(ic_default) else None,
    }


def save_weights(result_by_horizon: dict[str, dict[str, Any]], path: str | Path | None = None) -> Path:
    p = Path(path or DEFAULT_WEIGHTS_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "horizons": result_by_horizon}
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _CACHE.pop(str(p), None)
    return p


def learned_horizon_weights(horizon: str, path: str | Path | None = None) -> dict[str, float] | None:
    """Accepted learned weights for a horizon, else None (callers keep hand-set weights)."""
    p = Path(path or DEFAULT_WEIGHTS_PATH)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    hit = _CACHE.get(str(p))
    if not hit or hit[0] != mtime:
        try:
            hit = (mtime, json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            hit = (mtime, None)
        _CACHE[str(p)] = hit
    res = ((hit[1] or {}).get("horizons") or {}).get(horizon) or {}
    return dict(res["weights"]) if res.get("accepted") and res.get("weights") else None
