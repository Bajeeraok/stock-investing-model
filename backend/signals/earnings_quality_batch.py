"""
Batch earnings-quality hints onto signal rows (dashboard only; FMP calls).
"""
from __future__ import annotations

import logging
from typing import Any

from signals.earnings_quality import analyze_earnings_quality

logger = logging.getLogger(__name__)


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

    rows = [r for r in results if not r.get("error") and r.get("ticker")]
    rows.sort(key=lambda x: -(float(x.get("composite_buy") or 0)))
    for r in rows[:max_n]:
        t = r.get("ticker")
        if not t:
            continue
        try:
            q = analyze_earnings_quality(config, str(t))
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
