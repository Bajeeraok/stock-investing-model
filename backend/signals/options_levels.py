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


GAMMA_BAND = 0.15
GAMMA_TOP = 3
PLACEBO_SHIFT = 0.35


def bs_gamma(s: float, k: float, t: float, iv: float) -> float:
    if s <= 0 or k <= 0 or t <= 0 or iv <= 0:
        return 0.0
    v = iv * math.sqrt(t)
    d1 = (math.log(s / k) + 0.5 * iv * iv * t) / v
    return math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) / (s * v)


def gamma_levels(chains: list[tuple[Any, Any, float]], price: float) -> dict[str, Any]:
    """Dealer-gamma levels (calls +, puts −; the usual dealer-positioning assumption):
    gamma_flip = spot where total gamma exposure changes sign nearest price (the "Apex");
    gamma_strikes = strikes with the largest |exposure| within ±15%. Logged for tracking only."""
    rows = []
    for c, p, t in chains:
        t = max(t, 0.5 / 252)
        for df, sign in ((c, 1.0), (p, -1.0)):
            if df is None or df.empty or "impliedVolatility" not in df:
                continue
            for k, oi, iv in zip(df["strike"], df["openInterest"].fillna(0), df["impliedVolatility"].fillna(0)):
                k, oi, iv = float(k), float(oi), float(iv)
                if oi > 0 and 0.01 < iv < 5 and abs(k / price - 1) <= 0.25:
                    rows.append((k, t, iv, sign * oi))
    if not rows:
        return {}
    def total(s: float) -> float:
        return sum(w * bs_gamma(s, k, t, iv) * s * s for k, t, iv, w in rows)
    grid = [price * (1 - GAMMA_BAND + i * 2 * GAMMA_BAND / 120) for i in range(121)]
    vals = [total(s) for s in grid]
    flips = [grid[i] - vals[i] * (grid[i + 1] - grid[i]) / (vals[i + 1] - vals[i])
             for i in range(120) if vals[i] == 0 or (vals[i] < 0) != (vals[i + 1] < 0)]
    by_k: dict[float, float] = {}
    for k, t, iv, w in rows:
        if abs(k / price - 1) <= GAMMA_BAND:
            by_k[k] = by_k.get(k, 0.0) + w * bs_gamma(price, k, t, iv) * price * price
    top = sorted(by_k, key=lambda k: -abs(by_k[k]))[:GAMMA_TOP]
    out: dict[str, Any] = {"gamma_strikes": sorted(top), "gamma_at_spot": "positive" if vals[60] > 0 else "negative"}
    if flips:
        out["gamma_flip"] = round(min(flips, key=lambda x: abs(x - price)), 2)
    return out


def score_gamma(snap: dict, *, low: float, high: float, close: float) -> list[dict[str, Any]]:
    """Per gamma level: did price reach it after the snapshot, and did it hold (close stayed on the starting side)?
    Same test for placebo levels ±0.35 daily σ away, so 'holds more than any price' can be checked."""
    anchor = snap.get("last") or snap.get("premarket") or snap.get("ref_close")
    sig = (snap.get("sigma_pct") or 0) / 100 * (anchor or 0)
    levels = [("flip", snap["gamma_flip"])] if snap.get("gamma_flip") else []
    levels += [("strike", k) for k in snap.get("gamma_strikes") or []]
    if not anchor or sig <= 0:
        return []

    def one(lv: float) -> list[bool]:
        above = lv > anchor
        reached = high >= lv if above else low <= lv
        return [reached, reached and (close < lv if above else close > lv)]

    return [{"kind": kind, "price": lv, "res": one(lv),
             "placebo": [one(lv - PLACEBO_SHIFT * sig), one(lv + PLACEBO_SHIFT * sig)]} for kind, lv in levels]


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
            ty = lambda e: (sessions_between(now_day, e) - 0.5) / 252  # noqa: E731
            chains = [(ch.calls, ch.puts, ty(first))]
            for e in [e for e in exps if first < e <= now_day + timedelta(days=WALL_EXPIRY_DAYS)][:WALL_MAX_CHAINS - 1]:
                c2 = t.option_chain(e.isoformat())
                chains.append((c2.calls, c2.puts, ty(e)))
            out = {"expiry": first.isoformat(), **oi_walls([(c, p) for c, p, _ in chains], price)}
            try:
                out.update(gamma_levels(chains, price))
            except Exception:
                pass
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


def gamma_fields(opt: dict | None) -> dict[str, Any]:
    return {k: opt[k] for k in ("gamma_flip", "gamma_strikes", "gamma_at_spot") if opt and opt.get(k)}


def wall_levels(opt: dict | None) -> list[dict[str, Any]]:
    if not opt:
        return []
    out = []
    if opt.get("call_wall"):
        out.append({"label": f"Options call wall ({opt['call_wall_oi']:,} OI)", "price": opt["call_wall"]})
    if opt.get("put_wall"):
        out.append({"label": f"Options put wall ({opt['put_wall_oi']:,} OI)", "price": opt["put_wall"]})
    return out
