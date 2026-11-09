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
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

MODES: dict[str, dict[str, Any]] = {
    "swing": {"horizon": "medium", "min_rr": 2.0, "window": 63},
    "owner": {"horizon": "long", "min_rr": 1.5, "window": 252},
}
NEAR_BAND_PCT = 3.0
# Owner adds never sit above the max add (band top); only Swing gets the near-band allowance.
NEAR_BAND_PCT_BY_MODE = {"swing": NEAR_BAND_PCT, "owner": 0.0}
MIN_CHANCE = 40.0
ODDS_GAP_PTS = 30.0
TOP_N = 10
NEXT_UP_N = 8
TRACK_DAYS = 180
_DIR = "best_setups"


def _market_today() -> date:
    return datetime.now(ZoneInfo("America/New_York")).date()


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


def setup_row(detail: dict, mode: str, model_ok: bool = False) -> dict | None:
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
    lvl = _ref_level(h, price) or {}
    # Edge uses this plan's past first-touch odds (target vs stop) — the model's chance is for a
    # smaller +N% move, so applying it to the full target would overstate the payoff.
    tf, sf = _f(lvl.get("target_first_pct")), _f(lvl.get("stop_first_pct"))
    edge = None if tf is None or sf is None else (tf / 100.0) * tgt_pct - (sf / 100.0) * stop_pct
    rr = _f(h.get("risk_reward_from_entry"))
    status, gp, gt = _entry_status(inv.get("retail_action") or {}, mode)
    gap = _band_gap_pct(h, price)
    blockers: list[str] = []
    _labels = {"valuation": "Valuation", "regime": "Market weather", "momentum": "Momentum", "ml": "Model odds"}
    _gates = ((inv.get("retail_action") or {}).get("gates_by_mode") or {}).get(mode) or []
    gates_failing = [_labels[g["id"]] for g in _gates
                     if isinstance(g, dict) and g.get("id") in _labels and not g.get("pass")]
    if status is None:
        blockers.append("entry gates")
    if h.get("setup_status") == "no_setup" or rr is None or rr < cfg["min_rr"]:
        blockers.append(f"R:R under {cfg['min_rr']:.1f}")
    if gap is None or gap > NEAR_BAND_PCT_BY_MODE.get(mode, NEAR_BAND_PCT):
        blockers.append("price above band")
    if edge is None:
        blockers.append("no past odds")
    hp = _f(h.get("hist_prob_similar"))
    hist_basis = "similar" if hp is not None else None
    if hp is None:
        hp = _f(h.get("hist_prob"))
        hist_basis = "all" if hp is not None else None
    # Chance = this stock's own history for the model's +N% question; the model's odds count
    # (as the lower of the two) only once its horizon's model check says proven.
    pr = p if model_ok else None
    chance = min(x for x in (pr, hp) if x is not None) if (pr is not None or hp is not None) else None
    if model_ok and p is None:
        blockers.append("no model odds")
    elif chance is None:
        blockers.append("no history odds")
    elif chance < MIN_CHANCE:
        blockers.append(f"chance under {MIN_CHANCE:.0f}%")
    return {
        "ticker": str(detail.get("ticker") or "").upper(),
        "name": detail.get("company_name") or detail.get("name"),
        "price": round(price, 2),
        "status": status,
        "gates_passed": gp,
        "gates_total": gt,
        "gates_failing": gates_failing,
        "band_low": round(lo, 2),
        "band_high": round(hi, 2),
        "band_gap_pct": gap,
        "target": round(tgt, 2),
        "stop": round(stop, 2),
        "target_pct": round(tgt_pct, 1),
        "stop_pct": round(stop_pct, 1),
        "rr": None if rr is None else round(rr, 2),
        "model_prob": None if p is None else round(p),
        "model_proven": model_ok,
        "model_gain_pct": _f(h.get("ml_target_gain_pct")),
        "hist_prob": None if hp is None else round(hp),
        "hist_basis": hist_basis,
        "chance": None if chance is None else round(chance),
        "odds_gap": bool(p is not None and hp is not None and p - hp >= ODDS_GAP_PTS),
        "edge_pct": None if edge is None else round(edge, 2),
        "target_first_pct": lvl.get("target_first_pct"),
        "stop_first_pct": lvl.get("stop_first_pct"),
        "duration": h.get("duration"),
        "qualified": not blockers,
        "blockers": blockers,
    }


def dip_watch(scored: list[dict]) -> list[dict]:
    """Watch-only: would be a pick except Market weather fails (stock's trend not yet confirmed)."""
    rows = [r for r in scored if r.get("gates_failing") == ["Market weather"]
            and r["edge_pct"] > 0 and all(b == "entry gates" for b in r["blockers"])]
    return rows[:NEXT_UP_N]


