"""
Live tracking of the post-earnings range: at 3:50 PM ET, log the forecast for every stock whose
report lands before the next close (after-close today, or before-open next session); after the
reaction close, score it. File: DATA_ROOT/earnings_log.json. Display only — never feeds a signal.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _path():
    from config_loader import get_data_root

    return get_data_root() / "earnings_log.json"


def _load() -> dict:
    p = _path()
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=str))
    tmp.replace(p)


def pre_close_date(report_ts) -> date | None:
    """Session whose close is the 'before' price for this report."""
    from signals.earnings_move import _naive, report_timing

    t, when = _naive(report_ts), report_timing(report_ts)
    if when == "amc":
        return t.date()
    if when == "bmo":
        return (t.normalize() - pd.offsets.BDay(1)).date()
    return None


def build_entry(ticker: str, report_ts, close: pd.Series, earnings_dates, now: datetime) -> dict | None:
    from signals.earnings_move import _naive, forecast, options_implied_move, report_timing

    price = float(close.dropna().iloc[-1])
    f = forecast(close, earnings_dates, price)
    if not f:
        return None
    f.pop("history", None)
    return {
        "ticker": ticker, "report": _naive(report_ts).isoformat(), "timing": report_timing(report_ts),
        "pre_date": pre_close_date(report_ts).isoformat(), "price_at_log": round(price, 2),
        "typical_move_pct": f["typical_move_pct"], "move50_pct": f["move50_pct"], "move80_pct": f["move80_pct"],
        "options": options_implied_move(ticker, report_ts, price), "logged_at": now.isoformat(timespec="seconds"),
    }


def log_upcoming(config: dict, *, tickers: list[str] | None = None, now: datetime | None = None) -> int:
    from config_loader import get_dashboard_signal_universe
    from signals.earnings_move import next_report
    from signals.time_et import now_et

    now = now or now_et()
    today = now.date()
    data = _load()
    universe = [t for t in (tickers or get_dashboard_signal_universe(config)) if not t.endswith("-USD")]

    def _one(t: str):
        try:
            import yfinance as yf

            tk = yf.Ticker(t)
            ed = tk.get_earnings_dates(limit=8)
            nr = next_report(ed, now)
            if nr is None or pre_close_date(nr) != today:
                return None
            key = f"{t}|{pd.Timestamp(nr).date().isoformat()}"
            if key in data:
                return None
            close = tk.history(period="2y", auto_adjust=False)["Close"]
            e = build_entry(t, nr, close, ed, now)
            return (key, e) if e else None
        except Exception as e:
            logger.debug("earnings_log %s failed: %s", t, e)
            return None

    n = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(_one, universe):
            if res:
                data[res[0]] = res[1]
                n += 1
    if n:
        _save(data)
    return n


def score_entry(e: dict, pre_close: float, react_close: float) -> dict:
    m = (react_close / pre_close - 1) * 100
    opt = (e.get("options") or {}).get("move_pct")
    return {
        "pre_close": round(pre_close, 2), "react_close": round(react_close, 2), "actual_move_pct": round(m, 2),
        "in50": abs(m) <= e["move50_pct"], "in80": abs(m) <= e["move80_pct"],
        "in_options": None if opt is None else abs(m) <= opt,
        "size_err_pct": round(abs(abs(m) - e["typical_move_pct"]), 2),
    }


def score_pending(*, now: datetime | None = None) -> int:
    from signals.earnings_move import _naive
    from signals.time_et import now_et

    now = now or now_et()
    data = _load()
    n = 0
    for e in data.values():
        if e.get("scored") or e.get("pre_date", "9999") >= now.date().isoformat():
            continue
        try:
            import yfinance as yf

            h = yf.Ticker(e["ticker"]).history(start=e["pre_date"], auto_adjust=False)["Close"].dropna()
            days = [_naive(x).date().isoformat() for x in h.index]
            if len(days) < 2 or days[0] != e["pre_date"]:
                continue
            if days[1] == now.date().isoformat() and now.hour < 16:
                continue
            e["scored"] = score_entry(e, float(h.iloc[0]), float(h.iloc[1]))
            n += 1
        except Exception as ex:
            logger.debug("earnings_log score %s failed: %s", e.get("ticker"), ex)
    if n:
        _save(data)
    return n


def _rate(rows: list[dict], k: str) -> float | None:
    v = [r["scored"][k] for r in rows if r["scored"].get(k) is not None]
    return round(sum(v) / len(v) * 100) if v else None


def ticker_record(ticker: str) -> dict[str, Any] | None:
    data = _load()
    if not data:
        return None
    mine = sorted((e for e in data.values() if e.get("ticker") == ticker.upper()), key=lambda e: e["report"])
    scored = [e for e in data.values() if e.get("scored")]
    return {
        "rows": mine[-8:],
        "all": {"scored": len(scored), "in50_pct": _rate(scored, "in50"), "in80_pct": _rate(scored, "in80"),
                "in_options_pct": _rate(scored, "in_options")},
    }
