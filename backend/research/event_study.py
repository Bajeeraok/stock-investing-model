"""Event study: average move vs SPY around events, with date-clustered confidence bands.

Day 0 is the first trading day on or after the event date. Filings and reports released
after the close react on day +1, which the window covers. Abnormal return = stock close-to-close
return minus SPY's (SPY itself uses its raw return). Standard errors cluster events that share
a day-0 date, so 50 stocks reacting to one CPI print count as one observation.
"""
from __future__ import annotations

import json
import logging
import math
import time
import urllib.parse
import urllib.request
from typing import Any

import numpy as np
import pandas as pd

from research.dsl import describe, evaluate
from research.features import BENCH, FeatureCache

logger = logging.getLogger(__name__)

MAX_EVENTS = 20000
MAX_TICKERS_REMOTE = 60
FRED_RELEASES = {"cpi": (10, "CPI release"), "jobs": (50, "Jobs report"), "gdp": (53, "GDP release"), "ppi": (46, "PPI release")}


def _r(x, n=3):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, n)


def rule_events(fc: FeatureCache, rule: dict, include_etfs: bool = False, cooldown: int = 20) -> list[tuple]:
    """Day 0 is the session after the signal close, so the move that triggered the rule sits at day -1."""
    p = fc.p
    sig = evaluate(rule, fc) & p.members
    sig = sig & ~sig.shift(1, fill_value=False)
    if not include_etfs:
        sig.loc[:, [t for t in p.etfs if t in sig.columns]] = False
    out = []
    dates = p.close.index
    for t in sig.columns:
        last = -10**9
        for i in np.flatnonzero(sig[t].to_numpy()):
            if i - last >= cooldown and i + 1 < len(dates):
                out.append((t, dates[i + 1], {"signal_date": str(dates[i].date())}))
                last = i
    return out


def edgar_events(tickers: list[str], items: list[str]) -> list[tuple[str, pd.Timestamp, dict]]:
    from signals.edgar_insider import REQUEST_DELAY, SEC_DATA_BASE, _sec_request, get_ticker_to_cik

    want = set(items)
    out = []
    for t, cik in get_ticker_to_cik(tickers[:MAX_TICKERS_REMOTE]).items():
        body, err = _sec_request(f"{SEC_DATA_BASE}/submissions/CIK{cik}.json")
        time.sleep(REQUEST_DELAY)
        if err or not body:
            continue
        rec = (json.loads(body).get("filings") or {}).get("recent") or {}
        for f, d, it in zip(rec.get("form") or [], rec.get("filingDate") or [], rec.get("items") or []):
            codes = {c.strip() for c in (it or "").split(",") if c.strip()}
            if f in ("8-K", "8-K/A") and codes & want:
                out.append((t, pd.Timestamp(d), {"items": sorted(codes & want)}))
    return out


def earnings_events(config: dict, tickers: list[str], kind: str, threshold_pct: float) -> list[tuple[str, pd.Timestamp, dict]]:
    from signals.fmp_client import fetch_earnings_surprises

    out = []
    for t in tickers[:MAX_TICKERS_REMOTE]:
        rows, err = fetch_earnings_surprises(config, t, limit=200)
        for r in rows or []:
            s = r.get("eps_surprise_pct")
            if s is None or not r.get("date"):
                continue
            if (kind == "beat" and s >= threshold_pct) or (kind == "miss" and s <= -threshold_pct) or kind == "any":
                out.append((t, pd.Timestamp(r["date"]), {"surprise_pct": s}))
    return out


def fred_release_dates(config: dict, release: str) -> list[pd.Timestamp]:
    from signals.fred_client import get_api_key

    rid = FRED_RELEASES[release][0]
    key = get_api_key(config)
    if not key:
        raise ValueError("FRED key not configured")
    q = urllib.parse.urlencode({"release_id": rid, "api_key": key, "file_type": "json", "include_release_dates_with_no_data": "false", "limit": 10000})
    with urllib.request.urlopen(f"https://api.stlouisfed.org/fred/release/dates?{q}", timeout=30) as r:
        data = json.loads(r.read())
    return sorted({pd.Timestamp(x["date"]) for x in data.get("release_dates") or []})


