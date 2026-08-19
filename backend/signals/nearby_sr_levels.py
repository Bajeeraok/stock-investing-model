"""Next support / resistance for ticker-detail, per horizon.

Uses levels already on the card (MAs, 52w, 20d swing, horizon bands, named
support/resistance). No extra API. A level is omitted when nothing sits on
the right side of spot within that horizon's look-ahead.
"""
from __future__ import annotations

from typing import Any, Iterable

_MAX_DIST_PCT = {"short": 8.0, "medium": 12.0, "long": 30.0}
_CLUSTER_PCT = 0.45  # merge levels within this % of each other
_MIN_AWAY_PCT = {"short": 0.8, "medium": 2.0, "long": 3.0}


def _r(v: float, n: int = 2) -> float:
    return round(float(v), n)


def _dist_pct(price: float, spot: float) -> float:
    return _r((price - spot) / spot * 100, 1)


def _add(
    bucket: list[dict[str, Any]],
    *,
    price: float | None,
    label: str,
    spot: float,
    side: str,
    min_away_pct: float,
) -> None:
    if price is None:
        return
    try:
        px = float(price)
    except (TypeError, ValueError):
        return
    if not (px > 0 and spot > 0):
        return
    gap = abs(px - spot) / spot * 100
    if gap < min_away_pct:
        return
    if side == "support" and px >= spot:
        return
    if side == "resistance" and px <= spot:
        return
    bucket.append({"price": _r(px), "label": label, "dist_pct": _dist_pct(px, spot)})


def _dedupe(levels: list[dict[str, Any]], spot: float) -> list[dict[str, Any]]:
    if not levels:
        return []
    ranked = sorted(levels, key=lambda x: abs(float(x["price"]) - spot))
    kept: list[dict[str, Any]] = []
    for row in ranked:
        px = float(row["price"])
        if any(abs(px - float(k["price"])) / spot * 100 < _CLUSTER_PCT for k in kept):
            continue
        kept.append(row)
    return kept


def _nearest(
    levels: list[dict[str, Any]],
    *,
    below: bool,
    max_pct: float,
) -> dict[str, Any] | None:
    side = [r for r in levels if abs(float(r["dist_pct"])) <= max_pct + 1e-9]
    if not side:
        return None
    if below:
        below_rows = [r for r in side if float(r["dist_pct"]) < 0]
        if not below_rows:
            return None
        return max(below_rows, key=lambda r: float(r["price"]))
    above_rows = [r for r in side if float(r["dist_pct"]) > 0]
    if not above_rows:
        return None
    return min(above_rows, key=lambda r: float(r["price"]))


def _pivots_from_closes(closes: Iterable[float], spot: float) -> tuple[list[float], list[float]]:
    arr = [float(c) for c in closes if c is not None]
    if len(arr) < 8:
        return [], []
    lows: list[float] = []
    highs: list[float] = []
    for i in range(2, len(arr) - 2):
        if arr[i] < arr[i - 1] and arr[i] < arr[i - 2] and arr[i] < arr[i + 1] and arr[i] < arr[i + 2]:
            lows.append(arr[i])
        if arr[i] > arr[i - 1] and arr[i] > arr[i - 2] and arr[i] > arr[i + 1] and arr[i] > arr[i + 2]:
            highs.append(arr[i])
    supports = sorted((l for l in lows if l < spot * 0.998), reverse=True)[:4]
    resists = sorted(h for h in highs if h > spot * 1.002)[:4]
    return supports, resists


