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
    for k in ("live_price", "current_price"):
        x = _f(detail.get(k))
        if x is not None and x > 0:
            return x
    return None


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


KNOWN_ENTRY_MODES = {"full_go", "starter_only", "hard_lock", "go", "watch", "protect"}
WINDOW_BY_HORIZON = {"short": 20, "medium": 63, "long": 126}


def rule_ranges(d: dict, c: _Collector, row: dict | None) -> None:
    """Values that must sit inside a fixed range wherever they appear."""
    inv = d.get("investor_summary") or {}
    checks = [
        ("score", d.get("score"), 0, 100),
        ("model_confidence_pct", d.get("model_confidence_pct"), 0, 100),
        ("rsi", d.get("rsi"), 0, 100),
        ("regime_bull_pct", inv.get("regime_bull_pct"), 0, 100),
        ("max_sizing_pct", _retail(d).get("max_sizing_pct"), 0, 100),
    ]
    for h, hv in _horizons(d).items():
        checks.append((f"{h}.ml_prob", hv.get("ml_prob"), 0, 100))
    for name, v, lo, hi in checks:
        x = _f(v)
        if x is not None and not (lo <= x <= hi):
            c.add("value_out_of_range", "error", f"{name} = {x} (must be {lo}–{hi})", field=name, value=x)
    lo52, hi52 = _f(d.get("low_52w")), _f(d.get("high_52w"))
    if lo52 is not None and hi52 is not None and lo52 > hi52:
        c.add("range_52w_inverted", "error", f"52w low ${lo52} above 52w high ${hi52}")
    for k in ("ma20", "ma50", "ma200", "atr14"):
        x = _f(d.get(k))
        if x is not None and x <= 0:
            c.add("indicator_non_positive", "error", f"{k} = {x}", field=k)
    beta = _f(d.get("beta"))
    if beta is not None and not (-3 <= beta <= 6):
        c.add("beta_implausible", "warn", f"Beta {beta}", beta=beta)
    dm = _f(d.get("daily_move_pct"))
    if dm is not None and abs(dm) > 40:
        c.add("daily_move_implausible", "warn", f"Daily move {dm:.1f}%", daily_move_pct=dm)


def rule_live_vs_cached(d: dict, c: _Collector, row: dict | None) -> None:
    """Live quote, cached close and the Signals list row should describe the same stock state."""
    lp, cp = _f(d.get("live_price")), _f(d.get("current_price"))
    if lp and cp and abs(_pct(lp, cp)) > 15:
        c.add("live_vs_cached_price", "warn", f"Live ${lp:.2f} vs cached ${cp:.2f} ({_pct(lp, cp):+.1f}%)",
              live=lp, cached=cp)
    if row is None:
        return
    p = _price(d)
    rp = _f(row.get("current_price") or row.get("price"))
    if p and rp and abs(_pct(rp, p)) > 5:
        c.add("list_vs_detail_price", "warn", f"Signals list price ${rp:.2f} vs page ${p:.2f}", list=rp, detail=p)
    rs, ds = _f(row.get("score")), _f(d.get("score"))
    if rs is not None and ds is not None and abs(rs - ds) > 10:
        c.add("list_vs_detail_score", "warn", f"Signals list score {rs:.0f} vs page {ds:.0f}", list=rs, detail=ds)
    rr, dr = row.get("regime"), d.get("regime")
    if rr and dr and str(rr).upper() != str(dr).upper():
        c.add("list_vs_detail_regime", "warn", f"Signals list regime {rr} vs page {dr}", list=rr, detail=dr)


def rule_entry_state(d: dict, c: _Collector, row: dict | None) -> None:
    """Entry mode, headline, gate flags and the overall verdict must tell one story."""
    ra = _retail(d)
    mode = ra.get("entry_mode")
    gates = ra.get("gates") or []
    if mode and mode not in KNOWN_ENTRY_MODES:
        c.add("entry_mode_unknown", "warn", f"Unknown entry mode {mode}", entry_mode=mode)
    failing = [g.get("id") for g in gates if not g.get("pass")]
    if mode == "full_go" and failing:
        c.add("full_go_with_failing_gate", "error", f"full_go but gates fail: {', '.join(map(str, failing))}",
              failing=failing)
    if mode == "hard_lock" and gates and not failing:
        c.add("locked_with_all_gates_passing", "warn", "Entries locked but every listed gate passes")
    lc = ra.get("gates_locked_count")
    primary = set(ra.get("primary_gate_ids") or [])
    counted = [g for g in failing if g in primary] if primary else failing
    if isinstance(lc, (int, float)) and gates and int(lc) != len(counted):
        c.add("locked_count_mismatch", "warn", f"Says {int(lc)} gates locked, list shows {len(counted)} failing",
              said=lc, listed=len(counted))
    for g in gates:
        if "gate_cleared" in g and bool(g.get("gate_cleared")) != bool(g.get("pass")):
            c.add("gate_flag_mismatch", "warn", f"Gate {g.get('id')}: pass={g.get('pass')} cleared={g.get('gate_cleared')}",
                  gate=g.get("id"))
    headline = str(ra.get("action_title") or ra.get("entry_mode_headline") or "").lower()
    if mode in ("full_go", "starter_only") and "no new entries" in headline:
        c.add("headline_vs_entry_mode", "error", f"Headline '{headline}' but entry mode {mode}")
    if mode == "hard_lock" and headline and not any(w in headline for w in ("no new entries", "hold", "wait", "locked")):
        c.add("headline_vs_entry_mode", "warn", f"Entries locked but headline reads '{headline}'")
    ov = str((d.get("investor_summary") or {}).get("overall_verdict") or "").upper()
    if mode == "hard_lock" and any(ov == w or ov.startswith(w + " ") for w in BUY_WORDS):
        c.add("overall_buy_while_locked", "error", f"Overall verdict {ov} but entries are locked")


