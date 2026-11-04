"""Model odds check: did the saved 3-month / 6-month model probabilities come true?

Reads daily model probabilities logged in signal_audit.db and, for calls old enough, checks
whether the close `days` sessions later was >= the model's +N% threshold.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

BUCKETS = ((0, 20), (20, 40), (40, 60), (60, 80), (80, 101))
_COLS = {"medium": "ml_medium_prob", "long": "ml_long_prob"}


def _pct(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    return x * 100.0 if x <= 1.0 else x


MIN_PROVEN_N = 200
CAL_TOL_PTS = 10.0
CAL_MIN_BUCKET_N = 30


def score_calls(calls: list[tuple[float, bool]], buckets=BUCKETS) -> dict[str, Any] | None:
    """Said vs came true per bucket, plus Brier skill vs always guessing the base rate."""
    if not calls:
        return None
    n = len(calls)
    out = []
    for lo, hi in buckets:
        g = [(p, y) for p, y in calls if lo <= p < hi]
        if g:
            ct = round(100.0 * sum(1 for _, y in g if y) / len(g), 1)
            out.append({"range": f"{lo}–{min(hi, 100)}%", "n": len(g),
                        "avg_predicted_pct": round(sum(p for p, _ in g) / len(g), 1),
                        "came_true_pct": ct, "actual_hit_pct": ct})
    base = sum(1 for _, y in calls if y) / n
    brier = sum((p / 100.0 - (1.0 if y else 0.0)) ** 2 for p, y in calls) / n
    brier_base = base * (1.0 - base)
    skill = None if brier_base <= 0 else round(100.0 * (1.0 - brier / brier_base), 1)
    res = {"n": n, "avg_predicted_pct": round(sum(p for p, _ in calls) / n, 1),
           "came_true_pct": round(100.0 * base, 1), "actual_hit_pct": round(100.0 * base, 1),
           "brier": round(brier, 4), "brier_base": round(brier_base, 4), "skill_pct": skill,
           "buckets": out}
    res["verdict"] = verdict(res)
    return res


def verdict(sc: dict[str, Any] | None) -> str:
    """unproven (too few) · no_edge (worse than guessing the base rate) · miscalibrated · proven."""
    if not sc or sc.get("n", 0) < MIN_PROVEN_N or sc.get("skill_pct") is None:
        return "unproven"
    if sc["skill_pct"] <= 0:
        return "no_edge"
    for b in sc.get("buckets") or []:
        if b["n"] >= CAL_MIN_BUCKET_N and abs(b["came_true_pct"] - b["avg_predicted_pct"]) > CAL_TOL_PTS:
            return "miscalibrated"
    return "proven"


def model_trusted(horizon_key: str, report: dict | None = None) -> bool:
    """Model odds may drive ranking only once its own horizon's check says proven."""
    rep = report if report is not None else load_model_check()
    sc = ((rep or {}).get("horizons") or {}).get(horizon_key)
    return verdict(sc) == "proven"


def outcomes_for_ticker(rows: list[tuple[str, float]], bars, days: int, gain_pct: float) -> list[tuple[float, bool]]:
    """rows: (signal_date, prob%). One outcome per call whose horizon has fully elapsed."""
    if bars is None or len(bars) == 0:
        return []
    dates = [ts.date().isoformat() for ts in bars.index]
    closes = list(bars["close"])
    pos = {d: i for i, d in enumerate(dates)}
    out = []
    for day, p in rows:
        i = pos.get(day)
        if i is None or i + days >= len(closes):
            continue
        out.append((p, closes[i + days] / closes[i] - 1.0 >= gain_pct / 100.0))
    return out


def build_model_check(fetch=None) -> dict[str, Any]:
    from config_loader import get_data_root
    from signals.ml_models import HORIZONS, get_target_gain

    if fetch is None:
        from signals.fetcher import fetch_ohlcv_dataframe as fetch
    db = get_data_root() / "signal_audit.db"
    res: dict[str, Any] = {"horizons": {}}
    if not db.exists():
        return res
    with sqlite3.connect(db, timeout=30) as conn:
        rows = conn.execute(
            "SELECT DISTINCT ticker, signal_date, ml_medium_prob, ml_long_prob FROM signal_events "
            "WHERE source = 'live' ORDER BY ticker, signal_date"
        ).fetchall()
    by_ticker: dict[str, list[tuple]] = {}
    for t, d, m, lg in rows:
        by_ticker.setdefault(str(t).upper(), []).append((d, m, lg))
    calls: dict[str, list[tuple[float, bool]]] = {k: [] for k in _COLS}
    for t, items in by_ticker.items():
        if t.endswith("-USD"):
            continue
        try:
            bars = fetch(t, "2y")
        except Exception:
            bars = None
        for k, col_i in (("medium", 1), ("long", 2)):
            seen: dict[str, float] = {}
            for it in items:
                p = _pct(it[col_i])
                if p is not None:
                    seen[it[0]] = p
            days = int(HORIZONS[k]["days"])
            calls[k].extend(outcomes_for_ticker(sorted(seen.items()), bars, days, get_target_gain(t, k) * 100.0))
    for k, c in calls.items():
        res["horizons"][k] = score_calls(c)
    return res


def save_model_check(report: dict) -> None:
    from signals.best_setups import _dir

    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "model_check.json").write_text(json.dumps(report))


def load_model_check() -> dict | None:
    from signals.best_setups import _dir

    f = _dir() / "model_check.json"
    try:
        return json.loads(f.read_text()) if f.exists() else None
    except Exception:
        return None
