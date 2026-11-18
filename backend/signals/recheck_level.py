"""Re-check price for names the model is not buying (display + alert only; never a BUY).

Level = 50-day average when price is above it, else the 200-day when price is above that — the same
pullback levels as suggested_buy_price, but kept when the gates lock or the score is weak. Stop sits two
average daily moves below the level so the max loss is known before anyone acts."""
from __future__ import annotations

import math
from typing import Any


def recheck_price(close: float | None, ma50: float | None, ma200: float | None) -> tuple[float, str] | None:
    def ok(v):
        return v is not None and not (isinstance(v, float) and math.isnan(v)) and v > 0
    if not ok(close):
        return None
    if ok(ma50) and close > ma50:
        return round(float(ma50), 2), "50-day average"
    if ok(ma200) and close > ma200:
        return round(float(ma200), 2), "200-day average"
    return None


def recheck_level(close, ma50, ma200, closes=None, *, signal: str | None = None,
                  gates_passed: int | None = None, gates_total: int | None = None) -> dict[str, Any] | None:
    if (signal or "").upper() in ("BUY", "STRONG BUY"):
        return None
    lv = recheck_price(close, ma50, ma200)
    gates = f"{gates_passed}/{gates_total} gates pass" if gates_passed is not None and gates_total else None
    if lv is None:
        if close is None:
            return None
        return {"price": None, "basis": None, "stop": None, "max_loss_pct": None, "gates": gates,
                "note": "Price is below its 50- and 200-day averages, so there is no pullback level to wait for."}
    price, basis = lv
    stop = None
    try:
        xs = [float(x) for x in list(closes)[-15:]] if closes is not None else []
        moves = [abs(b - a) for a, b in zip(xs, xs[1:]) if a > 0 and b > 0]
        if len(moves) >= 10:
            stop = round(price - 2 * sum(moves) / len(moves), 2)
    except Exception:
        stop = None
    return {
        "price": price,
        "basis": basis,
        "stop": stop,
        "max_loss_pct": round((1 - stop / price) * 100, 1) if stop and stop < price else None,
        "gates": gates,
        "note": "Not a BUY: the price where we'd re-check the gates.",
    }