def pick_nearby_sr(
    *,
    spot: float,
    horizon_key: str,
    ma20: float | None = None,
    ma50: float | None = None,
    ma200: float | None = None,
    low_52w: float | None = None,
    high_52w: float | None = None,
    swing_low: float | None = None,
    swing_high: float | None = None,
    support_level: float | None = None,
    resistance_level: float | None = None,
    entry_low: float | None = None,
    entry_high: float | None = None,
    t1_high: float | None = None,
    t2_high: float | None = None,
    closes: Iterable[float] | None = None,
) -> dict[str, Any] | None:
    if not (spot and spot > 0):
        return None
    max_pct = _MAX_DIST_PCT.get(horizon_key, 12.0)
    min_away = _MIN_AWAY_PCT.get(horizon_key, 1.5)
    supports: list[dict[str, Any]] = []
    resists: list[dict[str, Any]] = []
    # Model entry/T1/T2 bands are not market structure — never echo them as S/R.
    _ = (entry_low, entry_high, t1_high, t2_high)

    swing_lo_label = "Near-term pivot" if horizon_key == "short" else "20d swing low"
    swing_hi_label = "Near-term pivot" if horizon_key == "short" else "20d swing high"

    def add(bucket, *, price, label, side):
        _add(bucket, price=price, label=label, spot=spot, side=side, min_away_pct=min_away)

    add(supports, price=swing_low, label=swing_lo_label, side="support")
    add(supports, price=support_level, label="Named support", side="support")
    add(supports, price=ma20, label="MA20", side="support")
    add(supports, price=ma50, label="MA50", side="support")
    add(supports, price=ma200, label="MA200", side="support")
    add(supports, price=low_52w, label="52w low", side="support")

    add(resists, price=swing_high, label=swing_hi_label, side="resistance")
    add(resists, price=resistance_level, label="Named resistance", side="resistance")
    add(resists, price=ma20, label="MA20", side="resistance")
    add(resists, price=ma50, label="MA50", side="resistance")
    add(resists, price=ma200, label="MA200", side="resistance")
    add(resists, price=high_52w, label="52w high", side="resistance")

    if closes:
        p_lo, p_hi = _pivots_from_closes(closes, spot)
        lo_lab = "Near-term pivot" if horizon_key == "short" else "Swing low"
        hi_lab = "Near-term pivot" if horizon_key == "short" else "Swing high"
        prior_lo = "Prior pivot" if horizon_key == "short" else "Prior swing low"
        prior_hi = "Prior pivot" if horizon_key == "short" else "Prior swing high"
        for i, px in enumerate(p_lo[:2]):
            add(supports, price=px, label=lo_lab if i == 0 else prior_lo, side="support")
        for i, px in enumerate(p_hi[:2]):
            add(resists, price=px, label=hi_lab if i == 0 else prior_hi, side="resistance")

    supports = _dedupe(supports, spot)
    resists = _dedupe(resists, spot)
    nxt_s = _nearest(supports, below=True, max_pct=max_pct)
    nxt_r = _nearest(resists, below=False, max_pct=max_pct)
    if nxt_s is None and nxt_r is None:
        return None
    stack_s = sorted(
        [r for r in supports if float(r["dist_pct"]) < 0 and abs(float(r["dist_pct"])) <= max_pct],
        key=lambda r: -float(r["price"]),
    )[:2]
    stack_r = sorted(
        [r for r in resists if float(r["dist_pct"]) > 0 and abs(float(r["dist_pct"])) <= max_pct],
        key=lambda r: float(r["price"]),
    )[:2]
    return {
        "next_support": nxt_s,
        "next_resistance": nxt_r,
        "support_stack": stack_s,
        "resistance_stack": stack_r,
    }


def attach_nearby_sr(
    horizons: dict[str, Any],
    *,
    spot: float,
    ma20: float | None = None,
    ma50: float | None = None,
    ma200: float | None = None,
    low_52w: float | None = None,
    high_52w: float | None = None,
    swing_low: float | None = None,
    swing_high: float | None = None,
    support_level: float | None = None,
    resistance_level: float | None = None,
    closes: Iterable[float] | None = None,
) -> None:
    """Mutates each horizon dict with `nearby_sr` when a next level exists."""
    for key in ("short", "medium", "long"):
        h = horizons.get(key)
        if not isinstance(h, dict):
            continue
        ez = h.get("entry_zone") or {}
        t1_high = t2_high = None
        if key == "long":
            for t in ((h.get("entry_tiers") or {}).get("tiers") or []):
                if not isinstance(t, dict):
                    continue
                tid = str(t.get("id") or "").upper()
                if tid == "T1" and t.get("high") is not None:
                    t1_high = float(t["high"])
                elif tid == "T2" and t.get("high") is not None:
                    t2_high = float(t["high"])
        nearby = pick_nearby_sr(
            spot=spot,
            horizon_key=key,
            ma20=ma20,
            ma50=ma50,
            ma200=ma200,
            low_52w=low_52w,
            high_52w=high_52w,
            swing_low=swing_low,
            swing_high=swing_high,
            support_level=support_level,
            resistance_level=resistance_level,
            entry_low=ez.get("low"),
            entry_high=ez.get("high"),
            t1_high=t1_high,
            t2_high=t2_high,
            closes=closes,
        )
        if nearby:
            h["nearby_sr"] = nearby
        else:
            h.pop("nearby_sr", None)