def rule_position_advice(d: dict, c: _Collector, row: dict | None) -> None:
    pa = d.get("position_advice") or {}
    if not pa:
        return
    buy, sell = pa.get("buy") or {}, pa.get("sell") or {}
    shares = _f(pa.get("shares")) or 0.0
    if not pa.get("held") and shares > 0:
        c.add("held_flag_mismatch", "error", f"Not marked held but {shares} shares listed")
    pv, val, w = _f(pa.get("portfolio_value")), _f(pa.get("value")), _f(pa.get("weight_pct"))
    if pv and val is not None and w is not None and abs(100 * val / pv - w) > 0.5:
        c.add("weight_mismatch", "warn", f"Weight {w}% but value/portfolio is {100 * val / pv:.2f}%")
    if (_f(buy.get("shares")) or 0) < 0 or (_f(buy.get("dollars")) or 0) < 0:
        c.add("buy_negative", "error", "Buy shares/dollars negative")
    if not buy.get("allowed") and ((_f(buy.get("shares")) or 0) > 0 or buy.get("tranches")):
        c.add("buy_disallowed_but_sized", "error", "Buy not allowed yet shares/tranches are shown")
    cap, nw = _f(pa.get("cap_pct")), _f(buy.get("new_weight_pct"))
    if buy.get("allowed") and cap and nw and nw > cap + 0.5:
        c.add("buy_exceeds_cap", "error", f"Buy takes weight to {nw}% above the {cap}% cap")
    p = _price(d)
    st = _f(buy.get("stop_used"))
    if buy.get("allowed") and st and p and st >= p:
        c.add("sizing_stop_above_price", "error", f"Sizing stop ${st} at/above price ${p}")
    for opt in sell.get("options") or []:
        q = _f(opt.get("shares"))
        if q is not None and (q < 0 or q > shares + 1e-6):
            c.add("sell_shares_invalid", "error", f"Sell option {q} shares vs {shares} held")
    if not pa.get("held") and sell.get("options"):
        c.add("sell_without_holding", "error", "Sell options shown for a stock you don't hold")


def rule_levels_quality(d: dict, c: _Collector, row: dict | None) -> None:
    p = _price(d)
    for h, hv in _horizons(d).items():
        mode = HORIZON_MODE[h]
        levels = [lv for lv in ((hv.get("entry_zone") or {}).get("levels") or []) if _f(lv.get("price"))]
        prices = [round(_f(lv["price"]), 2) for lv in levels if lv.get("role") == "entry"]
        if len(prices) != len(set(prices)):
            c.add("duplicate_levels", "warn", f"{mode} lists the same add price twice", horizon=h)
        timed = sorted((lv for lv in levels if _f(lv.get("touch_pct")) is not None and p and _f(lv["price"]) <= p),
                       key=lambda lv: -_f(lv["price"]))
        for a, b in zip(timed, timed[1:]):
            if _f(b["touch_pct"]) > _f(a["touch_pct"]) + 5:
                c.add("touch_odds_not_monotonic", "warn",
                      f"{mode}: deeper level ${_f(b['price']):.2f} has higher hit odds ({b['touch_pct']}%) than "
                      f"${_f(a['price']):.2f} ({a['touch_pct']}%)", horizon=h)
                break
        for lv in levels:
            ws, yrs, n = lv.get("window_sessions"), _f(lv.get("touch_history_years")), _f(lv.get("touch_sample_n"))
            if ws is not None and ws != WINDOW_BY_HORIZON[h]:
                c.add("touch_window_mismatch", "warn", f"{mode} level uses {ws}-session window", horizon=h)
            if yrs is not None and not (0 < yrs <= 10.5):
                c.add("touch_history_invalid", "error", f"{mode} touch history {yrs} years", horizon=h)
            if n is not None and n < 120 and lv.get("touch_pct") is not None:
                c.add("touch_sample_small", "info", f"{mode} hit odds from only {int(n)} samples", horizon=h)
            if p and _f(lv["price"]) >= p and (_f(lv.get("touch_pct")) or 100) < 100 and lv.get("role") == "entry" \
                    and h != "long" and lv.get("touch_pct") is not None:
                c.add("touch_odds_at_spot", "warn",
                      f"{mode} level ${_f(lv['price']):.2f} is at/above price but shows {lv['touch_pct']}% hit odds",
                      horizon=h)


