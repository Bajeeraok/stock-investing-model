"""Screen the latest panel day with a rule. Only stocks that are index members that day (plus ETFs if asked)."""
from __future__ import annotations

import math
from typing import Any

from research.dsl import evaluate, fields_used
from research.features import REGISTRY, FeatureCache

DEFAULT_COLUMNS = ["price", "ret_21d", "ret_252d", "dist_sma200", "rsi14", "dd_52w", "atr_pct"]
MAX_ROWS = 500


def _clean(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, 2)


def screen(fc: FeatureCache, rule: dict, columns: list[str] | None = None, sort: str | None = None,
           desc: bool = True, limit: int = 200, include_etfs: bool = False, as_of: str | None = None) -> dict[str, Any]:
    p = fc.p
    idx = len(p.close.index) - 1 if not as_of else int(p.close.index.searchsorted(as_of, side="right")) - 1
    if idx < 0:
        raise ValueError("as_of is before the panel starts")
    cols = [c for c in (columns or DEFAULT_COLUMNS) if c in REGISTRY]
    for f in fields_used(rule):
        if f not in cols:
            cols.append(f)
    rows = slice(max(0, idx - 1), idx + 1)
    hit = evaluate(rule, fc, rows).iloc[-1]
    members = p.members.iloc[idx]
    etfs = set(p.etfs)
    ok = hit & (members | False)
    tickers = [t for t in hit.index[ok] if include_etfs or t not in etfs]
    date = p.close.index[idx]
    out = []
    for t in tickers:
        r = {"ticker": t, "sector": p.sectors.get(t), "is_etf": t in etfs}
        for c in cols:
            r[c] = _clean(fc.get(c).iloc[idx].get(t))
        out.append(r)
    key = sort if sort in cols else (cols[0] if cols else None)
    if key:
        out.sort(key=lambda r: (r.get(key) is None, -(r.get(key) or 0) if desc else (r.get(key) or 0)))
    universe_n = int(members.sum()) if include_etfs else int(members[[t for t in members.index if t not in etfs]].sum())
    return {
        "as_of": str(date.date()),
        "n_matches": len(out),
        "universe_n": universe_n,
        "columns": cols,
        "rows": out[: min(limit, MAX_ROWS)],
        "truncated": len(out) > min(limit, MAX_ROWS),
    }
