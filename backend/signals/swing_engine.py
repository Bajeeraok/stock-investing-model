"""
Swing setup engine — EOD-friendly classifier fields (technical-first track).

Mirrors velocity_engine: attaches flat swing_* fields during run_daily without
changing primary 4-gate GO / accumulate track. Optional paper logging uses
track=swing when swing_tactical.log_paper_trades is enabled.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from signals.swing_classifier import (
    SETUP_LABELS,
    SwingSetupType,
    build_swing_classification_bundle,
)


def _default_cfg(config: dict | None) -> dict[str, Any]:
    base = {
        "enabled": True,
        "min_swing_score": 70,
        "log_paper_trades": False,
        "dedup_window_days": 5,
        "require_swing_signal_verdict": True,
    }
    st = (config or {}).get("swing_tactical") or {}
    if isinstance(st, dict):
        base.update({k: st[k] for k in base if k in st})
    return base


def _sf(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _regime_bull_from_row(row: dict[str, Any]) -> float | None:
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    rb = rs.get("stock_regime_bull_pct") or rs.get("regime_bull_pct")
    if rb is not None:
        return _sf(rb)
    try:
        from signals.retail_action_payload import _global_regime_bull_pct

        return _global_regime_bull_pct(row.get("_global_market_regime"))
    except Exception:
        return None


def _overall_verdict_from_row(row: dict[str, Any]) -> str:
    rs = row.get("retail_status") if isinstance(row.get("retail_status"), dict) else {}
    return str(
        rs.get("overall_verdict")
        or row.get("plan_action")
        or row.get("signal")
        or ""
    )


def build_swing_context_from_row(
    row: dict[str, Any],
    *,
    close: pd.Series | None = None,
) -> tuple[dict[str, Any], dict[str, Any], float | None, float | None]:
    """Map run_daily / EOD row → investor_out + response for swing_classifier."""
    cp = _sf(row.get("close") or row.get("price"))
    ma20 = _sf(row.get("ma20"))
    ma50 = _sf(row.get("ma50"))
    ma200 = _sf(row.get("ma200"))
    high_52w = _sf(row.get("high_52w"))
    low_52w = _sf(row.get("low_52w"))

    if close is not None and len(close) >= 20:
        try:
            if ma20 is None and len(close) >= 20:
                ma20 = float(close.rolling(20).mean().iloc[-1])
            if ma50 is None and len(close) >= 50:
                ma50 = float(close.rolling(50).mean().iloc[-1])
            if ma200 is None and len(close) >= 200:
                ma200 = float(close.rolling(200).mean().iloc[-1])
            if high_52w is None and len(close) >= 252:
                high_52w = float(close.iloc[-252:].max())
            if low_52w is None and len(close) >= 252:
                low_52w = float(close.iloc[-252:].min())
        except Exception:
            pass

    ml = row.get("ml_short_prob")
    ml_pct = _sf(ml)
    if ml_pct is not None and ml_pct <= 1:
        ml_pct = ml_pct * 100.0

    st_band = row.get("st_band") if isinstance(row.get("st_band"), dict) else {}
    entry_low = _sf(st_band.get("low"))
    entry_high = _sf(st_band.get("high"))
    if entry_low is None and cp is not None:
        entry_low = cp * 0.99
    if entry_high is None and cp is not None:
        entry_high = cp

    investor_out = {
        "rsi": row.get("rsi"),
        "pattern_score": row.get("confluence_score") or row.get("composite_buy"),
        "regime_bull_pct": _regime_bull_from_row(row),
        "overall_verdict": _overall_verdict_from_row(row),
        "horizons": {"short": {"ml_prob": ml_pct}},
    }
    response = {
        "close": cp,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "volume_ratio": row.get("volume_ratio") or 1.0,
        "atr14": row.get("atr_14"),
        "high_52w": high_52w,
        "low_52w": low_52w,
        "trend_score": row.get("trend_score") or row.get("composite_buy"),
    }
    return investor_out, response, entry_low, entry_high


def compute_swing_fields(
    row: dict[str, Any],
    *,
    close: pd.Series | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Run swing classifier; return flat EOD-friendly fields (does not mutate row)."""
    cfg = _default_cfg(config)
    if not cfg.get("enabled", True):
        return {
            "swing_setup_type": SwingSetupType.NO_SETUP.value,
            "swing_verdict": "NO_SIGNAL",
            "swing_triggered": False,
        }

    investor_out, response, entry_low, entry_high = build_swing_context_from_row(row, close=close)
    bundle = build_swing_classification_bundle(
        investor_out=investor_out,
        response=response,
        current_price=_sf(row.get("close") or row.get("price")),
        entry_low=entry_low,
        entry_high=entry_high,
    )
    sc = bundle.get("swing_score") or {}
    exits = bundle.get("exit_plan") if isinstance(bundle.get("exit_plan"), dict) else {}
    setup_type = str(bundle.get("setup_type") or SwingSetupType.NO_SETUP.value)
    verdict = str(sc.get("verdict") or "NO_SIGNAL")
    score = _sf(sc.get("score"))

    min_score = float(cfg.get("min_swing_score", 70))
    require_verdict = bool(cfg.get("require_swing_signal_verdict", True))
    triggered = (
        setup_type != SwingSetupType.NO_SETUP.value
        and score is not None
        and score >= min_score
        and (verdict == "SWING_SIGNAL" if require_verdict else verdict in ("SWING_SIGNAL", "WATCH"))
    )

    out: dict[str, Any] = {
        "swing_setup_type": setup_type,
        "swing_setup_label": bundle.get("setup_label") or SETUP_LABELS.get(SwingSetupType.NO_SETUP),
        "swing_score": score,
        "swing_verdict": verdict,
        "swing_triggered": triggered,
        "swing_reasons": (bundle.get("setup_reasons") or [])[:3],
        "swing_divergence_note": bundle.get("divergence_note"),
    }
    if exits:
        out.update(
            {
                "swing_entry_low": exits.get("entry_low"),
                "swing_entry_high": exits.get("entry_high"),
                "swing_stop": exits.get("hard_stop"),
                "swing_t1": exits.get("target_1"),
                "swing_t2": exits.get("target_2"),
                "swing_runner": exits.get("runner_target"),
                "swing_horizon_trading_days": exits.get("time_stop_days"),
                "swing_rr": exits.get("risk_reward_t1"),
                "swing_horizon_label": exits.get("horizon_label"),
            }
        )
    return out


def attach_swing_to_row(
    row: dict[str, Any],
    *,
    close: pd.Series | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Mutate row in place with swing classifier fields; return row."""
    fields = compute_swing_fields(row, close=close, config=config)
    row.update(fields)
    return row


def build_swing_setups_from_results(
    results: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Top swing signals for overview strips (sorted by swing_score desc)."""
    rows: list[dict[str, Any]] = []
    for r in results or []:
        if not isinstance(r, dict) or r.get("error") or not r.get("swing_triggered"):
            continue
        sym = str(r.get("ticker") or "").upper()
        if not sym:
            continue
        rows.append(
            {
                "ticker": sym,
                "swing_setup_type": r.get("swing_setup_type"),
                "swing_setup_label": r.get("swing_setup_label"),
                "swing_score": r.get("swing_score"),
                "swing_verdict": r.get("swing_verdict"),
                "swing_t1": r.get("swing_t1"),
                "swing_stop": r.get("swing_stop"),
                "go_no_go": r.get("go_no_go"),
                "reasons": (r.get("swing_reasons") or [])[:2],
            }
        )
    rows.sort(key=lambda x: -(float(x.get("swing_score") or 0)))
    return rows[: max(1, limit)]