def car_study(fc: FeatureCache, events: list[tuple], pre: int = 5, post: int = 20) -> dict[str, Any]:
    p = fc.p
    if not 0 <= pre <= 20 or not 1 <= post <= 60:
        raise ValueError("window: pre 0-20, post 1-60 days")
    C = p.close
    rets = C.pct_change(fill_method=None)
    cols = {t: i for i, t in enumerate(C.columns)}
    R = rets.to_numpy(dtype=float)
    spy = R[:, cols[BENCH]] if BENCH in cols else np.zeros(len(C))
    dates = C.index
    events = sorted(events, key=lambda e: (e[1], e[0]))
    if len(events) > MAX_EVENTS:
        step = len(events) / MAX_EVENTS
        events = [events[int(i * step)] for i in range(MAX_EVENTS)]
    W = pre + post + 1
    paths, d0s, used = [], [], []
    for ev in events:
        t, d = ev[0], ev[1]
        j = cols.get(t)
        if j is None:
            continue
        i0 = int(dates.searchsorted(d))
        if i0 - pre < 1 or i0 + post >= len(dates):
            continue
        r = R[i0 - pre:i0 + post + 1, j]
        if np.isnan(r).sum() > 2:
            continue
        ar = np.nan_to_num(r) - (0 if t == BENCH else np.nan_to_num(spy[i0 - pre:i0 + post + 1]))
        paths.append(np.cumsum(ar) * 100)
        d0s.append(i0)
        used.append((t, dates[i0], ev[2] if len(ev) > 2 else {}))
    if not paths:
        return {"n_events": 0, "message": "no events with enough price history"}
    P = np.vstack(paths)
    g = pd.DataFrame(P).groupby(np.asarray(d0s)).mean()
    k = len(g)
    mean = g.mean().to_numpy()
    se = g.std(ddof=1).to_numpy() / np.sqrt(k) if k > 1 else np.full(W, np.nan)
    days = list(range(-pre, post + 1))

    def at(day: int) -> dict[str, Any]:
        c = days.index(day)
        col = P[:, c] - (P[:, days.index(-1)] if -1 in days and day >= 0 else 0)
        gc = pd.Series(col).groupby(np.asarray(d0s)).mean()
        m, s = gc.mean(), gc.std(ddof=1) / math.sqrt(len(gc)) if len(gc) > 1 else float("nan")
        return {"day": day, "mean": _r(m, 2), "t": _r(m / s if s and s > 0 else None, 2), "pct_positive": _r((col > 0).mean() * 100, 1), "n": int(len(col))}

    ys = pd.Series([u[1].year for u in used])
    return {
        "n_events": int(len(P)), "n_dates": int(k), "days": days,
        "mean": [_r(v, 3) for v in mean],
        "lo": [_r(v, 3) for v in mean - 1.96 * se], "hi": [_r(v, 3) for v in mean + 1.96 * se],
        "from_day_minus1": [at(d) for d in (0, 1, 5, 10, post) if d <= post],
        "by_year": [{"year": int(y), "n": int(n)} for y, n in ys.value_counts().sort_index().items()],
        "events": [{"ticker": t, "date": str(d.date()), **{k2: v for k2, v in (m or {}).items()}} for t, d, m in used[-2000:][::-1]],
        "note": "Cumulative return vs SPY from day -%d. Day-N stats measure from the day -1 close (the reaction)." % pre,
    }


def run(fc: FeatureCache, config: dict, source: str, *, rule: dict | None = None, tickers: list[str] | None = None,
        items: list[str] | None = None, kind: str = "any", threshold_pct: float = 5.0, release: str = "cpi",
        pre: int = 5, post: int = 20, include_etfs: bool = False) -> dict[str, Any]:
    tickers = [t.upper() for t in (tickers or []) if t]
    if source == "rule":
        if not rule:
            raise ValueError("rule required")
        ev = rule_events(fc, rule, include_etfs)
        if tickers:
            ev = [e for e in ev if e[0] in set(tickers)]
        label = "Rule turns on: " + describe(rule)
    elif source == "8k":
        if not tickers or not items:
            raise ValueError("8-K study needs tickers and item codes")
        ev = edgar_events(tickers, items)
        label = "8-K items " + ", ".join(items)
    elif source == "earnings":
        if not tickers:
            raise ValueError("earnings study needs tickers")
        ev = earnings_events(config, tickers, kind, float(threshold_pct))
        label = f"Earnings {kind}" + (f" ≥{threshold_pct}% surprise" if kind != "any" else "")
    elif source == "macro":
        if release not in FRED_RELEASES:
            raise ValueError(f"release must be one of {sorted(FRED_RELEASES)}")
        ds = fred_release_dates(config, release)
        tickers = tickers or [BENCH]
        ev = [(t, d) for d in ds for t in tickers]
        label = FRED_RELEASES[release][1] + " days"
    else:
        raise ValueError("source must be rule, 8k, earnings or macro")
    out = car_study(fc, ev, pre, post)
    out.update({"source": source, "label": label, "params": {"pre": pre, "post": post, "tickers": tickers[:MAX_TICKERS_REMOTE], "items": items, "kind": kind, "threshold_pct": threshold_pct, "release": release}})
    if source in ("8k", "earnings") and len(tickers) > MAX_TICKERS_REMOTE:
        out["warning"] = f"only the first {MAX_TICKERS_REMOTE} tickers were checked"
    return out
