"""Thrive Alpha Phase 2 — tunable constants (override via config.thrive_phase2 in config.yaml)."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

# Minimum hit rate to trust 1m (~21d) short-term gate
MIN_HIT_RATE_1M = 0.65

# Starting points — tune after 2–4 weeks of live signals vs actual exits (see Phase 2 playbook).
ATR_CONFIG = {
    "breakout": {"t1": 1.0, "t2": 2.0, "stop": 0.5},
    "mean_reversion": {"t1": 0.8, "t2": 1.5, "stop": 0.4},
    "momentum_continuation": {"t1": 1.5, "t2": 3.0, "stop": 0.6},
}

SIGNAL_MAX_AGE = {
    "day_short": timedelta(hours=4),
    "swing": timedelta(days=2),
    "long_term": timedelta(days=30),
}


def merge_phase2_config(config: dict | None) -> dict[str, Any]:
    """Overlay config.thrive_phase2 onto defaults."""
    base = {
        "min_hit_rate_1m": MIN_HIT_RATE_1M,
        "atr_config": {k: dict(v) for k, v in ATR_CONFIG.items()},
        "bull_baseline_error": 0.0061,
        "observed_bear_error_band": 0.0061,
    }
    raw = (config or {}).get("thrive_phase2") or {}
    if isinstance(raw, dict):
        if "min_hit_rate_1m" in raw:
            base["min_hit_rate_1m"] = float(raw["min_hit_rate_1m"])
        if "bull_baseline_error" in raw:
            base["bull_baseline_error"] = float(raw["bull_baseline_error"])
        if "observed_bear_error_band" in raw:
            base["observed_bear_error_band"] = float(raw["observed_bear_error_band"])
        if "atr_config" in raw and isinstance(raw["atr_config"], dict):
            for k, v in raw["atr_config"].items():
                if isinstance(v, dict) and k in base["atr_config"]:
                    base["atr_config"][k] = {**base["atr_config"][k], **v}
    return base
