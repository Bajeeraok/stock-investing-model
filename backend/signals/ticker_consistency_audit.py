"""Rule checker for the ticker detail page.

Each rule compares numbers the page shows in more than one place (or against hard
invariants: stops below price, bands at/below spot, fresh data…). Findings are
deterministic so the same bug is caught every run; new bugs become new rules.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

HORIZONS = ("short", "medium", "long")
HORIZON_MODE = {"short": "Scout", "medium": "Swing", "long": "Owner"}
MAX_BAND_WIDTH_PCT = {"short": 8.0, "medium": 12.0}
BUY_WORDS = ("BUY", "ADD", "ACCUMULATE")


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _pct(a: float, b: float) -> float:
    return 100.0 * (a - b) / b if b else 0.0


class _Collector:
    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        self.findings: list[dict[str, Any]] = []

    def add(self, rule: str, severity: str, message: str, **values: Any) -> None:
        self.findings.append(
            {"ticker": self.ticker, "rule": rule, "severity": severity, "message": message, "values": values}
        )


def _price(detail: dict) -> float | None:
    return _f(detail.get("live_price")) or _f(detail.get("current_price"))


def _horizons(detail: dict) -> dict[str, dict]:
    inv = detail.get("investor_summary") or {}
    return {h: (inv.get("horizons") or {}).get(h) or {} for h in HORIZONS}


def _retail(detail: dict) -> dict:
    return (detail.get("investor_summary") or {}).get("retail_action") or {}


def _walk_non_finite(obj: Any, path: str = "", out: list[str] | None = None, limit: int = 5) -> list[str]:
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(obj, float) and not math.isfinite(obj):
        out.append(path or "<root>")
    elif isinstance(obj, str) and obj.strip().lower() in ("nan", "inf", "-inf", "$nan", "nan%"):
        out.append(path or "<root>")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("price_history", "ohlcv_close"):
                continue
            _walk_non_finite(v, f"{path}.{k}" if path else str(k), out, limit)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            _walk_non_finite(v, f"{path}[{i}]", out, limit)
    return out


# ── rules ────────────────────────────────────────────────────────────────────

def rule_price_consistency(d: dict, c: _Collector, row: dict | None) -> None:
    p = _price(d)
    if p is None:
        c.add("price_missing", "error", "No current price on the page")
        return
    pa = d.get("position_advice") or {}
    pap = _f(pa.get("price"))
    if pap and abs(_pct(pap, p)) > 1.0:
        c.add("price_mismatch_position_advice", "warn",
              f"Position sizing uses ${pap:.2f} but the header shows ${p:.2f}", sizing_price=pap, price=p)
    lo, hi = _f(d.get("low_52w")), _f(d.get("high_52w"))
    if lo and hi and (p < lo * 0.98 or p > hi * 1.02):
        c.add("price_outside_52w", "warn", f"Price ${p:.2f} outside 52w range ${lo:.2f}–${hi:.2f}",
              price=p, low_52w=lo, high_52w=hi)


def rule_gate_consistency(d: dict, c: _Collector, row: dict | None) -> None:
    ra = _retail(d)
    gates = ra.get("gates") or []
    mode = ra.get("entry_mode")
    passed = sum(1 for g in gates if g.get("pass"))
    gp = d.get("gates_passed")
    if isinstance(gp, (int, float)) and gates and int(gp) != passed:
        c.add("gate_count_mismatch", "warn", f"Header says {int(gp)} gates passed, gate list shows {passed}/{len(gates)}",
              header=gp, listed=passed, total=len(gates))
    gng = ra.get("go_no_go")
    if mode == "full_go" and gng not in (None, "go"):
        c.add("go_no_go_mismatch", "error", f"Entry mode full_go but go/no-go is {gng}", entry_mode=mode, go_no_go=gng)
    if mode == "hard_lock" and gng == "go":
        c.add("go_no_go_mismatch", "error", "Entries locked but go/no-go says go", entry_mode=mode, go_no_go=gng)
    if mode == "hard_lock" and (_f(ra.get("max_sizing_pct")) or 0) > 0:
        c.add("sizing_while_locked", "error", f"Entries locked but max sizing is {ra.get('max_sizing_pct')}%",
              max_sizing_pct=ra.get("max_sizing_pct"))
    pa = d.get("position_advice") or {}
    if pa.get("entry_mode") and mode and pa.get("entry_mode") != mode:
        c.add("position_advice_entry_mode", "error",
              f"Sizing card uses entry mode {pa.get('entry_mode')}, verdict uses {mode}",
              sizing=pa.get("entry_mode"), verdict=mode)
    if mode == "hard_lock" and (pa.get("buy") or {}).get("allowed"):
        c.add("buy_allowed_while_locked", "error", "Sizing card allows a buy while entries are locked")
    if row is not None:
        lm = (row.get("retail_status") or {}).get("entry_mode") or row.get("entry_mode")
        buyable = {"full_go", "starter_only", "go"}
        if lm and mode and ((lm in buyable) != (mode in buyable)):
            c.add("list_vs_detail_entry_mode", "error",
                  f"Signals list says {lm}, ticker page says {mode}", list=lm, detail=mode)


def rule_verdict_vs_entry(d: dict, c: _Collector, row: dict | None) -> None:
    ra = _retail(d)
    if ra.get("entry_mode") != "hard_lock":
        return
    for h, hv in _horizons(d).items():
        v = str(hv.get("verdict") or "").upper()
        if any(w == v or v.startswith(w + " ") for w in BUY_WORDS):
            c.add("buy_verdict_while_locked", "warn",
                  f"{HORIZON_MODE[h]} horizon verdict is {v} but entries are locked (No new entries)",
                  horizon=h, verdict=v)


def rule_bands(d: dict, c: _Collector, row: dict | None) -> None:
    p = _price(d)
    if p is None:
        return
    for h, hv in _horizons(d).items():
        ez = hv.get("entry_zone") or {}
        lo, hi = _f(ez.get("low")), _f(ez.get("high"))
        mode = HORIZON_MODE[h]
        if lo is None or hi is None:
            continue
        if lo <= 0 or hi <= 0 or lo > hi + 1e-6:
            c.add("band_invalid", "error", f"{mode} band ${lo}–${hi} is invalid", horizon=h, low=lo, high=hi)
            continue
        # Owner (long) bands are threshold ceilings; the page clamps tiers above spot to "at spot".
        if h != "long" and hi > p * 1.005:
            c.add("band_above_price", "error", f"{mode} band top ${hi:.2f} is above price ${p:.2f} (chasing)",
                  horizon=h, high=hi, price=p)
        width = _pct(hi, lo)
        cap = MAX_BAND_WIDTH_PCT.get(h)
        if cap and width > cap + 0.1:
            c.add("band_too_wide", "warn", f"{mode} band is {width:.1f}% wide (cap {cap:.0f}%)",
                  horizon=h, width_pct=round(width, 1))
        levels = ez.get("levels") or []
        entry_levels = [lv for lv in levels if lv.get("role") == "entry"]
        outside = [lv for lv in entry_levels if (_f(lv.get("price")) or 0) < lo * 0.995 or (_f(lv.get("price")) or 0) > hi * 1.005]
        if outside and len(outside) == len(entry_levels):
            lv = outside[0]
            c.add("levels_outside_band", "warn",
                  f"{mode} band ${lo:.2f}–${hi:.2f} but its add level '{lv.get('label')}' is ${_f(lv.get('price')) or 0:.2f}",
                  horizon=h, low=lo, high=hi, level=lv.get("price"))
        for lv in levels:
            tp, md = lv.get("touch_pct"), lv.get("median_days")
            if tp is not None and not (0 <= (_f(tp) or -1) <= 100):
                c.add("touch_odds_invalid", "error", f"{mode} level touch odds {tp}", horizon=h, touch_pct=tp)
            if md is not None and (_f(md) or 0) < 0:
                c.add("touch_odds_invalid", "error", f"{mode} level median days {md}", horizon=h, median_days=md)


def rule_stops_targets(d: dict, c: _Collector, row: dict | None) -> None:
    p = _price(d)
    if p is None:
        return
    for h, hv in _horizons(d).items():
        mode = HORIZON_MODE[h]
        sl, tg = _f(hv.get("stop_loss")), _f(hv.get("target"))
        if sl is not None and sl >= p:
            c.add("stop_above_price", "info", f"{mode} stop ${sl:.2f} is at/above price ${p:.2f}",
                  horizon=h, stop=sl, price=p)
        if tg is not None and tg <= p:
            c.add("target_below_price", "warn", f"{mode} target ${tg:.2f} is at/below price ${p:.2f}",
                  horizon=h, target=tg, price=p)
        if sl is not None and tg is not None and sl >= tg:
            c.add("stop_above_target", "error", f"{mode} stop ${sl:.2f} ≥ target ${tg:.2f}", horizon=h)
    sb = _f(d.get("suggested_buy_price"))
    if sb and sb > p * 1.01:
        c.add("suggested_buy_above_price", "warn", f"Suggested buy ${sb:.2f} is above price ${p:.2f}", suggested=sb)


def rule_valuation(d: dict, c: _Collector, row: dict | None) -> None:
    p = _price(d)
    inv = d.get("investor_summary") or {}
    fv = _f(inv.get("fair_value"))
    ra = _retail(d)
    ap = _f(ra.get("assessment_pct"))
    if p and fv and fv > 0 and ap is not None and ap != 0:
        expect = _pct(fv, p)
        if abs(expect - ap) > 2.0:
            c.add("valuation_mismatch", "warn",
                  f"Valuation gate uses {ap:.1f}% upside but fair value ${fv:.2f} vs price ${p:.2f} is {expect:.1f}%",
                  gate_upside=ap, implied_upside=round(expect, 1), fair_value=fv, price=p)


def rule_confidence(d: dict, c: _Collector, row: dict | None) -> None:
    a = _f(d.get("model_confidence_pct"))
    b = _f((d.get("investor_summary") or {}).get("model_confidence_pct"))
    if a is not None and b is not None and abs(a - b) > 1.0:
        c.add("confidence_mismatch", "warn", f"Confidence {a:.0f}% in header vs {b:.0f}% in summary", header=a, summary=b)


def rule_freshness(d: dict, c: _Collector, row: dict | None, today: date | None = None) -> None:
    today = today or date.today()
    hmm = ((d.get("confidence") or {}).get("hmm") or {}) if isinstance(d.get("confidence"), dict) else {}
    ec = hmm.get("earnings_context") or {}
    days = _f(ec.get("days_since_earnings"))
    if days is not None and days > 130:
        c.add("earnings_date_stale", "warn",
              f"Most recent earnings date used by the regime model is {ec.get('most_recent_earnings_date')} ({int(days)} days ago)",
              date=ec.get("most_recent_earnings_date"), days=int(days))
    earn = d.get("earnings") or {}
    nxt = earn.get("next_date") or earn.get("next_earnings_date") if isinstance(earn, dict) else None
    if isinstance(nxt, str) and len(nxt) >= 10:
        try:
            nd = datetime.strptime(nxt[:10], "%Y-%m-%d").date()
            if (today - nd).days > 3:
                c.add("next_earnings_in_past", "warn", f"Next earnings date {nxt[:10]} is in the past", next_date=nxt[:10])
        except ValueError:
            pass
    dy = _f(d.get("dividend_yield"))
    if dy is not None and (dy < 0 or dy > 15):
        c.add("dividend_yield_invalid", "warn", f"Dividend yield {dy}%", dividend_yield=dy)
    se = d.get("sanity_errors") or []
    if se:
        c.add("sanity_errors", "info", f"Built-in data checks flagged: {', '.join(map(str, se))[:200]}", errors=se)
    bad = _walk_non_finite(d)
    if bad:
        c.add("non_finite_values", "error", f"NaN/inf in fields: {', '.join(bad)}", fields=bad)


RULES: list[Callable[[dict, _Collector, dict | None], None]] = [
    rule_price_consistency,
    rule_gate_consistency,
    rule_verdict_vs_entry,
    rule_bands,
    rule_stops_targets,
    rule_valuation,
    rule_confidence,
    rule_freshness,
]


def audit_ticker_detail(detail: dict, list_row: dict | None = None) -> list[dict[str, Any]]:
    ticker = str(detail.get("ticker") or "?").upper()
    c = _Collector(ticker)
    if detail.get("error"):
        c.add("detail_error", "error", f"Ticker page failed: {detail.get('error')}")
        return c.findings
    for rule in RULES:
        try:
            rule(detail, c, list_row)
        except Exception as exc:  # a broken rule must not hide the others
            c.add("rule_crashed", "info", f"{rule.__name__} crashed: {exc}")
    return c.findings


def summarize(findings: Iterable[dict[str, Any]], tickers: list[str]) -> dict[str, Any]:
    findings = list(findings)
    by_rule: dict[str, dict[str, Any]] = {}
    for f in findings:
        r = by_rule.setdefault(f["rule"], {"rule": f["rule"], "severity": f["severity"], "count": 0, "tickers": []})
        r["count"] += 1
        if f["ticker"] not in r["tickers"]:
            r["tickers"].append(f["ticker"])
    sev = {s: sum(1 for f in findings if f["severity"] == s) for s in ("error", "warn", "info")}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_tickers": len(tickers),
        "tickers": tickers,
        "counts": sev,
        "by_rule": sorted(by_rule.values(), key=lambda r: ({"error": 0, "warn": 1, "info": 2}[r["severity"]], -r["count"])),
        "findings": findings,
    }


# ── runner (in-process, Railway) ─────────────────────────────────────────────

_RUN_LOCK = threading.Lock()
REPORT_NAME = "ticker_consistency_latest.json"


def _report_path():
    from config_loader import writable_data_path

    return writable_data_path("audit", REPORT_NAME)


def load_latest_report() -> dict | None:
    try:
        p = _report_path()
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:
        logger.exception("audit report read failed")
        return None


def run_ticker_consistency_audit(tickers: list[str] | None = None, config: dict | None = None) -> dict | None:
    if not _RUN_LOCK.acquire(blocking=False):
        logger.info("[ticker-audit] already running")
        return None
    try:
        from api.ticker_detail import _signal_row_from_dashboard_cache, get_ticker_detail
        from config_loader import load_config

        config = config or load_config()
        rows: dict[str, dict] = {}
        if tickers is None:
            from signals.cache import get_cached_dashboard, get_last_dashboard_snapshot

            for payload in (get_cached_dashboard(), get_last_dashboard_snapshot()):
                if isinstance(payload, dict) and payload.get("signals"):
                    for r in payload["signals"]:
                        if isinstance(r, dict) and r.get("ticker") and not r.get("error"):
                            rows[str(r["ticker"]).upper()] = r
                    break
            tickers = sorted(t for t in rows if not t.endswith("-USD"))
        findings: list[dict[str, Any]] = []
        t0 = time.time()
        for t in tickers:
            try:
                detail = get_ticker_detail(t, config)
            except Exception as exc:
                detail = {"ticker": t, "error": str(exc)[:200]}
            row = rows.get(t) or _signal_row_from_dashboard_cache(t)
            findings.extend(audit_ticker_detail(detail, row))
        report = summarize(findings, list(tickers))
        report["duration_s"] = round(time.time() - t0, 1)
        p = _report_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, default=str))
        (p.parent / f"ticker_consistency_{date.today().isoformat()}.json").write_text(json.dumps(report, default=str))
        logger.info("[ticker-audit] %d tickers, %s in %.0fs", len(tickers), report["counts"], report["duration_s"])
        return report
    finally:
        _RUN_LOCK.release()


def start_background_audit(tickers: list[str] | None = None) -> bool:
    if _RUN_LOCK.locked():
        return False
    threading.Thread(target=run_ticker_consistency_audit, kwargs={"tickers": tickers}, daemon=True,
                     name="ticker-consistency-audit").start()
    return True
