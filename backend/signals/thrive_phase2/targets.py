"""ATR-based price targets per setup type."""
from __future__ import annotations

from typing import Any, Optional

from ._constants import ATR_CONFIG
from .models import IntradayData, SetupType


class PriceTargetGenerator:
    def __init__(self, atr_config: dict[str, dict[str, float]] | None = None):
        self._atr = atr_config if atr_config is not None else {k: dict(v) for k, v in ATR_CONFIG.items()}

    def generate(
        self,
        data: IntradayData,
        setup_type: SetupType,
        profile: str,
    ) -> Optional[dict[str, Any]]:
        if setup_type == SetupType.NO_SETUP:
            return None

        p = data.current_price
        atr = data.atr
        cfg = self._atr.get(setup_type.value)
        if not cfg:
            return {"valid": False, "reason": f"Unknown setup {setup_type.value}"}

        if setup_type == SetupType.BREAKOUT:
            entry = round(data.resistance + (atr * 0.1), 2)
            target_1 = round(data.resistance + (atr * cfg["t1"]), 2)
            target_2 = round(data.resistance + (atr * cfg["t2"]), 2)
            stop = round(data.resistance - (atr * cfg["stop"]), 2)
        elif setup_type == SetupType.MEAN_REVERSION:
            entry = round(p, 2)
            target_1 = round(data.vwap, 2)
            target_2 = round(data.ma20, 2)
            stop = round(data.support - (atr * cfg["stop"]), 2)
            if target_1 <= entry:
                target_1 = round(entry + atr * cfg["t1"], 2)
            if target_2 <= target_1:
                target_2 = round(entry + atr * cfg["t2"], 2)
        elif setup_type == SetupType.MOMENTUM_CONTINUATION:
            entry = round(p, 2)
            target_1 = round(p + (atr * cfg["t1"]), 2)
            target_2 = round(p + (atr * cfg["t2"]), 2)
            stop = round(data.ma20 - (atr * cfg["stop"]), 2)
        else:
            return None

        risk = entry - stop
        reward = target_1 - entry

        if risk <= 0:
            return {"valid": False, "reason": "Stop above entry — invalid"}

        rr = reward / risk
        if rr < 1.5:
            return {
                "valid": False,
                "reason": f"R:R {rr:.1f} below minimum 1.5 — skip setup",
            }

        if profile == "long_term":
            stop = round(stop * 0.97, 2)
            target_2 = round(target_2 * 1.10, 2)
        elif profile == "day_short":
            stop = round(stop * 1.02, 2)

        risk = entry - stop
        reward = target_1 - entry
        rr = reward / risk if risk > 0 else 0.0

        return {
            "valid": True,
            "entry": entry,
            "target_1": target_1,
            "target_2": target_2,
            "stop": stop,
            "rr_ratio": round(rr, 2),
            "atr_used": round(atr, 4),
            "setup": setup_type.value,
        }
