"""Storm meter: how far along today's market "stormy" spell is versus past spells (display only, not a timing signal).

Spell = SPY closes below its 50-day average; it ends after 5 straight closes back above. Spells shorter than 5 sessions
are ignored. Tested 2000-2026: no input (VIX level, VIX curve flip) predicted the end better than the base rates."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
END_RUN = 5
MIN_DAYS = 5


def spells(below: list[bool]) -> list[tuple[int, int]]:
    """(start, end) index pairs; an open spell has end = last index."""
    out, i, n = [], 0, len(below)
    while i < n:
        if not below[i]:
            i += 1
            continue
        j, above = i, 0
        while j < n and above < END_RUN:
            above = above + 1 if not below[j] else 0
            j += 1
        end = j - END_RUN - 1 if above >= END_RUN else n - 1
        out.append((i, end))
        i = j
    return out


def build(close: list[float], dates: list[str], vix: list[float], vix3m: list[float | None]) -> dict[str, Any] | None:
    n = len(close)
    if n < 300:
        return None
    ma = [None] * 49 + [sum(close[k - 49:k + 1]) / 50 for k in range(49, n)]
    below = [ma[k] is not None and close[k] < ma[k] for k in range(n)]
    sp = spells(below)
    open_spell = sp[-1] if sp and sp[-1][1] == n - 1 else None
    past = [(a, b) for a, b in (sp[:-1] if open_spell else sp) if b - a + 1 >= MIN_DAYS]

    def peak_dd(a, b):
        pk = max(close[max(0, a - 60):a + 1])
        return min(close[a:b + 1]) / pk - 1

    lens = sorted(b - a + 1 for a, b in past)
    med = lens[len(lens) // 2]
    over = {k: round(sum(1 for x in lens if x <= k) / len(lens) * 100) for k in (10, 20, 40, 60)}
    deep = sorted(b - a + 1 for a, b in past if peak_dd(a, b) <= -0.10)
    hist = [{"start": dates[a], "end": dates[b], "days": b - a + 1, "max_drawdown_pct": round(peak_dd(a, b) * 100, 1),
             "max_vix": round(max(vix[a:b + 1]), 1),
             "spy_20d_after_pct": round((close[b + 20] / close[b] - 1) * 100, 1) if b + 20 < n else None}
            for a, b in past]
    after = [h["spy_20d_after_pct"] for h in hist if h["spy_20d_after_pct"] is not None]
    pk60 = max(close[-61:])
    out: dict[str, Any] = {
        "as_of": dates[-1], "spy": round(close[-1], 2), "ma50": round(ma[-1], 2),
        "drawdown_pct": round((close[-1] / pk60 - 1) * 100, 1), "vix": round(vix[-1], 1),
        "vix_curve_inverted": bool(vix3m[-1] and vix[-1] > vix3m[-1]),
        "past": {"n": len(lens), "median_days": med, "over_by_pct": over,
                 "deep_n": len(deep), "deep_median_days": deep[len(deep) // 2] if deep else None,
                 "spy_20d_after_median_pct": round(sorted(after)[len(after) // 2], 1) if after else None,
                 "spy_20d_after_up_pct": round(sum(1 for x in after if x > 0) / len(after) * 100) if after else None},
        "recent_spells": hist[-12:][::-1],
        "active": bool(open_spell),
    }
    if open_spell:
        a = open_spell[0]
        days = n - a
        dd = (min(close[a:]) / max(close[max(0, a - 60):a + 1]) - 1) * 100
        ended_by_now = round(sum(1 for x in lens if x <= days) / len(lens) * 100)
        still = [x - days for x in lens if x > days]
        similar = [b - a2 + 1 for a2, b in past if b - a2 + 1 > days and peak_dd(a2, b) <= min(-0.07, dd / 100 + 0.02)]
        out["spell"] = {"start": dates[a], "days": days, "max_drawdown_pct": round(dd, 1), "past_ended_by_now_pct": ended_by_now,
                        "remaining_median_days": sorted(still)[len(still) // 2] if still else None,
                        "similar_n": len(similar),
                        "similar_remaining_median_days": (sorted(similar)[len(similar) // 2] - days) if similar else None}
    return out


def compute() -> dict[str, Any] | None:
    from signals.cache import cache_key, get_cached, set_cached

    key = cache_key("storm_tracker", "v1")
    hit = get_cached(key)
    if isinstance(hit, dict):
        return hit
    try:
        import yfinance as yf

        d = yf.download(["SPY", "^VIX", "^VIX3M"], start="2000-01-01", auto_adjust=True, progress=False)["Close"]
        d = d.dropna(subset=["SPY", "^VIX"])
        out = build([float(x) for x in d["SPY"]], [i.date().isoformat() for i in d.index], [float(x) for x in d["^VIX"]],
                    [float(x) if x == x else None for x in d["^VIX3M"]])
    except Exception as e:
        logger.warning("storm tracker failed: %s", e)
        return None
    if out:
        set_cached(key, out, 6 * 3600)
    return out
