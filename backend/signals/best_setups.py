"""Best setups: rank watchlist tickers per mode (Swing / Owner) by model edge, keeping only
plans whose entry is allowed, R:R clears the mode minimum and price is in or near the band.
Built from the full ticker pages during the post-EOD audit; daily picks are saved and
tracked forward (target first / stop first / open) so the list's real hit rate is visible."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODES: dict[str, dict[str, Any]] = {
    "swing": {"horizon": "medium", "min_rr": 2.0, "window": 63},
    "owner": {"horizon": "long", "min_rr": 1.5, "window": 252},
}
NEAR_BAND_PCT = 3.0
TOP_N = 10
NEXT_UP_N = 8
TRACK_DAYS = 180
_DIR = "best_setups"


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _entry_status(ra: dict, mode: str) -> tuple[str | None, int | None, int | None]:
    disp = ((ra.get("display_by_mode") or {}).get(mode)) or {}
    gp, gt = disp.get("gates_passed"), disp.get("gates_total")
    em = ra.get("entry_mode")
    if em == "full_go" or (gt and gp == gt):
        return "Can add", gp, gt
    if em == "starter_only":
        return "Starter only", gp, gt
    return None, gp, gt


def _band_gap_pct(h: dict, price: float) -> float | None:
    ez = h.get("entry_zone") or {}
    hi = _f(ez.get("high"))
    if not hi or hi <= 0:
        return None
    return round(max(0.0, (price - hi) / hi * 100.0), 1)


def _ref_level(h: dict, price: float) -> dict | None:
    lv = [x for x in ((h.get("entry_zone") or {}).get("levels") or []) if x.get("role") == "entry"
          and _f(x.get("price"))]
    if not lv:
        return None
    at_or_below = [x for x in lv if _f(x["price"]) <= price]
    pool = at_or_below or lv
    return max(pool, key=lambda x: _f(x["price"])) if at_or_below else min(pool, key=lambda x: _f(x["price"]))


def setup_row(detail: dict, mode: str) -> dict | None:
    """One ranked row for a ticker in a mode, or None when the plan has no usable levels."""
    cfg = MODES[mode]
    inv = (detail or {}).get("investor_summary") or {}
    h = (inv.get("horizons") or {}).get(cfg["horizon"]) or {}
    price = _f(detail.get("current_price"))
    ez = h.get("entry_zone") or {}
    lo, hi = _f(ez.get("low")), _f(ez.get("high"))
    tgt, stop = _f(h.get("target")), _f(h.get("stop_loss"))
    if not (price and lo and hi and tgt and stop) or stop >= lo:
        return None
    mid = (lo + hi) / 2.0
    tgt_pct = (tgt - mid) / mid * 100.0
    stop_pct = (mid - stop) / mid * 100.0
    if tgt_pct <= 0:
        return None
    p = _f(h.get("ml_prob")) if h.get("ml_scored") is not False else None
    edge = None if p is None else (p / 100.0) * tgt_pct - (1 - p / 100.0) * stop_pct
    rr = _f(h.get("risk_reward_from_entry"))
    status, gp, gt = _entry_status(inv.get("retail_action") or {}, mode)
    gap = _band_gap_pct(h, price)
    lvl = _ref_level(h, price) or {}
    blockers: list[str] = []
    if status is None:
        blockers.append("entry gates")
    if h.get("setup_status") == "no_setup" or rr is None or rr < cfg["min_rr"]:
        blockers.append(f"R:R under {cfg['min_rr']:.1f}")
    if gap is None or gap > NEAR_BAND_PCT:
        blockers.append("price above band")
    if edge is None:
        blockers.append("no model score")
    return {
        "ticker": str(detail.get("ticker") or "").upper(),
        "name": detail.get("company_name") or detail.get("name"),
        "price": round(price, 2),
        "status": status,
        "gates_passed": gp,
        "gates_total": gt,
        "band_low": round(lo, 2),
        "band_high": round(hi, 2),
        "band_gap_pct": gap,
        "target": round(tgt, 2),
        "stop": round(stop, 2),
        "target_pct": round(tgt_pct, 1),
        "stop_pct": round(stop_pct, 1),
        "rr": None if rr is None else round(rr, 2),
        "model_prob": None if p is None else round(p),
        "model_gain_pct": _f(h.get("ml_target_gain_pct")),
        "edge_pct": None if edge is None else round(edge, 2),
        "target_first_pct": lvl.get("target_first_pct"),
        "stop_first_pct": lvl.get("stop_first_pct"),
        "duration": h.get("duration"),
        "qualified": not blockers,
        "blockers": blockers,
    }


def rank(rows_by_mode: dict[str, list[dict]]) -> dict[str, dict[str, list[dict]]]:
    out: dict[str, dict[str, list[dict]]] = {}
    for mode, rows in rows_by_mode.items():
        scored = [r for r in rows if r.get("edge_pct") is not None]
        scored.sort(key=lambda r: r["edge_pct"], reverse=True)
        picks = [r for r in scored if r["qualified"]][:TOP_N]
        # Next up: positive edge, one blocker away (not the model score itself).
        nxt = [r for r in scored if not r["qualified"] and r["edge_pct"] > 0 and len(r["blockers"]) == 1]
        out[mode] = {"picks": picks, "next_up": nxt[:NEXT_UP_N]}
    return out


def build_report(details: list[dict], as_of: date | None = None) -> dict:
    rows: dict[str, list[dict]] = {m: [] for m in MODES}
    for d in details:
        if not isinstance(d, dict) or d.get("error") or not d.get("ticker"):
            continue
        if str(d["ticker"]).upper().endswith("-USD"):
            continue
        for m in MODES:
            try:
                r = setup_row(d, m)
            except Exception:
                logger.exception("best-setups row failed %s/%s", d.get("ticker"), m)
                r = None
            if r:
                rows[m].append(r)
    return {
        "as_of": (as_of or date.today()).isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scanned": len(details),
        "modes": rank(rows),
    }


def _dir() -> Path:
    from config_loader import writable_data_path

    return writable_data_path("audit", _DIR)


def save_report(report: dict) -> None:
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(report, default=str)
    (d / "latest.json").write_text(blob)
    (d / f"best_setups_{report['as_of']}.json").write_text(blob)


def load_latest() -> dict | None:
    p = _dir() / "latest.json"
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        logger.exception("best-setups read failed")
        return None


def _history(days: int = TRACK_DAYS) -> list[dict]:
    d = _dir()
    if not d.exists():
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    out = []
    for p in sorted(d.glob("best_setups_*.json")):
        day = p.stem.replace("best_setups_", "")
        if day < cutoff:
            continue
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            continue
    return out


def pick_outcome(pick: dict, pick_day: str, bars, window: int) -> dict | None:
    """Follow a pick from the session after its date: which of target/stop was touched first."""
    if bars is None or len(bars) == 0:
        return None
    idx = bars.index
    try:
        after = bars[[ts.date().isoformat() > pick_day for ts in idx]]
    except Exception:
        return None
    if len(after) == 0:
        return None
    after = after.iloc[:window]
    entry, tgt, stop = pick["price"], pick["target"], pick["stop"]
    result = "open"
    for _, b in after.iterrows():
        hit_s = b.get("low") is not None and b["low"] <= stop
        hit_t = b.get("high") is not None and b["high"] >= tgt
        if hit_s:
            result = "stop"
            break
        if hit_t:
            result = "target"
            break
    if result == "open" and len(after) >= window:
        result = "expired"
    last = float(after["close"].iloc[-1])
    exit_px = tgt if result == "target" else stop if result == "stop" else last
    return {"result": result, "return_pct": round((exit_px - entry) / entry * 100.0, 2),
            "sessions": int(len(after))}


def track_record(fetch=None) -> dict:
    """Forward results of every saved pick (one per ticker/mode/day)."""
    if fetch is None:
        from signals.fetcher import fetch_ohlcv_dataframe as fetch
    hist = _history()
    bars_cache: dict[str, Any] = {}
    out: dict[str, Any] = {}
    for mode, cfg in MODES.items():
        rows = []
        prev: set[str] = set()
        for rep in hist:
            day = rep.get("as_of")
            todays = ((rep.get("modes") or {}).get(mode) or {}).get("picks") or []
            # A ticker that stays on the list day after day counts once, from its first day.
            cur = {pk.get("ticker") for pk in todays}
            for pk in todays:
                t = pk.get("ticker")
                if not t or t in prev or day >= date.today().isoformat():
                    continue
                if t not in bars_cache:
                    try:
                        bars_cache[t] = fetch(t, "2y")
                    except Exception:
                        bars_cache[t] = None
                oc = pick_outcome(pk, day, bars_cache[t], cfg["window"])
                if oc:
                    rows.append({"date": day, "ticker": t, **oc})
            prev = cur
        closed = [r for r in rows if r["result"] in ("target", "stop", "expired")]
        wins = [r for r in closed if r["result"] == "target"]
        out[mode] = {
            "picks": len(rows),
            "closed": len(closed),
            "target_first_pct": round(100.0 * len(wins) / len(closed)) if closed else None,
            "avg_return_pct": round(sum(r["return_pct"] for r in rows) / len(rows), 2) if rows else None,
            "recent": rows[-15:][::-1],
        }
    return out
