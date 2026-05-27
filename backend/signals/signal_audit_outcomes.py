"""
Resolve signal audit outcomes from EOD snapshots (Phase 2).

Uses Redis EOD first, then DATA_ROOT/eod — same chain as paper trades.
"""
from __future__ import annotations

import logging
from typing import Any

from signals.signal_audit_verdict import compute_verdict

logger = logging.getLogger(__name__)


def _outcomes_cfg(config: dict | None) -> dict[str, Any]:
    audit = (config or {}).get("signal_audit") or {}
    oc = audit.get("outcomes") or {}
    horizons = oc.get("horizon_trading_days") or oc.get("horizons_trading_days") or [7, 20]
    if not isinstance(horizons, (list, tuple)) or len(horizons) < 2:
        horizons = [7, 20]
    return {
        "enabled": oc.get("enabled", True),
        "horizon_short": int(horizons[0]),
        "horizon_long": int(horizons[1]),
        "use_intraday_touch": bool(oc.get("use_intraday_touch", True)),
        "benchmark_ticker": str(oc.get("benchmark_ticker") or "SPY").upper(),
        "win_return_pct": float(oc.get("win_return_pct", 3.0)),
        "loss_return_pct": float(oc.get("loss_return_pct", -3.0)),
        "false_negative_pct": float(oc.get("false_negative_pct", 5.0)),
    }


def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _chain_from_signal(dates: list[str], signal_date: str) -> list[str]:
    return [d for d in dates if d >= signal_date]


def _bar_from_snapshot(snap: dict | None, ticker: str) -> dict[str, float | None]:
    if not snap:
        return {"close": None, "high": None, "low": None}
    want = ticker.upper()
    for r in snap.get("run_results") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("ticker") or "").upper() != want:
            continue
        return {
            "close": _safe_float(r.get("close")),
            "high": _safe_float(r.get("high")),
            "low": _safe_float(r.get("low")),
        }
    return {"close": None, "high": None, "low": None}


def _return_pct(entry: float, exit_px: float) -> float | None:
    if entry <= 0 or exit_px is None:
        return None
    return round(100.0 * (exit_px - entry) / entry, 2)


def _path_excursions(
    entry: float,
    bars: list[dict[str, float | None]],
    use_intraday: bool,
) -> tuple[float | None, float | None]:
    if entry <= 0 or not bars:
        return None, None
    max_gain = None
    max_dd = None
    for bar in bars:
        candidates_high = [entry]
        candidates_low = [entry]
        if use_intraday:
            if bar.get("high") is not None:
                candidates_high.append(float(bar["high"]))
            if bar.get("low") is not None:
                candidates_low.append(float(bar["low"]))
        if bar.get("close") is not None:
            candidates_high.append(float(bar["close"]))
            candidates_low.append(float(bar["close"]))
        hi = max(candidates_high)
        lo = min(candidates_low)
        g = 100.0 * (hi - entry) / entry
        d = 100.0 * (lo - entry) / entry
        max_gain = g if max_gain is None else max(max_gain, g)
        max_dd = d if max_dd is None else min(max_dd, d)
    return (
        round(max_gain, 2) if max_gain is not None else None,
        round(max_dd, 2) if max_dd is not None else None,
    )


def _touch_hits(
    stop: float | None,
    target: float | None,
    mt_target: float | None,
    bars: list[dict[str, float | None]],
    use_intraday: bool,
) -> tuple[int | None, int | None, int | None]:
    hit_stop = hit_st = hit_mt = None
    for bar in bars:
        hi = bar.get("high") if use_intraday else None
        lo = bar.get("low") if use_intraday else None
        cl = bar.get("close")
        if stop is not None:
            if (lo is not None and lo <= stop) or (cl is not None and cl <= stop):
                hit_stop = 1
                break
        if target is not None:
            if (hi is not None and hi >= target) or (cl is not None and cl >= target):
                hit_st = 1
        if mt_target is not None:
            if (hi is not None and hi >= mt_target) or (cl is not None and cl >= mt_target):
                hit_mt = 1
        if hit_stop == 1:
            break
    if hit_stop is None and bars:
        hit_stop = 0
    if hit_st is None and bars:
        hit_st = 0
    if hit_mt is None and bars:
        hit_mt = 0
    return hit_stop, hit_st, hit_mt