def rank(rows_by_mode: dict[str, list[dict]]) -> dict[str, dict[str, list[dict]]]:
    out: dict[str, dict[str, list[dict]]] = {}
    for mode, rows in rows_by_mode.items():
        scored = [r for r in rows if r.get("edge_pct") is not None]
        scored.sort(key=lambda r: (r["edge_pct"], r.get("chance") or 0), reverse=True)
        picks = [r for r in scored if r["qualified"]][:TOP_N]
        # Next up: positive edge, one blocker away (not the model score itself).
        nxt = [r for r in scored if not r["qualified"] and r["edge_pct"] > 0 and len(r["blockers"]) == 1]
        dips = dip_watch(scored)
        dip_ids = {r["ticker"] for r in dips}
        nxt = [r for r in nxt if r["ticker"] not in dip_ids]
        out[mode] = {"picks": picks, "next_up": nxt[:NEXT_UP_N], "dip_watch": dips}
    return out


def build_report(details: list[dict], as_of: date | None = None, previous: dict | None = None) -> dict:
    rows: dict[str, list[dict]] = {m: [] for m in MODES}
    try:
        from signals.model_odds_check import load_model_check, model_trusted

        mc = load_model_check()
        trusted = {m: model_trusted(MODES[m]["horizon"], mc) for m in MODES}
    except Exception:
        trusted = {m: False for m in MODES}
    for d in details:
        if not isinstance(d, dict) or d.get("error") or not d.get("ticker"):
            continue
        if str(d["ticker"]).upper().endswith("-USD"):
            continue
        for m in MODES:
            try:
                r = setup_row(d, m, trusted[m])
            except Exception:
                logger.exception("best-setups row failed %s/%s", d.get("ticker"), m)
                r = None
            if r:
                rows[m].append(r)
    day = (as_of or _market_today()).isoformat()
    modes = rank(rows)
    prev = previous if previous is not None else load_latest()
    prev_modes = (prev or {}).get("modes") or {} if (prev or {}).get("as_of") != day else {}
    new_count = 0
    for m, v in modes.items():
        before = {r.get("ticker") for r in ((prev_modes.get(m) or {}).get("picks") or [])}
        for r in v["picks"]:
            r["new"] = r["ticker"] not in before
            new_count += int(r["new"])
    return {
        "as_of": day,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scanned": len(details),
        "new_count": new_count,
        "model_proven": trusted,
        "modes": modes,
    }


def publish_new_picks(report: dict) -> int:
    """Bell alert + web push for tickers that newly qualify today."""
    new = [(m, r) for m, v in (report.get("modes") or {}).items() for r in v.get("picks") or [] if r.get("new")]
    if not new:
        return 0
    try:
        from alerts.events import AlertEvent, AlertEventStore
        from config_loader import get_data_root

        AlertEventStore(get_data_root()).append_events([
            AlertEvent.create(
                ticker=r["ticker"], alert_type="best_setup", severity="info",
                title=f"{r['ticker']} is now a {m.title()} best setup",
                message=f"Band ${r['band_low']:,.2f}–${r['band_high']:,.2f} · target +{r['target_pct']}% · "
                        f"stop −{r['stop_pct']}% · chance {r.get('chance')}%",
                payload={"mode": m, **r}, dedupe_key=f"{r['ticker']}:best_setup:{m}:{report['as_of']}",
            ) for m, r in new
        ])
    except Exception:
        logger.exception("best-setups alert events failed")
    try:
        from api.routers.push import broadcast_web_push

        names = ", ".join(f"{r['ticker']} ({m.title()})" for m, r in new[:4])
        broadcast_web_push("New best setups", names + (" …" if len(new) > 4 else ""), "/")
    except Exception:
        logger.exception("best-setups push failed")
    return len(new)


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


def recheck_picks(report: dict, get_detail) -> dict:
    """Re-run each saved pick against its current ticker page (intraday)."""
    trusted = report.get("model_proven") or {}
    picks: dict[str, dict] = {}
    for m, v in (report.get("modes") or {}).items():
        for r in v.get("picks") or []:
            t = r.get("ticker")
            try:
                row = setup_row(get_detail(t), m, bool(trusted.get(m)))
            except Exception:
                logger.exception("best-setups recheck %s failed", t)
                continue
            if row is None:
                picks[f"{m}:{t}"] = {"qualified": False, "price": None, "reasons": ["no usable levels"]}
                continue
            reasons = [
                f"entry gates ({', '.join(row['gates_failing'])})" if b == "entry gates" and row.get("gates_failing") else b
                for b in row["blockers"]
            ]
            picks[f"{m}:{t}"] = {"qualified": row["qualified"], "price": row["price"], "status": row["status"],
                                 "band_low": row["band_low"], "band_high": row["band_high"], "reasons": reasons}
    return {"as_of": report.get("as_of"),
            "checked_at": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="minutes"),
            "picks": picks}


