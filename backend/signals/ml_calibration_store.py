"""
Load / apply ML calibration artifacts (reliability + actionable discount factor).

Artifact written by scripts/fit_ml_calibration_from_audit.py
-> data/calibration/ml_horizons.json
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_REL = "data/calibration/ml_horizons.json"


def resolve_calibration_path(config: dict | None = None) -> Path:
    conf = ((config or {}).get("confidence") or {}).get("calibration") or {}
    rel = conf.get("path") or _DEFAULT_REL
    base = conf.get("base_path")
    if base:
        return Path(base) / rel
    p = Path(rel)
    if p.is_absolute():
        return p
    return (_BACKEND_ROOT / rel).resolve()


def load_ml_calibration_artifact(
    path: str | Path | None = None,
    *,
    config: dict | None = None,
) -> dict[str, Any] | None:
    p = Path(path) if path else resolve_calibration_path(config)
    if not p.is_file():
        return None
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning("Failed to load ML calibration %s: %s", p, e)
        return None


@lru_cache(maxsize=4)
def _cached_factor(path_str: str, mtime_ns: int) -> float:
    art = load_ml_calibration_artifact(path_str)
    if not art:
        return 1.0
    raw = art.get("ml_calibration_factor")
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return 1.0
    # Never inflate headline scores; floor so a bad fit cannot zero the card.
    return max(0.5, min(1.0, f))


def clear_ml_calibration_cache() -> None:
    _cached_factor.cache_clear()


def get_ml_calibration_factor(config: dict | None = None) -> float:
    """
    Discount for actionable_score when audit shows ML overconfidence.
    Returns 1.0 when no artifact / missing factor.
    """
    conf = ((config or {}).get("confidence") or {}).get("calibration") or {}
    if conf.get("actionable_factor_enabled") is False:
        return 1.0
    path = resolve_calibration_path(config)
    if not path.is_file():
        return 1.0
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return 1.0
    return _cached_factor(str(path), mtime)


def reliability_bins(
    probs: list[float],
    ys: list[int],
    *,
    n_bins: int = 10,
) -> list[dict[str, Any]]:
    """Equal-width bins on [0,1]; y is 0/1 realized positive forward return."""
    if not probs or len(probs) != len(ys):
        return []
    out: list[dict[str, Any]] = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        idx = [
            j
            for j, p in enumerate(probs)
            if (lo <= p < hi) or (i == n_bins - 1 and p == 1.0)
        ]
        if not idx:
            continue
        pred = sum(probs[j] for j in idx) / len(idx)
        realized = sum(ys[j] for j in idx) / len(idx)
        out.append(
            {
                "bin_lo": round(lo, 2),
                "bin_hi": round(hi, 2),
                "n": len(idx),
                "mean_predicted": round(pred, 4),
                "mean_realized": round(realized, 4),
                "gap": round(realized - pred, 4),
            }
        )
    return out


def brier_score(probs: list[float], ys: list[int]) -> float | None:
    if not probs or len(probs) != len(ys):
        return None
    return sum((p - y) ** 2 for p, y in zip(probs, ys)) / len(probs)
