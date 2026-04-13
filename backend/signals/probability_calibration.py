"""
Post-hoc calibration for ML horizon probabilities (Platt scaling or isotonic on logit).

When enabled in config, raw LightGBM probs are mapped so validation reliability improves.
Persist JSON via scripts/fit_probability_calibration.py.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-np.clip(x, -50, 50))))


def _platt_from_logit(p: float, a: float, b: float) -> float:
    eps = 1e-9
    p = float(np.clip(p, eps, 1.0 - eps))
    z = np.log(p / (1.0 - p))
    return _sigmoid(a * z + b)


def _isotonic_apply(p: float, knots: list[dict[str, float]]) -> float:
    """Piecewise linear: knots sorted by x (raw prob), y is calibrated."""
    if not knots:
        return p
    xs = [float(k["x"]) for k in knots]
    ys = [float(k["y"]) for k in knots]
    if p <= xs[0]:
        return ys[0]
    if p >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= p <= xs[i + 1]:
            t = (p - xs[i]) / (xs[i + 1] - xs[i] + 1e-15)
            return float(ys[i] + t * (ys[i + 1] - ys[i]))
    return p


def load_calibration_artifact(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        logger.debug("Calibration file not found: %s", p)
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load calibration %s: %s", p, e)
        return None


def calibrate_probability(
    p: float | None,
    horizon_key: str,
    artifact: dict[str, Any] | None,
) -> float | None:
    if p is None or artifact is None:
        return p
    method = (artifact.get("method") or "platt").lower()
    block = artifact.get(horizon_key) or artifact.get(horizon_key.replace("_term", ""))
    if block is None:
        return p
    if method == "platt":
        a = float(block.get("a", 1.0))
        b = float(block.get("b", 0.0))
        return round(_platt_from_logit(p, a, b), 4)
    if method == "isotonic":
        knots = block.get("knots")
        if isinstance(knots, list) and knots:
            return round(_isotonic_apply(p, knots), 4)
    return p


def _resolve_calibration_path(config: dict) -> Path | None:
    conf = (config.get("confidence") or {}).get("calibration") or {}
    rel = conf.get("path") or "data/calibration/ml_horizons.json"
    base = conf.get("base_path")
    if base:
        return Path(base) / rel
    p = Path(rel)
    if p.is_absolute():
        return p
    # backend/ root (one level above signals/)
    backend_root = Path(__file__).resolve().parent.parent
    return (backend_root / rel).resolve()


def apply_calibration_to_ml_horizons(
    ml_horizons: dict[str, Any] | None,
    config: dict | None,
) -> dict[str, Any] | None:
    if not ml_horizons or not config:
        return ml_horizons
    conf = (config.get("confidence") or {}).get("calibration") or {}
    if not conf.get("enabled"):
        return ml_horizons
    path = _resolve_calibration_path(config)
    art = load_calibration_artifact(path)
    if not art:
        return ml_horizons
    out = dict(ml_horizons)
    for key in ("short", "medium", "long"):
        if key not in out:
            continue
        h = dict(out[key] or {})
        raw = h.get("prob")
        if raw is not None:
            h["prob_raw"] = raw
            h["prob"] = calibrate_probability(float(raw), key, art)
        out[key] = h
    return out
