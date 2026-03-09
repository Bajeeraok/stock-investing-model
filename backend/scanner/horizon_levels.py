"""
Horizon levels cache and retail-alert state for ENTRY_ZONE_ENTERED, STOP_HIT, TARGET_HIT, ML_PROB_CROSSED.
Levels are written when ticker detail builds investor_summary; scanner reads them to fire price-level alerts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("scanner.horizon_levels")

LEVELS_FILENAME = "horizon_levels.json"
STATE_FILENAME = "retail_alert_state.json"

# Days to surface "Earnings soon" (retail quick decision)
EARNINGS_SOON_DAYS = (1, 3, 5, 7)

# ML prob threshold for "model supports add" alert
ML_PROB_CROSS_THRESHOLD = 25.0


def _scanner_dir(data_root: Path) -> Path:
    d = data_root / "scanner"
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_horizon_levels(data_root: Path) -> dict[str, dict[str, Any]]:
    """Read ticker -> {entry_low, entry_high, stop_loss, target, horizon_label}. Empty if missing."""
    path = _scanner_dir(data_root) / LEVELS_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("read_horizon_levels failed: %s", e)
        return {}


def write_horizon_levels(data_root: Path, levels: dict[str, dict[str, Any]]) -> None:
    """Write full horizon levels map (merge with existing or replace)."""
    path = _scanner_dir(data_root) / LEVELS_FILENAME
    try:
        path.write_text(json.dumps(levels, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("write_horizon_levels failed: %s", e)


def merge_horizon_levels_for_ticker(
    data_root: Path,
    ticker: str,
    *,
    entry_low: float,
    entry_high: float,
    stop_loss: float,
    target: float,
    horizon_label: str = "Short-term",
) -> None:
    """Merge one ticker's horizon levels into the cache (e.g. when ticker detail is built)."""
    ticker = ticker.upper()
    levels = read_horizon_levels(data_root)
    levels[ticker] = {
        "entry_low": round(entry_low, 2),
        "entry_high": round(entry_high, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target, 2),
        "horizon_label": horizon_label,
    }
    write_horizon_levels(data_root, levels)


def read_retail_alert_state(data_root: Path) -> dict[str, dict[str, Any]]:
    """Read ticker -> {was_in_entry_zone, last_price, previous_ml_prob}. Empty if missing."""
    path = _scanner_dir(data_root) / STATE_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("read_retail_alert_state failed: %s", e)
        return {}


def write_retail_alert_state(data_root: Path, state: dict[str, dict[str, Any]]) -> None:
    """Write full retail alert state for next scan."""
    path = _scanner_dir(data_root) / STATE_FILENAME
    try:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("write_retail_alert_state failed: %s", e)


def read_ml_probs(data_root: Path) -> dict[str, float]:
    """Read ticker -> short-term ML prob (0-100). From dashboard cache if present."""
    path = _scanner_dir(data_root) / "ml_probs.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {k.upper(): float(v) for k, v in data.items() if v is not None}
    except Exception as e:
        logger.debug("read_ml_probs failed: %s", e)
        return {}


def merge_ml_prob_for_ticker(data_root: Path, ticker: str, prob_pct: float) -> None:
    """Write one ticker's short-term ML prob so scanner can fire ML_PROB_CROSSED."""
    ticker = ticker.upper()
    probs = read_ml_probs(data_root)
    probs[ticker] = round(float(prob_pct), 2)
    path = _scanner_dir(data_root) / "ml_probs.json"
    try:
        path.write_text(json.dumps(probs, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("merge_ml_prob_for_ticker failed: %s", e)
