"""
Private model report card: what the current model said vs what happened, and whether it has
earned the right to be published.

Honest-stats rules:
  • Calls made on the same day share one market move, so uncertainty is computed over trading
    days (each day = mean of that day's calls), not over individual calls.
  • "Edge vs hold" = following the model (full position on HOLD/ADD, half on TRIM/REDUCE)
    minus holding the same stock, after a trading cost on every call that changes exposure.
  • Publish gate: ≥ MIN_DAYS trading days with completed 20-day outcomes, positive mean edge
    after costs, and positive edge in each of the last two complete calendar months.
"""
from __future__ import annotations

import math
from typing import Any

MIN_DAYS = 60
COST_PCT = 0.10  # round-trip-ish cost per exposure change, % of position
HORIZON = 20


def _exposure(signal: str | None) -> float:
    s = (signal or "").upper()
    return 0.5 if any(x in s for x in ("TRIM", "REDUCE", "SELL", "AVOID")) else 1.0


def _right(signal: str | None, ret: float | None) -> bool | None:
    if ret is None:
        return None
    s = (signal or "").upper()
    if "ADD" in s or "BUY" in s:
        return ret > 0
    if any(x in s for x in ("TRIM", "REDUCE", "SELL", "AVOID")):
        return ret < 0
    return None


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(100 * max(0.0, c - h), 1), round(100 * min(1.0, c + h), 1)


def _mean_ci(xs: list[float]) -> dict[str, Any]:
    n = len(xs)
    if n == 0:
        return {"mean": None, "ci95": None, "n": 0}
    m = sum(xs) / n
    if n < 2:
        return {"mean": round(m, 3), "ci95": None, "n": n}
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    se = sd / math.sqrt(n)
    return {"mean": round(m, 3), "ci95": [round(m - 1.96 * se, 3), round(m + 1.96 * se, 3)], "n": n}


def _ok(r: dict, version: str, horizon: int) -> bool:
    return (
        r.get("horizon_days") == horizon
        and str(r.get("model_version") or "legacy") == version
        and r.get("forward_status") == "complete"
        and r.get("actual_return_pct") is not None
        and r.get("data_quality") != "stale_session"
    )


