"""
Resolve Yahoo institutional holder names → 13F filer CIKs.

Uses keyword hints for known mega-filers, then edgartools find() with 13F + optional
ticker verification. Results cached to disk.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from config_loader import resolve_existing_data_file, writable_data_path
from signals.edgar_common import ensure_edgar_identity, shares_for_ticker_in_report

logger = logging.getLogger(__name__)

TTL_CIK_MAP = 30 * 86400


def _cik_map_rel() -> tuple[str, str]:
    return ("edgar_13f_cache", "holder_cik_map.json")

# Parent 13F filer CIKs (not subsidiary names Yahoo often shows)
_KEYWORD_FILERS: list[tuple[tuple[str, ...], int, str]] = [
    (("BLACKROCK",), 2012383, "BlackRock"),
    (("VANGUARD",), 102909, "Vanguard Group"),
    (("STATE STREET",), 93751, "State Street"),
    (("FIDELITY", "FMR LLC", "FIL ", " FMR"), 315066, "Fidelity"),
    (("CAPITAL RESEARCH", "CAPITAL RESEARCH GLOBAL"), 1422846, "Capital Research"),
    (("GEODE",), 1217410, "Geode Capital"),
    (("NORGES BANK",), 1369667, "Norges Bank"),
    (("MORGAN STANLEY",), 711058, "Morgan Stanley"),
    (("GOLDMAN SACHS", "GOLDMAN"), 886982, "Goldman Sachs"),
    (("JPMORGAN", "JP MORGAN"), 19617, "JPMorgan"),
    (("BANK OF AMERICA", "BANK OF AMERICA CORP"), 1067983, "Bank of America"),
    (("WELLINGTON",), 897971, "Wellington"),
    (("INVESCO",), 92122, "Invesco"),
    (("SCHWAB", "CHARLES SCHWAB"), 874396, "Charles Schwab"),
    (("UBS ", "UBS AG"), 1610520, "UBS"),
    (("BANK OF NEW YORK", "BNY MELLON", "MELLON"), 1033757, "BNY Mellon"),
]

_DEFAULT_FALLBACK = [
    {"name": "BlackRock", "cik": 2012383},
    {"name": "Vanguard Group", "cik": 102909},
    {"name": "State Street", "cik": 93751},
]


def _normalize_holder_name(name: str) -> str:
    s = re.sub(r"[^\w\s&]", " ", (name or "").upper())
    s = re.sub(r"\s+", " ", s).strip()
    for suffix in (" LLC", " INC", " CORP", " LTD", " CO", " LP", " PLC", " AG"):
        while s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s


def _load_cik_map() -> dict[str, Any]:
    path = resolve_existing_data_file(*_cik_map_rel())
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cik_map(data: dict[str, Any]) -> None:
    try:
        path = writable_data_path(*_cik_map_rel())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("holder cik map write failed: %s", exc)


def _keyword_resolve(holder_name: str) -> dict[str, Any] | None:
    norm = _normalize_holder_name(holder_name)
    padded = f" {norm} "
    for keywords, cik, label in _KEYWORD_FILERS:
        if any(kw in norm or kw in padded for kw in keywords):
            return {"name": label, "cik": cik, "source": "keyword_map", "holder_query": holder_name}
    return None


def _holds_ticker(cik: int, ticker: str) -> bool:
    from edgar import Company

    try:
        company = Company(cik)
        filings = company.get_filings(form="13F-HR")
        if filings is None or len(filings) == 0:
            return False
        report = filings[0].obj()
        return shares_for_ticker_in_report(report, ticker) > 0
    except Exception:
        return False


def _find_resolve(holder_name: str, ticker: str | None) -> dict[str, Any] | None:
    from edgar import Company, find

    norm = _normalize_holder_name(holder_name)
    queries = [holder_name.strip(), norm]
    if "CAPITAL MANAGEMENT" in norm:
        queries.append(norm.replace("CAPITAL MANAGEMENT", "GROUP").strip())
    seen_q: set[str] = set()
    for query in queries:
        if not query or query in seen_q:
            continue
        seen_q.add(query)
        try:
            results = find(query)
        except Exception as exc:
            logger.debug("find(%s) failed: %s", query, exc)
            continue
        limit = min(10, len(results))
        for i in range(limit):
            try:
                entity = results[i]
                cik = int(entity.cik)
            except Exception:
                continue
            try:
                company = Company(cik)
                if len(company.get_filings(form="13F-HR")) == 0:
                    continue
                if ticker and not _holds_ticker(cik, ticker):
                    continue
                return {
                    "name": company.name or holder_name,
                    "cik": cik,
                    "source": "edgar_find",
                    "holder_query": holder_name,
                }
            except Exception:
                continue
    return None


def resolve_holder_to_filer(
    holder_name: str,
    ticker: str | None = None,
    *,
    config: dict | None = None,
    use_cache: bool = True,
) -> dict[str, Any] | None:
    """Map one Yahoo holder name to a 13F filer CIK."""
    if not holder_name or not str(holder_name).strip():
        return None
    norm = _normalize_holder_name(holder_name)
    cache = _load_cik_map() if use_cache else {}
    cached = cache.get(norm)
    if cached and time.time() - float(cached.get("ts", 0)) <= TTL_CIK_MAP:
        return {k: v for k, v in cached.items() if k != "ts"}

    try:
        ensure_edgar_identity(config)
    except ImportError:
        hit = _keyword_resolve(holder_name)
        return hit

    hit = _keyword_resolve(holder_name) or _find_resolve(holder_name, ticker)
    if hit:
        cache[norm] = {**hit, "ts": time.time()}
        _save_cik_map(cache)
    return hit


def resolve_filers_from_yahoo_holders(
    top_holders: list[dict] | None,
    ticker: str,
    config: dict | None = None,
    *,
    max_filers: int = 5,
) -> tuple[list[dict[str, Any]], str]:
    """
    Build deduped filer list from Yahoo top_holders.

    Returns (filers, resolution_source) where resolution_source is
    yahoo_dynamic | yahoo_partial | default_fallback.
    """
    cfg = config or {}
    inst = cfg.get("institutional") or {}
    custom = inst.get("edgar_13f_filers")
    if isinstance(custom, list) and custom:
        out = []
        for row in custom:
            if isinstance(row, dict) and row.get("cik"):
                out.append({
                    "name": row.get("name") or str(row["cik"]),
                    "cik": int(row["cik"]),
                    "source": "config",
                })
        if out:
            return out[:max_filers], "config"

    sym = (ticker or "").upper().strip()
    holders = top_holders or []
    resolved: list[dict[str, Any]] = []
    seen_ciks: set[int] = set()

    for h in holders[: max_filers + 3]:
        name = (h.get("holder") or "").strip()
        if not name:
            continue
        filer = resolve_holder_to_filer(name, sym, config=config)
        if not filer:
            continue
        cik = int(filer["cik"])
        if cik in seen_ciks:
            continue
        seen_ciks.add(cik)
        resolved.append(filer)
        if len(resolved) >= max_filers:
            break

    if len(resolved) >= 2:
        return resolved, "yahoo_dynamic"
    if resolved:
        # Pad with defaults not already present
        for fb in _DEFAULT_FALLBACK:
            cik = int(fb["cik"])
            if cik not in seen_ciks:
                resolved.append({**fb, "source": "default_fallback"})
                seen_ciks.add(cik)
            if len(resolved) >= max_filers:
                break
        return resolved[:max_filers], "yahoo_partial"

    fallback = [{**f, "source": "default_fallback"} for f in _DEFAULT_FALLBACK]
    return fallback[:max_filers], "default_fallback"
