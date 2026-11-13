"""Daily alerts when a strong Research rule turns on for one of our tracked tickers.

Only rules that clear the promotion bar or that the owner approved alert, once per ticker on the day the rule
turns on. Alerts carry the ticker's Best setups plan status; they never change gates or BUY/HOLD/SELL."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

MAX_PUSH_NAMES = 4


def _sent_path():
    from research.panel import panel_dir

    return panel_dir() / "alerts_sent.json"


def _load_sent() -> dict[str, str]:
    p = _sent_path()
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def _plan_line(rows: dict, ticker: str) -> tuple[str, bool]:
    """(plan text, gates clear) from the Swing row, falling back to Owner."""
    modes = (rows or {}).get("modes") or {}
    for m in ("swing", "owner"):
        r = (modes.get(m) or {}).get(ticker)
        if not r:
            continue
        band = f"{m.title()} band ${r['band_low']:,.2f}–${r['band_high']:,.2f}"
        gap = r.get("band_gap_pct")
        where = "in band" if gap is not None and gap <= 0 else (f"{gap:.1f}% above band" if gap is not None else "no band")
        if r.get("status") is None:
            gates = "watch, gates blocked" + (f" ({', '.join(r['gates_failing'])})" if r.get("gates_failing") else "")
        else:
            gates = r["status"]
        return f"{band} · {where} · stop ${r['stop']:,.2f} · {gates}", r.get("status") is not None
    return "no Best setups plan today, check the ticker page", False


def turned_on(fc, rules: list[dict], tickers: set[str]) -> list[tuple[str, dict]]:
    """(ticker, rule run) where the rule is on at the last close and was off the session before."""
    from research.dsl import evaluate

    idx = len(fc.p.close.index) - 1
    if idx < 1:
        return []
    out = []
    for r in rules:
        try:
            m = evaluate(r["rule"], fc, slice(idx - 1, idx + 1))
        except Exception:
            logger.warning("[research-alerts] rule %s failed to evaluate", r.get("id"))
            continue
        on = m.iloc[-1] & ~m.iloc[-2]
        out += [(str(t), r) for t in on.index[on.values] if str(t) in tickers]
    return out


def publish_rule_alerts(fc=None, rows: dict | None = None, tickers: list[str] | None = None) -> int:
    """Called after the panel update and after the Best setups build; sends only once both cover the same day."""
    from research.integration import get_fc, saved_rules, tracked_tickers
    from signals.best_setups import load_rows

    fc = fc or get_fc()
    rows = rows if rows is not None else load_rows()
    if fc is None or not rows:
        return 0
    as_of = str(fc.p.close.index[-1].date())
    if rows.get("as_of") != as_of:
        logger.info("[research-alerts] waiting: panel %s, plans %s", as_of, rows.get("as_of"))
        return 0
    rules = [r for r in saved_rules() if r.get("approved") or (r.get("promotion") or {}).get("passes")]
    if not rules:
        return 0
    want = {t.upper() for t in (tickers if tickers is not None else tracked_tickers())}
    sent = _load_sent()
    fresh = []
    for t, r in turned_on(fc, rules, want):
        key = f"{t}:{r['id']}:{as_of}"
        if key not in sent:
            fresh.append((key, t, r))
    if not fresh:
        return 0
    events: list[Any] = []
    try:
        from alerts.events import AlertEvent, AlertEventStore
        from config_loader import get_data_root

        for key, t, r in fresh:
            plan, clear = _plan_line(rows, t)
            oos = r.get("oos") or {}
            tag = "approved" if r.get("approved") else "clears the bar"
            events.append(AlertEvent.create(
                ticker=t, alert_type="research_rule", severity="info",
                title=f"{t}: Research rule on ({tag}): {r.get('label') or r.get('rule_text')}",
                message=f"{plan}. Since 2019: {oos.get('n')} trades, avg {oos.get('mean')}% after costs, "
                        f"win {oos.get('win_rate')}%. Research only, not a buy signal.",
                payload={"run_id": r["id"], "rule_text": r.get("rule_text"), "approved": bool(r.get("approved")),
                         "gates_clear": clear, "as_of": as_of},
                dedupe_key=f"{key}:research_rule",
            ))
        AlertEventStore(get_data_root()).append_events(events)
    except Exception:
        logger.exception("[research-alerts] alert events failed")
        return 0
    sent.update({k: as_of for k, _, _ in fresh})
    cutoff = sorted(set(sent.values()))[-30:]
    sent = {k: v for k, v in sent.items() if v in cutoff}
    p = _sent_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sent))
    if "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            from api.routers.push import broadcast_web_push

            names = ", ".join(sorted({t for _, t, _ in fresh})[:MAX_PUSH_NAMES])
            broadcast_web_push("Research rules turned on", names + (" …" if len({t for _, t, _ in fresh}) > MAX_PUSH_NAMES else ""), "/")
        except Exception:
            logger.exception("[research-alerts] push failed")
    logger.info("[research-alerts] %d alerts for %s", len(fresh), as_of)
    return len(fresh)


def publish_safely() -> None:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    try:
        publish_rule_alerts()
    except Exception:
        logger.exception("[research-alerts] failed")
