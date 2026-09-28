"""
fv_eps_history.py — Quarterly EPS history counts for FV data-sanity gates.

Used by fv_router to suppress model FV when:
  - Recent spinoff has < 4 clean post-event quarters (§4/§6)
  - Recent IPO / stub history has < 8 total quarterly records (§6)

Fetches FMP quarterly income statements (same source as earnings_quality).
"""
from __future__ import annotations

import logging
from typing import Any

from signals.fmp_client import BASE_V3, get_api_key
from signals.http_session import get_requests_session

logger = logging.getLogger(__name__)

MIN_CLEAN_QUARTERS_SPINOFF = 4
MIN_TOTAL_QUARTERS_IPO = 8


def _parse_quarter_eps(row: dict[str, Any]) -> float | None:
    """Extract diluted/ basic EPS from one quarterly income row."""
    for key in ("epsdiluted", "eps", "netIncomePerShare"):
        v = row.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    ni = row.get("netIncome")
    sh = row.get("weightedAverageShsOutDil") or row.get("weightedAverageShsOut")
    try:
        if ni is not None and sh and float(sh) > 0:
            return float(ni) / float(sh)
    except (TypeError, ValueError):
        pass
    return None


def _is_clean_eps_quarter(row: dict[str, Any]) -> bool:
    """
    A quarter is 'clean' when revenue and EPS are present and finite.
    Does not detect restatements — only filters empty/stub rows.
    """
    try:
        rev = row.get("revenue")
        if rev is None or float(rev) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    eps = _parse_quarter_eps(row)
    return eps is not None


def fetch_quarterly_income(config: dict, ticker: str, *, limit: int = 12) -> list[dict[str, Any]] | None:
    """FMP quarterly income-statement rows, newest first. None on failure.

    Logged at WARNING (not DEBUG) on 401/403/429 specifically, rather than silently
    swallowed — confirmed live that this endpoint intermittently failed for GOOGL
    (eps_quarters_total/clean both None, TTM EPS stayed at the raw un-adjusted ~$19.91),
    breaking fv_router's spinoff/IPO quarter-count gates and eps_normalization.py's
    one-time non-operating-item detection with zero trace of why. A direct manual call to
    this endpoint succeeded, ruling out a plan-tier restriction — 429 (rate limited) is the
    likelier cause under real request volume; this used to be independently fetched from two
    call sites per ticker (fv_router's history check and eps_normalization's own fetch),
    doubling load against whatever per-minute limit applies. See counts_from_rows() /
    fair_value_pipeline.compute_fair_value(), which now share one fetch.
    """
    api_key = get_api_key(config)
    if not api_key:
        return None
    sym = (ticker or "").upper().split("-")[0]
    params = {"period": "quarter", "limit": limit, "apikey": api_key}
    try:
        r = get_requests_session().get(f"{BASE_V3}/income-statement/{sym}", params=params, timeout=15)
        if r.status_code == 429:
            logger.warning("fetch_quarterly_income %s: HTTP 429 — rate limited by FMP.", ticker)
            return None
        if r.status_code in (401, 403):
            logger.warning(
                "fetch_quarterly_income %s: HTTP %d — could be an invalid/expired key, a "
                "plan restriction, or a rate limit surfaced as 403; check the response body "
                "in a direct call if this recurs.", ticker, r.status_code,
            )
            return None
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.debug("fetch_quarterly_income failed %s: %s", ticker, e)
        return None
    if isinstance(data, dict) and (data.get("Error") or data.get("error") or data.get("Error Message")):
        logger.warning(
            "fetch_quarterly_income %s: FMP returned an error payload: %s",
            ticker, data.get("Error") or data.get("error") or data.get("Error Message"),
        )
        return None
    if not isinstance(data, list):
        return None
    return [row for row in data if isinstance(row, dict)]


def counts_from_rows(rows: list[dict[str, Any]] | None) -> tuple[int | None, int | None]:
    """
    (total_quarters, clean_quarters) from an already-fetched quarterly-income rows list —
    pulled out of count_eps_quarter_history so a caller that already has rows (e.g.
    fair_value_pipeline.py, which needs the same rows for EPS normalization) can derive
    counts without a second fetch_quarterly_income() call against the same FMP endpoint.
    """
    if rows is None:
        return None, None
    total = len(rows)
    clean = sum(1 for row in rows if _is_clean_eps_quarter(row))
    return total, clean


def count_eps_quarter_history(
    config: dict,
    ticker: str,
    *,
    limit: int = 12,
) -> tuple[int | None, int | None]:
    """
    Return (total_quarters, clean_quarters).

    total_quarters: rows returned with a parseable date/period
    clean_quarters: rows passing _is_clean_eps_quarter

    Both None if fetch failed.
    """
    rows = fetch_quarterly_income(config, ticker, limit=limit)
    return counts_from_rows(rows)


def get_eps_history_counts(config: dict, ticker: str) -> dict[str, int | None]:
    """Convenience dict for route_fair_value call sites."""
    total, clean = count_eps_quarter_history(config, ticker)
    return {
        "total_quarters": total,
        "clean_quarters": clean,
    }
