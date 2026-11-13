"""Safe rule language for the screener and rule tester (no eval).

Rule: {"all": [cond, ...]} or {"any": [...]}, nesting allowed (depth <= 3, <= 12 conditions).
Cond: {"field": "rsi14", "op": "<", "value": 30}
      {"field": "price", "op": ">", "value_field": "dist_sma200"}   # compare two fields
      {"field": "mom_12_1", "op": "top_pct", "value": 20}            # top 20% of members that day
      {"field": "rsi14", "op": "between", "value": [30, 50]}
      {"field": "rsi14", "op": "crosses_above", "value": 30}         # was <= 30 yesterday, > 30 today
      {"field": "sector", "op": "in", "value": ["Energy"]}
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from research.features import RANKABLE, REGISTRY, FeatureCache

NUM_OPS = (">", ">=", "<", "<=", "between", "top_pct", "bottom_pct", "crosses_above", "crosses_below")
MAX_CONDS = 12
MAX_DEPTH = 3


class RuleError(ValueError):
    pass


def _iter_conds(rule: Any, depth: int = 0):
    if not isinstance(rule, dict):
        raise RuleError("rule must be an object")
    keys = [k for k in ("all", "any") if k in rule]
    if keys:
        if len(keys) != 1 or depth >= MAX_DEPTH:
            raise RuleError("use one of 'all'/'any' per group, nested at most 3 deep")
        items = rule[keys[0]]
        if not isinstance(items, list) or not items:
            raise RuleError(f"'{keys[0]}' needs a non-empty list")
        for it in items:
            yield from _iter_conds(it, depth + 1)
    else:
        yield rule


def validate(rule: Any) -> list[dict]:
    conds = list(_iter_conds(rule))
    if len(conds) > MAX_CONDS:
        raise RuleError(f"at most {MAX_CONDS} conditions")
    for c in conds:
        f, op, v = c.get("field"), c.get("op"), c.get("value")
        if f == "sector":
            if op not in ("in", "not_in") or not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                raise RuleError("sector needs op 'in'/'not_in' and a list of names")
            continue
        if f not in REGISTRY:
            raise RuleError(f"unknown field '{f}'")
        if op not in NUM_OPS:
            raise RuleError(f"unknown op '{op}' for {f}")
        if "value_field" in c:
            if c["value_field"] not in REGISTRY or op not in (">", ">=", "<", "<=", "crosses_above", "crosses_below"):
                raise RuleError("value_field must be a known field compared with >, <, crosses")
            continue
        if op == "between":
            if not (isinstance(v, list) and len(v) == 2 and all(_num(x) for x in v)):
                raise RuleError(f"{f} between needs [low, high]")
        elif not _num(v):
            raise RuleError(f"{f} {op} needs a number")
        if op in ("top_pct", "bottom_pct"):
            if f not in RANKABLE or not 0 < float(v) <= 100:
                raise RuleError("top/bottom % needs a rankable field and 0-100")
    return conds


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and np.isfinite(x)


def fields_used(rule: dict) -> list[str]:
    out = []
    for c in _iter_conds(rule):
        for k in ("field", "value_field"):
            if c.get(k) and c[k] not in out:
                out.append(c[k])
    return out


def family_key(rule: dict) -> str:
    """Thresholds stripped: tweaking a number on the same idea counts as another trial of that idea."""
    parts = []
    for c in _iter_conds(rule):
        parts.append(f"{c.get('field')}{c.get('op')}{c.get('value_field') or ''}" + ("".join(c["value"]) if c.get("field") == "sector" else ""))
    return "|".join(sorted(parts))


def _cond_mask(c: dict, fc: FeatureCache, rows: slice | None) -> pd.DataFrame:
    p = fc.p
    if c["field"] == "sector":
        cols = [t for t in p.tickers if p.sectors.get(t) in set(c["value"])]
        m = pd.DataFrame(False, index=p.close.index, columns=p.close.columns)
        m[cols] = True
        if c["op"] == "not_in":
            m = ~m
        return m.iloc[rows] if rows is not None else m
    op = c["op"]
    if op in ("top_pct", "bottom_pct"):
        r = fc.get(c["field"] + "_pct_rank")
        r = r.iloc[rows] if rows is not None else r
        return r > 100 - float(c["value"]) if op == "top_pct" else r <= float(c["value"])
    x = fc.get(c["field"])
    y = fc.get(c["value_field"]) if c.get("value_field") else float(c["value"]) if op != "between" else None
    if op in ("crosses_above", "crosses_below"):
        xp = x.shift(1)
        yp = y.shift(1) if isinstance(y, pd.DataFrame) else y
        m = (xp <= yp) & (x > y) if op == "crosses_above" else (xp >= yp) & (x < y)
        return m.iloc[rows] if rows is not None else m
    if rows is not None:
        x = x.iloc[rows]
        y = y.iloc[rows] if isinstance(y, pd.DataFrame) else y
    if op == "between":
        lo, hi = sorted(float(v) for v in c["value"])
        return (x >= lo) & (x <= hi)
    return {">": x > y, ">=": x >= y, "<": x < y, "<=": x <= y}[op]


def evaluate(rule: dict, fc: FeatureCache, rows: slice | None = None) -> pd.DataFrame:
    """Boolean dates x tickers; NaN inputs are False. ``rows`` limits to a date slice (screener uses the last row)."""
    validate(rule)

    def ev(node):
        if "all" in node or "any" in node:
            parts = [ev(n) for n in node.get("all") or node.get("any")]
            out = parts[0]
            for q in parts[1:]:
                out = (out & q) if "all" in node else (out | q)
            return out
        return _cond_mask(node, fc, rows).fillna(False).astype(bool)

    return ev(rule)


def describe(rule: dict, labels: dict[str, str] | None = None) -> str:
    labels = labels or {k: f.label for k, f in REGISTRY.items()}

    def d(node):
        if "all" in node or "any" in node:
            j = " AND " if "all" in node else " OR "
            s = j.join(d(n) for n in node.get("all") or node.get("any"))
            return f"({s})" if len(node.get("all") or node.get("any")) > 1 else s
        f = "Sector" if node["field"] == "sector" else labels.get(node["field"], node["field"])
        op, v = node["op"], node.get("value")
        if node.get("value_field"):
            return f"{f} {op.replace('_', ' ')} {labels.get(node['value_field'], node['value_field'])}"
        if op == "between":
            return f"{f} {v[0]}–{v[1]}"
        if op in ("top_pct", "bottom_pct"):
            return f"{f} in {'top' if op == 'top_pct' else 'bottom'} {v}%"
        if op in ("in", "not_in"):
            return f"{f} {'is' if op == 'in' else 'not'} {', '.join(v)}"
        return f"{f} {op.replace('_', ' ')} {v}"

    s = d(rule)
    return s[1:-1] if s.startswith("(") and s.endswith(")") else s
