"""
Options-market context for the day-range card (display only): the expected move priced by the
nearest-expiry ATM straddle, and the open-interest "walls" (strikes with the most call / put OI).
Yahoo option data is delayed and OI updates once a day; nothing here feeds BUY/HOLD/SELL.
"""
from __future__ import annotations

import math
import time
from datetime import date, timedelta
from typing import Any

MEAN_ABS_PER_SD = math.sqrt(2 / math.pi)  # straddle ≈ E|move| ≈ 0.798 σ√T
WALL_EXPIRY_DAYS = 30
WALL_MAX_CHAINS = 4
WALL_BAND = 0.20
WALL_MIN_OI = 500
TTL_S = 900
_CACHE: dict[str, tuple[float, dict | None]] = {}


def sessions_between(start: date, end: date) -> int:
    """Weekday sessions from start through end inclusive (holidays ignored)."""
    n, d = 0, start
    while d <= end:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


def _mid(row) -> float | None:
    b, a, last = float(row["bid"]), float(row["ask"]), float(row["lastPrice"])
    if b > 0 and a > 0 and a >= b:
        return (a + b) / 2
    return last if last > 0 else None


def straddle_sd(calls, puts, price: float) -> tuple[float, float] | None:
    """(σ over the life of the expiry as a fraction of price, ATM strike) from the ATM call+put mid."""
    if calls is None or puts is None or calls.empty or puts.empty or price <= 0:
        return None
    common = sorted(set(calls["strike"]) & set(puts["strike"]), key=lambda k: abs(k - price))
    if not common:
        return None
    k = common[0]
    cm, pm = _mid(calls[calls.strike == k].iloc[0]), _mid(puts[puts.strike == k].iloc[0])
    if not cm or not pm:
        return None
    # ITM leg carries intrinsic value; remove it so the straddle measures the move only.
    extrinsic = cm + pm - abs(price - k)
    if extrinsic <= 0:
        return None
    return extrinsic / price / MEAN_ABS_PER_SD, float(k)


def oi_walls(chains: list[tuple[Any, Any]], price: float) -> dict[str, Any]:
    """Strike with the most call OI above price and most put OI below it (within ±20%), summed over chains."""
    calls: dict[float, float] = {}
    puts: dict[float, float] = {}
    for c, p in chains:
        for df, acc in ((c, calls), (p, puts)):
            for k, oi in zip(df["strike"], df["openInterest"].fillna(0)):
                acc[float(k)] = acc.get(float(k), 0.0) + float(oi)
    out: dict[str, Any] = {}
    up = {k: v for k, v in calls.items() if price < k <= price * (1 + WALL_BAND)}
    dn = {k: v for k, v in puts.items() if price * (1 - WALL_BAND) <= k < price}
    if up and max(up.values()) >= WALL_MIN_OI:
        k = max(up, key=up.get)
        out.update(call_wall=k, call_wall_oi=int(up[k]))
    if dn and max(dn.values()) >= WALL_MIN_OI:
        k = max(dn, key=dn.get)
        out.update(put_wall=k, put_wall_oi=int(dn[k]))
    return out


def fetch(t, ticker: str, price: float, session_day: date, *, now_day: date) -> dict | None:
    """Nearest expiry on/after session_day → straddle σ; OI walls over the next 30 days. 15-min cache."""
    hit = _CACHE.get(ticker)
    if hit and time.time() - hit[0] < TTL_S:
        return hit[1]
    out: dict | None = None
    try:
        exps = [date.fromisoformat(e) for e in (t.options or ())]
        first = next((e for e in exps if e >= session_day), None)
        if first is not None and (first - session_day).days <= 10:
            ch = t.option_chain(first.isoformat())
            sd = straddle_sd(ch.calls, ch.puts, price)
            chains = [(ch.calls, ch.puts)]
            for e in [e for e in exps if first < e <= now_day + timedelta(days=WALL_EXPIRY_DAYS)][:WALL_MAX_CHAINS - 1]:
                c2 = t.option_chain(e.isoformat())
                chains.append((c2.calls, c2.puts))
            out = {"expiry": first.isoformat(), **oi_walls(chains, price)}
            if sd:
                out.update(sd_to_expiry=sd[0], strike=sd[1], ref_price=round(price, 2))
    except Exception:
        out = None
    _CACHE[ticker] = (time.time(), out)
    return out


def day_range_fields(opt: dict | None, anchor: float, *, session_day: date, live_left: float | None) -> dict[str, Any]:
    """Options 80% close range for the forecast session, comparable with our own 80% band.
    σ to expiry is spread evenly over the sessions left (an earnings day inside the window is understated)."""
    if not opt or not opt.get("sd_to_expiry") or anchor <= 0:
        return {}
    exp = date.fromisoformat(opt["expiry"])
    later = sessions_between(session_day + timedelta(days=1), exp)
    today = live_left if live_left is not None else 1.0
    if today <= 0:
        return {}
    sd = opt["sd_to_expiry"] * math.sqrt(today / (today + later))
    z80 = 1.2816
    return {
        "opt_sd_pct": round(sd * 100, 2),
        "opt_low80": round(anchor * math.exp(-z80 * sd), 2),
        "opt_high80": round(anchor * math.exp(z80 * sd), 2),
        "opt_expiry": opt["expiry"],
    }


def wall_levels(opt: dict | None) -> list[dict[str, Any]]:
    if not opt:
        return []
    out = []
    if opt.get("call_wall"):
        out.append({"label": f"Options call wall ({opt['call_wall_oi']:,} OI)", "price": opt["call_wall"]})
    if opt.get("put_wall"):
        out.append({"label": f"Options put wall ({opt['put_wall_oi']:,} OI)", "price": opt["put_wall"]})
    return out