def save_live(live: dict) -> None:
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "live.json").write_text(json.dumps(live, default=str))


def load_live() -> dict | None:
    p = _dir() / "live.json"
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        return None


def apply_live(report: dict | None, live: dict | None) -> dict | None:
    """Attach the latest intraday re-check to each pick; the saved EOD list itself is not changed."""
    if not report or not live or live.get("as_of") != report.get("as_of"):
        return report
    out = {**report, "live_checked_at": live.get("checked_at"), "modes": {}}
    for m, v in (report.get("modes") or {}).items():
        out["modes"][m] = {**v, "picks": [
            {**r, "live": live["picks"].get(f"{m}:{r.get('ticker')}")} for r in v.get("picks") or []
        ]}
    return out


def recheck_latest(config: dict) -> dict | None:
    from api.ticker_detail import get_ticker_detail

    report = load_latest()
    if not report:
        return None
    live = recheck_picks(report, lambda t: get_ticker_detail(t, config, allow_stale=False))
    save_live(live)
    return live


def _history(days: int = TRACK_DAYS) -> list[dict]:
    d = _dir()
    if not d.exists():
        return []
    cutoff = (_market_today() - timedelta(days=days)).isoformat()
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


DIP_WATCH_SESSIONS = 21  # ~30 calendar days


def _fwd_return(bars, day: str, sessions: int) -> tuple[float | None, int]:
    """Close on `day` (or last before it) to close `sessions` later (or latest so far)."""
    if bars is None or len(bars) == 0:
        return None, 0
    try:
        keys = [ts.date().isoformat() for ts in bars.index]
    except Exception:
        return None, 0
    base = [i for i, k in enumerate(keys) if k <= day]
    if not base:
        return None, 0
    i0 = base[-1]
    after = len(keys) - 1 - i0
    if after <= 0:
        return None, 0
    i1 = i0 + min(sessions, after)
    c0, c1 = float(bars["close"].iloc[i0]), float(bars["close"].iloc[i1])
    return (round((c1 / c0 - 1) * 100.0, 2) if c0 else None), min(sessions, after)


def dip_watch_record(hist: list[dict], fetch, bars_cache: dict, mode: str) -> dict:
    """Forward result of each Dip watch name (first day on the list) vs SPY over ~30 days."""
    today = _market_today().isoformat()
    if "SPY" not in bars_cache:
        try:
            bars_cache["SPY"] = fetch("SPY", "2y")
        except Exception:
            bars_cache["SPY"] = None
    rows, prev = [], set()
    for k, rep in enumerate(hist):
        day = rep.get("as_of")
        todays = ((rep.get("modes") or {}).get(mode) or {}).get("dip_watch") or []
        cur = {r.get("ticker") for r in todays}
        for r in todays:
            t = r.get("ticker")
            if not t or t in prev or not day or day >= today:
                continue
            if t not in bars_cache:
                try:
                    bars_cache[t] = fetch(t, "2y")
                except Exception:
                    bars_cache[t] = None
            ret, n = _fwd_return(bars_cache[t], day, DIP_WATCH_SESSIONS)
            spy, _ = _fwd_return(bars_cache["SPY"], day, n) if n else (None, 0)
            if ret is None or spy is None:
                continue
            became_pick = any(
                t in {p.get("ticker") for p in ((later.get("modes") or {}).get(mode) or {}).get("picks") or []}
                for later in hist[k + 1:]
            )
            rows.append({"date": day, "ticker": t, "return_pct": ret, "spy_pct": spy,
                         "vs_spy_pts": round(ret - spy, 2), "sessions": n,
                         "status": "closed" if n >= DIP_WATCH_SESSIONS else "open", "became_pick": became_pick})
        prev = cur
    closed = [r for r in rows if r["status"] == "closed"]
    return {
        "names": len(rows),
        "closed": len(closed),
        "avg_vs_spy_pts": round(sum(r["vs_spy_pts"] for r in closed) / len(closed), 2) if closed else None,
        "beat_spy_pct": round(100.0 * sum(1 for r in closed if r["vs_spy_pts"] > 0) / len(closed)) if closed else None,
        "recent": rows[-15:][::-1],
    }


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
                if not t or t in prev or day >= _market_today().isoformat():
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
            "dip_watch": dip_watch_record(hist, fetch, bars_cache, mode),
        }
    return out