def build_report_card(
    records: list[dict[str, Any]],
    version: str,
    *,
    min_days: int = MIN_DAYS,
    cost_pct: float = COST_PCT,
    public: bool = False,
    max_calls: int = 60,
) -> dict[str, Any]:
    r20 = [r for r in records if _ok(r, version, HORIZON)]
    r1 = [r for r in records if r.get("horizon_days") == 1 and str(r.get("model_version") or "legacy") == version]

    by_day_edge: dict[str, list[float]] = {}
    by_day_spy: dict[str, list[float]] = {}
    hits = dir_n = changed = 0
    for r in r20:
        ret = float(r["actual_return_pct"])
        exp = _exposure(r.get("our_signal"))
        edge = (exp - 1.0) * ret - (cost_pct if exp != 1.0 else 0.0)
        d = str(r.get("as_of_date"))
        by_day_edge.setdefault(d, []).append(edge)
        if r.get("benchmark_return_pct") is not None:
            by_day_spy.setdefault(d, []).append(exp * ret - float(r["benchmark_return_pct"]))
        changed += int(exp != 1.0)
        h = _right(r.get("our_signal"), ret)
        if h is not None:
            dir_n += 1
            hits += int(h)
    days = sorted(by_day_edge)
    day_edges = [sum(by_day_edge[d]) / len(by_day_edge[d]) for d in days]
    day_spy = [sum(v) / len(v) for _, v in sorted(by_day_spy.items())]
    edge = _mean_ci(day_edges)
    vs_spy = _mean_ci(day_spy)

    months: dict[str, list[float]] = {}
    for d, e in zip(days, day_edges):
        months.setdefault(d[:7], []).append(e)
    month_rows = [{"month": m, "days": len(v), "edge_pct": round(sum(v) / len(v), 3)} for m, v in sorted(months.items())]
    complete_months = month_rows[:-1]  # the latest month is still filling
    last_two = complete_months[-2:]

    checks = [
        {
            "label": f"At least {min_days} trading days with 20-day outcomes",
            "ok": len(days) >= min_days,
            "detail": f"{len(days)} of {min_days}",
        },
        {
            "label": "Beats holding the same stock after costs",
            "ok": edge["mean"] is not None and edge["mean"] > 0,
            "detail": "—" if edge["mean"] is None else f"{edge['mean']:+.3f}% per 20 days",
        },
        {
            "label": "Positive in each of the last 2 complete months",
            "ok": len(last_two) == 2 and all(m["edge_pct"] > 0 for m in last_two),
            "detail": ", ".join(f"{m['month']} {m['edge_pct']:+.2f}%" for m in last_two) or "not enough months yet",
        },
    ]

    r20_idx = {(str(r.get("ticker")).upper(), r.get("as_of_date")): r for r in r20}
    calls = []
    for r in sorted(r1, key=lambda x: (str(x.get("as_of_date")), str(x.get("ticker"))), reverse=True)[:max_calls]:
        k = (str(r.get("ticker")).upper(), r.get("as_of_date"))
        x20 = r20_idx.get(k)
        calls.append({
            "date": r.get("as_of_date"),
            "ticker": k[0],
            "signal": r.get("our_signal"),
            "entry_mode": r.get("entry_mode"),
            "price_at_call": r.get("close_at_signal"),
            "next_close": r.get("close_at_forward") if r.get("forward_status") == "complete" else None,
            "return_1d_pct": r.get("actual_return_pct"),
            "return_20d_pct": x20.get("actual_return_pct") if x20 else None,
            "spy_20d_pct": x20.get("benchmark_return_pct") if x20 else None,
            "right_20d": _right(r.get("our_signal"), x20.get("actual_return_pct")) if x20 else None,
        })

    return {
        "model_version": version,
        "public": bool(public),
        "trading_days_scored": len(days),
        "calls_scored": len(r20),
        "calls_changing_exposure": changed,
        "edge_vs_hold_20d": edge,
        "model_vs_spy_20d": vs_spy,
        "directional_hit_rate": {
            "calls": dir_n,
            "hit_pct": round(100 * hits / dir_n, 1) if dir_n else None,
            "ci95": _wilson(hits, dir_n),
        },
        "months": month_rows,
        "publish_checks": checks,
        "ready_to_publish": all(c["ok"] for c in checks),
        "calls": calls,
        "weekly_draft": weekly_draft(version, r1, edge, checks),
        "method": (
            f"Edge = model position (full, or half on TRIM/REDUCE) minus holding the same stock over {HORIZON} trading "
            f"days, minus {cost_pct:.2f}% per call that changes exposure. Uncertainty is over trading days, not calls."
        ),
    }


def weekly_draft(version: str, r1: list[dict], edge: dict, checks: list[dict]) -> str | None:
    done = [r for r in r1 if r.get("forward_status") == "complete" and r.get("actual_return_pct") is not None]
    if not done:
        return None
    dates = sorted({str(r["as_of_date"]) for r in done})[-5:]
    week = [r for r in done if str(r["as_of_date"]) in dates]
    sig: dict[str, int] = {}
    for r in week:
        sig[str(r.get("our_signal") or "—")] = sig.get(str(r.get("our_signal") or "—"), 0) + 1
    model = sum(_exposure(r.get("our_signal")) * float(r["actual_return_pct"]) for r in week) / len(week)
    hold = sum(float(r["actual_return_pct"]) for r in week) / len(week)
    spy_vals = [float(r["benchmark_return_pct"]) for r in week if r.get("benchmark_return_pct") is not None]
    trims = sorted({str(r["ticker"]).upper() for r in week if _exposure(r.get("our_signal")) != 1.0})
    lines = [
        f"## Thrive Alpha weekly report card — {dates[0]} to {dates[-1]} (model {version})",
        "",
        f"- Calls this week: {len(week)} across {len({r['ticker'] for r in week})} tickers "
        + "(" + ", ".join(f"{k} {v}" for k, v in sorted(sig.items(), key=lambda kv: -kv[1])) + ").",
        f"- Average next-day move when following the model: {model:+.2f}% vs {hold:+.2f}% holding the same stocks"
        + (f" and {sum(spy_vals) / len(spy_vals):+.2f}% for SPY." if spy_vals else "."),
        f"- Trim calls: {', '.join(trims) if trims else 'none'}.",
        "- 20-day edge vs holding so far: "
        + ("not enough completed 20-day outcomes yet." if edge.get("mean") is None else f"{edge['mean']:+.3f}% (n={edge['n']} days)."),
        f"- Publish checklist: {sum(c['ok'] for c in checks)}/{len(checks)} met.",
        "",
        "_Educational report of past model output, not investment advice._",
    ]
    return "\n".join(lines)