def rule_stop_target_math(d: dict, c: _Collector, row: dict | None) -> None:
    """Percentages and R:R shown next to stop/target must match the prices."""
    p = _price(d)
    if not p:
        return
    for h, hv in _horizons(d).items():
        mode = HORIZON_MODE[h]
        sl, tg = _f(hv.get("stop_loss")), _f(hv.get("target"))
        slp, tgp, rr = _f(hv.get("stop_loss_pct")), _f(hv.get("target_pct")), _f(hv.get("risk_reward"))
        if sl and slp is not None and abs(_pct(sl, p) - slp) > 1.5:
            c.add("stop_pct_mismatch", "warn", f"{mode} stop {slp}% but ${sl:.2f} vs ${p:.2f} is {_pct(sl, p):.1f}%",
                  horizon=h)
        if tg and tgp is not None and abs(_pct(tg, p) - tgp) > 1.5:
            c.add("target_pct_mismatch", "warn", f"{mode} target {tgp}% but ${tg:.2f} vs ${p:.2f} is {_pct(tg, p):.1f}%",
                  horizon=h)
        if sl and tg and rr and sl < p < tg:
            implied = (tg - p) / (p - sl)
            if abs(implied - rr) > max(0.25, 0.15 * implied):
                c.add("rr_mismatch", "warn", f"{mode} R:R {rr} but stop/target imply {implied:.2f}", horizon=h)
        if sl and sl < p * 0.5:
            c.add("stop_too_far", "warn", f"{mode} stop ${sl:.2f} is {_pct(sl, p):.0f}% below price", horizon=h)
        if tg and h == "short" and tg > p * 1.5:
            c.add("target_too_far", "warn", f"Scout target ${tg:.2f} is {_pct(tg, p):.0f}% above price", horizon=h)


def rule_fair_value(d: dict, c: _Collector, row: dict | None) -> None:
    p = _price(d)
    fv = _f((d.get("investor_summary") or {}).get("fair_value"))
    if fv is None:
        return
    if fv <= 0:
        c.add("fair_value_invalid", "error", f"Fair value ${fv}")
    elif p and (fv > p * 5 or fv < p * 0.2):
        c.add("fair_value_implausible", "warn", f"Fair value ${fv:.2f} vs price ${p:.2f}", fair_value=fv, price=p)


def rule_earnings_calendar(d: dict, c: _Collector, row: dict | None, today: date | None = None) -> None:
    today = today or date.today()
    e = d.get("earnings") or {}
    if not isinstance(e, dict) or not e.get("date"):
        return
    try:
        ed = datetime.strptime(str(e["date"])[:10], "%Y-%m-%d").date()
    except ValueError:
        c.add("earnings_date_unparseable", "warn", f"Earnings date {e.get('date')}")
        return
    du = e.get("days_until")
    if isinstance(du, (int, float)) and abs((ed - today).days - int(du)) > 3:
        c.add("earnings_days_mismatch", "warn", f"Earnings {ed} but says {int(du)} days away", date=str(ed), days_until=du)
    if (ed - today).days > 120:
        c.add("earnings_far_out", "info", f"Next earnings {ed} is {(ed - today).days} days away", date=str(ed))


