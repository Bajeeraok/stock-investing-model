"""Research → product hooks: shared feature cache, approved rules, and today's rule hits for Best setups.

Only rules that clear the promotion bar can be approved; only approved rules reorder Best setups,
and they never change gates or BUY/HOLD/SELL."""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

MAX_BADGE_RULES = 30
_lock = threading.Lock()
_fc_cache: dict[str, Any] = {}
_hits_cache: dict[str, Any] = {}


def get_fc():
    """Cached FeatureCache for the current panel build, or None when no panel exists."""
    from research import panel
    from research.features import FeatureCache

    with _lock:
        meta = panel.read_meta()
        if meta is None:
            return _fc_cache.get("fc")
        if meta.get("built_at") != _fc_cache.get("key"):
            p = panel.load()
            if p is not None:
                _fc_cache.clear()
                _fc_cache.update(key=p.meta.get("built_at"), fc=FeatureCache(p))
        return _fc_cache.get("fc")


def tracked_tickers() -> list[str]:
    try:
        from signals.cache import get_signals_panel

        rows = (get_signals_panel() or {}).get("signals") or []
        return sorted({str(r.get("ticker")).upper() for r in rows if isinstance(r, dict) and r.get("ticker")})
    except Exception:
        logger.exception("[research] tracked tickers unavailable")
        return []


def _approved_path():
    from research.panel import panel_dir

    return panel_dir() / "approved_rules.json"


def load_approved() -> dict[str, dict]:
    p = _approved_path()
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def _save_approved(d: dict) -> None:
    p = _approved_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1, default=str))
    _hits_cache.clear()


def approve(run_id: str) -> dict:
    from research.service import read_runs

    run = next((r for r in read_runs() if r.get("id") == run_id), None)
    if not run:
        raise KeyError("run not found")
    if not (run.get("promotion") or {}).get("passes"):
        raise ValueError("only rules that clear the promotion bar can be approved")
    d = load_approved()
    d[run_id] = {"approved_at": time.time(), "rule": run.get("rule"), "rule_text": run.get("rule_text"), "label": run.get("label")}
    _save_approved(d)
    return d[run_id]


def unapprove(run_id: str) -> bool:
    d = load_approved()
    found = d.pop(run_id, None) is not None
    if found:
        _save_approved(d)
    return found


def saved_rules(limit: int = MAX_BADGE_RULES) -> list[dict]:
    """Latest run per distinct rule, approved rules first."""
    from research.service import read_runs

    approved = load_approved()
    seen: dict[str, dict] = {}
    for r in read_runs():
        if not isinstance(r.get("rule"), dict):
            continue
        seen[json.dumps(r["rule"], sort_keys=True)] = r
    rows = sorted(seen.values(), key=lambda r: (r.get("id") not in approved, -(r.get("ts") or 0)))
    return [r | {"approved": r.get("id") in approved} for r in rows[:limit]]


def _badge(r: dict, as_of: str) -> dict:
    oos, pc = r.get("oos") or {}, r.get("promotion") or {}
    return {
        "run_id": r.get("id"), "rule_text": r.get("rule_text"), "label": r.get("label"),
        "approved": bool(r.get("approved")), "passes": bool(pc.get("passes")),
        "oos_n": oos.get("n"), "oos_mean": oos.get("mean"), "oos_win": oos.get("win_rate"),
        "t_stat": pc.get("t_stat"), "hold_days": (r.get("params") or {}).get("hold_days"), "as_of": as_of,
    }


def rule_hits(tickers: list[str] | None = None, fc=None) -> dict[str, list[dict]]:
    """Ticker -> saved Research rules that are on at the last panel close."""
    from research.dsl import evaluate

    fc = fc or get_fc()
    if fc is None:
        return {}
    rules = saved_rules()
    key = json.dumps([fc.p.meta.get("built_at"), [(r.get("id"), r.get("approved")) for r in rules]])
    key = f"{id(fc)}:{key}"
    if _hits_cache.get("key") == key:
        out = _hits_cache["hits"]
    else:
        out: dict[str, list[dict]] = {}
        idx = len(fc.p.close.index) - 1
        as_of = str(fc.p.close.index[idx].date())
        for r in rules:
            try:
                row = evaluate(r["rule"], fc, slice(max(0, idx - 1), idx + 1)).iloc[-1]
            except Exception:
                logger.warning("[research] saved rule %s failed to evaluate", r.get("id"))
                continue
            for t in row.index[row.values]:
                out.setdefault(str(t), []).append(_badge(r, as_of))
        _hits_cache.update(key=key, hits=out)
    if tickers is None:
        return out
    want = {t.upper() for t in tickers}
    return {t: v for t, v in out.items() if t in want}


def approved_hit_tickers(fc=None) -> set[str]:
    try:
        return {t for t, bs in rule_hits(fc=fc).items() if any(b["approved"] for b in bs)}
    except Exception:
        logger.exception("[research] approved hits unavailable")
        return set()


def annotate_best_setups(report: dict | None, fc=None) -> dict | None:
    """Attach Research badges to every row; approved-rule hits move up within each list."""
    if not report or not report.get("modes"):
        return report
    try:
        tick = {r.get("ticker") for m in report["modes"].values() for lst in m.values() if isinstance(lst, list) for r in lst}
        hits = rule_hits([t for t in tick if t], fc=fc)
    except Exception:
        logger.exception("[research] best-setups annotation failed")
        return report
    for m in report["modes"].values():
        for name, lst in list(m.items()):
            if not isinstance(lst, list):
                continue
            for r in lst:
                r["research"] = hits.get(r.get("ticker"), [])
                r["research_boost"] = any(b["approved"] for b in r["research"])
            m[name] = sorted(lst, key=lambda r: not r["research_boost"])
    report["research_approved_rules"] = len(load_approved())
    return report
