"""Investor rulebook: well-known investor/institutional rules mapped to Thrive Alpha, with live hits.

Each rule says how the model applies it:
  in_model  — already drives a gate, stop or cap.
  highlight — shown as a flag only; never changes BUY/HOLD/SELL (needs a backtest + owner OK first).
  habit     — a process rule for the investor; no live check.
Hits are computed from the cached signals-panel rows and macro factors. Educational, not advice.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

Row = dict[str, Any]


def _f(v: Any) -> float | None:
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _px(r: Row) -> float | None:
    return _f(r.get("live_price")) or _f(r.get("price")) or _f(r.get("close"))


def _gate(r: Row, gid: str) -> dict | None:
    for g in (r.get("retail_status") or {}).get("gates") or []:
        if isinstance(g, dict) and g.get("id") == gid:
            return g
    return None


def _model_fv(r: Row) -> float | None:
    fv = _f(r.get("fair_value"))
    meth = str(r.get("fair_value_method") or "")
    if not fv or r.get("fair_value_suppressed") or meth.startswith("Analyst") or "COMMODITY" in meth:
        return None
    return fv


def _pct(a: float, b: float) -> float:
    return (a / b - 1.0) * 100.0


# ── ticker checks: return a short detail string when the rule is hit ─────────────────

def _hit_margin_of_safety(r: Row) -> str | None:
    g = _gate(r, "valuation")
    return (g.get("detail") or "Valuation gate passes") if g and g.get("pass") else None


def _hit_trend_template(r: Row) -> str | None:
    p, m50, m200, dd = _px(r), _f(r.get("ma50")), _f(r.get("ma200")), _f(r.get("drawdown_52w"))
    if p and m50 and m200 and p > m50 > m200 and dd is not None and dd >= -25:
        return f"Above 50-day ${m50:,.2f} > 200-day ${m200:,.2f}, {abs(dd):.0f}% off the high"
    return None


def _hit_fat_pitch(r: Row) -> str | None:
    if r.get("gate_cleared"):
        return f"All {r.get('gates_total') or 5} gates clear"
    return None


def _hit_quality_dip(r: Row) -> str | None:
    g = _gate(r, "valuation")
    dd = _f(r.get("drawdown_52w"))
    if g and g.get("pass") and dd is not None and dd <= -20:
        return f"Valuation gate passes, {abs(dd):.0f}% below the 52-week high"
    return None


def _hit_below_200d(r: Row) -> str | None:
    p, m200 = _px(r), _f(r.get("ma200"))
    if p and m200 and p < m200:
        return f"{_pct(p, m200):+.1f}% vs 200-day ${m200:,.2f}"
    return None


def _hit_falling_knife(r: Row) -> str | None:
    from signals.readiness_score import is_falling_knife

    if not is_falling_knife(r):
        return None
    sc, rsi = _f(r.get("composite_buy")), _f(r.get("rsi"))
    bits = ["Own trend DOWN"]
    if sc is not None:
        bits.append(f"score {sc:.0f}")
    if rsi is not None:
        bits.append(f"RSI {rsi:.0f}")
    return ", ".join(bits)


def _hit_earnings(r: Row) -> str | None:
    d = r.get("earnings_days_until")
    if isinstance(d, (int, float)) and 0 <= d <= 5:
        return "Earnings today" if d == 0 else f"Earnings in {int(d)} day{'s' if d != 1 else ''}"
    return None


def _hit_overextended(r: Row) -> str | None:
    p, m200, rsi = _px(r), _f(r.get("ma200")), _f(r.get("rsi"))
    bits = []
    if p and m200 and p >= 1.25 * m200:
        bits.append(f"{_pct(p, m200):+.0f}% above 200-day")
    if rsi is not None and rsi >= 75:
        bits.append(f"RSI {rsi:.0f}")
    return " · ".join(bits) or None


def _hit_rich_vs_value(r: Row) -> str | None:
    p, fv = _px(r), _model_fv(r)
    if p and fv and p >= 1.2 * fv:
        return f"{_pct(p, fv):+.0f}% vs model fair value ${fv:,.2f}"
    return None


def _hit_distribution(r: Row) -> str | None:
    p, m50, vr, ch = _px(r), _f(r.get("ma50")), _f(r.get("volume_ratio")), _f(r.get("change_pct"))
    if p and m50 and p < m50 and vr is not None and vr >= 1.5 and ch is not None and ch < 0:
        return f"Down {ch:.1f}% below the 50-day on {vr:.1f}× normal volume"
    return None


def _hit_story_change(r: Row) -> str | None:
    s = r.get("story_change")
    return str(s).replace("HORIZON SHIFT: ", "Plan changed: ") if s else None


def _hit_sec_8k(r: Row) -> str | None:
    ev = [e for e in (r.get("sec_8k") or []) if e.get("story")]
    if not ev:
        return None
    e = ev[0]
    labels = [lab for lab, c in zip(e.get("labels") or [], [c for c in e.get("items") or [] if c != "9.01"]) if c in e["story"]]
    more = f" (+{len(ev) - 1} more)" if len(ev) > 1 else ""
    return f"{'SEVERE · ' if any(x.get('severe') for x in ev) else ''}8-K {e.get('date')}: {', '.join(labels) or 'material event'}{more}"


# ── market checks: (market dict) -> detail or None ────────────────────────────────────

def _m_fear(m: dict) -> str | None:
    vix, dd = _f(m.get("vix")), _f(m.get("spy_drawdown_52w"))
    bits = []
    if vix is not None and vix >= 30:
        bits.append(f"VIX {vix:.1f}")
    if dd is not None and dd <= -10:
        bits.append(f"SPY {dd:.0f}% off its high")
    return " · ".join(bits) or None


def _m_complacency(m: dict) -> str | None:
    vix = _f(m.get("vix"))
    return f"VIX {vix:.1f}" if vix is not None and vix <= 13 else None


def _m_spy_200(m: dict) -> str | None:
    p, m200 = _f(m.get("spy_price")), _f(m.get("spy_ma200"))
    if p and m200 and p < m200:
        return f"SPY ${p:,.2f} is {_pct(p, m200):+.1f}% vs its 200-day ${m200:,.2f}"
    return None


def _m_curve(m: dict) -> str | None:
    yc = _f(m.get("yield_curve_2s10s"))
    return f"10y − 2y = {yc:+.2f} pts" if yc is not None and yc < 0 else None


def _m_credit(m: dict) -> str | None:
    hy = _f(m.get("hy_oas_bp"))
    if hy is None:
        return None
    pct = hy / 100.0 if hy > 30 else hy  # FRED series is in percent; tolerate bp
    return f"High-yield spread {pct:.1f}%" if pct >= 5.0 else None


RULES: list[dict[str, Any]] = [
    # Buy / add
    {"id": "margin_of_safety", "group": "buy", "who": "Benjamin Graham · Warren Buffett",
     "rule": "Buy only at a clear discount to what the business is worth.",
     "applied": "in_model", "how": "Valuation gate: price must sit well below the model's long-term value band before adds unlock.",
     "evidence": "Core gate since launch; scored in the Loss check.", "check": _hit_margin_of_safety},
    {"id": "fat_pitch", "group": "buy", "who": "Warren Buffett (Ted Williams' 'fat pitch')",
     "rule": "Wait for the pitch you want. Act only when everything lines up.",
     "applied": "in_model", "how": "Full-size entries need every gate cleared; otherwise HOLD/AVOID is the default.",
     "evidence": "Signal rule: 'When unsure, don't buy'.", "check": _hit_fat_pitch},
    {"id": "trend_template", "group": "buy", "who": "William O'Neil · Mark Minervini",
     "rule": "Buy leaders in uptrends: price above a rising 50-day, 50-day above 200-day, near the highs.",
     "applied": "in_model", "how": "Trend weather + momentum gates; Swing entries only on uptrend pullbacks.",
     "evidence": "Swing stop/target tuned on 2014–26 uptrend entries.", "check": _hit_trend_template},
    {"id": "quality_dip", "group": "buy", "who": "Peter Lynch · Shelby Davis",
     "rule": "Great companies on temporary sell-offs are where long-term gains come from. Buy in stages.",
     "applied": "highlight", "how": "Flag only: valuation passes and the stock is 20%+ off its high. Owner band handles staging.",
     "evidence": "Not a gate. Dip-timing on its own showed no edge for index funds.", "check": _hit_quality_dip},
    {"id": "fear_buy", "group": "market", "who": "Warren Buffett · John Templeton",
     "rule": "Be greedy when others are fearful. The best buys come at maximum pessimism.",
     "applied": "highlight", "how": "Market flag: VIX ≥ 30 or SPY 10%+ off its high. Buy core index in stages; single stocks still need their gates.",
     "evidence": "Our CBOE put/call test (2006–19): fear spikes were followed by above-normal 20-day returns.", "market_check": _m_fear},
    # Risk / avoid
    {"id": "below_200d", "group": "risk", "who": "Paul Tudor Jones",
     "rule": "Nothing good happens below the 200-day moving average. Play defense.",
     "applied": "in_model", "how": "Trend weather gate blocks adds; Protect mode halves exposure below the 200-day.",
     "evidence": "2000–26 S&P 500: worst drop −66% → −52% for ~1.5%/yr less return.", "check": _hit_below_200d},
    {"id": "spy_below_200d", "group": "market", "who": "Paul Tudor Jones · Meb Faber",
     "rule": "When the index itself is below its 200-day, cut risk and raise cash.",
     "applied": "in_model", "how": "Market regime feeds every gate; full-go overrides are off in a bear tape.",
     "evidence": "Same 200-day study as Protect mode.", "market_check": _m_spy_200},
    {"id": "falling_knife", "group": "risk", "who": "Jesse Livermore · Mark Minervini",
     "rule": "Never average down into a broken trend. Wait for the stock to stop falling.",
     "applied": "in_model", "how": "Same falling-knife flag the model uses: own trend DOWN with a weak score (or RSI < 30). It can never be 'almost ready', and adds stay locked until the trend gate flips.",
     "evidence": "Added after oversold bounces promoted weak downtrends (e.g. IREN). Trend weather is the top blocker weight.", "check": _hit_falling_knife},
    {"id": "earnings_binary", "group": "risk", "who": "Stanley Druckenmiller · institutional risk desks",
     "rule": "Shrink size before binary events. Don't bet the position on one report.",
     "applied": "in_model", "how": "Earnings caution window: smaller starter size and wider odds around the report.",
     "evidence": "Event strip calibrates expected moves on past earnings.", "check": _hit_earnings},
    {"id": "stop_first", "group": "risk", "who": "William O'Neil · Paul Tudor Jones",
     "rule": "Cut every loss small (O'Neil: 7–8% max). Decide the exit before you enter.",
     "applied": "in_model", "how": "Every BUY has a stop and max loss fixed at entry; stops are never widened.",
     "evidence": "Signal rule #1: no open-ended losses."},
    {"id": "position_cap", "group": "risk", "who": "Ray Dalio · hedge-fund risk limits",
     "rule": "No single bet big enough to hurt you. Spread risk across uncorrelated holdings.",
     "applied": "in_model", "how": "Position caps 15/20/25% by risk profile, 1% book risk per trade (Portfolio Doctor + sizing card).",
     "evidence": "Portfolio Doctor flags positions over the cap."},
    {"id": "credit_stress", "group": "market", "who": "Howard Marks",
     "rule": "Watch the credit cycle. When lenders get scared, stocks follow.",
     "applied": "highlight", "how": "Market flag: high-yield spread ≥ 5%. Feeds the macro score; no gate of its own.",
     "evidence": "Macro score uses HY spread; no standalone backtest.", "market_check": _m_credit},
    {"id": "yield_curve", "group": "market", "who": "Ray Dalio · Campbell Harvey",
     "rule": "An inverted yield curve has preceded most US recessions. Prepare, don't predict.",
     "applied": "highlight", "how": "Market flag: 10y yield below 2y. Feeds the macro score; no gate of its own.",
     "evidence": "Lead time has ranged from months to 2 years, so it's a warning, not a timer.", "market_check": _m_curve},
    # Trim
    {"id": "overextended", "group": "trim", "who": "William O'Neil · Mark Minervini",
     "rule": "Sell into strength when a stock runs far above its averages (climax run).",
     "applied": "in_model", "how": "Trim extension gate (RSI ≥ 65 or rich vs long-term band) + 2 of 4 trim gates. Flag here: 25%+ above 200-day or RSI ≥ 75.",
     "evidence": "Forward tracking: 3/4-gate trims helped 60% of the time.", "check": _hit_overextended},
    {"id": "rich_vs_value", "group": "trim", "who": "Warren Buffett · Howard Marks",
     "rule": "Price is what you pay, value is what you get. Trim when price runs well past value.",
     "applied": "in_model", "how": "Valuation blocks adds above fair value; flag here: 20%+ above the model's own fair value (Wall St fallbacks excluded).",
     "evidence": "BLK 2012–26: >10% above fair value → next 12 months averaged +2%.", "check": _hit_rich_vs_value},
    {"id": "distribution", "group": "trim", "who": "William O'Neil",
     "rule": "Heavy-volume drops through key averages mean big holders are selling.",
     "applied": "highlight", "how": "Flag only: down day below the 50-day on 1.5×+ normal volume.",
     "evidence": "Not tested in our data yet.", "check": _hit_distribution},
    {"id": "story_change", "group": "trim", "who": "Peter Lynch",
     "rule": "Sell when the story changes, not when the price wiggles.",
     "applied": "in_model", "how": "Plan change alerts when a horizon's playbook flips; review the thesis before acting.",
     "evidence": "Story-change log in What changed.", "check": _hit_story_change},
    {"id": "sec_8k_story", "group": "trim", "who": "Peter Lynch · SEC filings",
     "rule": "A material filing can change the story before the price does.",
     "applied": "highlight", "how": "Flag only: an 8-K in the last 7 days with a story item (officer change, restructuring, impairment, deal closed, auditor change, restatement, delisting). Read the filing before acting.",
     "evidence": "Not tested in our data yet; event categories need an event study before any gate.", "check": _hit_sec_8k},
    {"id": "complacency", "group": "market", "who": "Howard Marks",
     "rule": "When everyone is carefree, be cautious. Low fear means low margin for error.",
     "applied": "highlight", "how": "Market flag: VIX ≤ 13. Tighten adds, don't sell on this alone.",
     "evidence": "Our put/call test: complacency in up markets was followed by below-normal returns.", "market_check": _m_complacency},
    # Habits
    {"id": "index_core", "group": "habit", "who": "John Bogle · Warren Buffett",
     "rule": "Make a low-cost index fund the core. Most stock pickers trail it over 10+ years.",
     "applied": "habit", "how": "Prefer-SPY verdict when a stock's edge isn't proven; SPY/QQQ in the watchlist.",
     "evidence": "S&P SPIVA scorecards."},
    {"id": "dca", "group": "habit", "who": "Benjamin Graham · John Bogle",
     "rule": "Invest on a schedule. Time in the market beats timing the market.",
     "applied": "habit", "how": "Smart DCA panel; our 2000–26 test found DCA beat waiting for dips.",
     "evidence": "Index-entry backtest SPY/QQQ 2000–26."},
    {"id": "rebalance", "group": "habit", "who": "David Swensen (Yale endowment)",
     "rule": "Rebalance back to target weights on a schedule. It trims winners without guessing.",
     "applied": "habit", "how": "Portfolio Doctor shows drift vs your caps; act once or twice a year.",
     "evidence": "Standard endowment practice."},
    {"id": "written_plan", "group": "habit", "who": "Paul Tudor Jones · Ed Seykota",
     "rule": "Write the plan before the trade: entry, stop, target, size. Then follow it.",
     "applied": "habit", "how": "Every ticker page gives the plan; the Journal records what you did.",
     "evidence": "Decision journal + Track tab score every call, losers included."},
]

GROUPS = [
    {"id": "buy", "label": "When to buy"},
    {"id": "risk", "label": "Risk and when to stay out"},
    {"id": "trim", "label": "When to trim"},
    {"id": "market", "label": "Market events"},
    {"id": "habit", "label": "Habits"},
]


def market_inputs(rows: list[Row], factors: dict | None) -> dict[str, Any]:
    spy = next((r for r in rows if str(r.get("ticker")).upper() == "SPY"), {}) or {}
    f = factors or {}
    return {
        "vix": f.get("vix"),
        "yield_curve_2s10s": f.get("yield_curve_2s10s"),
        "hy_oas_bp": f.get("hy_oas_bp"),
        "spy_price": _px(spy) if spy else None,
        "spy_ma200": spy.get("ma200"),
        "spy_drawdown_52w": spy.get("drawdown_52w"),
    }


def evaluate_rules(
    rows: list[Row],
    market: dict[str, Any],
    *,
    first_seen: dict[str, str] | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    """Return the rulebook with live hits. ``first_seen`` maps 'rule:TICKER' → date and is updated in place."""
    seen = first_seen if first_seen is not None else {}
    today = today or datetime.now().strftime("%Y-%m-%d")
    live: set[str] = set()
    out_rules: list[dict[str, Any]] = []
    for rule in RULES:
        hits: list[dict[str, Any]] = []
        check: Callable[[Row], str | None] | None = rule.get("check")
        mcheck: Callable[[dict], str | None] | None = rule.get("market_check")
        if check:
            for r in rows:
                t = str(r.get("ticker") or "").upper()
                if not t:
                    continue
                try:
                    d = check(r)
                except Exception as e:  # one bad row never breaks the page
                    logger.debug("rule %s %s: %s", rule["id"], t, e)
                    d = None
                if d:
                    hits.append({"ticker": t, "detail": d})
        elif mcheck:
            d = mcheck(market)
            if d:
                hits.append({"ticker": "MARKET", "detail": d})
        for h in hits:
            k = f"{rule['id']}:{h['ticker']}"
            live.add(k)
            seen.setdefault(k, today)
            h["since"] = seen[k]
            h["new"] = seen[k] == today
        hits.sort(key=lambda h: (not h["new"], h["ticker"]))
        out_rules.append({
            **{k: v for k, v in rule.items() if k not in ("check", "market_check")},
            "live": bool(check or mcheck),
            "hits": hits,
            "hit_count": len(hits),
            "new_count": sum(1 for h in hits if h["new"]),
        })
    for k in [k for k in seen if k not in live]:
        seen.pop(k, None)  # a rule that stops hitting starts fresh next time
    return {
        "groups": GROUPS,
        "rules": out_rules,
        "market": market,
        "n_tickers": len(rows),
        "new_total": sum(r["new_count"] for r in out_rules),
    }


def rules_for_ticker(payload: dict[str, Any], ticker: str) -> list[dict[str, Any]]:
    t = ticker.upper()
    out = []
    for r in payload.get("rules") or []:
        for h in r.get("hits") or []:
            if h.get("ticker") == t:
                out.append({"id": r["id"], "group": r["group"], "who": r["who"], "rule": r["rule"],
                            "applied": r["applied"], "detail": h["detail"], "new": h.get("new"), "since": h.get("since")})
    return out
