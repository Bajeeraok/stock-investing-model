"""
Aggregate model health for dashboard: EOD freshness, accuracy report time, forward tracking,
optional persisted backtest/calibration from scripts/update_model_health.py.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def build_model_health(
    data_root: Path,
    config: dict | None,
    forward_tracking: dict | None,
    eod_snapshots: list[dict] | None,
    model_validation: dict | None = None,
) -> dict[str, Any]:
    """
    Single object for ModelHealthStrip + API. Merges live data with optional data/model_health.json
    written by scheduled backtest validation.
    """
    out: dict[str, Any] = {
        "accuracy_as_of": None,
        "eod_latest_date": None,
        "forward_hold_add_hit_rate_20d": None,
        "forward_observations_20d": None,
        "validation_direction_accuracy_pct": None,
        "calibration_ok": None,
        "calibration_score": None,
        "walk_forward_ok": None,
        "backtest_last_run": None,
        "message": None,
    }
    cfg = config or {}

    acc_path = data_root / "accuracy_price_targets.json"
    if acc_path.exists():
        try:
            with open(acc_path, encoding="utf-8") as f:
                acc = json.load(f)
            out["accuracy_as_of"] = acc.get("as_of")
        except Exception as e:
            logger.debug("model_health accuracy read: %s", e)

    if eod_snapshots:
        try:
            out["eod_latest_date"] = eod_snapshots[0].get("date")
        except Exception:
            pass

    sb = (forward_tracking or {}).get("summary_by_signal") or {}
    ha = sb.get("HOLD/ADD")
    if isinstance(ha, dict):
        out["forward_hold_add_hit_rate_20d"] = ha.get("hit_rate_pct")
        out["forward_observations_20d"] = ha.get("n_observations")

    mv_sum = (model_validation or {}).get("summary") or {}
    if isinstance(mv_sum, dict) and mv_sum.get("direction_accuracy_pct") is not None:
        out["validation_direction_accuracy_pct"] = mv_sum.get("direction_accuracy_pct")

    mh_path = data_root / "model_health.json"
    if mh_path.exists():
        try:
            with open(mh_path, encoding="utf-8") as f:
                persisted = json.load(f)
            for k in (
                "calibration_ok",
                "calibration_score",
                "walk_forward_ok",
                "backtest_last_run",
                "walk_forward_note",
                "walk_forward_regime_breakdown",
                "backtest_ticker",
            ):
                if k in persisted:
                    out[k] = persisted[k]
        except Exception as e:
            logger.debug("model_health persisted read: %s", e)

    cal_min = float((cfg.get("backtest") or {}).get("calibration_ok_min", cfg.get("score", {}).get("buy_min", 70)))
    if out.get("calibration_score") is not None:
        try:
            out["calibration_ok"] = float(out["calibration_score"]) >= cal_min
        except (TypeError, ValueError):
            pass

    if not out["accuracy_as_of"] and not out["eod_latest_date"] and not out["forward_hold_add_hit_rate_20d"]:
        out["message"] = (forward_tracking or {}).get("message") or "Add EOD snapshots for forward stats"
    return out
