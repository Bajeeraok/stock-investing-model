"""
Batch earnings-quality hints onto signal rows (dashboard only; FMP calls).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from signals.cache import cached_earnings_quality
from signals.earnings_quality import analyze_earnings_quality

logger = logging.getLogger(__name__)

_EARNINGS_DAYS_RE = re.compile(r"Earnings in ~?(\d+) days?")


def _days_to_earnings(row: dict[str, Any]) -> int | None:
    m = _EARNINGS_DAYS_RE.search(row.get("earnings_note") or "")
    return int(m.group(1)) if m else None


def enrich_results_earnings_quality(
    config: dict,
    results: list[dict[str, Any]],
    *,
    max_tickers: int = 12,
) -> None:
    """
    Mutates each result dict with optional earnings_quality: { grade, quality_score, flags }.
    Processes top names by composite_buy first to stay within API budget.
    """
    cfg = (config.get("dashboard_earnings_quality") or {})
    if not cfg.get("enabled", True):
        return
    try:
        max_n = int(cfg.get("max_tickers", max_tickers))
    except (TypeError, ValueError):
        max_n = max_tickers
    try:
        near_days = int(cfg.get("near_earnings_days", 7))
    except (TypeError, ValueError):
        near_days = 7

    rows = [r for r in results if not r.get("error") and r.get("ticker")]
    rows.sort(key=lambda x: -(float(x.get("composite_buy") or 0)))
    for r in rows[:max_n]:
        t = r.get("ticker")
        if not t:
            continue
        try:
            q = cached_earnings_quality(
                str(t),
                lambda t=t: analyze_earnings_quality(config, str(t)),
                days_to_earnings=_days_to_earnings(r),
                near_earnings_days=near_days,
            )
            if not isinstance(q, dict):
                r["earnings_quality"] = None
                continue
            flags = q.get("flags") or []
            r["earnings_quality"] = {
                "grade": q.get("grade"),
                "quality_score": q.get("quality_score"),
                "flags": flags[:3],
                "error": q.get("error"),
            }
        except Exception as e:
            logger.debug("earnings_quality %s: %s", t, e)
            r["earnings_quality"] = None