def audit_track_record(tr: dict, ticker: str, today: date | None = None) -> list[dict[str, Any]]:
    """Track tab: HOLD never scored, ADD/TRIM scored by direction, cumulative maths add up."""
    c = _Collector(ticker)
    if not isinstance(tr, dict) or not tr.get("available", True):
        return c.findings
    today = today or date.today()
    calls = tr.get("daily_calls") or []
    dates = [r.get("date") for r in calls if r.get("date")]
    if len(dates) != len(set(dates)):
        c.add("track_duplicate_days", "error", "Track lists the same call date twice")
    for r in calls:
        sig, ret, right = str(r.get("signal") or "").upper(), _f(r.get("return_pct")), r.get("right")
        if "ADD" not in sig and "TRIM" not in sig and sig not in ("REDUCE", "SELL") and right is not None:
            c.add("track_hold_scored", "error", f"{r.get('date')}: {sig or 'HOLD'} call scored as right={right}",
                  date=r.get("date"))
        if ret is not None and right is not None:
            want = ret > 0 if "ADD" in sig else ret < 0
            if bool(right) != want:
                c.add("track_right_wrong_direction", "error",
                      f"{r.get('date')}: {sig} with {ret:+.2f}% marked right={right}", date=r.get("date"))
        cl, nc = _f(r.get("close")), _f(r.get("next_close"))
        if cl and nc and ret is not None and abs(_pct(nc, cl) - ret) > 0.1:
            c.add("track_return_math", "error", f"{r.get('date')}: return {ret}% but closes imply {_pct(nc, cl):.2f}%",
                  date=r.get("date"))
        if r.get("date") and r.get("next_date") and str(r["next_date"]) <= str(r["date"]):
            c.add("track_next_date_order", "error", f"{r.get('date')}: next date {r.get('next_date')} not after it")
        gp, gt = r.get("gates_passed"), r.get("gates_total")
        if isinstance(gp, int) and isinstance(gt, int) and not (0 <= gp <= gt):
            c.add("track_gate_count_invalid", "error", f"{r.get('date')}: {gp}/{gt} gates")
    for hz, st in (tr.get("by_horizon") or {}).items():
        if not isinstance(st, dict):
            continue
        pct, n, obs = _f(st.get("calls_right_pct")), st.get("calls_n"), st.get("n_observations")
        if pct is not None and not (0 <= pct <= 100):
            c.add("track_pct_out_of_range", "error", f"{hz}d calls right {pct}%")
        if isinstance(n, int) and isinstance(obs, int) and n > obs:
            c.add("track_calls_exceed_obs", "error", f"{hz}d: {n} scored calls but {obs} observations")
        if n == 0 and pct is not None:
            c.add("track_pct_without_calls", "error", f"{hz}d shows {pct}% right with no ADD/TRIM calls")
    lm = tr.get("latest_model_daily") or {}
    m, h, s = _f(lm.get("model_cum_pct")), _f(lm.get("hold_cum_pct")), _f(lm.get("spy_cum_pct"))
    mvh, mvs = _f(lm.get("model_vs_hold_pct")), _f(lm.get("model_vs_spy_pct"))
    if m is not None and h is not None and mvh is not None and abs((m - h) - mvh) > 0.1:
        c.add("track_vs_hold_math", "error", f"Model {m}% − hold {h}% ≠ shown {mvh}%")
    if m is not None and s is not None and mvs is not None and abs((m - s) - mvs) > 0.1:
        c.add("track_vs_spy_math", "error", f"Model {m}% − SPY {s}% ≠ shown {mvs}%")
    if lm.get("days_reduced") == 0 and m is not None and h is not None and abs(m - h) > 0.1:
        c.add("track_model_differs_without_trims", "error", f"No reduced days but model {m}% ≠ hold {h}%")
    last = tr.get("eod_date_last")
    if isinstance(last, str) and len(last) >= 10:
        try:
            age = (today - datetime.strptime(last[:10], "%Y-%m-%d").date()).days
            if age > 4:
                c.add("track_stale", "warn", f"Track data last updated {last[:10]} ({age} days ago)", days=age)
        except ValueError:
            pass
    for t in tr.get("daily_trades") or []:
        sig = str(t.get("signal") or "").upper()
        mp, tg, sl = _f(t.get("model_price")), _f(t.get("target")), _f(t.get("stop"))
        if "BUY" in sig and mp and tg and sl and not (sl < mp < tg):
            c.add("trade_levels_invalid", "warn", f"{t.get('date')} {sig}: stop ${sl} / entry ${mp} / target ${tg}")
    return c.findings


RULES: list[Callable[[dict, _Collector, dict | None], None]] = [
    rule_price_consistency,
    rule_gate_consistency,
    rule_verdict_vs_entry,
    rule_bands,
    rule_stops_targets,
    rule_valuation,
    rule_confidence,
    rule_freshness,
    rule_ranges,
    rule_live_vs_cached,
    rule_entry_state,
    rule_position_advice,
    rule_levels_quality,
    rule_stop_target_math,
    rule_fair_value,
    rule_earnings_calendar,
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
            try:
                import asyncio

                from api.routers.dashboard import get_ticker_track_record

                findings.extend(audit_track_record(asyncio.run(get_ticker_track_record(t)), t))
            except Exception as exc:
                findings.append({"ticker": t, "rule": "track_unavailable", "severity": "info",
                                 "message": f"Track check skipped: {str(exc)[:120]}", "values": {}})
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
