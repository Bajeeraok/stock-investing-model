"""
Income Book planner — ad-hoc swing portfolio for dollar income goals.

Scans ~100-ticker EOD universe, excludes long-term holdings by default,
ranks swing setups, and produces daily entry/exit game plan.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from config_loader import get_eod_signal_universe, portfolio_tickers_from_config
from signals.income_book_store import DEFAULT_SETTINGS
from signals.swing_engine import compute_swing_fields
from signals.tracking_gate import enrich_tracking_row, gate_snapshot_from_row

_SECTOR_CACHE: dict[str, str] | None = None


def _income_cfg(config: dict | None) -> dict[str, Any]:
    base = {
        "enabled": True,
        "exclude_long_term_holdings": True,
        "min_swing_score": 65,
        "min_gates_passed": 3,
        "gates_total": 4,
        "max_proposed_slots": 8,
        "max_sector_slots": 2,
        "require_swing_setup": True,
        "block_new_entries_regime_down": True,
        "candidate_pool_size": 30,
    }
    block = (config or {}).get("income_book") or {}
    if isinstance(block, dict):
        base.update({k: block[k] for k in base if k in block})
    return base


def _sf(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _sector_for(ticker: str) -> str:
    global _SECTOR_CACHE
    if _SECTOR_CACHE is None:
        _SECTOR_CACHE = {}
        try:
            path = Path(__file__).resolve().parent.parent / "data" / "asset_registry_inferred.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                for sym, meta in (data or {}).items():
                    if isinstance(meta, dict) and meta.get("sector"):
                        _SECTOR_CACHE[str(sym).upper()] = str(meta["sector"])
        except Exception:
            pass
    return _SECTOR_CACHE.get((ticker or "").upper(), "Unknown")


def load_signal_rows(config: dict | None = None) -> tuple[list[dict[str, Any]], str | None, str]:
    """Best available signal rows for universe scan."""
    rows: list[dict] = []
    as_of: str | None = None
    source = "none"
    try:
        from signals.cache import get_cached_dashboard, get_signals_panel, get_universe_signals

        uni = get_universe_signals()
        if uni and isinstance(uni.get("rows"), list) and uni["rows"]:
            rows = [r for r in uni["rows"] if isinstance(r, dict)]
            as_of = uni.get("as_of")
            source = "universe_signals"
        if not rows:
            sp = get_signals_panel()
            if sp and isinstance(sp.get("signals"), list) and sp["signals"]:
                rows = [r for r in sp["signals"] if isinstance(r, dict)]
                as_of = sp.get("as_of")
                source = "signals_panel"
        if not rows:
            dash = get_cached_dashboard()
            if dash and isinstance(dash.get("signals"), list) and dash["signals"]:
                rows = [r for r in dash["signals"] if isinstance(r, dict)]
                as_of = dash.get("as_of_date") or dash.get("run_date")
                source = "dashboard_cache"
    except Exception:
        pass

    if not rows and config:
        try:
            from api.routers.dashboard import _load_config, _pick_best_eod_snapshot

            cfg = config or _load_config()
            eod_rows, eod_as_of, eod_src = _pick_best_eod_snapshot(cfg, date="latest", allow_thin=True)
            if eod_rows:
                rows = [r for r in eod_rows if isinstance(r, dict)]
                as_of = eod_as_of
                source = eod_src or "eod_snapshot"
        except Exception:
            pass

    return rows, as_of, source


def _rows_by_ticker(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if not isinstance(r, dict) or r.get("error"):
            continue
        sym = str(r.get("ticker") or "").upper().strip()
        if sym:
            out[sym] = r
    return out


def _ensure_swing_fields(row: dict, config: dict | None) -> dict:
    if row.get("swing_score") is not None and row.get("swing_setup_type"):
        return row
    enriched = dict(row)
    enriched.update(compute_swing_fields(enriched, config=config))
    return enriched


def _gates_from_row(row: dict) -> dict[str, Any]:
    if row.get("gates_passed") is None:
        try:
            enrich_tracking_row(row)
        except Exception:
            pass
    snap = gate_snapshot_from_row(row)
    passed = snap.get("gates_passed")
    total = int(snap.get("gates_total") or 4)
    try:
        passed_i = int(passed) if passed is not None else 0
    except (TypeError, ValueError):
        passed_i = 0
    return {
        "gates_passed": passed_i,
        "gates_total": total,
        "gate_cleared": bool(snap.get("gate_cleared")),
        "go_no_go": snap.get("go_no_go"),
    }


def _entry_status(close: float | None, el: float | None, eh: float | None) -> str:
    if close is None or el is None or eh is None:
        return "watch"
    lo, hi = min(el, eh), max(el, eh)
    if lo <= close <= hi:
        return "ready"
    if close < lo:
        return "watch_pullback"
    return "watch_extended"


def compute_goal_summary(settings: dict[str, Any]) -> dict[str, Any]:
    goal = float(settings.get("goal_usd") or DEFAULT_SETTINGS["goal_usd"])
    capital = float(settings.get("capital_usd") or DEFAULT_SETTINGS["capital_usd"])
    months = int(settings.get("timeframe_months") or DEFAULT_SETTINGS["timeframe_months"])
    risk_pct = float(settings.get("risk_pct") or DEFAULT_SETTINGS["risk_pct"])
    if capital <= 0:
        capital = DEFAULT_SETTINGS["capital_usd"]
    required_pct = round(100.0 * goal / capital, 2) if capital > 0 else None
    monthly_pct = round(required_pct / max(months, 1), 2) if required_pct is not None else None
    risk_usd = round(capital * risk_pct / 100.0, 0)
    feasibility = "green"
    if required_pct is not None:
        if required_pct >= 15:
            feasibility = "red"
        elif required_pct >= 8:
            feasibility = "amber"
    return {
        "goal_usd": goal,
        "capital_usd": capital,
        "timeframe_months": months,
        "risk_pct": risk_pct,
        "risk_per_trade_usd": risk_usd,
        "required_return_pct": required_pct,
        "required_monthly_pct": monthly_pct,
        "feasibility": feasibility,
        "feasibility_note": _feasibility_note(feasibility, required_pct, months),
    }


def _feasibility_note(feasibility: str, required_pct: float | None, months: int) -> str:
    if required_pct is None:
        return "Set capital and goal to see feasibility."
    if feasibility == "red":
        return (
            f"Target needs ~{required_pct:.1f}% in {months}mo — very aggressive. "
            "Reduce goal or increase dedicated capital."
        )
    if feasibility == "amber":
        return (
            f"Target needs ~{required_pct:.1f}% in {months}mo — aggressive swing plan. "
            "Strict stops and 2–3 concurrent trades required."
        )
    return (
        f"Target needs ~{required_pct:.1f}% in {months}mo — plausible with disciplined swing execution "
        "(not guaranteed)."
    )


def _size_trade(
    *,
    capital: float,
    risk_pct: float,
    entry: float,
    stop: float | None,
) -> dict[str, Any]:
    risk_usd = capital * risk_pct / 100.0
    if entry <= 0 or stop is None or stop >= entry:
        return {
            "shares": 0,
            "notional_usd": 0,
            "risk_usd": round(risk_usd, 0),
            "risk_per_share": None,
        }
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return {"shares": 0, "notional_usd": 0, "risk_usd": round(risk_usd, 0), "risk_per_share": None}
    shares = int(risk_usd / risk_per_share)
    notional = round(shares * entry, 0)
    return {
        "shares": shares,
        "notional_usd": notional,
        "risk_usd": round(risk_usd, 0),
        "risk_per_share": round(risk_per_share, 2),
        "est_pnl_at_t1_usd": None,
    }


def candidate_from_row(
    row: dict,
    *,
    config: dict | None,
    settings: dict[str, Any],
    held_tickers: set[str],
) -> dict[str, Any] | None:
    icfg = _income_cfg(config)
    sym = str(row.get("ticker") or "").upper()
    if not sym or sym in held_tickers:
        return None

    row = _ensure_swing_fields(row, config)
    setup = str(row.get("swing_setup_type") or "no_setup")
    if icfg.get("require_swing_setup") and setup == "no_setup":
        return None

    score = _sf(row.get("swing_score"))
    min_score = float(icfg.get("min_swing_score", 65))
    if score is None or score < min_score:
        return None

    gates = _gates_from_row(row)
    min_gates = int(icfg.get("min_gates_passed", 3))
    if gates["gates_passed"] < min_gates:
        return None

    close = _sf(row.get("close") or row.get("price"))
    el = _sf(row.get("swing_entry_low"))
    eh = _sf(row.get("swing_entry_high"))
    stop = _sf(row.get("swing_stop"))
    t1 = _sf(row.get("swing_t1"))
    t2 = _sf(row.get("swing_t2"))

    capital = float(settings.get("capital_usd") or DEFAULT_SETTINGS["capital_usd"])
    risk_pct = float(settings.get("risk_pct") or DEFAULT_SETTINGS["risk_pct"])
    entry_mid = (el + eh) / 2.0 if el is not None and eh is not None else close
    sizing = _size_trade(
        capital=capital,
        risk_pct=risk_pct,
        entry=entry_mid or close or 0,
        stop=stop,
    )
    if sizing.get("shares") and t1 and entry_mid:
        sizing["est_pnl_at_t1_usd"] = round(float(sizing["shares"]) * (t1 - entry_mid), 0)

    status = _entry_status(close, el, eh)
    if gates["gate_cleared"] and status in ("ready", "watch_pullback"):
        slot_status = "ready" if status == "ready" else "watch"
    else:
        slot_status = "watch"

    return {
        "ticker": sym,
        "close": close,
        "sector": _sector_for(sym),
        "swing_setup_type": setup,
        "swing_setup_label": row.get("swing_setup_label"),
        "swing_score": score,
        "swing_verdict": row.get("swing_verdict"),
        "swing_reasons": row.get("swing_reasons") or [],
        "gates_passed": gates["gates_passed"],
        "gates_total": gates["gates_total"],
        "gate_cleared": gates["gate_cleared"],
        "go_no_go": gates.get("go_no_go"),
        "regime": row.get("regime"),
        "composite_buy": row.get("composite_buy"),
        "entry_low": el,
        "entry_high": eh,
        "stop": stop,
        "t1": t1,
        "t2": t2,
        "runner": _sf(row.get("swing_runner")),
        "swing_rr": _sf(row.get("swing_rr")),
        "horizon_label": row.get("swing_horizon_label"),
        "horizon_days": row.get("swing_horizon_trading_days"),
        "status": slot_status,
        "sizing": sizing,
        "earnings_days_until": row.get("earnings_days_until"),
        "in_long_term_portfolio": sym in held_tickers,
    }


def pick_diversified_candidates(
    candidates: list[dict[str, Any]],
    *,
    limit: int,
    max_sector_slots: int = 2,
    open_tickers: set[str] | None = None,
) -> list[dict[str, Any]]:
    open_tickers = open_tickers or set()
    sector_counts: dict[str, int] = {}
    picked: list[dict] = []
    for c in sorted(candidates, key=lambda x: (-(x.get("swing_score") or 0), -(x.get("swing_rr") or 0))):
        sym = c.get("ticker")
        if not sym or sym in open_tickers:
            continue
        sec = str(c.get("sector") or "Unknown")
        if sector_counts.get(sec, 0) >= max_sector_slots:
            continue
        picked.append(c)
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        if len(picked) >= limit:
            break
    return picked


def refresh_open_trade(trade: dict, row: dict | None) -> dict[str, Any]:
    out = dict(trade)
    if not row:
        out["today_action"] = "no_signal_data"
        return out
    row = _ensure_swing_fields(row, None)
    close = _sf(row.get("close") or row.get("price"))
    stop = _sf(out.get("stop"))
    t1 = _sf(out.get("t1"))
    entry = _sf(out.get("entry_price"))
    shares = _sf(out.get("shares")) or 0
    out["mark_price"] = close
    if close is not None and entry:
        out["unrealized_pnl_usd"] = round(shares * (close - entry), 2)
        out["unrealized_return_pct"] = round(100.0 * (close - entry) / entry, 2)
    action = "hold"
    if stop is not None and close is not None and close <= stop:
        action = "exit_stop"
    elif t1 is not None and close is not None and close >= t1:
        action = "trim_t1"
    gates = _gates_from_row(row)
    if gates["gates_passed"] < 2:
        action = "exit_gates_broke"
    out["today_action"] = action
    out["gates_passed"] = gates["gates_passed"]
    return out


def build_daily_changes(
    *,
    prev_proposed: list[dict] | None,
    proposed: list[dict],
    open_trades: list[dict],
) -> list[str]:
    changes: list[str] = []
    prev_map = {p["ticker"]: p for p in (prev_proposed or []) if p.get("ticker")}
    new_map = {p["ticker"]: p for p in proposed if p.get("ticker")}
    for sym, p in new_map.items():
        old = prev_map.get(sym)
        if not old:
            changes.append(f"+ {sym} added to watch ({p.get('swing_setup_label') or p.get('swing_setup_type')})")
        elif old.get("status") != p.get("status") and p.get("status") == "ready":
            changes.append(f"→ {sym} now READY in entry zone")
    for sym in prev_map:
        if sym not in new_map:
            changes.append(f"− {sym} dropped from watch (setup/gates no longer qualify)")
    for t in open_trades:
        if t.get("today_action") == "trim_t1":
            changes.append(f"★ {t.get('ticker')}: at T1 — trim ~⅓ per plan")
        elif t.get("today_action") == "exit_stop":
            changes.append(f"✕ {t.get('ticker')}: at/below stop — exit tactical size")
        elif t.get("today_action") == "exit_gates_broke":
            changes.append(f"✕ {t.get('ticker')}: gates broke — consider exit")
    return changes[:12]


def build_income_plan(
    config: dict | None = None,
    *,
    book: dict[str, Any] | None = None,
    market_regime: str | None = None,
) -> dict[str, Any]:
    from signals.income_book_store import load_income_book

    config = config or {}
    icfg = _income_cfg(config)
    book = book or load_income_book()
    settings = dict(DEFAULT_SETTINGS)
    settings.update(book.get("settings") or {})

    universe = get_eod_signal_universe(config)
    long_term = set(portfolio_tickers_from_config(config))
    exclude = bool(settings.get("exclude_long_term_holdings", icfg.get("exclude_long_term_holdings", True)))
    scan_exclude = long_term if exclude else set()

    rows, as_of, source = load_signal_rows(config)
    by_ticker = _rows_by_ticker(rows)

    open_trades = list(book.get("open_trades") or [])
    open_tickers = {str(t.get("ticker") or "").upper() for t in open_trades}
    refreshed_open = [
        refresh_open_trade(t, by_ticker.get(str(t.get("ticker") or "").upper()))
        for t in open_trades
    ]

    candidates: list[dict] = []
    for sym in universe:
        if sym in scan_exclude:
            continue
        row = by_ticker.get(sym)
        if not row:
            continue
        c = candidate_from_row(row, config=config, settings=settings, held_tickers=scan_exclude)
        if c:
            candidates.append(c)

    pool_size = int(icfg.get("candidate_pool_size", 30))
    max_slots = int(icfg.get("max_proposed_slots", 8))
    max_open = int(settings.get("max_open_trades") or 3)
    slots_available = max(0, max_open - len(open_trades))

    proposed = pick_diversified_candidates(
        candidates,
        limit=max(max_slots, slots_available + 2),
        max_sector_slots=int(icfg.get("max_sector_slots", 2)),
        open_tickers=open_tickers,
    )

    closed = list(book.get("closed_trades") or [])
    realized = round(sum(float(c.get("realized_pnl_usd") or 0) for c in closed), 2)
    unrealized = round(
        sum(float(t.get("unrealized_pnl_usd") or 0) for t in refreshed_open),
        2,
    )
    goal = float(settings.get("goal_usd") or 0)

    regime_down = str(market_regime or "").upper() == "DOWN"
    block_new = bool(icfg.get("block_new_entries_regime_down")) and regime_down

    prev_proposed = book.get("_last_proposed") if isinstance(book.get("_last_proposed"), list) else []
    daily_changes = build_daily_changes(
        prev_proposed=prev_proposed,
        proposed=proposed,
        open_trades=refreshed_open,
    )
    book["_last_proposed"] = proposed

    goal_summary = compute_goal_summary(settings)
    return {
        "enabled": icfg.get("enabled", True),
        "as_of": as_of,
        "signal_source": source,
        "universe_size": len(universe),
        "scanned_count": len([s for s in universe if s in by_ticker and s not in scan_exclude]),
        "candidate_pool_count": len(candidates),
        "exclude_long_term_holdings": exclude,
        "excluded_long_term_tickers": sorted(scan_exclude) if exclude else [],
        "market_regime": market_regime,
        "block_new_entries": block_new,
        "settings": settings,
        "goal_summary": goal_summary,
        "progress": {
            "realized_pnl_usd": realized,
            "unrealized_pnl_usd": unrealized,
            "total_pnl_usd": round(realized + unrealized, 2),
            "goal_usd": goal,
            "pct_of_goal": round(100.0 * (realized + unrealized) / goal, 1) if goal > 0 else None,
            "closed_trades_count": len(closed),
            "open_trades_count": len(refreshed_open),
        },
        "open_trades": refreshed_open,
        "closed_trades": closed[-20:],
        "proposed_trades": proposed[:max_slots],
        "candidate_pool": candidates[:pool_size],
        "daily_changes": daily_changes,
        "disclaimer": (
            "Income book is a separate tactical sleeve — not your long-term portfolio. "
            "Decision support only; confirm every trade manually."
        ),
    }