def resolve_event_outcome(
    event: dict[str, Any],
    dates: list[str],
    load_snapshot,
    *,
    horizon_short: int = 7,
    horizon_long: int = 20,
    use_intraday_touch: bool = True,
    benchmark_ticker: str = "SPY",
    win_return_pct: float = 3.0,
    loss_return_pct: float = -3.0,
    false_negative_pct: float = 5.0,
) -> dict[str, Any] | None:
    """Build outcome row when enough EOD history exists; else None."""
    signal_date = str(event.get("signal_date") or "")
    ticker = str(event.get("ticker") or "").upper()
    entry = _safe_float(event.get("price_at_signal"))
    if not signal_date or not ticker or entry is None or entry <= 0:
        return None

    chain = _chain_from_signal(dates, signal_date)
    if len(chain) <= horizon_long:
        return None

    short_date = chain[horizon_short]
    long_date = chain[horizon_long]
    path_dates = chain[1 : horizon_long + 1]
    bars: list[dict[str, float | None]] = []
    for d in path_dates:
        bars.append(_bar_from_snapshot(load_snapshot(d), ticker))

    short_bar = _bar_from_snapshot(load_snapshot(short_date), ticker)
    long_bar = _bar_from_snapshot(load_snapshot(long_date), ticker)
    price_7d = short_bar.get("close")
    price_30d = long_bar.get("close")
    if price_7d is None or price_30d is None:
        return None

    return_7d = _return_pct(entry, float(price_7d))
    return_30d = _return_pct(entry, float(price_30d))
    max_gain, max_dd = _path_excursions(entry, bars, use_intraday_touch)
    stop = _safe_float(event.get("stop_swing"))
    st_tgt = _safe_float(event.get("st_target"))
    mt_tgt = _safe_float(event.get("mt_target"))
    hit_stop, hit_st, hit_mt = _touch_hits(stop, st_tgt, mt_tgt, bars, use_intraday_touch)

    bench_entry = _bar_from_snapshot(load_snapshot(chain[0]), benchmark_ticker).get("close")
    bench_exit = _bar_from_snapshot(load_snapshot(long_date), benchmark_ticker).get("close")
    bench_ret = _return_pct(float(bench_entry), float(bench_exit)) if bench_entry and bench_exit else None

    verdict, verdict_rule = compute_verdict(
        event,
        return_30d_pct=return_30d,
        hit_st_target=hit_st,
        hit_stop_swing=hit_stop,
        win_return_pct=win_return_pct,
        loss_return_pct=loss_return_pct,
        false_negative_pct=false_negative_pct,
    )

    from signals.signal_audit_store import _now_iso

    return {
        "signal_event_id": event["id"],
        "resolved_ts": _now_iso(),
        "price_7d": round(float(price_7d), 4),
        "price_30d": round(float(price_30d), 4),
        "return_7d_pct": return_7d,
        "return_30d_pct": return_30d,
        "hit_stop_swing": hit_stop,
        "hit_st_target": hit_st,
        "hit_mt_target": hit_mt,
        "max_gain_pct": max_gain,
        "max_drawdown_pct": max_dd,
        "path_days": len(path_dates),
        "verdict": verdict,
        "verdict_rule": verdict_rule,
        "benchmark_return_30d_pct": bench_ret,
        "notes": None,
    }


def resolve_signal_audit_outcomes(
    config: dict | None = None,
    data_root=None,
    *,
    cohort_tag: str | None = None,
    max_events: int = 5000,
) -> dict[str, Any]:
    """
    Backfill signal_outcomes for cohort events with sufficient EOD history.
    Idempotent upsert on signal_event_id.
    """
    from config_loader import get_audit_cohort_tag, load_config
    from signals.paper_trade_logger import PaperTradeLogger
    from signals.signal_audit_store import SignalAuditStore

    if config is None:
        config = load_config()
    oc = _outcomes_cfg(config)
    if not oc["enabled"]:
        return {"updated": 0, "skipped": 0, "pending": 0, "message": "signal_audit.outcomes.enabled is false"}

    audit_cfg = config.get("signal_audit") or {}
    if not audit_cfg.get("enabled"):
        return {"updated": 0, "message": "signal_audit disabled"}

    tag = cohort_tag or get_audit_cohort_tag(config)
    store = SignalAuditStore(data_root=data_root)
    pt = PaperTradeLogger(data_root=data_root or store.data_root)
    dates = pt._list_eod_dates()
    if len(dates) < oc["horizon_long"] + 1:
        return {
            "updated": 0,
            "pending": store.count_events(cohort_tag=tag) if tag else 0,
            "message": f"Need {oc['horizon_long'] + 1}+ EOD snapshots; have {len(dates)}.",
        }

    events = store.list_events_for_resolution(cohort_tag=tag, limit=max_events)
    updated = 0
    skipped = 0
    pending = 0

    for ev in events:
        if store.has_outcome(int(ev["id"])):
            skipped += 1
            continue
        row = resolve_event_outcome(
            ev,
            dates,
            pt._load_snapshot,
            horizon_short=oc["horizon_short"],
            horizon_long=oc["horizon_long"],
            use_intraday_touch=oc["use_intraday_touch"],
            benchmark_ticker=oc["benchmark_ticker"],
            win_return_pct=oc["win_return_pct"],
            loss_return_pct=oc["loss_return_pct"],
            false_negative_pct=oc["false_negative_pct"],
        )
        if row is None:
            pending += 1
            continue
        store.upsert_outcome(row)
        updated += 1

    summary = store.outcome_summary(cohort_tag=tag)
    return {
        "updated": updated,
        "skipped_existing": skipped,
        "pending_insufficient_history": pending,
        "cohort_tag": tag,
        "eod_snapshots": len(dates),
        "summary": summary,
        "message": None,
    }
