"""
Versioned verdict rules for signal audit outcomes (Phase 2).

See docs/audit/SIGNAL_AUDIT_FORWARD_TRACKING.md §7.
"""
from __future__ import annotations

from typing import Any

VERDICT_RULE_V1 = "audit_v1"
VERDICT_RULE_TACTICAL_5D = "tactical_5d_v1"


def _sig_upper(*parts: str | None) -> str:
    return " ".join(str(p or "").upper() for p in parts if p)


def classify_signal_side(
    ml_signal: str | None,
    retail_verdict: str | None,
    go_no_go: str | None,
) -> str:
    """
    buy | trim | caution | neutral
    """
    ml = _sig_upper(ml_signal)
    rv = _sig_upper(retail_verdict)
    go = str(go_no_go or "").lower()

    if any(x in ml for x in ("TRIM", "SELL", "REDUCE", "AVOID")) or any(
        x in rv for x in ("TRIM", "SELL", "REDUCE", "AVOID")
    ):
        return "trim"
    if go == "go" or any(x in ml for x in ("STRONG BUY", "BUY", "HOLD/ADD")):
        if "STRONG BUY" in ml or ml.strip() == "BUY" or "HOLD/ADD" in ml or go == "go":
            return "buy"
    if any(x in ml for x in ("WATCH", "WAIT", "HOLD")) or go in ("no_go", "mixed"):
        return "caution"
    return "neutral"


def compute_verdict(
    event: dict[str, Any],
    *,
    return_30d_pct: float | None,
    hit_st_target: int | None,
    hit_stop_swing: int | None,
    win_return_pct: float = 3.0,
    loss_return_pct: float = -3.0,
    false_negative_pct: float = 5.0,
) -> tuple[str, str]:
    """
    Return (verdict, verdict_rule) where verdict is WIN | LOSS | NEUTRAL.
    """
    side = classify_signal_side(
        event.get("ml_signal"),
        event.get("retail_verdict"),
        event.get("go_no_go"),
    )
    go = str(event.get("go_no_go") or "").lower()
    ret = return_30d_pct

    if side == "buy" or (go == "go" and side != "trim"):
        if hit_st_target == 1 and hit_stop_swing != 1:
            return "WIN", f"{VERDICT_RULE_V1}:st_target_before_stop"
        if hit_stop_swing == 1:
            return "LOSS", f"{VERDICT_RULE_V1}:swing_stop_hit"
        if ret is not None:
            if ret >= win_return_pct:
                return "WIN", f"{VERDICT_RULE_V1}:return>={win_return_pct}"
            if ret <= loss_return_pct:
                return "LOSS", f"{VERDICT_RULE_V1}:return<={loss_return_pct}"
        return "NEUTRAL", f"{VERDICT_RULE_V1}:buy_flat"

    if side == "trim":
        if ret is not None:
            if ret <= 0:
                return "WIN", f"{VERDICT_RULE_V1}:trim_downside"
            if ret > false_negative_pct:
                return "LOSS", f"{VERDICT_RULE_V1}:trim_missed_rally"
        return "NEUTRAL", f"{VERDICT_RULE_V1}:trim_flat"

    # WATCH / NO-GO / non-action
    if ret is not None:
        if ret <= 0:
            return "WIN", f"{VERDICT_RULE_V1}:caution_avoided_loss"
        if ret > false_negative_pct:
            return "LOSS", f"{VERDICT_RULE_V1}:caution_false_negative"
    return "NEUTRAL", f"{VERDICT_RULE_V1}:caution_flat"


def compute_tactical_verdict(
    event: dict[str, Any],
    *,
    return_horizon_pct: float | None,
    hit_t1: int | None,
    hit_stop: int | None,
    horizon_days: int = 5,
    win_return_pct: float = 1.5,
    loss_return_pct: float = -1.5,
) -> tuple[str, str]:
    """
    Tactical 5d track: WIN if T1 before stop or return >= win threshold; LOSS on stop or deep loss.
    """
    if hit_t1 == 1 and hit_stop != 1:
        return "WIN", f"{VERDICT_RULE_TACTICAL_5D}:t1_before_stop"
    if hit_stop == 1:
        return "LOSS", f"{VERDICT_RULE_TACTICAL_5D}:stop_hit"
    ret = return_horizon_pct
    if ret is not None:
        if ret >= win_return_pct:
            return "WIN", f"{VERDICT_RULE_TACTICAL_5D}:return>={win_return_pct}"
        if ret <= loss_return_pct:
            return "LOSS", f"{VERDICT_RULE_TACTICAL_5D}:return<={loss_return_pct}"
    return "NEUTRAL", f"{VERDICT_RULE_TACTICAL_5D}:time_exit_{horizon_days}d"
