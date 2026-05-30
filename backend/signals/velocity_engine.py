"""
Velocity / tactical breakout engine — EOD-friendly signals for quick in/out track.

Does NOT change primary GO/NO-GO gates. When velocity_triggered is true, the row is
tagged track=velocity for audit batch split and (later) tactical paper logging.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _default_cfg(config: dict | None) -> dict[str, Any]:
    base = {
        "enabled": True,
        "rvol_min": 2.0,
        "bb_pct_b_min": 1.0,
        "bb_pct_b_extended": 0.85,
        "min_velocity_score": 55,
        "require_rvol_or_bb": True,
        "horizon_trading_days": 5,
    }
    vt = (config or {}).get("velocity_tactical") or {}
    if isinstance(vt, dict):
        base.update({k: vt[k] for k in base if k in vt})
    return base


def _bollinger_pct_b(close: pd.Series, window: int = 20, num_std: float = 2.0) -> float | None:
    if close is None or len(close) < window + 2:
        return None
    mid = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    band_w = upper - lower
    last_w = band_w.iloc[-1]
    if pd.isna(last_w) or float(last_w) <= 0:
        return None
    pct_b = (float(close.iloc[-1]) - float(lower.iloc[-1])) / float(last_w)
    return pct_b


def _relative_volume(volume: pd.Series | None, lookback: int = 20) -> float | None:
    if volume is None or len(volume) < lookback + 1:
        return None
    avg = float(volume.iloc[-lookback - 1 : -1].mean())
    if avg <= 0:
        return None
    return float(volume.iloc[-1]) / avg


def compute_velocity_fields(
    close: pd.Series,
    volume: pd.Series | None = None,
    *,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    Compute velocity/tactical fields from daily OHLCV.

    Returns dict with: velocity_triggered, velocity_score, track, rvol, bb_pct_b, velocity_reasons.
    """
    cfg = _default_cfg(config)
    if not cfg.get("enabled", True):
        return {
            "velocity_triggered": False,
            "velocity_score": 0.0,
            "track": "accumulate",
            "rvol": None,
            "bb_pct_b": None,
            "velocity_reasons": [],
        }

    if close is None or len(close) < 25:
        return {
            "velocity_triggered": False,
            "velocity_score": 0.0,
            "track": "accumulate",
            "rvol": None,
            "bb_pct_b": None,
            "velocity_reasons": ["insufficient history"],
        }

    price = float(close.iloc[-1])
    rvol = _relative_volume(volume)
    bb_pct_b = _bollinger_pct_b(close)

    ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
    rvol_min = float(cfg.get("rvol_min", 2.0))
    bb_min = float(cfg.get("bb_pct_b_min", 1.0))
    bb_ext = float(cfg.get("bb_pct_b_extended", 0.85))
    min_score = int(cfg.get("min_velocity_score", 55))

    score = 0.0
    reasons: list[str] = []
    rvol_ok = rvol is not None and rvol >= rvol_min
    bb_break = bb_pct_b is not None and bb_pct_b >= bb_min
    bb_ext_ok = bb_pct_b is not None and bb_pct_b >= bb_ext

    if rvol_ok:
        score += 40.0
        reasons.append(f"RVOL {rvol:.1f}× avg (≥{rvol_min:.1f}×)")
    elif rvol is not None and rvol >= 1.5:
        score += 18.0
        reasons.append(f"Elevated volume {rvol:.1f}× avg")

    if bb_break:
        score += 35.0
        reasons.append(f"Bollinger %B {bb_pct_b:.2f} — at/above upper band")
    elif bb_ext_ok:
        score += 15.0
        reasons.append(f"Bollinger %B {bb_pct_b:.2f} — extended")

    if ma20 is not None and price > ma20 and rvol is not None and rvol >= 1.5:
        score += 12.0
        reasons.append("Price above MA20 on volume")

    if ma20 is not None and price > ma20 * 1.02 and bb_ext_ok:
        score += 8.0
        reasons.append("Breakout extension above MA20")

    score = round(float(np.clip(score, 0, 100)), 1)

    core_hit = rvol_ok or bb_break
    if cfg.get("require_rvol_or_bb", True):
        triggered = score >= min_score and core_hit
    else:
        triggered = score >= min_score

    return {
        "velocity_triggered": bool(triggered),
        "velocity_score": score,
        "track": "velocity" if triggered else "accumulate",
        "rvol": round(rvol, 2) if rvol is not None else None,
        "bb_pct_b": round(bb_pct_b, 3) if bb_pct_b is not None else None,
        "velocity_reasons": reasons,
    }


def compute_tactical_targets(
    close: pd.Series,
    *,
    atr: float | None = None,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """
    EOD-friendly Phase 2 breakout targets (T1/T2/stop) using daily ATR + 20d resistance.
    """
    if close is None or len(close) < 20:
        return None
    price = float(close.iloc[-1])
    if atr is None or atr <= 0:
        try:
            from signals.indicators import compute_indicators

            df = compute_indicators(close)
            if not df.empty and pd.notna(df.iloc[-1].get("ATR14")):
                atr = float(df.iloc[-1]["ATR14"])
        except Exception:
            atr = None
    if atr is None or atr <= 0:
        atr = max(0.01, price * 0.02)

    from signals.thrive_phase2._constants import merge_phase2_config

    p2 = merge_phase2_config(config)
    cfg = p2["atr_config"].get("breakout") or {"t1": 1.0, "t2": 2.0, "stop": 0.5}
    resistance = float(close.iloc[-20:].max())
    entry = round(resistance + (atr * 0.1), 2)
    t1 = round(resistance + (atr * float(cfg.get("t1", 1.0))), 2)
    t2 = round(resistance + (atr * float(cfg.get("t2", 2.0))), 2)
    stop = round(resistance - (atr * float(cfg.get("stop", 0.5))), 2)
    risk = entry - stop
    reward = t1 - entry
    rr = round(reward / risk, 2) if risk > 0 else None
    horizon = int(_default_cfg(config).get("horizon_trading_days", 5))
    return {
        "tactical_entry": entry,
        "tactical_t1": t1,
        "tactical_t2": t2,
        "tactical_stop": stop,
        "tactical_rr": rr,
        "tactical_resistance": round(resistance, 2),
        "tactical_atr": round(float(atr), 4),
        "tactical_horizon_trading_days": horizon,
        "tactical_expiry_note": f"Review or exit by T+{horizon} trading days if neither target nor stop hits.",
    }


def build_tactical_ui_payload(row: dict[str, Any], *, config: dict | None = None) -> dict[str, Any]:
    """Compact payload for ticker detail TacticalEntryPanel."""
    cfg = _default_cfg(config)
    horizon = int(row.get("tactical_horizon_trading_days") or cfg.get("horizon_trading_days", 5))
    triggered = bool(row.get("velocity_triggered"))
    try:
        score = float(row.get("velocity_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    min_score = int(cfg.get("min_velocity_score", 55))
    # Show panel when triggered OR score is in watch band (aligns with paper-trading tactical track visibility).
    show_panel = triggered or score >= max(40, min_score - 15)
    return {
        "active": triggered,
        "velocity_triggered": triggered,
        "show_panel": show_panel,
        "track": row.get("track") or ("velocity" if triggered else "accumulate"),
        "velocity_score": row.get("velocity_score"),
        "rvol": row.get("rvol"),
        "bb_pct_b": row.get("bb_pct_b"),
        "reasons": row.get("velocity_reasons") or [],
        "entry": row.get("tactical_entry"),
        "target_1": row.get("tactical_t1"),
        "target_2": row.get("tactical_t2"),
        "stop": row.get("tactical_stop"),
        "rr_ratio": row.get("tactical_rr"),
        "horizon_trading_days": horizon,
        "expiry_note": row.get("tactical_expiry_note")
        or f"Tactical window: {horizon} trading days — quick in/out, not accumulate GO.",
        "gates_passed": row.get("gates_passed"),
        "gates_total": row.get("gates_total") or 4,
        "go_no_go": row.get("go_no_go"),
    }


def build_tactical_breakouts_from_results(
    results: list[dict[str, Any]],
    *,
    config: dict | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Top velocity names for Overview strip (sorted by velocity_score desc)."""
    rows: list[dict[str, Any]] = []
    for r in results or []:
        if not isinstance(r, dict) or r.get("error") or not r.get("velocity_triggered"):
            continue
        sym = str(r.get("ticker") or "").upper()
        if not sym:
            continue
        rows.append({
            "ticker": sym,
            "velocity_score": r.get("velocity_score"),
            "rvol": r.get("rvol"),
            "bb_pct_b": r.get("bb_pct_b"),
            "gates_passed": r.get("gates_passed"),
            "gates_total": r.get("gates_total") or 4,
            "go_no_go": r.get("go_no_go"),
            "close": r.get("close"),
            "tactical_t1": r.get("tactical_t1"),
            "tactical_stop": r.get("tactical_stop"),
            "reasons": (r.get("velocity_reasons") or [])[:2],
        })
    rows.sort(key=lambda x: -(float(x.get("velocity_score") or 0)))
    return rows[: max(1, limit)]


def attach_velocity_to_row(
    row: dict[str, Any],
    *,
    close: pd.Series,
    volume: pd.Series | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Mutate row in place with velocity fields; return row."""
    fields = compute_velocity_fields(close, volume, config=config)
    row.update(fields)
    if fields.get("velocity_triggered"):
        atr = row.get("atr_14")
        try:
            atr_f = float(atr) if atr is not None else None
        except (TypeError, ValueError):
            atr_f = None
        tactical = compute_tactical_targets(close, atr=atr_f, config=config)
        if tactical:
            row.update(tactical)
    elif row.get("track") != "velocity":
        row.setdefault("tactical_horizon_trading_days", int(_default_cfg(config).get("horizon_trading_days", 5)))
    return row
